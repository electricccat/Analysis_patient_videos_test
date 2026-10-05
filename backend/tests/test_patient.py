from copy import deepcopy
from datetime import date, timedelta
import pytest
from backend.app.patient import validate_profile, personalized_section
from backend.app.evidence.enrich import enrich_report
from backend.app.evidence.service import ReviewedCatalogService
from backend.app.movement_analysis.analyze import analyze
from backend.tests.test_analysis import synthetic
from backend.tests.test_api import client
from backend.app import storage, main


def patient_report(**profile):
    return enrich_report({**analyze(synthetic(), 1000, 1000), 'affected_side': 'right', 'task': 'reach',
                          'patient_profile': {'age': 60, 'condition': 'stroke', 'diagnosis_confirmed': 'yes',
                                              'goals': 'Самостоятельно есть', **profile}},
                         catalog=ReviewedCatalogService(as_of=date(2026, 10, 2)))


@pytest.mark.parametrize('profile', [{'age': -1}, {'age': True}, {'pain_movement': 11},
    {'pain_rest': float('nan')}, {'condition': 'invented'}, {'unexpected': 'value'},
    {'onset_date': (date.today() + timedelta(days=1)).isoformat()}])
def test_invalid_profile_rejected(profile):
    with pytest.raises(ValueError): validate_profile(profile)


def test_unknown_history_never_becomes_clearance_or_diagnosis():
    r = patient_report(condition='unknown', diagnosis='инсульт по словам пациента', medical_restrictions='Разрешены все нагрузки')
    assert r['personalized']['options'] == []
    assert 'Врач оценил возможность реабилитационной нагрузки' in r['personalized']['missing_information']
    assert validate_profile({})['pain_rest'] is None
    assert validate_profile({})['medical_clearance'] == 'unknown'


def test_patient_context_uses_side_goals_and_keeps_measurements():
    r = patient_report()
    before = deepcopy(r['metrics'])
    section = r['personalized']
    assert section['options']
    assert section['goals'] == 'Самостоятельно есть'
    assert all(not m['metric'].startswith('left_arm.') for m in section['measurements'])
    assert all(o['requires_clinician_review'] for o in section['options'])
    assert all(o['evidence'] for o in section['options'])
    assert enrich_report(r)['metrics'] == before


@pytest.mark.parametrize('profile', [{'age': 12}, {'condition': 'orthopedic'}, {'diagnosis_confirmed': 'unknown'}])
def test_stroke_catalog_not_applied_to_other_populations(profile):
    assert patient_report(**profile)['personalized']['options'] == []


def test_new_symptoms_suspend_method_selection():
    r = patient_report(new_neurological_symptoms='yes')
    assert r['personalized']['status'] == 'urgent_assessment'
    assert r['personalized']['options'] == []
    assert r['metrics']['right_arm']['shoulder_max']['value'] is not None


def test_cimt_requires_clinician_measured_hand_criteria():
    r = patient_report(assessment_source='clinician', assessment_date='2026-10-01', wrist_extension=10, finger_extension=5)
    cimt = next(o for o in r['personalized']['options'] if o['id'] == 'cimt')
    assert cimt['status'] == 'criteria_not_met'
    r = patient_report(assessment_source='patient', wrist_extension=30, finger_extension=20)
    cimt = next(o for o in r['personalized']['options'] if o['id'] == 'cimt')
    assert cimt['status'] == 'requires_assessment'
    assert any('измеренные специалистом' in x for x in cimt['checks'])


def test_pain_and_devices_are_not_ignored():
    r = patient_report(pain_movement=3, implanted_device='yes', vision_attention='yes')
    assert any('Сообщена боль' in x for x in r['personalized']['priorities'])
    electric = next(o for o in r['personalized']['options'] if o['id'] == 'electrical')
    assert any('имплантированные' in x for x in electric['checks'])


def test_unmeasured_affected_arm_does_not_use_other_arm_for_methods():
    r = patient_report()
    for metric in r['metrics']['right_arm'].values():
        metric['value'] = None
    updated = enrich_report(r)
    assert all(o['id'] == 'trunk_control' for o in updated['personalized']['options'])


def test_history_and_medication_never_leave_in_online_search():
    import httpx
    from backend.app.evidence.pubmed import PubMedSearch
    r = patient_report(history='PRIVATE_HISTORY_TEST', medications='PRIVATE_MEDICATION_TEST')
    calls = []
    def handler(request):
        calls.append(request)
        assert 'PRIVATE_HISTORY_TEST' not in str(request.url)
        assert 'PRIVATE_MEDICATION_TEST' not in str(request.url)
        assert 'Самостоятельно' not in str(request.url)
        return httpx.Response(200, json={'esearchresult': {'idlist': []}})
    enrich_report(r, online=True, topic='upper_limb', search=PubMedSearch(httpx.MockTransport(handler)))
    assert len(calls) == 1


def test_patient_api_persistence_legacy_report_update_and_busy_guard(client):
    study_id = 'c' * 32
    directory = storage.DATA / study_id
    directory.mkdir()
    storage.write_json(directory / 'study.json', {'study_id': study_id, 'created_at': '2026-10-02', 'extension': '.mp4', 'status': 'completed'})
    assert client.get(f'/api/studies/{study_id}/patient').json()['age'] is None
    assert len(client.get('/api/patient-form').json()['fields']) >= 40
    from backend.app.report.build import clean
    original = clean({**analyze(synthetic(), 1000, 1000), 'study_id': study_id, 'affected_side': 'right'})
    storage.write_json(directory / 'report.json', original)
    profile = {'age': 60, 'condition': 'stroke', 'diagnosis_confirmed': 'yes', 'goals': 'Одеваться'}
    response = client.post(f'/api/studies/{study_id}/patient', json=profile)
    assert response.status_code == 200, response.text
    assert response.json()['report']['metrics'] == original['metrics']
    assert response.json()['report']['personalized']['goals'] == 'Одеваться'
    assert response.json()['report']['patient_literature']['status'] == 'unavailable'
    assert response.json()['report']['patient_literature']['groups'][0]['topic'] == 'assessment'
    assert client.get(f'/api/studies/{study_id}/files/patient').json()['goals'] == 'Одеваться'
    assert client.get(f'/api/studies/{study_id}/report').json()['patient_profile']['age'] == 60
    assert client.post(f'/api/studies/{study_id}/patient', json={'pain_rest': 99}).status_code == 422
    main.evidence_active.add(study_id)
    try:
        assert client.post(f'/api/studies/{study_id}/patient', json=profile).status_code == 409
    finally:
        main.evidence_active.discard(study_id)
    assert client.delete(f'/api/studies/{study_id}').status_code == 204
    assert not directory.exists()


def test_invalid_upload_history_rejected_before_storing_video(client):
    response = client.post('/api/studies', files={'file': ('test.mp4', b'invalid')}, data={'patient_profile': '{"age": -1}'})
    assert response.status_code == 422
    assert list(storage.DATA.iterdir()) == []


def test_patient_literature_api_refresh_and_offline_evidence_preserve_block(client, monkeypatch):
    from backend.app.evidence import patient_search
    from backend.app.evidence.pubmed import PubMedSearch
    from backend.tests.test_patient_search import transport
    calls = []
    monkeypatch.setattr(patient_search, 'PubMedSearch', lambda **kwargs: PubMedSearch(transport(calls), **kwargs))
    study_id = 'b' * 32
    directory = storage.study_dir(study_id)
    directory.mkdir()
    storage.write_json(directory / 'study.json', {'study_id': study_id, 'status': 'completed'})
    original = patient_report()
    original['study_id'] = study_id
    storage.write_json(directory / 'report.json', original)
    response = client.post(f'/api/studies/{study_id}/evidence', json={'patient_online': True})
    assert response.status_code == 200, response.text
    block = response.json()['patient_literature']
    assert block['status'] == 'completed'
    assert len(calls) == 6
    assert response.json()['metrics'] == original['metrics']
    saved = client.get(f'/api/studies/{study_id}/report').json()
    assert saved['patient_literature'] == block
    refreshed = client.post(f'/api/studies/{study_id}/evidence', json={'online': False})
    assert refreshed.json()['patient_literature'] == block
    assert len(calls) == 6
    assert study_id not in main.evidence_active
