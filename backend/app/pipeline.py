import hashlib
import time
from datetime import datetime, timezone
from .storage import study_dir, MODEL, write_json, read_json
from .video.processing import extract, PreviewWriter
from .pose.provider import MediaPipeProvider
from .movement_analysis.analyze import analyze, CONFIDENCE, MIN_COVERAGE
from .report.build import build_report
from .evidence.patient_search import with_patient_literature


def run(study_id):
    directory = study_dir(study_id)
    status_path = directory / 'study.json'
    status = read_json(status_path)
    provider = writer = None
    try:
        status.update(status='processing', progress=0)
        write_json(status_path, status)
        provider = MediaPipeProvider(MODEL)
        video = directory / ('original' + status['extension'])
        quality = status['video_quality']
        writer = PreviewWriter(directory / 'preview.mp4', quality['width'], quality['height'], quality['nominal_fps'])
        frames, last_ms, updated = [], -1, time.monotonic()
        for index, timestamp, rgb in extract(video):
            # Tasks API needs strictly increasing integer ms even for unusually high FPS.
            timestamp_ms = max(round(timestamp * 1000), last_ms + 1)
            result = provider.detect(rgb, timestamp_ms)
            last_ms = timestamp_ms
            for landmark in result['landmarks'].values():
                landmark['timestamp'] = timestamp
            frames.append({'frame_index': index, 'timestamp': timestamp, **result})
            writer.write(rgb, timestamp)
            if time.monotonic() - updated > .5:
                status['processed_frames'] = index + 1
                duration = quality['duration_seconds']
                status['progress'] = min(.95, timestamp / duration) if duration else None
                write_json(status_path, status)
                updated = time.monotonic()
        writer.close()
        writer = None
        provider.close()
        provider_version, model_hash = provider.version, provider.model_hash
        provider = None
        write_json(directory / 'landmarks.json', {'schema_version': '1.0', 'coordinate_system': 'image normalized; z is model relative depth, not clinical 3D', 'frames': frames})
        analysis = analyze(frames, quality['width'], quality['height'])
        metadata = {'study_id': study_id, 'affected_side': status['affected_side'], 'task': status['task'],
                    'patient_profile': read_json(directory / 'patient.json') if (directory / 'patient.json').exists() else {},
                    'video_quality': {**quality, 'decoded_frames': len(frames), 'decoded_duration_seconds': frames[-1]['timestamp']},
                    'provenance': {'algorithm_version': '0.1.0', 'model': 'MediaPipe Pose Landmarker Lite',
                                   'model_sha256': model_hash, 'mediapipe_version': provider_version,
                                   'video_sha256': hashlib.sha256(video.read_bytes()).hexdigest(),
                                   'created_at': datetime.now(timezone.utc).isoformat(),
                                   'parameters': {'landmark_confidence': CONFIDENCE, 'min_coverage': MIN_COVERAGE,
                                                  'smoothing_window_seconds': .15, 'max_derivative_gap_seconds': .25}}}
        report = build_report(analysis, metadata)
        status.update(progress=.97, stage='patient_literature')
        write_json(status_path, status)
        report = with_patient_literature(report)
        write_json(directory / 'metrics.json', {key: report[key] for key in ('metrics', 'asymmetry', 'normalization', 'series')})
        write_json(directory / 'report.json', report)
        write_json(directory / 'evidence.json', report['evidence'])
        status.update(status='completed', progress=1, processed_frames=len(frames))
    except Exception as exc:
        # No paths, video data or tracebacks in client error messages.
        status.update(status='failed', progress=None,
                      error=str(exc) if isinstance(exc, ValueError) else 'Ошибка обработки видео. Проверьте модель, кодек и зависимости.')
    finally:
        if writer:
            try:
                writer.close()
            except Exception:
                pass
        if provider:
            provider.close()
        write_json(status_path, status)
