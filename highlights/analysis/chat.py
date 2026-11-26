from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def parse_timestamp(value: str | float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    parts = str(value).split(":")
    result = 0.0
    for part in parts:
        result = result * 60 + float(part)
    return result


def load_manual_timestamps(path: str | Path | None, duration: float) -> np.ndarray:
    signal = np.zeros(duration, dtype=np.float32)
    if not path:
        return signal
    text = Path(path).read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        token = line.replace("\t", " ").replace(",", " ").split()[0]
        try:
            timestamp = parse_timestamp(token)
        except ValueError:
            continue
        if 0 <= timestamp < duration:
            signal[min(int(timestamp), len(signal) - 1)] += 1.0
    if signal.max() > 0:
        signal /= signal.max()
    return signal


def chat_activity(path: str | Path | None, duration: float, offset: float = 8.0, keywords: dict[str, float] | None = None) -> np.ndarray:
    activity = np.zeros(duration, dtype=np.float32)
    keyword_counts = np.zeros(duration, dtype=np.float32)
    if not path:
        return activity

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("actions", data.get("messages", []))
    keywords = keywords or {}

    for item in items:
        timestamp = item.get("timestamp", item.get("timestampText", 0))
        try:
            seconds = parse_timestamp(timestamp)
        except (TypeError, ValueError):
            continue
        seconds = max(0.0, seconds - offset)
        if seconds >= duration:
            continue
        index = int(seconds)
        activity[index] += 1.0
        text = str(item.get("message", item.get("text", ""))).upper()
        for word, weight in keywords.items():
            if word.upper() in text:
                keyword_counts[index] += float(weight)

    combined = activity + 2.0 * keyword_counts
    if combined.max() > 0:
        combined /= combined.max()
    return combined
