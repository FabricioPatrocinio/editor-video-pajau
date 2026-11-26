from __future__ import annotations

from pathlib import Path

import numpy as np

from .audio import audio_energy, detect_silence
from .chat import chat_activity, load_manual_timestamps
from .scenes import detect_scene_changes


def _curve(value: np.ndarray, duration: float) -> np.ndarray:
    curve = np.asarray(value, dtype=np.float32)
    if curve.size > int(duration):
        curve = curve[:int(duration)]
    elif curve.size < int(duration):
        curve = np.pad(curve, (0, int(duration) - curve.size))
    if curve.max() > 0:
        curve = (curve - curve.min()) / (curve.max() - curve.min() + 1e-6)
    return curve


def silence_penalty(duration: float, intervals: list[tuple[float, float]]) -> np.ndarray:
    curve = np.ones(int(duration), dtype=np.float32)
    for start, end in intervals:
        a = max(0, int(start))
        b = min(len(curve), int(np.ceil(end)))
        curve[a:b] = 0.0
    return curve


def heatmap_curve(info: dict | None, duration: float) -> np.ndarray:
    curve = np.zeros(int(duration), dtype=np.float32)
    if not info:
        return curve
    heatmap = info.get("heatmap")
    if isinstance(heatmap, list):
        for mark in heatmap:
            if isinstance(mark, dict):
                start = mark.get("start_time", mark.get("start", 0))
                score = mark.get("value", mark.get("intensity", 1.0))
            else:
                continue
            index = int(float(start))
            if 0 <= index < len(curve):
                curve[index] = max(curve[index], float(score))
    return _curve(curve, duration)


def build_signal_bundle(
    video: str,
    duration: float,
    wav_path: str | None = None,
    chat_path: str | None = None,
    manual_path: str | None = None,
    youtube_info: dict | None = None,
    chat_offset: float = 8.0,
    chat_keywords: dict[str, float] | None = None,
) -> dict[str, np.ndarray]:
    seconds = int(np.ceil(duration))
    audio_rms, audio_z = audio_energy(wav_path, seconds) if wav_path else (np.zeros(seconds), np.zeros(seconds))
    silence_intervals = detect_silence(wav_path) if wav_path else []

    return {
        "audio": _curve(np.maximum(audio_z, 0), seconds),
        "chat": _curve(chat_activity(chat_path, seconds, chat_offset, chat_keywords), seconds),
        "heatmap": heatmap_curve(youtube_info, seconds),
        "scene": _curve(detect_scene_changes(video, seconds), seconds),
        "silence": silence_penalty(seconds, silence_intervals),
        "manual": _curve(load_manual_timestamps(manual_path, seconds), seconds),
    }
