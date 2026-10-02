from typing import Protocol
from pathlib import Path
import hashlib
import numpy as np

LANDMARKS = {'nose': 0, 'left_shoulder': 11, 'right_shoulder': 12,
             'left_elbow': 13, 'right_elbow': 14, 'left_wrist': 15,
             'right_wrist': 16, 'left_hip': 23, 'right_hip': 24}


class PoseProvider(Protocol):
    def detect(self, rgb, timestamp_ms: int) -> dict: ...
    def close(self): ...


class MediaPipeProvider:
    def __init__(self, model_path: Path):
        import mediapipe as mp
        self.mp = mp
        self.model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
        self.version = mp.__version__
        self.detector = mp.tasks.vision.PoseLandmarker.create_from_options(
            mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=2,
                min_pose_detection_confidence=0.5, min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5))

    def detect(self, rgb, timestamp_ms):
        result = self.detector.detect_for_video(
            self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)), timestamp_ms)
        # Ambiguous identity is missing data, not an arbitrary patient selection.
        if len(result.pose_landmarks) != 1:
            return {'landmarks': {}, 'people': len(result.pose_landmarks)}
        landmarks = {}
        for name, index in LANDMARKS.items():
            point = result.pose_landmarks[0][index]
            landmarks[name] = {'x': point.x, 'y': point.y, 'z': point.z,
                               'visibility': point.visibility, 'presence': point.presence,
                               'confidence': min(point.visibility, point.presence),
                               'timestamp': timestamp_ms / 1000}
        return {'landmarks': landmarks, 'people': 1}

    def close(self):
        self.detector.close()
