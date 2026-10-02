"""Deterministic 2D geometry. Missing data remain NaN; never bridge gaps."""
import numpy as np


def angle(a, b, c):
    a, b, c = (np.asarray(p, dtype=float) for p in (a, b, c))
    u, v = a - b, c - b
    denominator = np.linalg.norm(u) * np.linalg.norm(v)
    if not np.all(np.isfinite([a, b, c])) or denominator < 1e-9:
        return float('nan')
    return float(np.degrees(np.arccos(np.clip(np.dot(u, v) / denominator, -1, 1))))


def normalize(points, origin, scale):
    points = np.asarray(points, dtype=float)
    if not np.isfinite(scale) or scale <= 1e-9:
        return np.full_like(points, np.nan)
    return (points - origin) / scale


def segments(values, times, max_gap=0.25):
    values = np.asarray(values)
    valid = np.isfinite(values) if values.ndim == 1 else np.all(np.isfinite(values), axis=1)
    start = None
    for i, good in enumerate(valid):
        if start is not None and (not good or times[i] - times[i - 1] > max_gap):
            yield slice(start, i)
            start = None
        if good and start is None:
            start = i
    if start is not None:
        yield slice(start, len(values))


def smooth(values, times, window_seconds=0.15):
    values, times = np.asarray(values, float), np.asarray(times, float)
    output = np.full_like(values, np.nan)
    for section in segments(values, times):
        section_times = times[section]
        for i in range(section.start, section.stop):
            lo = section.start + np.searchsorted(section_times, times[i] - window_seconds / 2, side='left')
            hi = section.start + np.searchsorted(section_times, times[i] + window_seconds / 2, side='right')
            output[i] = np.mean(values[lo:hi], axis=0)
    return output


def velocity(values, times):
    values, times = np.asarray(values, float), np.asarray(times, float)
    if len(times) > 1 and (not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0)):
        raise ValueError('Timestamps must be finite and strictly increasing')
    output = np.full_like(values, np.nan)
    for section in segments(values, times):
        if section.stop - section.start >= 3:
            output[section] = np.gradient(values[section], times[section], axis=0)
    return output


def rom(values):
    values = np.asarray(values, float)
    valid = values[np.isfinite(values)]
    return float(np.ptp(valid)) if len(valid) else float('nan')


def asymmetry(left, right):
    """Unsigned symmetric index: 200*abs(L-R)/(abs(L)+abs(R))."""
    if left is None or right is None or not np.isfinite([left, right]).all():
        return None
    denominator = abs(left) + abs(right)
    return None if denominator < 1e-9 else 200 * abs(left - right) / denominator
