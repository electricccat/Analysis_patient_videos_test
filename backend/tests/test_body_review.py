import httpx
import pytest
from fastapi.testclient import TestClient
from backend.app.body_review import review, validate_regions
from backend.app.clinical_review import clinical_review, discover
from backend.app import storage, main


def frames():
    points = {name: {'x':x,'y':y,'confidence':.9} for name,x,y in [
        ('left_shoulder', .3,.2), ('left_elbow',.3,.5), ('left_wrist',.6,.5),
        ('right_shoulder',.7,.2), ('right_elbow',.7,.5), ('right_wrist',.7,.8)]}
    return [{'landmarks':points,'people':1,'timestamp':i/30} for i in range(10)]


def test_only_selected_regions_and_no_movement_metrics():
    result = review(frames(),1000,1000,['left_arm'])
    assert set(result['pose_quality']['landmarks']) == {'left_shoulder','left_elbow','left_wrist'}
    assert result['metrics'] == {} and result['series'] == [] and result['events'] == []
    assert len(result['body_details']) == 1
    assert result['body_details'][0]['value'] == pytest.approx(90)
    assert result['body_details'][0]['timestamp'] is not None
    assert 'Правая' not in str(result['observations'])


def test_missing_regions_and_ambiguous_person_do_not_invent_findings():
    result = review(frames(),1000,1000,['left_foot'])
    assert result['body_details'][0]['value'] is None
    ambiguous = frames()
    for frame in ambiguous:
        frame['people'] = 2
    assert review(ambiguous,1000,1000,['left_arm'])['body_details'][0]['value'] is None
    for bad in ([], ['invalid'], 'left_arm', [None]):
        with pytest.raises(ValueError):
            validate_regions(bad)


def test_independent_hypothesis_is_not_documented_diagnosis():
    report = review(frames(),1000,1000,['left_arm'])
    report['patient_profile'] = {'diagnosis':'Подтверждённый диагноз','diagnosis_confirmed':'yes'}
    result = clinical_review(report, {'text':''})
    assert result['documented_diagnosis'] == 'Подтверждённый диагноз'
    assert result['hypotheses'][0]['title'] != result['documented_diagnosis']
    assert len(result['hypotheses'][0]['alternatives']) >= 2
    result = clinical_review({}, {'text':'Диагноз: травма руки\nРекомендации: осмотр. Инсульт исключён.'})
    assert result['documented_diagnosis']=='травма руки'


def test_selected_pipeline_skips_movement_and_filters_saved_points(tmp_path,monkeypatch):
    from backend.app import pipeline
    from backend.app.video.processing import PreviewWriter, inspect_video
    import numpy as np
    monkeypatch.setattr(storage,'DATA',tmp_path)
    study_id='c'*32
    directory=tmp_path/study_id
    directory.mkdir()
    path=directory/'original.mp4'
    writer=PreviewWriter(path,320,240,30)
    for i in range(10):
        writer.write(np.zeros((240,320,3),dtype=np.uint8),i/30)
    writer.close()
    storage.write_json(directory/'study.json',{'status':'queued','study_id':study_id,'extension':'.mp4','selected_regions':['left_arm'],
        'affected_side':'left','task':'unspecified','video_quality':inspect_video(path)})
    class Provider:
        version='test'
        model_hash='test'
        def __init__(self,*args): pass
        def detect(self,rgb,timestamp): return {'landmarks':frames()[0]['landmarks'],'people':1}
        def close(self): pass
    monkeypatch.setattr(pipeline,'MediaPipeProvider',Provider)
    monkeypatch.setattr(pipeline,'analyze',lambda *args: pytest.fail('Movement analysis must not run'))
    pipeline.run(study_id)
    assert storage.read_json(directory/'study.json')['status']=='completed'
    saved=storage.read_json(directory/'report.json')
    assert saved['analysis_mode']=='posture' and saved['metrics']=={}
    points=storage.read_json(directory/'landmarks.json')['frames'][0]['landmarks']
    assert set(points)=={'left_shoulder','left_elbow','left_wrist'}


def test_web_search_uses_only_public_topic_and_labels_snippets(monkeypatch):
    monkeypatch.setattr('backend.app.clinical_review.curated_resources',lambda *args: [])
    monkeypatch.setattr('backend.app.resource_content.enrich_resources',lambda result,*args: result)
    queries = []
    def reply(request):
        queries.append(request.url.params['q'])
        link='https://www.youtube.com/watch?v=LvTfeTnL-90' if 'youtube' in request.url.params['q'] else 'https://www.nice.org.uk/guide'
        return httpx.Response(200, text=f'<rss><channel><item><title>Stroke rehabilitation guideline exercises patient recovery video photo story</title><link>{link}</link><description>Stroke rehabilitation</description></item><item><link>javascript:bad</link></item></channel></rss>')
    result = discover({'patient_profile':{'patient_code':'SECRET'},'discharge':{'text':'PRIVATE'}},'stroke', httpx.MockTransport(reply))
    assert len(result['groups']) == 5
    assert all('SECRET' not in q and 'PRIVATE' not in q for q in queries)
    assert all(len(g['sources'])==1 and g['sources'][0]['verification']=='search_snippet_only' for g in result['groups'])
    unavailable = discover({}, 'stroke', httpx.MockTransport(lambda request: httpx.Response(503)))
    assert len(unavailable['warnings'])==5
    assert all(not g['sources'] for g in unavailable['groups'])


def test_document_update_and_public_search_persist_without_movement(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path)
    study_id='a'*32
    directory=tmp_path/study_id
    directory.mkdir()
    storage.write_json(directory/'study.json',{'status':'completed','extension':'.mp4'})
    report={**review(frames(),1000,1000,['left_arm']),'study_id':study_id,'analysis_mode':'posture'}
    storage.write_json(directory/'report.json',report)
    monkeypatch.setattr(main,'discover',lambda r,t: {'topic':t,'groups':[]})
    client=TestClient(main.app)
    response=client.post(f'/api/studies/{study_id}/discharge',json={'text':'Инсульт','verified':True})
    assert response.status_code==200
    assert response.json()['discharge']['status']=='verified_by_user'
    assert len(response.json()['clinical_review']['hypotheses'])==2
    response=client.post(f'/api/studies/{study_id}/resources',json={'topic':'stroke'})
    assert response.status_code==200
    assert storage.read_json(directory/'report.json')['web_resources']['topic']=='stroke'
    main.evidence_active.add(study_id)
    try:
        assert client.post(f'/api/studies/{study_id}/discharge',json={'text':'x'}).status_code==409
    finally:
        main.evidence_active.discard(study_id)


def test_reanalyze_legacy_video_preserves_source_and_copies_history(tmp_path,monkeypatch):
    from concurrent.futures import Future
    from backend.app.video.processing import PreviewWriter
    import numpy as np
    monkeypatch.setattr(storage,'DATA',tmp_path)
    model=tmp_path/'model.task'
    model.write_bytes(b'test')
    monkeypatch.setattr(main,'MODEL',model)
    monkeypatch.setattr(main,'active',{})
    queued=[]
    class Queue:
        def submit(self,fn,study_id):
            queued.append(study_id)
            future=Future()
            future.set_result(None)
            return future
    monkeypatch.setattr(main,'executor',Queue())
    study_id='d'*32
    source=tmp_path/study_id
    source.mkdir()
    writer=PreviewWriter(source/'original.mp4',320,240,30)
    for i in range(5):
        writer.write(np.zeros((240,320,3),dtype=np.uint8),i/30)
    writer.close()
    state={'study_id':study_id,'status':'completed','extension':'.mp4','affected_side':'right','task':'elbow'}
    storage.write_json(source/'study.json',state)
    storage.write_json(source/'report.json',{'patient_profile':{'diagnosis':'test'}})
    storage.write_json(source/'discharge.json',{'text':'Выписка','status':'verified_by_user'})
    (source/'discharge.jpg').write_bytes(b'photo')
    original=(source/'original.mp4').read_bytes()
    client=TestClient(main.app)
    assert client.post(f'/api/studies/{study_id}/reanalyze',json={'selected_regions':[]}).status_code==422
    main.evidence_active.add(study_id)
    try:
        assert client.post(f'/api/studies/{study_id}/reanalyze',json={'selected_regions':['left_arm']}).status_code==409
    finally:
        main.evidence_active.discard(study_id)
    response=client.post(f'/api/studies/{study_id}/reanalyze',json={'selected_regions':['left_arm','right_foot']})
    assert response.status_code==202,response.text
    next_state=response.json()
    target=tmp_path/next_state['study_id']
    assert queued==[next_state['study_id']]
    assert next_state['source_study_id']==study_id
    assert next_state['analysis_mode']=='posture'
    assert next_state['selected_regions']==['left_arm','right_foot']
    assert storage.read_json(target/'patient.json')['diagnosis']=='test'
    assert storage.read_json(target/'discharge.json')['text']=='Выписка'
    assert (target/'discharge.jpg').read_bytes()==b'photo'
    assert (target/'original.mp4').read_bytes()==original
    assert storage.read_json(source/'study.json')==state
    (source/'original.mp4').unlink()
    assert client.post(f'/api/studies/{study_id}/reanalyze',json={'selected_regions':['left_arm']}).status_code==422
