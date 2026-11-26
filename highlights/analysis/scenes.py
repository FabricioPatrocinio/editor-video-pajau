from __future__ import annotations

import numpy as np


def detect_scene_changes(video: str, duration: float) -> np.ndarray:
    """Optional PySceneDetect integration. Unavailable scenes are zero-valued."""
    changes = np.zeros(duration, dtype=np.float32)
    try:
        from scenedetect import AdaptiveDetector, SceneManager, open_video
    except ImportError:
        return changes

    try:
        video_obj = open_video(video)
        scene_manager = SceneManager()
        scene_manager.add_detector(AdaptiveDetector())
        scene_manager.detect_scenes(video_obj, show_progress=False)
        for scene in scene_manager.get_scene_list():
            seconds = scene[0].get_seconds()
            if 0 <= seconds < duration:
                changes[int(seconds)] = 1.0
    except Exception:
        return changes
    return changes
