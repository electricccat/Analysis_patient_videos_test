"""Optional local HTTP smoke check with public MediaPipe sample, never a patient.

Download https://storage.googleapis.com/mediapipe-assets/pose.jpg separately into
.validation/public_pose.jpg. Run after starting the server. Test study is deleted.
"""
from pathlib import Path
import time
import cv2
import httpx
from backend.app.video.processing import PreviewWriter


def main(online=False):
    root = Path(__file__).resolve().parents[1]
    fixture = root / '.validation' / 'public_pose.jpg'
    image = cv2.imread(str(fixture))
    if image is None:
        raise SystemExit('Download the public sample into .validation/public_pose.jpg first.')
    height, width = image.shape[:2]
    path = fixture.with_suffix('.mp4')
    writer = PreviewWriter(path, width, height, 30)
    try:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        for i in range(30):
            writer.write(rgb, i / 30)
    finally:
        writer.close()
    study_id = None
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=30) as client:
        try:
            assert client.get('/').status_code == 200
            assert client.get('/api/health').json()['model_ready']
            with path.open('rb') as video:
                response = client.post('/api/studies', files={'file': ('public_sample.mp4', video, 'video/mp4')})
            response.raise_for_status()
            study_id = response.json()['study_id']
            for _ in range(300):
                status = client.get(f'/api/studies/{study_id}').json()
                if status['status'] in ('completed', 'failed'):
                    break
                time.sleep(.1)
            assert status['status'] == 'completed', status
            report = client.get(f'/api/studies/{study_id}/report').json()
            print('Pose quality:', report['pose_quality'])
            assert report['metrics']['left_arm']['elbow_max']['value'] is not None
            assert report['metrics']['right_arm']['elbow_max']['value'] is not None
            assert report['observations']
            assert report['clinical_context']
            assert report['rehabilitation_options']
            assert report['safety_screen']['requires_clinician_review']
            assert client.get(f'/api/studies/{study_id}/files/evidence').status_code == 200
            response = client.post(f'/api/studies/{study_id}/evidence',json={'online':online,'topic':'upper_limb' if online else None})
            response.raise_for_status()
            updated = response.json()
            assert updated['metrics']==report['metrics']
            assert all(option['requires_clinician_review'] and option['evidence'] for option in updated['rehabilitation_options'])
            if online:
                assert updated['evidence']['online_search']['status']=='completed',updated['evidence']['warnings']
                assert updated['evidence']['search_results']
                print('Live PubMed HTTP search passed:',len(updated['evidence']['search_results']),'bibliographic records.')
            preview = client.get(f'/api/studies/{study_id}/files/preview', headers={'Range': 'bytes=0-99'})
            assert preview.status_code == 206
            print('HTTP smoke passed: frontend, real person inference, measured report, MP4 range playback.')
            print({side: report['metrics'][f'{side}_arm']['elbow_max']['value'] for side in ('left', 'right')})
        finally:
            if study_id:
                response = client.delete(f'/api/studies/{study_id}')
                response.raise_for_status()
                assert client.get(f'/api/studies/{study_id}').status_code == 404
                print('Temporary public-sample study completely deleted.')
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--online',action='store_true',help='Also test real PubMed search using generic terms only')
    main(online=parser.parse_args().online)
