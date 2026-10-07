import os
import shutil
import subprocess
from pathlib import Path
import cv2
import numpy as np
from .storage import ROOT

MAX_PHOTO = 12 * 1024 * 1024


def save_photo(upload, directory):
    extension = Path(upload.filename or '').suffix.lower()
    if extension not in ('.jpg', '.jpeg', '.png', '.webp'):
        raise ValueError('Р¤РѕС‚Рѕ РІС‹РїРёСЃРєРё: JPG, PNG РёР»Рё WebP.')
    content = upload.file.read(MAX_PHOTO+1)
    if not content or len(content)>MAX_PHOTO:
        raise ValueError('Р¤РѕС‚Рѕ РІС‹РїРёСЃРєРё РґРѕР»Р¶РЅРѕ Р±С‹С‚СЊ РЅРµ Р±РѕР»СЊС€Рµ 12 РњР‘.')
    pixels = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if pixels is None or max(pixels.shape[:2])>8000 or pixels.shape[0]*pixels.shape[1]>25_000_000:
        raise ValueError('Р¤РѕС‚Рѕ РЅРµ С‡РёС‚Р°РµС‚СЃСЏ РёР»Рё РїСЂРµРІС‹С€Р°РµС‚ 25 РјРµРіР°РїРёРєСЃРµР»РµР№ / 8000 РїРёРєСЃРµР»РµР№ РїРѕ СЃС‚РѕСЂРѕРЅРµ.')
    # Normalize the decoded image, discarding EXIF and untrusted original metadata.
    path = directory / 'discharge.jpg'
    if not cv2.imwrite(str(path), pixels):
        raise ValueError('РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕС…СЂР°РЅРёС‚СЊ С„РѕС‚Рѕ РІС‹РїРёСЃРєРё.')
    return path


def read_photo(path):
    try:
        if os.name == 'nt':
            powershell = Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
            command = [str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT/'scripts'/'read_discharge.ps1'), '-ImagePath', str(path.resolve())]
        elif shutil.which('tesseract'):
            command = ['tesseract', str(path), 'stdout', '-l', 'rus+eng']
        else:
            return {'status':'manual_required', 'text':'', 'warning':'Р›РѕРєР°Р»СЊРЅС‹Р№ OCR РЅРµРґРѕСЃС‚СѓРїРµРЅ. Р’РІРµРґРёС‚Рµ С‚РµРєСЃС‚ РІС‹РїРёСЃРєРё РІСЂСѓС‡РЅСѓСЋ.'}
        result = subprocess.run(command, capture_output=True, timeout=40, encoding='utf-8', errors='replace', **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
        if result.returncode != 0 or not result.stdout.strip():
            raise ValueError('OCR unavailable')
        return {'status':'needs_verification', 'text':result.stdout.strip()[:30000], 'warning':'РџСЂРѕРІРµСЂСЊС‚Рµ СЂР°СЃРїРѕР·РЅР°РЅРЅС‹Р№ С‚РµРєСЃС‚ РїРѕ С„РѕС‚Рѕ, РѕСЃРѕР±РµРЅРЅРѕ РґРёР°РіРЅРѕР·, РѕС‚СЂРёС†Р°РЅРёСЏ, РґРѕР·РёСЂРѕРІРєРё Рё СЃС‚РѕСЂРѕРЅС‹ С‚РµР»Р°.'}
    except (OSError, subprocess.SubprocessError, ValueError):
        return {'status':'manual_required', 'text':'', 'warning':'OCR РЅРµ РїСЂРѕС‡РёС‚Р°Р» С„РѕС‚Рѕ. Р’РІРµРґРёС‚Рµ С‚РµРєСЃС‚ РІС‹РїРёСЃРєРё РІСЂСѓС‡РЅСѓСЋ; С„РѕС‚Рѕ СЃРѕС…СЂР°РЅРµРЅРѕ.'}
