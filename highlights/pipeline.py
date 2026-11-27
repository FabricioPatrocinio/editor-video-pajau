"""Fluxo completo usado pela interface e pela CLI.

1. find_candidates: sinais locais (FFmpeg) -> candidatos + miniaturas (+ transcrição). Fica em cache por vídeo.
2. plan_with_ai:    IA escolhe, ordena e define transições. Pode ser refeito sem repetir o passo 1.
3. export_plan:     FFmpeg corta os trechos aprovados e junta com as transições.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from .ai.config import env_int
from .ai.plan import Candidate, PlanItem, ReviewPlan, build_review_plan
from .analysis.transcribe import transcribe_windows, transcription_enabled
from .cli import analyze
from .models import Cut

Progress = Callable[[float, str], None]


def _no_progress(fraction: float, text: str) -> None:
    print(text)


def candidate_pool_duration(target_duration: float) -> float:
    """A IA precisa de opções: o conjunto de candidatos é bem maior que o vídeo final."""
    return max(target_duration * 4, target_duration + 900)


def _fingerprint(path: Path) -> str:
    """Identifica o vídeo pelo conteúdo (nome + tamanho + começo e fim), não pela pasta onde está."""
    size = path.stat().st_size
    digest = hashlib.sha1(f"{path.name}:{size}".encode())
    with path.open("rb") as handle:
        digest.update(handle.read(1 << 20))
        handle.seek(max(0, size - (1 << 20)))
        digest.update(handle.read(1 << 20))
    return digest.hexdigest()


def analysis_dir(source: str, target_duration: float, ignore_intervals: list[list[float]]) -> Path:
    """Pasta da análise de um vídeo. O mesmo vídeo com as mesmas opções reaproveita tudo."""
    path = Path(source)
    key = json.dumps([
        _fingerprint(path) if path.exists() else source,
        candidate_pool_duration(target_duration),
        ignore_intervals,
        transcription_enabled(),
        env_int("PAJAU_MAX_CANDIDATES", 60),
    ])
    digest = hashlib.sha1(key.encode()).hexdigest()[:10]
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in path.stem)[:40] or "live"
    return Path("output") / f"{stem}-{digest}"


def load_candidates(output: Path) -> list[Candidate]:
    data = json.loads((output / "candidates.json").read_text(encoding="utf-8"))
    return [Candidate(**item) for item in data]


def find_candidates(
    source: str,
    target_duration: float,
    ignore_intervals: list[list[float]] | None = None,
    url: bool = False,
    progress: Progress = _no_progress,
) -> tuple[Path, list[Candidate]]:
    ignore_intervals = ignore_intervals or []
    output = analysis_dir(source, target_duration, ignore_intervals)
    if (output / "candidates.json").exists():
        progress(0.9, "Live já analisada antes: reaproveitando candidatos.")
        return output, load_candidates(output)

    args = argparse.Namespace(
        input=None if url else source, url=source if url else None, chat=None, manual=None,
        preset="highlights_10min", target_duration=candidate_pool_duration(target_duration),
        max_cuts=env_int("PAJAU_MAX_CANDIDATES", 60), aspect="16:9",
        cache=str(Path("cache") / output.name), output=str(output), review_only=True,
        ignore_intervals=ignore_intervals, progress=progress,
    )
    analyze(args)

    project = json.loads((output / "project.json").read_text(encoding="utf-8"))
    candidates = [
        Candidate(
            id=f"evento-{index:02d}",
            start=float(cut["start"]),
            end=float(cut["end"]),
            score=float(cut["score"]),
            previews=list(cut.get("preview_paths") or []),
            signals={k: float(v) for k, v in (cut.get("contributions") or {}).items()},
        )
        for index, cut in enumerate(project["cuts"], 1)
    ]

    if candidates and transcription_enabled():
        progress(0.8, f"Transcrevendo {len(candidates)} trechos no seu computador...")
        texts = transcribe_windows(Path(args.cache) / "audio" / "mono.wav", [(c.start, c.end) for c in candidates])
        for candidate, text in zip(candidates, texts):
            candidate.transcript = text

    (output / "candidates.json").write_text(
        json.dumps([asdict(c) for c in candidates], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output, candidates


def plan_with_ai(output: Path, candidates: list[Candidate], briefing: str, avoid: str, target_duration: float) -> ReviewPlan:
    plan = build_review_plan(candidates, briefing, target_duration, avoid=avoid)
    (output / "ia-plan.json").write_text(json.dumps({
        "provider": plan.provider,
        "briefing": briefing,
        "ignorar": avoid,
        "summary": plan.summary,
        "usage": plan.usage,
        "approved": [asdict(item) for item in plan.items],
        "rejected": plan.rejected,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan


def video_path(output: Path) -> str:
    return json.loads((output / "project.json").read_text(encoding="utf-8"))["video_path"]


def export_plan(output: Path, items: list[PlanItem] | list[dict], aspect: str) -> Path:
    from .export.ffmpeg import export_cuts
    from .export.transitions import join_with_transitions

    project = json.loads((output / "project.json").read_text(encoding="utf-8"))
    rows = [item if isinstance(item, dict) else asdict(item) for item in items]
    if not rows:
        raise RuntimeError("Nenhum trecho aprovado para exportar.")
    cuts = [Cut(start=float(row["start"]), end=float(row["end"]), score=float(row.get("confidence", 1.0))) for row in rows]

    stamp = datetime.now().strftime("%H%M%S")
    clips = export_cuts(project["video_path"], cuts, output / f"clips-{stamp}", aspect, "precise")
    return join_with_transitions(clips, [row.get("transition", "corte") for row in rows], output / f"video-final-{stamp}.mp4")
