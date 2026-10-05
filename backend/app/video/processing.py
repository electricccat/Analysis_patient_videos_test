"""Use decoded presentation timestamps, including variable frame rate video."""
from pathlib import Path
import av
import numpy as np

MAX_SECONDS = 180
MAX_FRAMES = 12000


def display_rotation(frame, stream):
    """PyAV DISPLAYMATRIX rotation is counterclockwise; never guess arbitrary angles."""
    rotation = int(frame.rotation) % 360
    if rotation not in (0, 90, 180, 270):
        raise ValueError('Поддерживаются только повороты видео на 0°, 90°, 180° и 270°.')
    if not rotation and float(stream.metadata.get('rotate', '0')) % 360:
        raise ValueError('Не удалось прочитать матрицу поворота видео. Экспортируйте его в правильной ориентации.')
    return rotation


def inspect_video(path: Path):
    try:
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            first = next(container.decode(stream))
            rotation = display_rotation(first, stream)
            encoded_width, encoded_height = first.width, first.height
            width, height = (encoded_height, encoded_width) if rotation in (90,270) else (encoded_width,encoded_height)
            duration = float(container.duration / av.time_base) if container.duration else None
            fps = float(stream.average_rate) if stream.average_rate else None
            if width < 64 or height < 64 or width * height > 3840 * 2160:
                raise ValueError('Разрешение должно быть от 64×64 до 3840×2160.')
            if duration and duration > MAX_SECONDS:
                raise ValueError('Максимальная длительность видео — 180 секунд.')
            return {'width': width, 'height': height, 'duration_seconds': duration,
                    'encoded_width': encoded_width, 'encoded_height': encoded_height,
                    'rotation_ccw': rotation,
                    'nominal_fps': fps, 'codec': stream.codec_context.name,
                    'timestamp_method': 'decoded presentation timestamps (PTS)',
                    'lighting': 'not assessed', 'camera_motion': 'not assessed'}
    except (IndexError, StopIteration, av.error.FFmpegError) as exc:
        raise ValueError('Не удалось декодировать видеопоток.') from exc


def extract(path: Path):
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        start = previous = None
        rotation = None
        for i, frame in enumerate(container.decode(stream)):
            current_rotation = display_rotation(frame, stream)
            if rotation is None:
                rotation = current_rotation
            elif current_rotation != rotation:
                raise ValueError('Ориентация видео меняется между кадрами. Снимайте в одном положении устройства.')
            if i >= MAX_FRAMES:
                raise ValueError('Слишком много кадров: максимум 12000.')
            if frame.pts is None or frame.time_base is None:
                raise ValueError('В видео отсутствуют достоверные временные метки.')
            timestamp = float(frame.pts * frame.time_base)
            if start is None:
                start = timestamp
            timestamp -= start
            if previous is not None and timestamp <= previous:
                raise ValueError('Временные метки кадров не возрастают.')
            if timestamp > MAX_SECONDS:
                raise ValueError('Максимальная длительность видео — 180 секунд.')
            previous = timestamp
            rgb = frame.to_ndarray(format='rgb24')
            if rotation:
                rgb = np.rot90(rgb, rotation // 90)
            yield i, timestamp, np.ascontiguousarray(rgb)


class PreviewWriter:
    """Browser compatible silent MP4, retaining PTS. Original is stored separately."""
    def __init__(self, path, width, height, fps):
        from fractions import Fraction
        self.time_base = Fraction(1, 1000000)
        self.container = av.open(str(path), mode='w')
        self.stream = self.container.add_stream('libx264', rate=Fraction(str(fps or 30)).limit_denominator(1000))
        self.stream.width = width - width % 2
        self.stream.height = height - height % 2
        self.stream.pix_fmt = 'yuv420p'
        self.stream.time_base = self.time_base
        self.stream.codec_context.time_base = self.time_base
        self.stream.options = {'crf': '23', 'preset': 'veryfast'}

    def write(self, rgb, timestamp):
        frame = av.VideoFrame.from_ndarray(rgb, format='rgb24')
        frame = frame.reformat(width=self.stream.width, height=self.stream.height, format='yuv420p')
        frame.pts = round(timestamp * 1000000)
        frame.time_base = self.time_base
        for packet in self.stream.encode(frame):
            self.container.mux(packet)

    def close(self):
        try:
            for packet in self.stream.encode():
                self.container.mux(packet)
        finally:
            self.container.close()
