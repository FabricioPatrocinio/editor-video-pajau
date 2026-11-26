from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Settings


DEFAULT_CONFIG = {
    "target_duration": 600,
    "min_cut": 20,
    "max_cut": 90,
    "padding_before": 8,
    "padding_after": 4,
    "min_distance": 12,
    "chat_offset": 8,
    "order": "score",
    "aspect": "16:9",
    "export_mode": "precise",
}


def load_config(path: str | Path | None = None) -> Settings:
    data = dict(DEFAULT_CONFIG)
    if path:
        loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        data.update(loaded)
    data["weights"] = data.get("weights", {
        "audio": 0.30, "chat": 0.20, "heatmap": 0.20,
        "scene": 0.15, "silence": 0.10, "manual": 0.05,
    })
    data["chat_keywords"] = data.get("chat_keywords", {})
    data["ignore_intervals"] = data.get("ignore_intervals", [])
    known = Settings.__dataclass_fields__
    return Settings(**{key: value for key, value in data.items() if key in known})


def load_preset(name: str) -> Settings:
    presets = Path(__file__).resolve().parents[1] / "configs" / "presets.yaml"
    data = yaml.safe_load(presets.read_text(encoding="utf-8")) or {}
    if name not in data:
        raise KeyError(f"Preset desconhecido: {name}. Disponíveis: {', '.join(data)}")
    return load_config_from_mapping(data[name])


def load_config_from_mapping(data: dict[str, Any]) -> Settings:
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    merged.setdefault("weights", DEFAULT_CONFIG.get("weights", {}))
    merged.setdefault("chat_keywords", {})
    merged.setdefault("ignore_intervals", [])
    known = Settings.__dataclass_fields__
    return Settings(**{key: value for key, value in merged.items() if key in known})
