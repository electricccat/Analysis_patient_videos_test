"""Selected-region posture observations; no temporal movement analysis."""
import math
from statistics import median

REGIONS = {
    'head': ('Голова', ['nose', 'left_ear', 'right_ear']),
    'trunk': ('Корпус', ['left_shoulder', 'right_shoulder', 'left_hip', 'right_hip']),
}
for side, label in [('left', 'Левая'), ('right', 'Правая')]:
    REGIONS[f'{side}_arm'] = (f'{label} рука', [f'{side}_{p}' for p in ('shoulder', 'elbow', 'wrist')])
    REGIONS[f'{side}_hand'] = (f'{label} кисть', [f'{side}_{p}' for p in ('wrist', 'index', 'pinky', 'thumb')])
    REGIONS[f'{side}_leg'] = (f'{label} нога', [f'{side}_{p}' for p in ('hip', 'knee', 'ankle')])
    REGIONS[f'{side}_foot'] = (f'{label} стопа', [f'{side}_{p}' for p in ('ankle', 'heel', 'foot_index')])


def validate_regions(value):
    if not isinstance(value, list) or not value or len(value) > len(REGIONS) or any(not isinstance(x, str) or x not in REGIONS for x in value):
        raise ValueError('Выберите хотя бы одну допустимую часть тела.')
    return list(dict.fromkeys(value))


def selected_landmarks(regions):
    return set(p for region in regions for p in REGIONS[region][1])


def angle(a, b, c):
    u, v = (a[0]-b[0], a[1]-b[1]), (c[0]-b[0], c[1]-b[1])
    norm = math.hypot(*u)*math.hypot(*v)
    return math.degrees(math.acos(max(-1, min(1, (u[0]*v[0]+u[1]*v[1])/norm)))) if norm > 1e-9 else None


def review(frames, width, height, regions):
    observations, quality, details = [], {}, []
    n = max(1, len(frames))
    for name in selected_landmarks(regions):
        points = [f['landmarks'][name] for f in frames if f['people']==1 and name in f['landmarks'] and f['landmarks'][name]['confidence'] >= .65 and all(0 <= f['landmarks'][name][k] <= 1 for k in ('x', 'y'))]
        quality[name] = {'coverage': len(points)/n, 'mean_confidence': sum(p['confidence'] for p in points)/max(1, len(points))}
    for region in regions:
        label, keys = REGIONS[region]
        samples = []
        for frame in frames:
            points = frame['landmarks']
            if frame['people'] != 1 or any(k not in points or points[k]['confidence'] < .65 or not all(0 <= points[k][v] <= 1 for v in ('x', 'y')) for k in keys):
                continue
            xy = [(points[k]['x']*width, points[k]['y']*height) for k in keys]
            value = None
            if region.endswith('_arm') or region.endswith('_leg'):
                value = angle(*xy)
            elif region.endswith('_foot'):
                # Foot axis is heel-to-toe, relative to image horizontal, NOT a clinical ankle angle.
                dx, dy = xy[2][0]-xy[1][0], xy[2][1]-xy[1][1]
                if math.hypot(dx, dy) > 1e-9:
                    value = math.degrees(math.atan2(abs(dy), abs(dx)))
            elif region.endswith('_hand'):
                value = angle(xy[1], xy[0], xy[2])
            elif region == 'trunk':
                a = ((xy[0][0]+xy[1][0])/2, (xy[0][1]+xy[1][1])/2)
                b = ((xy[2][0]+xy[3][0])/2, (xy[2][1]+xy[3][1])/2)
                if math.dist(a,b) > 1e-9:
                    value = math.degrees(math.atan2(abs(a[0]-b[0]), abs(a[1]-b[1])))
            elif region == 'head':
                dx, dy = xy[2][0]-xy[1][0], xy[2][1]-xy[1][1]
                if math.hypot(dx, dy) > 1e-9:
                    value = math.degrees(math.atan2(abs(dy), abs(dx)))
            if value is not None:
                samples.append((value, frame['timestamp']))
        coverage = len(samples)/n
        if coverage < .5 or len(samples) < 3:
            details.append({'region': region, 'label': label, 'status': 'insufficient_data', 'coverage': coverage, 'value': None,
                            'statement': 'Недостаточно видимых ориентиров. Нужен другой ракурс или более чёткое видео.', 'timestamp': None})
            continue
        value = median(x[0] for x in samples)
        timestamp = min(samples, key=lambda x: abs(x[0]-value))[1]
        if region.endswith('_arm'):
            statement = f'Медианный внутренний угол локтя {value:.1f}°; сгибание относительно прямой руки ≈ {180-value:.1f}°. Положение не доказывает спастичность.'
        elif region.endswith('_leg'):
            statement = f'Медианный внутренний угол колена {value:.1f}°; сгибание ≈ {180-value:.1f}°. Причина положения по видео не установлена.'
        elif region.endswith('_foot'):
            statement = f'Ось пятка–носок: {value:.1f}° к горизонтали кадра. Проверьте опору на пятку, заворот стопы и обувь на указанном кадре; нагрузка и правильность постановки автоматически не определяются.'
        elif region.endswith('_hand'):
            statement = f'Угол ориентиров указательного пальца–запястья–мизинца {value:.1f}°. Это грубая геометрия кисти, а не оценка сгибания пальцев или тонуса.'
        elif region == 'head':
            statement = f'Наклон линии ушей к горизонтали кадра {value:.1f}°. Учитывайте наклон камеры и ракурс.'
        else:
            statement = f'Ось плечи–таз отклонена от вертикали кадра на {value:.1f}°. Учитывайте наклон камеры и ракурс.'
        item = {'region': region, 'label': label, 'status': 'observed', 'coverage': coverage, 'value': round(value, 2), 'statement': statement, 'timestamp': timestamp}
        details.append(item)
        observations.append({'level': 'measurement', 'statement': f'{label}: {statement}', 'technical_reliability': 'medium'})
    coverage = sum(x['coverage'] for x in quality.values())/max(1,len(quality))
    return {'body_details': details, 'observations': observations, 'metrics': {}, 'asymmetry': {}, 'series': [], 'events': [], 'normalization': {},
            'pose_quality': {'level': 'medium' if coverage >= .7 else 'low', 'threshold': .65, 'landmarks': quality,
                             'no_person_frames': sum(f['people']==0 for f in frames), 'ambiguous_person_frames': sum(f['people']>1 for f in frames)}}
