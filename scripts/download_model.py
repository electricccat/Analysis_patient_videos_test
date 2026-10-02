"""Only downloads public model weights. Never reads/uploads patient video."""
from pathlib import Path
import hashlib
import urllib.request
import zipfile

URL = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task'
path = Path(__file__).resolve().parents[1] / 'models' / 'pose_landmarker_lite.task'
path.parent.mkdir(exist_ok=True)
temporary = path.with_suffix('.download')
try:
    urllib.request.urlretrieve(URL, temporary)
    if not zipfile.is_zipfile(temporary):
        raise RuntimeError('Invalid model bundle')
    temporary.replace(path)
    print(f'Model ready: {path.name}; SHA256: {hashlib.sha256(path.read_bytes()).hexdigest()}')
finally:
    temporary.unlink(missing_ok=True)
