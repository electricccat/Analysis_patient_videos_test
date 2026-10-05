import time
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient
from backend.app import main, storage
from backend.app.video.processing import PreviewWriter, extract


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DATA',tmp_path/'studies')
    monkeypatch.setattr(main,'DATA',tmp_path/'studies')
    (tmp_path/'studies').mkdir()
    # Don't stop the shared executor between tests; lifespan recovery is tested separately.
    with TestClient(main.app) as client:
        yield client


def test_bad_file_and_traversal(client):
    assert client.post('/api/studies',files={'file':('test.txt',b'abc')}).status_code==415
    assert client.post('/api/studies',files={'file':('test.mp4',b'not video')}).status_code==422
    assert client.get('/api/studies/invalid').status_code==404
    assert client.post('/api/studies',files={'file':('test.mp4',b'abc')},data={'affected_side':'bad'}).status_code==422


def test_external_origin_and_upload_limit(client):
    assert client.delete('/api/studies/'+'a'*32,headers={'Origin':'https://example.com'}).status_code==403
    assert client.post('/api/studies',content=b'x',headers={'Content-Length':str(main.MAX_UPLOAD*2)}).status_code==413


def test_phone_origin_requires_explicit_lan_address(client, monkeypatch):
    study_path = '/api/studies/' + 'a' * 32
    phone_origin = 'http://192.168.1.231:8000'
    monkeypatch.setattr(main, 'LAN_ADDRESS', '')
    assert client.delete(study_path, headers={'Origin': phone_origin}).status_code == 403
    monkeypatch.setattr(main, 'LAN_ADDRESS', '192.168.1.231')
    assert client.get('/api/health').json()['lan_address'] == '192.168.1.231'
    # Allowed origin reaches the route; the nonexistent study remains protected.
    assert client.delete(study_path, headers={'Origin': phone_origin}).status_code == 404
    assert client.delete(study_path, headers={'Origin': 'http://192.168.1.232:8000'}).status_code == 403
    assert client.delete(study_path, headers={'Origin': phone_origin + '.evil.test'}).status_code == 403


def test_evidence_upgrade_saved_legacy_report_and_delete(client,tmp_path):
    from backend.tests.test_analysis import synthetic
    from backend.app.movement_analysis.analyze import analyze
    study_id='b'*32
    directory=storage.DATA/study_id
    directory.mkdir()
    storage.write_json(directory/'study.json',{'study_id':study_id,'created_at':'2026-10-02','extension':'.mp4','status':'completed'})
    from backend.app.report.build import clean
    storage.write_json(directory/'report.json',clean({**analyze(synthetic(),1000,1000),'study_id':study_id}))
    response=client.post(f'/api/studies/{study_id}/evidence',json={'online':False})
    assert response.status_code==200,response.text
    assert response.json()['schema_version']=='1.1'
    assert response.json()['safety_screen']['requires_clinician_review']
    assert client.get(f'/api/studies/{study_id}/files/evidence').status_code==200
    assert client.get(f'/api/studies/{study_id}/report').json()['clinical_context']
    assert client.post(f'/api/studies/{study_id}/evidence',json={'online':True,'topic':'evil'}).status_code==422
    main.evidence_active.add(study_id)
    try:
        assert client.delete(f'/api/studies/{study_id}').status_code==409
    finally:
        main.evidence_active.discard(study_id)
    assert client.delete(f'/api/studies/{study_id}').status_code==204
    assert not directory.exists()


def test_variable_frame_rate_pts_survive_browser_transcode(tmp_path):
    path=tmp_path/'vfr.mp4'
    timestamps=[0,.03,.09,.17,.25,.31,.49]
    writer=PreviewWriter(path,320,240,30)
    try:
        for timestamp in timestamps:
            writer.write(np.zeros((240,320,3),np.uint8),timestamp)
    finally:
        writer.close()
    assert [t for _,t,_ in extract(path)]==pytest.approx(timestamps,abs=1e-5)


@pytest.mark.parametrize('rotation', [0,90])
def test_real_model_blank_video_pipeline_and_deletion(client,tmp_path,monkeypatch,rotation):
    from concurrent.futures import ThreadPoolExecutor
    executor=ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(main,'executor',executor)
    monkeypatch.setattr(main,'active',{})
    path=tmp_path/'blank.mp4'
    writer=PreviewWriter(path,320,240,30)
    writer.stream.set_display_rotation(rotation)
    try:
        for i in range(15): writer.write(np.zeros((240,320,3),np.uint8),i/30)
    finally:
        writer.close()
    assert len(list(extract(path)))==15
    with path.open('rb') as video:
        response=client.post('/api/studies',files={'file':('blank.mp4',video,'video/mp4')},data={'patient_profile':'{"age":60,"condition":"stroke","goals":"Одеваться"}'})
    assert response.status_code==202, response.text
    study_id=response.json()['study_id']
    for _ in range(200):
        status=client.get(f'/api/studies/{study_id}').json()
        if status['status'] in ('completed','failed'): break
        time.sleep(.1)
    assert status['status']=='completed',status
    report=client.get(f'/api/studies/{study_id}/report').json()
    assert (report['video_quality']['width'],report['video_quality']['height']) == ((240,320) if rotation else (320,240))
    assert report['video_quality']['rotation_ccw'] == rotation
    assert report['patient_literature']['status'] == 'unavailable'
    assert report['patient_literature']['feature_links'] == []
    assert report['pose_quality']['no_person_frames']==15
    assert report['metrics']['left_arm']['elbow_rom']['value'] is None
    assert report['observations']==[]
    assert report['patient_profile']['age']==60
    assert report['personalized']['goals']=='Одеваться'
    assert report['personalized']['options']==[]
    assert report['provenance']['model_sha256']
    preview=client.get(f'/api/studies/{study_id}/files/preview')
    assert preview.status_code==200
    assert preview.headers['cache-control']=='no-store'
    assert client.get(f'/api/studies/{study_id}/files/original').status_code==200
    assert client.delete(f'/api/studies/{study_id}').status_code==204
    assert not (storage.DATA/study_id).exists()
    assert client.get(f'/api/studies/{study_id}/report').status_code==404
    executor.shutdown()
