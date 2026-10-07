from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import shutil
import uuid
import os
from ipaddress import IPv4Address, IPv4Network
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .storage import ROOT, DATA, MODEL, LOCK, study_dir, write_json, read_json
from .video.processing import inspect_video
from .pipeline import run
from .evidence.enrich import enrich_report
from .evidence.patient_search import with_patient_literature
from .patient import FIELDS, PatientProfile, validate_profile
from .body_review import validate_regions
from .medical_documents import save_photo
from .clinical_review import clinical_review, discover, filter_report_resources

MAX_UPLOAD = 300 * 1024 * 1024
TASKS = {'unspecified', 'forward_raise', 'side_raise', 'overhead', 'elbow', 'reach', 'hand_to_mouth', 'opposite_shoulder', 'free'}
executor = ThreadPoolExecutor(max_workers=1)
active = {}
evidence_active = set()
LAN_ADDRESS = os.environ.get('KINEMA_LAN_ADDRESS', '')
if LAN_ADDRESS and not any(IPv4Address(LAN_ADDRESS) in IPv4Network(cidr) for cidr in
                          ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
    raise ValueError('KINEMA_LAN_ADDRESS must be a private IPv4 address')


def browser_origins():
    origins = {'http://127.0.0.1:8000', 'http://localhost:8000',
               'http://127.0.0.1:5173', 'http://localhost:5173'}
    if LAN_ADDRESS:
        origins.add(f'http://{LAN_ADDRESS}:8000')
    return origins


class EvidenceRequest(BaseModel):
    online: bool = False
    topic: str | None = None
    patient_online: bool = False


class DischargeRequest(BaseModel):
    text: str
    verified: bool = False


class WebRequest(BaseModel):
    topic: str


class ReanalysisRequest(BaseModel):
    selected_regions: list[str]


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
            if 'evidence' not in saved and saved.get('analysis_mode') != 'posture':
                upgraded = enrich_report(saved)
                write_json(path.parent / 'evidence.json',upgraded['evidence'])
                write_json(report_path,upgraded)
    yield
    executor.shutdown(wait=True)


app = FastAPI(title='Upper Limb Motion Lab', version='0.1.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=sorted(browser_origins()),
                   allow_methods=['GET', 'POST', 'DELETE'], allow_headers=['Content-Type'])


@app.middleware('http')
async def local_request_guard(request, call_next):
    if request.method in ('POST', 'DELETE'):
        origin = request.headers.get('origin')
        allowed = browser_origins()
        if origin and origin not in allowed:
            return JSONResponse({'detail': 'Внешний origin запрещён.'}, status_code=403)
    if request.method == 'POST' and request.url.path == '/api/studies':
        length = request.headers.get('content-length')
        if length is None:
            return JSONResponse({'detail': 'Content-Length обязателен.'}, status_code=411)
        try:
            oversized = int(length) > MAX_UPLOAD + 14 * 1024 * 1024
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
    return {'status': 'ok', 'model_ready': MODEL.is_file(), 'external_video_transfer': False,
            'lan_address': LAN_ADDRESS or None}


@app.post('/api/studies', status_code=202)
def upload(file: UploadFile = File(...), affected_side: str = Form('unknown'), task: str = Form('unspecified'), patient_profile: str = Form('{}'),
           selected_regions: str | None = Form(None), discharge_photo: UploadFile | None = File(None), discharge_text: str = Form(''), search_topic: str = Form('')):
    if len(patient_profile) > 100000:
        raise HTTPException(422, 'Анкета слишком большая.')
    try:
        import json
        profile = validate_profile(json.loads(patient_profile))
        regions = validate_regions(json.loads(selected_regions)) if selected_regions is not None else None
        if len(discharge_text)>30000 or len(search_topic)>160 or any(ord(c)<32 for c in search_topic):
            raise ValueError('Invalid document or search topic')
    except ValueError:
        raise HTTPException(422, 'Проверьте поля анкеты: допустимые значения, числовые диапазоны и даты.')
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
            if discharge_photo:
                save_photo(discharge_photo, directory)
            if discharge_text or discharge_photo:
                write_json(directory/'discharge.json', {'text':discharge_text, 'status':'user_provided' if discharge_text else 'pending_ocr'})
            status = {'study_id': study_id, 'created_at': datetime.now(timezone.utc).isoformat(),
                      'affected_side': affected_side, 'task': task, 'extension': extension,
                      'status': 'queued', 'progress': 0, 'video_quality': quality}
            if regions:
                status.update(selected_regions=regions, analysis_mode='posture', search_topic=search_topic.strip())
            write_json(directory / 'study.json', status)
            write_json(directory / 'patient.json', profile)
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
            if discharge_photo:
                discharge_photo.file.close()


@app.get('/api/studies')
def studies():
    return sorted([read_json(path) for path in DATA.glob('*/study.json')], key=lambda s: s['created_at'], reverse=True)


@app.post('/api/studies/{study_id}/reanalyze', status_code=202)
def reanalyze(study_id: str, request: ReanalysisRequest):
    try:
        regions = validate_regions(request.selected_regions)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    with LOCK:
        source = existing(study_id)
        state = read_json(source/'study.json')
        if state['status'] not in ('completed', 'failed') or study_id in evidence_active or any(not f.done() for f in active.values()):
            raise HTTPException(409, 'Дождитесь завершения анализа или поиска.')
        extension = state.get('extension')
        if extension not in ('.mp4', '.mov', '.webm') or not (source/('original'+extension)).is_file():
            raise HTTPException(422, 'Исходное видео не сохранилось. Загрузите его как новое исследование.')
        if not MODEL.is_file():
            raise HTTPException(503, 'Модель не установлена. Выполните python scripts/download_model.py.')
        new_id = uuid.uuid4().hex
        directory = study_dir(new_id)
        directory.mkdir()
        try:
            shutil.copy2(source/('original'+extension), directory/('original'+extension))
            for name in ('patient.json', 'discharge.json', 'discharge.jpg'):
                if (source/name).is_file():
                    shutil.copy2(source/name, directory/name)
            # Older reports may contain history that was never saved separately.
            previous = read_json(source/'report.json') if (source/'report.json').exists() else {}
            if not (directory/'patient.json').exists():
                write_json(directory/'patient.json', previous.get('patient_profile', {}))
            if not (directory/'discharge.json').exists() and previous.get('discharge'):
                write_json(directory/'discharge.json', previous['discharge'])
            next_state = {'study_id':new_id, 'created_at':datetime.now(timezone.utc).isoformat(),
                          'affected_side':state.get('affected_side','unknown'), 'task':'unspecified',
                          'extension':extension, 'video_quality':inspect_video(directory/('original'+extension)),
                          'status':'queued', 'progress':0, 'selected_regions':regions, 'analysis_mode':'posture',
                          'source_study_id':study_id, 'search_topic':state.get('search_topic','')}
            if state.get('is_demo'):
                next_state['is_demo'] = True
            write_json(directory/'study.json', next_state)
            active.clear()
            active[new_id] = executor.submit(run, new_id)
            return next_state
        except Exception as exc:
            shutil.rmtree(directory)
            raise HTTPException(422, str(exc) if isinstance(exc,ValueError) else 'Не удалось подготовить повторный анализ.')


@app.get('/api/patient-form')
def patient_form():
    return {'fields': FIELDS, 'defaults': PatientProfile().model_dump(mode='json')}


@app.get('/api/studies/{study_id}/patient')
def patient(study_id: str):
    directory = existing(study_id)
    return read_json(directory / 'patient.json') if (directory / 'patient.json').exists() else PatientProfile().model_dump(mode='json')


@app.post('/api/studies/{study_id}/patient')
def update_patient(study_id: str, request: PatientProfile):
    try:
        profile = validate_profile(request.model_dump(mode='json'))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    with LOCK:
        directory = existing(study_id)
        state = read_json(directory / 'study.json')
        if state['status'] not in ('completed', 'failed') or study_id in evidence_active or (study_id in active and not active[study_id].done()):
            raise HTTPException(409, 'Дождитесь завершения анализа или обновления отчёта.')
        report_path = directory / 'report.json'
        updated = None
        if state['status'] == 'completed' and report_path.exists():
            original = read_json(report_path)
            original['patient_profile'] = profile
            original.setdefault('provenance', {})['patient_profile_updated_at'] = datetime.now(timezone.utc).isoformat()
            evidence_active.add(study_id)
        else:
            write_json(directory / 'patient.json', profile)
            return {'patient_profile': profile, 'report': None}
    # Network traffic must not hold the shared storage lock.
    try:
        if original.get('analysis_mode') == 'posture':
            updated = original
            updated['clinical_review'] = clinical_review(updated, updated.get('discharge', {}))
        else:
            updated = with_patient_literature(enrich_report(original))
        with LOCK:
            write_json(directory / 'patient.json', profile)
            write_json(directory / 'evidence.json', updated['evidence'])
            write_json(report_path, updated)
        return {'patient_profile': profile, 'report': updated}
    finally:
        with LOCK:
            evidence_active.discard(study_id)


@app.get('/api/studies/{study_id}')
def status(study_id: str):
    return read_json(existing(study_id) / 'study.json')


@app.get('/api/studies/{study_id}/report')
def report(study_id: str):
    directory = existing(study_id)
    if not (directory / 'report.json').exists():
        raise HTTPException(409, 'Отчёт ещё не готов.')
    return filter_report_resources(read_json(directory / 'report.json'))


@app.get('/api/studies/{study_id}/files/{kind}')
def files(study_id: str, kind: str):
    directory = existing(study_id)
    names = {'discharge_photo':'discharge.jpg', 'discharge':'discharge.json', 'patient': 'patient.json', 'landmarks': 'landmarks.json', 'metrics': 'metrics.json', 'report': 'report.json', 'evidence': 'evidence.json', 'preview': 'preview.mp4',
             'original': 'original' + read_json(directory / 'study.json')['extension']}
    if kind not in names or not (directory / names[kind]).exists():
        raise HTTPException(404, 'Файл не найден.')
    if kind == 'preview' and read_json(directory / 'study.json')['status'] != 'completed':
        raise HTTPException(409, 'Видео ещё обрабатывается.')
    if kind == 'report':
        return JSONResponse(filter_report_resources(read_json(directory/'report.json')), headers={'Content-Disposition':'attachment; filename="report.json"'})
    return FileResponse(directory / names[kind], filename=names[kind], content_disposition_type='inline' if kind in ('preview','discharge_photo') else 'attachment')


@app.post('/api/studies/{study_id}/discharge')
def update_discharge(study_id: str, request: DischargeRequest):
    if len(request.text)>30000:
        raise HTTPException(422, 'Текст выписки слишком большой.')
    with LOCK:
        directory = existing(study_id)
        if read_json(directory/'study.json')['status'] != 'completed' or study_id in evidence_active or (study_id in active and not active[study_id].done()):
            raise HTTPException(409, 'Дождитесь завершения обработки.')
        saved = read_json(directory/'report.json')
        discharge = {'text':request.text, 'status':'verified_by_user' if request.verified else 'needs_verification', 'photo_attached':(directory/'discharge.jpg').exists()}
        saved['discharge'] = discharge
        saved['clinical_review'] = clinical_review(saved, discharge)
        # The previous public search may no longer match the edited medical context.
        saved.pop('web_resources', None)
        write_json(directory/'discharge.json', discharge)
        write_json(directory/'report.json', saved)
        return saved


@app.post('/api/studies/{study_id}/resources')
def search_resources(study_id: str, request: WebRequest):
    with LOCK:
        directory = existing(study_id)
        if read_json(directory/'study.json')['status'] != 'completed' or study_id in evidence_active or (study_id in active and not active[study_id].done()):
            raise HTTPException(409, 'Дождитесь завершения обработки или поиска.')
        saved = read_json(directory/'report.json')
        evidence_active.add(study_id)
    try:
        saved['web_resources'] = discover(saved, request.topic)
        with LOCK:
            write_json(directory/'report.json', saved)
        return saved
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        with LOCK:
            evidence_active.discard(study_id)


@app.post('/api/studies/{study_id}/evidence')
def update_evidence(study_id: str, request: EvidenceRequest):
    with LOCK:
        directory = existing(study_id)
        if not (directory / 'report.json').exists():
            raise HTTPException(409, 'Отчёт ещё не готов.')
        if read_json(directory / 'study.json')['status'] != 'completed':
            raise HTTPException(409, 'Дождитесь завершения анализа.')
        if study_id in evidence_active:
            raise HTTPException(409, 'Поиск литературы уже выполняется.')
        original = read_json(directory / 'report.json')
        if original.get('analysis_mode') == 'posture':
            raise HTTPException(422, 'Для оценки положения используйте поиск материалов по диагнозу.')
        evidence_active.add(study_id)
    try:
        enriched = enrich_report(original,online=request.online,topic=request.topic)
        if request.patient_online:
            enriched = with_patient_literature(enriched)
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
