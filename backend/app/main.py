from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import shutil
import uuid
import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .storage import ROOT, DATA, MODEL, LOCK, study_dir, write_json, read_json
from .video.processing import inspect_video
from .pipeline import run
from .evidence.enrich import enrich_report

MAX_UPLOAD = 300 * 1024 * 1024
TASKS = {'unspecified', 'forward_raise', 'side_raise', 'overhead', 'elbow', 'reach', 'hand_to_mouth', 'opposite_shoulder', 'free'}
executor = ThreadPoolExecutor(max_workers=1)
active = {}
evidence_active = set()


class EvidenceRequest(BaseModel):
    online: bool = False
    topic: str | None = None


@asynccontextmanager
async def lifespan(app):
    DATA.mkdir(parents=True, exist_ok=True)
    for path in DATA.glob('*/study.json'):
        status = read_json(path)
        if status['status'] in ('queued', 'processing', 'uploading'):
            status.update(status='failed', error='Обработка прервана перезапуском сервера. Загрузите видео повторно.')
            write_json(path, status)
        report_path = path.parent / 'report.json'
        if status['status'] == 'completed' and report_path.exists():
            saved = read_json(report_path)
            if 'evidence' not in saved:
                upgraded = enrich_report(saved)
                write_json(path.parent / 'evidence.json',upgraded['evidence'])
                write_json(report_path,upgraded)
    yield
    executor.shutdown(wait=True)


app = FastAPI(title='Upper Limb Motion Lab', version='0.1.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=['http://127.0.0.1:5173', 'http://localhost:5173'],
                   allow_methods=['GET', 'POST', 'DELETE'], allow_headers=['Content-Type'])


@app.middleware('http')
async def local_request_guard(request, call_next):
    if request.method in ('POST', 'DELETE'):
        origin = request.headers.get('origin')
        allowed = {'http://127.0.0.1:8000', 'http://localhost:8000', 'http://127.0.0.1:5173', 'http://localhost:5173'}
        if origin and origin not in allowed:
            return JSONResponse({'detail': 'Внешний origin запрещён.'}, status_code=403)
    if request.method == 'POST' and request.url.path == '/api/studies':
        length = request.headers.get('content-length')
        if length is None:
            return JSONResponse({'detail': 'Content-Length обязателен.'}, status_code=411)
        try:
            oversized = int(length) > MAX_UPLOAD + 2 * 1024 * 1024
        except ValueError:
            return JSONResponse({'detail': 'Некорректный Content-Length.'}, status_code=400)
        if oversized:
            return JSONResponse({'detail': 'Максимальный размер файла — 300 МБ.'}, status_code=413)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def existing(study_id):
    try:
        directory = study_dir(study_id)
    except ValueError:
        raise HTTPException(404, 'Исследование не найдено.')
    if not (directory / 'study.json').exists():
        raise HTTPException(404, 'Исследование не найдено.')
    return directory


@app.get('/api/health')
def health():
    return {'status': 'ok', 'model_ready': MODEL.is_file(), 'external_video_transfer': False}


@app.post('/api/studies', status_code=202)
def upload(file: UploadFile = File(...), affected_side: str = Form('unknown'), task: str = Form('unspecified')):
    if affected_side not in ('left', 'right', 'unknown') or task not in TASKS:
        raise HTTPException(422, 'Недопустимая сторона или задание.')
    extension = Path(file.filename or '').suffix.lower()
    if extension not in ('.mp4', '.mov', '.webm'):
        raise HTTPException(415, 'Поддерживаются MP4, MOV и WebM.')
    if not MODEL.is_file():
        raise HTTPException(503, 'Модель не установлена. Выполните python scripts/download_model.py.')
    # Bounded single-user queue: reject overload before storing another medical video.
    with LOCK:
        if any(not future.done() for future in active.values()):
            raise HTTPException(409, 'Дождитесь завершения текущего анализа.')
        study_id = uuid.uuid4().hex
        directory = study_dir(study_id)
        directory.mkdir(parents=True)
        try:
            size = 0
            with (directory / ('original' + extension)).open('wb') as destination:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD:
                        raise HTTPException(413, 'Максимальный размер файла — 300 МБ.')
                    destination.write(chunk)
            quality = inspect_video(directory / ('original' + extension))
            status = {'study_id': study_id, 'created_at': datetime.now(timezone.utc).isoformat(),
                      'affected_side': affected_side, 'task': task, 'extension': extension,
                      'status': 'queued', 'progress': 0, 'video_quality': quality}
            write_json(directory / 'study.json', status)
            active.clear()
            active[study_id] = executor.submit(run, study_id)
            return status
        except Exception as exc:
            shutil.rmtree(directory)
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else 'Невозможно прочитать видео.')
        finally:
            file.file.close()


@app.get('/api/studies')
def studies():
    return sorted([read_json(path) for path in DATA.glob('*/study.json')], key=lambda s: s['created_at'], reverse=True)


@app.get('/api/studies/{study_id}')
def status(study_id: str):
    return read_json(existing(study_id) / 'study.json')


@app.get('/api/studies/{study_id}/report')
def report(study_id: str):
    directory = existing(study_id)
    if not (directory / 'report.json').exists():
        raise HTTPException(409, 'Отчёт ещё не готов.')
    return read_json(directory / 'report.json')


@app.get('/api/studies/{study_id}/files/{kind}')
def files(study_id: str, kind: str):
    directory = existing(study_id)
    names = {'landmarks': 'landmarks.json', 'metrics': 'metrics.json', 'report': 'report.json', 'evidence': 'evidence.json', 'preview': 'preview.mp4',
             'original': 'original' + read_json(directory / 'study.json')['extension']}
    if kind not in names or not (directory / names[kind]).exists():
        raise HTTPException(404, 'Файл не найден.')
    if kind == 'preview' and read_json(directory / 'study.json')['status'] != 'completed':
        raise HTTPException(409, 'Видео ещё обрабатывается.')
    return FileResponse(directory / names[kind], filename=names[kind], content_disposition_type='inline' if kind == 'preview' else 'attachment')


@app.post('/api/studies/{study_id}/evidence')
def update_evidence(study_id: str, request: EvidenceRequest):
    with LOCK:
        directory = existing(study_id)
        if not (directory / 'report.json').exists():
            raise HTTPException(409, 'Отчёт ещё не готов.')
        if study_id in evidence_active:
            raise HTTPException(409, 'Поиск литературы уже выполняется.')
        evidence_active.add(study_id)
        original = read_json(directory / 'report.json')
    try:
        enriched = enrich_report(original,online=request.online,topic=request.topic)
        with LOCK:
            write_json(directory / 'evidence.json',enriched['evidence'])
            write_json(directory / 'report.json',enriched)
        return enriched
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    finally:
        with LOCK:
            evidence_active.discard(study_id)


@app.delete('/api/studies/{study_id}', status_code=204)
def delete(study_id: str):
    with LOCK:
        directory = existing(study_id)
        if (study_id in active and not active[study_id].done()) or study_id in evidence_active:
            raise HTTPException(409, 'Дождитесь завершения обработки или поиска литературы перед удалением.')
        shutil.rmtree(directory)
        active.pop(study_id, None)


dist = ROOT / 'frontend' / 'dist'
if dist.is_dir():
    app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
