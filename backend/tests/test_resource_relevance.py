import httpx
from fastapi.testclient import TestClient
from backend.app import main, storage
from backend.app.clinical_review import relevant_source, filter_resources, discover


def source(title, summary='', url='https://example.org/page'):
    return {'title':title,'summary':summary,'url':url,'domain':'example.org','verification':'search_snippet_only'}


def test_reject_screenshot_results_wrong_diagnosis_and_generic_encyclopedia():
    unrelated = [source('Изменение режима электропитания для компьютера с Windows'),
                 source('PvP визуалы — моды на Майнкрафт'),source('Дневник.ру'), source('Microsoft Community'),
                 source('Stroke', 'Stroke rehabilitation helps patients with recovery', 'https://en.wikipedia.org/wiki/Stroke')]
    for item in unrelated:
        for category in ('guidelines','exercise','cases','video','photo'):
            assert not relevant_source(item,'реабилитация после инсульта',category)
    assert not relevant_source(source('Fracture rehabilitation exercises'),'инсульт','exercise')
    assert not relevant_source(source('Stroke rehabilitation guideline'),'инсульт','guidelines')
    assert not relevant_source(source('Stroke rehabilitation guideline',url='https://nice.org.uk.evil.test/guide'),'инсульт','guidelines')
    assert not relevant_source(source('Windows power options',url='https://example.org/?q=stroke+rehabilitation+exercises'),'инсульт','exercise')


def test_accept_relevant_bilingual_categories_and_safe_domains():
    assert relevant_source(source('Stroke rehabilitation exercise video'),'реабилитация после инсульта','video')
    assert relevant_source(source('ЛФК после инсульта: упражнения'),'stroke','exercise')
    assert relevant_source(source('Stroke rehabilitation guideline',url='https://www.nice.org.uk/guidance/ng236'),'инсульт','guidelines')
    assert relevant_source(source('Stroke survivor rehabilitation story'),'инсульт','cases')
    assert not relevant_source(source('Stroke rehabilitation exercises'),'инсульт','photo')
    assert not relevant_source(source('Stroke rehabilitation exercises',url='javascript:alert(1)'),'инсульт','exercise')


def test_saved_resources_are_filtered_and_empty_is_explicit():
    resources={'topic':'инсульт','groups':[{'id':'exercise','status':'completed','sources':[source('Windows 11 power settings')]}]}
    filtered=filter_resources(resources)
    assert filtered['groups'][0]['sources']==[]
    assert filtered['groups'][0]['status']=='no_relevant_results'
    assert filtered['groups'][0]['rejected_count']==1
    assert resources['groups'][0]['sources']
    assert filter_resources(filtered)==filtered


def test_curated_links_work_without_search_and_match_only_the_condition(monkeypatch):
    monkeypatch.setattr('backend.app.resource_content.public_url',lambda url:None)
    transport=httpx.MockTransport(lambda request:httpx.Response(503))
    result=discover({},'реабилитация после инсульта',transport)
    assert all(g['sources'] for g in result['groups'])
    assert all(s['verification']=='curated_resource' for g in result['groups'] for s in g['sources'])
    other=discover({},'реабилитация после перелома',transport)
    assert all(not g['sources'] for g in other['groups'])


def test_old_report_and_download_no_longer_expose_irrelevant_links(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    study_id='f'*32
    directory=tmp_path/study_id
    directory.mkdir()
    storage.write_json(directory/'study.json',{'status':'completed','extension':'.mp4'})
    storage.write_json(directory/'report.json',{'web_resources':{'topic':'инсульт','groups':[{'id':'video','status':'completed','sources':[source('Дневник.ру')]}]}})
    client=TestClient(main.app)
    for suffix in ('report','files/report'):
        response=client.get(f'/api/studies/{study_id}/{suffix}')
        assert response.status_code==200
        assert response.json()['web_resources']['groups'][0]['sources']==[]
