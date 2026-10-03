from backend.app.storage import read_json, ROOT
from backend.app.patient import FIELDS, validate_profile
from backend.app.movement_analysis.analyze import analyze
from backend.app.report.build import build_report
from scripts.create_demo import demo_frames, WIDTH, HEIGHT, create_demo, DEMO_ID
import pytest


def test_demo_profile_and_synthetic_motion_are_explicit_and_usable():
    profile = validate_profile(read_json(ROOT / 'examples' / 'demo_patient.json'))
    assert set(profile) == {f['key'] for f in FIELDS}
    assert profile['condition'] == 'stroke' and profile['age'] >= 18
    assert 'вымышлен' in profile['patient_code']
    assert 'не запись человека' in profile['video_context']
    frames = demo_frames()
    report = build_report(analyze(frames, WIDTH, HEIGHT), {'patient_profile': profile, 'affected_side': 'right'})
    assert report['personalized']['options']
    assert not report['personalized']['missing_information']
    assert report['metrics']['left_arm']['shoulder_max']['value'] > report['metrics']['right_arm']['shoulder_max']['value']
    assert report['personalized']['priorities']


def test_existing_demo_edits_preserved_and_other_studies_not_overwritten(tmp_path, monkeypatch):
    from backend.app import storage
    from scripts import create_demo as module
    monkeypatch.setattr(storage, 'DATA', tmp_path)
    monkeypatch.setattr(module, 'DATA', tmp_path)
    directory = tmp_path / DEMO_ID
    directory.mkdir()
    storage.write_json(directory / 'study.json', {'is_demo': True})
    storage.write_json(directory / 'patient.json', {'goals': 'Edited during presentation'})
    assert create_demo() == DEMO_ID
    assert read_json(directory / 'patient.json')['goals'] == 'Edited during presentation'
    storage.write_json(directory / 'study.json', {'is_demo': False})
    with pytest.raises(RuntimeError): create_demo()
    assert read_json(directory / 'study.json')['is_demo'] is False
