import json
import os
import re
from pathlib import Path
from threading import RLock

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get('STUDY_DATA_DIR', ROOT / 'data')).resolve()
MODEL = Path(os.environ.get('POSE_MODEL_PATH', ROOT / 'models' / 'pose_landmarker_lite.task')).resolve()
LOCK = RLock()


def study_dir(study_id):
    if not re.fullmatch(r'[a-f0-9]{32}', study_id):
        raise ValueError('Invalid study ID')
    return DATA / study_id


def write_json(path, payload):
    with LOCK:
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        temp.replace(path)


def read_json(path):
    with LOCK:
        return json.loads(path.read_text(encoding='utf-8'))
