from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class Cut:
    start: float
    end: float
    score: float
    contributions: Dict[str, float] = field(default_factory=dict)
    accepted: bool = True
    preview_paths: List[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Settings:
    target_duration: float = 600.0
    min_cut: float = 20.0
    max_cut: float = 90.0
    max_cuts: Optional[int] = None
    padding_before: float = 8.0
    padding_after: float = 4.0
    min_distance: float = 12.0
    ignore_intervals: List[List[float]] = field(default_factory=list)
    chat_offset: float = 8.0
    chat_keywords: Dict[str, float] = field(default_factory=dict)
    weights: Dict[str, float] = field(default_factory=lambda: {
        "audio": 0.30,
        "chat": 0.20,
        "heatmap": 0.20,
        "scene": 0.15,
        "silence": 0.10,
        "manual": 0.05,
    })
    order: str = "score"
    aspect: str = "16:9"
    export_mode: str = "precise"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Project:
    source: str
    video_path: str
    duration: float
    settings: Settings
    cuts: List[Cut] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "video_path": self.video_path,
            "duration": self.duration,
            "settings": self.settings.to_dict(),
            "cuts": [asdict(cut) for cut in self.cuts],
        }
