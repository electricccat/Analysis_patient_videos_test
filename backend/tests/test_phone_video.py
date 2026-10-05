import av
import numpy as np
import pytest
from backend.app.video.processing import inspect_video, extract


@pytest.mark.parametrize('rotation,shape,corner', [
    (0, (80,120,3), (230,20,20)),
    (90, (120,80,3), (20,230,20)),
    (180, (80,120,3), (20,20,230)),
    (270, (120,80,3), (230,230,20)),
])
def test_phone_display_matrix_is_applied_before_analysis_and_preserves_pts(tmp_path, rotation, shape, corner):
    path = tmp_path / 'phone.mov'
    image = np.zeros((80,120,3), dtype=np.uint8)
    image[:40,:60] = (230,20,20)
    image[:40,60:] = (20,230,20)
    image[40:,60:] = (20,20,230)
    image[40:,:60] = (230,230,20)
    with av.open(str(path), 'w') as output:
        stream = output.add_stream('libx264', rate=30)
        stream.width, stream.height, stream.pix_fmt = 120,80,'yuv420p'
        stream.set_display_rotation(rotation)
        for i in range(3):
            frame = av.VideoFrame.from_ndarray(image, format='rgb24')
            for packet in stream.encode(frame): output.mux(packet)
        for packet in stream.encode(): output.mux(packet)
    quality = inspect_video(path)
    assert (quality['height'],quality['width'],3) == shape
    assert quality['rotation_ccw'] == rotation
    assert (quality['encoded_height'],quality['encoded_width']) == (80,120)
    frames = list(extract(path))
    assert len(frames) == 3
    assert [frame[1] for frame in frames] == pytest.approx([0,1/30,2/30])
    for _,_,rgb in frames:
        assert rgb.shape == shape
        assert rgb.flags.c_contiguous
        assert rgb[10,10] == pytest.approx(corner, abs=12)
