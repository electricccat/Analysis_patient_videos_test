import numpy as np
from ..biomechanics.math import angle, normalize, smooth, velocity, rom, asymmetry, segments
from ..pose.provider import LANDMARKS

CONFIDENCE = 0.6
MIN_COVERAGE = 0.6


def metric(values, operation, unit):
    values = np.asarray(values, float)
    valid = values[np.isfinite(values)]
    coverage = len(valid) / max(len(values), 1)
    reliable = coverage >= MIN_COVERAGE and len(valid) >= 5
    result = float(operation(valid)) if reliable else None
    reliable = reliable and result is not None and np.isfinite(result)
    return {'value': result if reliable else None, 'unit': unit,
            'coverage': round(coverage, 4), 'valid_frames': len(valid),
            'technical_reliability': ('high' if coverage >= .9 else 'medium') if reliable else 'low',
            'status': 'measured' if reliable else 'Данный показатель не удалось надёжно определить по этому видео.'}


def analyze(frames, width, height):
    times = np.array([f['timestamp'] for f in frames], float)
    if len(times) < 5:
        raise ValueError('Для анализа требуется минимум 5 кадров.')
    points, quality = {}, {}
    for name in LANDMARKS:
        coordinates, confidences = [], []
        for frame in frames:
            p = frame['landmarks'].get(name)
            good = p and p['confidence'] >= CONFIDENCE and 0 <= p['x'] <= 1 and 0 <= p['y'] <= 1
            coordinates.append([p['x'] * width, p['y'] * height] if good else [np.nan, np.nan])
            confidences.append(p['confidence'] if p else 0)
        raw = np.asarray(coordinates, float)
        quality[name] = {'coverage': float(np.isfinite(raw[:, 0]).mean()),
                         'mean_confidence': float(np.mean(confidences))}
        points[name] = smooth(raw, times)

    ls, rs, lh, rh = [points[k] for k in ['left_shoulder', 'right_shoulder', 'left_hip', 'right_hip']]
    widths = np.linalg.norm(ls - rs, axis=1)
    widths[widths < 5] = np.nan
    scale = float(np.nanmedian(widths)) if np.isfinite(widths).mean() >= MIN_COVERAGE else float('nan')
    shoulder_center, hip_center = (ls + rs) / 2, (lh + rh) / 2
    torso = shoulder_center - hip_center
    tilt = np.degrees(np.arctan2(torso[:, 0], -torso[:, 1]))
    tilt[np.linalg.norm(torso, axis=1) < 5] = np.nan
    baseline_mask = times <= times[0] + .5

    def baseline(values):
        initial = values[baseline_mask]
        finite = initial[np.isfinite(initial)]
        return float(np.median(finite)) if len(finite) >= 3 else float('nan')

    tilt_delta = tilt - baseline(tilt)
    shoulder_line = np.degrees(np.arctan2(ls[:, 1] - rs[:, 1], ls[:, 0] - rs[:, 0]))
    # Angle modulo 180 avoids discontinuity at horizontal shoulder line.
    shoulder_line = (shoulder_line + 90) % 180 - 90
    head = normalize(points['nose'], shoulder_center, scale)
    series = {'timestamp': times, 'trunk_tilt': tilt_delta, 'shoulder_line_tilt': shoulder_line,
              'head_x': head[:, 0], 'head_y': head[:, 1]}
    metrics, events = {}, []
    for side in ('left', 'right'):
        s, e, w, h = [points[f'{side}_{joint}'] for joint in ('shoulder', 'elbow', 'wrist', 'hip')]
        elbow = np.array([angle(a, b, c) for a, b, c in zip(s, e, w)])
        shoulder = np.array([angle(a, b, c) for a, b, c in zip(h, s, e)])
        wrist = normalize(w, shoulder_center, scale)
        speed = np.linalg.norm(velocity(wrist, times), axis=1)
        angular_speed = np.abs(velocity(shoulder, times))
        elbow_speed = np.abs(velocity(elbow, times))
        elevation = normalize(s, hip_center, scale)[:, 1]
        elevation = -(elevation - baseline(elevation))
        height_relative = -normalize(w, s, scale)[:, 1]
        arm = {
            'shoulder_max': metric(shoulder, np.max, 'deg'),
            'shoulder_rom': metric(shoulder, rom, 'deg'),
            'shoulder_peak_angular_speed': metric(angular_speed, np.max, 'deg/s'),
            'elbow_min': metric(elbow, np.min, 'deg'),
            'elbow_max': metric(elbow, np.max, 'deg'),
            'elbow_rom': metric(elbow, rom, 'deg'),
            'elbow_peak_angular_speed': metric(elbow_speed, np.max, 'deg/s'),
            'wrist_mean_speed': metric(speed, np.mean, 'shoulder_width/s'),
            'wrist_peak_speed': metric(speed, np.max, 'shoulder_width/s'),
            'wrist_max_height': metric(height_relative, np.max, 'shoulder_width'),
            'shoulder_girdle_rise': metric(elevation, np.max, 'shoulder_width'),
            'speed_variability_cv': metric(speed, lambda v: np.std(v) / np.mean(v) if np.mean(v) > .01 else np.nan, 'ratio'),
        }
        path_length = []
        for section in segments(wrist, times):
            path_length.extend(np.linalg.norm(np.diff(wrist[section], axis=0), axis=1).tolist())
        path_quality = metric(wrist[:, 0], np.mean, 'shoulder_width')
        path_quality['value'] = float(np.sum(path_length)) if path_quality['value'] is not None else None
        arm['wrist_path_length'] = path_quality
        # Only report a peak time if the underlying angle metric is usable.
        peak = int(np.nanargmax(shoulder)) if arm['shoulder_max']['value'] is not None else None
        arm['time_to_max'] = {**arm['shoulder_max'], 'value': float(times[peak]) if peak is not None else None, 'unit': 's'}
        arm['elbow_at_shoulder_max'] = {**arm['elbow_max'], 'value': None, 'technical_reliability': 'low',
                                        'status': 'Данный показатель не удалось надёжно определить по этому видео.'}
        if peak is not None:
            if np.isfinite(elbow[peak]) and arm['elbow_max']['value'] is not None:
                arm['elbow_at_shoulder_max']['value'] = float(elbow[peak])
                arm['elbow_at_shoulder_max']['technical_reliability'] = arm['elbow_max']['technical_reliability']
                arm['elbow_at_shoulder_max']['status'] = 'measured'
            events.append({'side': side, 'kind': 'maximum', 'timestamp': float(times[peak]),
                           'label': f'Максимальный подъём: {"левая" if side == "left" else "правая"} рука'})
            initial = baseline(shoulder)
            # Candidate phases of the dominant elevation, not validated task recognition.
            if np.isfinite(initial) and shoulder[peak] - initial >= 15:
                before = np.flatnonzero((np.arange(len(times)) < peak) & (shoulder > initial + 10))
                if len(before):
                    onset = int(before[0])
                    events.append({'side': side, 'kind': 'onset_candidate', 'timestamp': float(times[onset]), 'label': f'Начало подъёма ({side}), оценка'})
                    after = np.flatnonzero((np.arange(len(times)) > peak) & (shoulder <= initial + 10))
                    if len(after):
                        events.append({'side': side, 'kind': 'return_candidate', 'timestamp': float(times[after[0]]), 'label': f'Возвращение ({side}), оценка'})
                    arm['reach_duration'] = {**arm['time_to_max'], 'value': float(times[peak] - times[onset])}
        for name, values in {'shoulder_angle': shoulder, 'elbow_angle': elbow, 'wrist_x': wrist[:, 0],
                             'wrist_y': wrist[:, 1], 'wrist_speed': speed, 'shoulder_rise': elevation}.items():
            series[f'{side}_{name}'] = values
        metrics[f'{side}_arm'] = arm

    metrics['trunk'] = {'max_lateral_tilt_change': metric(np.abs(tilt_delta), np.max, 'deg'),
                        'shoulder_line_rom': metric(shoulder_line, rom, 'deg'),
                        'head_lateral_range': metric(head[:, 0], rom, 'shoulder_width')}
    comparison = {}
    for key in ('shoulder_rom', 'elbow_rom', 'wrist_mean_speed', 'wrist_peak_speed', 'wrist_path_length', 'time_to_max'):
        left, right = metrics['left_arm'][key], metrics['right_arm'][key]
        comparison[key] = {'left': left['value'], 'right': right['value'], 'unit': left['unit'],
                           'index_percent': asymmetry(left['value'], right['value']),
                           'technical_reliability': 'low' if left['value'] is None or right['value'] is None else 'medium',
                           'formula': '200 * |L-R| / (|L|+|R|)'}
    coverage = float(np.mean([v['coverage'] for v in quality.values()]))
    return {'metrics': metrics, 'asymmetry': comparison,
            'pose_quality': {'level': 'high' if coverage >= .9 else 'medium' if coverage >= .6 else 'low',
                             'landmarks': quality, 'threshold': CONFIDENCE,
                             'ambiguous_person_frames': sum(f['people'] > 1 for f in frames),
                             'no_person_frames': sum(f['people'] == 0 for f in frames)},
            'normalization': {'method': 'fixed median visible shoulder width, aspect-corrected 2D', 'scale_pixels': scale},
            'series': [{key: float(values[i]) for key, values in series.items()} for i in range(len(times))],
            'events': sorted(events, key=lambda e: e['timestamp'])}
