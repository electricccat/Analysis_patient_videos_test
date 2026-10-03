"""Create a clearly labelled fictional study; never overwrite a saved study.

Run from the project root: .venv/Scripts/python.exe -m scripts.create_demo
The schematic video and canonical landmarks are generated, not inferred.
"""
import hashlib
import math
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from backend.app.storage import ROOT, DATA, write_json, read_json, study_dir
from backend.app.patient import validate_profile
from backend.app.movement_analysis.analyze import analyze
from backend.app.report.build import build_report
from backend.app.video.processing import PreviewWriter, inspect_video

DEMO_ID = uuid.uuid5(uuid.NAMESPACE_URL, 'kinema:fictional-upper-limb-demo:v1').hex
WIDTH, HEIGHT, FPS, SECONDS = 1280, 720, 30, 6


def demo_frames():
    frames = []
    for i in range(FPS * SECONDS + 1):
        t = i / FPS
        phase = math.sin(math.pi * t / SECONDS) ** 2
        shift = 7 * phase
        coords = {'nose': (640 + shift, 140), 'left_shoulder': (750 + shift, 260),
                  'right_shoulder': (530 + shift, 260), 'left_hip': (730, 530), 'right_hip': (550, 530)}
        for side, sign, amplitude in [('left', 1, 90), ('right', -1, 55)]:
            shoulder = np.array(coords[f'{side}_shoulder'], float)
            theta = math.radians(8 + amplitude * phase)
            elbow = shoulder + 105 * np.array([sign * math.sin(theta), math.cos(theta)])
            bend = math.radians((8 if side == 'left' else 25) + (5 if side == 'left' else 20) * phase)
            wrist = elbow + 100 * np.array([sign * math.sin(theta + bend), math.cos(theta + bend)])
            coords[f'{side}_elbow'], coords[f'{side}_wrist'] = elbow, wrist
        frames.append({'frame_index': i, 'timestamp': t, 'people': 1, 'landmarks': {
            name: {'x': float(p[0]) / WIDTH, 'y': float(p[1]) / HEIGHT, 'z': 0,
                   'visibility': 1, 'presence': 1, 'confidence': 1, 'timestamp': t}
            for name, p in coords.items()}})
    return frames


def render_frame(frame):
    image = Image.new('RGB', (WIDTH, HEIGHT), '#f5f7f3')
    draw = ImageDraw.Draw(image)
    font_path = Path('C:/Windows/Fonts/segoeui.ttf')
    font = ImageFont.truetype(str(font_path), 25) if font_path.exists() else ImageFont.load_default(size=25)
    small = ImageFont.truetype(str(font_path), 19) if font_path.exists() else ImageFont.load_default(size=19)
    draw.text((32, 20), 'ДЕМО · ВЫМЫШЛЕННЫЙ ПАЦИЕНТ · СИНТЕТИЧЕСКОЕ ДВИЖЕНИЕ', fill='#173c34', font=font)
    draw.text((32, 58), 'Это схема, а не запись человека. Координаты заданы программно.', fill='#526e44', font=small)
    points = {name: (p['x'] * WIDTH, p['y'] * HEIGHT) for name, p in frame['landmarks'].items()}
    edges = [('left_shoulder', 'right_shoulder'), ('left_hip', 'right_hip'),
             ('left_shoulder', 'left_hip'), ('right_shoulder', 'right_hip')]
    for side in ('left', 'right'):
        edges.extend([(f'{side}_shoulder', f'{side}_elbow'), (f'{side}_elbow', f'{side}_wrist')])
    for a, b in edges:
        color = '#299e80' if a.startswith('left') else '#db9654'
        draw.line([points[a], points[b]], fill=color, width=11)
    for name, (x, y) in points.items():
        color = '#299e80' if name.startswith('left') else '#db9654'
        draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill=color)
    x, y = points['nose']
    draw.ellipse((x - 36, y - 36, x + 36, y + 36), outline='#526e44', width=4)
    draw.text((45, 600), 'Оранжевая: правая рука (поражённая сторона в учебной истории)', fill='#a16631', font=small)
    draw.text((45, 632), 'Зелёная: левая рука · Стороны анатомические', fill='#237f67', font=small)
    draw.text((45, 670), f'Время: {frame["timestamp"]:.2f} с · Числа демонстрационные, без клинической интерпретации', fill='#526e44', font=small)
    return np.array(image)


def create_demo():
    directory = study_dir(DEMO_ID)
    if directory.exists():
        saved = directory / 'study.json'
        if saved.exists() and read_json(saved).get('is_demo'):
            print(f'Demo already exists: {DEMO_ID}. Saved edits were preserved.')
            return DEMO_ID
        raise RuntimeError('Target directory exists; refusing to overwrite it.')
    profile = validate_profile(read_json(ROOT / 'examples' / 'demo_patient.json'))
    DATA.mkdir(parents=True, exist_ok=True)
    directory.mkdir()
    frames = demo_frames()
    writer = PreviewWriter(directory / 'preview.mp4', WIDTH, HEIGHT, FPS)
    try:
        for frame in frames:
            writer.write(render_frame(frame), frame['timestamp'])
    finally:
        writer.close()
    shutil.copyfile(directory / 'preview.mp4', directory / 'original.mp4')
    quality = {**inspect_video(directory / 'preview.mp4'), 'decoded_frames': len(frames), 'decoded_duration_seconds': SECONDS}
    now = datetime.now(timezone.utc).isoformat()
    provenance = {'algorithm_version': '0.1.0', 'data_origin': 'synthetic_demo', 'inference_performed': False,
                  'created_at': now, 'video_sha256': hashlib.sha256((directory / 'original.mp4').read_bytes()).hexdigest(),
                  'generator': 'scripts.create_demo:v1', 'note': 'Fictional history; generated coordinates, no clinical video or model inference.'}
    report = build_report(analyze(frames, WIDTH, HEIGHT), {'study_id': DEMO_ID, 'affected_side': 'right', 'task': 'side_raise',
                          'patient_profile': profile, 'video_quality': quality, 'provenance': provenance, 'is_demo': True})
    report['limitations'].insert(0, 'Демонстрационный пример: история вымышлена, видео — схема, все измерения получены из заданных координат. Они не описывают реального пациента и не подтверждают точность распознавания.')
    write_json(directory / 'patient.json', profile)
    write_json(directory / 'landmarks.json', {'schema_version': '1.0', 'data_origin': 'synthetic_demo', 'frames': frames})
    write_json(directory / 'metrics.json', {k: report[k] for k in ('metrics', 'asymmetry', 'normalization', 'series')})
    write_json(directory / 'evidence.json', report['evidence'])
    write_json(directory / 'report.json', report)
    write_json(directory / 'study.json', {'study_id': DEMO_ID, 'created_at': now, 'affected_side': 'right', 'task': 'side_raise',
               'extension': '.mp4', 'status': 'completed', 'progress': 1, 'processed_frames': len(frames), 'video_quality': quality,
               'is_demo': True, 'title': 'Демо · пациент после инсульта'})
    print(f'Demo ready: {DEMO_ID}')
    return DEMO_ID


if __name__ == '__main__':
    create_demo()
