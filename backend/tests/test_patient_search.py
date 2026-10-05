import httpx
import pytest
from backend.app.evidence.patient_search import patient_literature
from backend.app.evidence.pubmed import PubMedSearch
from backend.app.evidence.enrich import enrich_report
from backend.tests.test_analysis import synthetic
from backend.app.movement_analysis.analyze import analyze
from backend.tests.test_evidence import article


@pytest.fixture
def patient_report():
    return enrich_report({**analyze(synthetic(), 1000, 1000), 'patient_profile': {
        'patient_code': 'secret-code', 'age': 58, 'condition': 'stroke',
        'diagnosis_confirmed': 'yes', 'diagnosis': 'secret diagnosis',
        'history': 'secret history', 'medications': 'secret medication',
        'onset_date': '2025-01-01', 'spasticity': 'yes',
    }})


def transport(calls, *, fail_topic=None):
    def handler(request):
        calls.append(request)
        if fail_topic and fail_topic in str(request.url):
            raise httpx.ConnectError('offline', request=request)
        if request.url.path.endswith('esearch.fcgi'):
            return httpx.Response(200, json={'esearchresult': {'idlist': ['12345']}})
        return httpx.Response(200, text='<PubmedArticleSet>' + article() + '</PubmedArticleSet>')
    return httpx.MockTransport(handler)


def test_patient_search_is_explained_private_and_not_promoted_to_diagnosis(patient_report):
    calls = []
    result = patient_literature(patient_report, search=PubMedSearch(transport(calls)))
    assert result['status'] == 'completed'
    assert len(calls) == 6
    assert len(result['sources']) == 1  # Deduplicated across topics.
    assert result['sources'][0]['verification_scope'] == 'bibliographic_metadata'
    assert result['groups'][0]['topic'] == 'assessment'
    assert result['groups'][2]['topic'] == 'spasticity'
    assert all(group['reason'] for group in result['groups'])
    urls = ' '.join(str(call.url) for call in calls)
    assert all(secret not in urls for secret in ('secret', '2025-01-01', '58'))
    assert 'adult' in urls and 'chronic' in urls
    assert result['requires_clinician_review'] is True
    assert 'patient_literature' not in patient_report


def test_unsupported_condition_never_substitutes_stroke(patient_report):
    patient_report['patient_profile']['condition'] = 'other_neurological'
    calls = []
    result = patient_literature(patient_report, search=PubMedSearch(transport(calls)))
    assert result['status'] == 'needs_history'
    assert calls == []
    assert result['sources'] == []


def test_children_and_brain_injury_get_own_population_not_stroke_catalog(patient_report):
    patient_report['patient_profile'].update(condition='brain_injury', age=12)
    calls = []
    result = patient_literature(patient_report, search=PubMedSearch(transport(calls)))
    queries = ' '.join(group['query'] for group in result['groups'])
    assert 'traumatic brain injury' in queries
    assert 'stroke[' not in queries
    assert 'child[' in queries
    assert result['reviewed_sources'] == []


def test_partial_failure_keeps_successful_groups_and_measured_report(patient_report):
    before = patient_report['metrics'].copy()
    calls = []
    result = patient_literature(patient_report, search=PubMedSearch(transport(calls, fail_topic='spasticity')))
    assert result['status'] == 'partial'
    assert len(result['sources']) == 1
    assert result['groups'][2]['status'] == 'unavailable'
    assert result['warnings']
    assert patient_report['metrics'] == before


def test_unknown_measurements_not_inferred_and_cache_is_population_specific(monkeypatch):
    from backend.app.evidence import pubmed
    calls = []
    client_class = httpx.Client
    def client(**kwargs):
        kwargs['transport'] = transport(calls)
        return client_class(**kwargs)
    monkeypatch.setattr(pubmed.httpx, 'Client', client)
    monkeypatch.setattr(pubmed, 'cache', {})
    search = PubMedSearch()
    search.search('assessment', condition='stroke', age_group='adult')
    other = search.search('assessment', condition='brain_injury', age_group='child')
    assert other['from_cache'] is False and len(calls) == 4
    result = patient_literature({'patient_profile': {'condition': 'stroke'}}, search=PubMedSearch(transport(calls)))
    assert result['feature_links'] == []
    assert any('Нет надёжных' in warning for warning in result['warnings'])
    assert result['reviewed_sources'] == []


@pytest.mark.parametrize('filters', [{'condition': 'private diagnosis'}, {'age_group': '58'}, {'stage': '2025-01-01'}])
def test_arbitrary_patient_filter_rejected(filters):
    with pytest.raises(ValueError):
        PubMedSearch().search('assessment', **filters)
