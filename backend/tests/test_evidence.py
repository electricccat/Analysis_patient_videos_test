from copy import deepcopy
from datetime import date
import json
import httpx
import pytest
from backend.app.evidence.service import ReviewedCatalogService, EvidenceRecord, CATALOG, feature_topics
from backend.app.evidence.pubmed import PubMedSearch, parse_articles
from backend.app.evidence.enrich import enrich_report
from backend.app.recommendations.service import grounded_sections
from backend.tests.test_analysis import synthetic
from backend.app.movement_analysis.analyze import analyze

AS_OF = date(2026,10,2)


@pytest.fixture
def report():
    return {**analyze(synthetic(),1000,1000),'study_id':'private-patient-id','affected_side':'right','task':'private-task'}


def test_catalog_prioritizes_guidelines_and_preserves_measurements(report):
    enriched = enrich_report(report,catalog=ReviewedCatalogService(as_of=AS_OF))
    assert enriched['metrics'] == report['metrics']
    assert enriched['evidence']['sources'][0]['publication_type']=='clinical_practice_guideline'
    assert enriched['clinical_context']
    assert {o['category'] for o in enriched['rehabilitation_options']} == {'therapeutic_exercise','physiotherapy','occupational_therapy'}
    for item in enriched['clinical_context']+enriched['rehabilitation_options']:
        assert item['evidence']
        assert item['requires_clinician_review']
        assert item['feature_links']
        assert all(e['verified'] and e['verification_scope']=='reviewed_content' for e in item['evidence'])
    assert enriched['safety_screen']['requires_clinician_review']
    assert len(enriched['safety_screen']['video_cannot_assess'])==11
    assert enriched['evidence_disagreements']
    assert report.get('evidence') is None  # No input mutation.


def test_low_confidence_does_not_trigger_clinical_templates(report):
    for group in report['metrics'].values():
        for metric in group.values():
            metric['technical_reliability']='low'
    enriched=enrich_report(report,catalog=ReviewedCatalogService(as_of=AS_OF))
    assert enriched['clinical_context']==[]
    assert enriched['rehabilitation_options']==[]
    assert enriched['evidence']['sources']==[]


def test_stale_sources_cannot_ground_new_options(report):
    enriched=enrich_report(report,catalog=ReviewedCatalogService(as_of=date(2027,10,2)))
    assert enriched['clinical_context']==[]
    assert enriched['rehabilitation_options']==[]
    assert enriched['evidence']['warnings']


def test_metadata_only_and_unverified_sources_never_ground_rules(report):
    bundle=ReviewedCatalogService(as_of=AS_OF).retrieve(report)
    for source in bundle['sources']: source['verification_scope']='bibliographic_metadata'
    assert grounded_sections(bundle)==([],[],[])
    bundle=ReviewedCatalogService(as_of=AS_OF).retrieve(report)
    for source in bundle['sources']: source['verified']=False
    assert grounded_sections(bundle)==([],[],[])


@pytest.mark.parametrize('url',['https://www.cochrane.org.evil.test/test','http://www.nice.org.uk/','https://evil.test/','https://user@www.nice.org.uk/','https://www.nice.org.uk:8443/test'])
def test_only_authoritative_source_hosts_allowed(url):
    source=json.loads(CATALOG.read_text(encoding='utf-8'))['sources'][0]
    with pytest.raises(ValueError): EvidenceRecord.model_validate({**source,'url':url})


def test_invalid_catalog_preserves_measurements(report,tmp_path):
    path=tmp_path/'broken.json'
    path.write_text('not json')
    enriched=enrich_report(report,catalog=ReviewedCatalogService(path,AS_OF))
    assert enriched['metrics']==report['metrics']
    assert enriched['evidence']['warnings']
    assert enriched['rehabilitation_options']==[]


def article(pmid='12345',pub_type='Systematic Review',year='2025'):
    return f'''<PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article>
    <ArticleTitle>Stroke rehabilitation review</ArticleTitle><Journal><JournalIssue><PubDate><Year>{year}</Year></PubDate></JournalIssue></Journal>
    <AuthorList><Author><LastName>Example</LastName><Initials>AB</Initials></Author></AuthorList>
    <PublicationTypeList><PublicationType>{pub_type}</PublicationType></PublicationTypeList>
    </Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="doi">10.1234/example</ArticleId></ArticleIdList></PubmedData></PubmedArticle>'''


def test_pubmed_verifies_identifiers_and_skips_retractions_missing_bibliography():
    xml='<PubmedArticleSet>'+article()+article('99999')+article('54321','Retracted Publication')+article('11111',year='')+'</PubmedArticleSet>'
    records=parse_articles(xml,{'12345','54321','11111'},'upper_limb','2026-10-02')
    assert [r.id for r in records]==['pubmed_12345']
    assert records[0].verification_scope=='bibliographic_metadata'
    assert records[0].doi=='10.1234/example'
    with pytest.raises(ValueError): parse_articles('<!ENTITY test "a">',set(),'upper_limb','2026-10-02')


def test_online_search_sends_only_generic_terms_not_patient_information(report):
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.url.host=='eutils.ncbi.nlm.nih.gov'
        assert 'private-patient' not in str(request.url) and 'private-task' not in str(request.url)
        assert 'right' not in str(request.url) and '89.0' not in str(request.url)
        if request.url.path.endswith('esearch.fcgi'):
            return httpx.Response(200,json={'esearchresult':{'idlist':['12345']}})
        return httpx.Response(200,text='<PubmedArticleSet>'+article()+'</PubmedArticleSet>')
    search=PubMedSearch(transport=httpx.MockTransport(handler))
    enriched=enrich_report(report,online=True,topic='upper_limb',catalog=ReviewedCatalogService(as_of=AS_OF),search=search)
    assert len(calls)==2
    assert enriched['evidence']['online_search']['status']=='completed'
    assert enriched['evidence']['search_results'][0]['id']=='pubmed_12345'
    assert not any(e['id']=='pubmed_12345' for c in enriched['clinical_context'] for e in c['evidence'])


def test_network_failure_preserves_report_and_shows_warning(report):
    def handler(request): raise httpx.ConnectError('offline',request=request)
    enriched=enrich_report(report,online=True,topic='upper_limb',catalog=ReviewedCatalogService(as_of=AS_OF),search=PubMedSearch(httpx.MockTransport(handler)))
    assert enriched['metrics']==report['metrics']
    assert enriched['evidence']['online_search']['status']=='unavailable'
    assert enriched['evidence']['search_results']==[]
    assert enriched['evidence']['sources']


def test_arbitrary_topic_and_ssrf_rejected(report):
    with pytest.raises(ValueError): PubMedSearch().search('https://evil.test/')
    with pytest.raises(ValueError): enrich_report(report,online=True,topic='arbitrary',catalog=ReviewedCatalogService(as_of=AS_OF))


def test_cimt_does_not_infer_eligibility_from_pose(report):
    enriched=enrich_report(report,catalog=ReviewedCatalogService(as_of=AS_OF))
    option=next(o for o in enriched['rehabilitation_options'] if o['id']=='cimt')
    assert option['applicability']=='not_assessed'
    assert 'кисти' in option['clinician_checks']
    assert not {'frequency','dose','intensity','medication','contraindications'}.intersection(option)
