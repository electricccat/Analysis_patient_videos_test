from types import SimpleNamespace
import numpy as np
from backend.app.pose.provider import MediaPipeProvider


def test_padded_decoder_rows_are_copied_before_inference():
    # FFmpeg RGB buffers commonly have 32-byte aligned (padded) row strides.
    backing = np.zeros((10, 40, 3), dtype=np.uint8)
    rgb = backing[:, :33, :]
    assert not rgb.flags.c_contiguous
    def image(*, image_format, data):
        assert data.flags.c_contiguous
        assert np.array_equal(data, rgb)
        return data
    provider = object.__new__(MediaPipeProvider)
    provider.mp = SimpleNamespace(Image=image, ImageFormat=SimpleNamespace(SRGB='rgb'))
    provider.detector = SimpleNamespace(detect_for_video=lambda image, timestamp: SimpleNamespace(pose_landmarks=[]))
    assert provider.detect(rgb, 0) == {'landmarks': {}, 'people': 0}
