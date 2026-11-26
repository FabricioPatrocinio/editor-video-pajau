from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from ..models import Cut, Project


def write_project(project: Project, path: str | Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(project.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_csv(cuts: list[Cut], path: str | Path) -> Path:
    path = Path(path)
    fields = ["start", "end", "duration", "score"] + sorted({name for cut in cuts for name in cut.contributions})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for cut in cuts:
            row = {"start": cut.start, "end": cut.end, "duration": cut.duration, "score": cut.score}
            row.update(cut.contributions)
            writer.writerow(row)
    return path


def write_json(cuts: list[Cut], path: str | Path) -> Path:
    path = Path(path)
    payload = [{"start": cut.start, "end": cut.end, "duration": cut.duration, "score": cut.score, "contributions": cut.contributions} for cut in cuts]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def plot_score(score: np.ndarray, cuts: list[Cut], path: str | Path) -> Path:
    path = Path(path)
    fig, axis = plt.subplots(figsize=(14, 5))
    axis.plot(np.arange(len(score)), score, label="Pontuação")
    for cut in cuts:
        axis.axvspan(cut.start, cut.end, color="orange", alpha=0.25)
    axis.set_xlabel("Tempo (segundos)")
    axis.set_ylabel("Pontuação normalizada")
    axis.set_xlim(0, len(score))
    axis.grid(alpha=0.2)
    axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
