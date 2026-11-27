"""Fluxo completo usado pela interface e pela CLI.

1. find_candidates: sinais locais (FFmpeg) -> candidatos + miniaturas (+ transcrição). Fica em cache por vídeo.
2. plan_with_ai:    IA escolhe, ordena e define transições. Pode ser refeito sem repetir o passo 1.
3. export_plan:     FFmpeg corta os trechos aprovados e junta com as transições.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
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
    started = time.monotonic()
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
    (output / "analise.json").write_text(json.dumps({"segundos": round(time.monotonic() - started)}), encoding="utf-8")
    return output, candidates


def analysis_mode() -> str:
    """mapa (padrão): a IA olha a live inteira. picos: só os picos de áudio (mais rápido, menos preciso)."""
    return "picos" if os.getenv("PAJAU_MODO", "mapa").strip().lower() == "picos" else "mapa"


def find_segments_with_map(
    source: str,
    briefing: str,
    avoid: str,
    target_duration: float,
    ignore_intervals: list[list[float]] | None = None,
    progress: Progress = _no_progress,
    reuse_map: bool = True,
) -> tuple[Path, list[Candidate], str]:
    """Etapa 1 (mapa da live) + preparação da etapa 2 (zoom e fala nos trechos escolhidos).

    Se a live já foi mapeada (mapa.json), a IA escolhe pelo índice em texto, sem olhar as fotos de novo.
    Se o índice não tiver o que foi pedido, olha a live inteira como da primeira vez."""
    from .ai.plan import build_live_map
    from .analysis.audio import extract_mono_audio
    from .analysis.frames import sample_frames
    from .download.youtube import probe_video

    path = Path(source)
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in path.stem)[:40] or "live"
    output = Path("output") / f"{stem}-{_fingerprint(path)[:10]}"
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    duration = float(probe_video(path)["duration"])
    (output / "project.json").write_text(json.dumps({
        "source": source, "video_path": str(path.resolve()), "duration": duration,
        "settings": {"export_mode": "precise"}, "cuts": [],
    }, ensure_ascii=False), encoding="utf-8")

    muted_file = output / "mudo.json"
    if not muted_file.exists():
        progress(0.02, "Verificando se a live tem trechos sem áudio...")
        from .analysis.audio import find_muted_ranges
        muted_file.write_text(json.dumps(find_muted_ranges(path)), encoding="utf-8")
    muted = [tuple(item) for item in json.loads(muted_file.read_text(encoding="utf-8"))]

    interval = float(os.getenv("PAJAU_MAPA_SEGUNDOS", "20") or 20)
    index_file = output / "mapa.json"
    live_map = None
    if reuse_map and index_file.exists():
        from .ai.plan import build_map_from_index
        progress(0.15, "Live já mapeada: a IA escolhe pelo índice, sem olhar as fotos de novo...")
        index = json.loads(index_file.read_text(encoding="utf-8"))
        live_map, usage_text = build_map_from_index(index, briefing, avoid, target_duration)
        if any(raw.get("usar") for raw in live_map.get("segmentos", [])):
            usage_text = f"pelo índice, sem fotos: {usage_text}"
        else:
            progress(0.15, "O índice não tinha isso. Olhando a live inteira de novo...")
            live_map = None

    if live_map is None:
        progress(0.05, "Tirando fotos da live inteira para o mapa...")
        frames = sample_frames(path, output / "mapa", interval, fast=True)
        for start, end in ignore_intervals or []:
            frames = [(t, f) for t, f in frames if not start <= t <= end]
        progress(0.15, f"IA olhando o mapa da live ({len(frames)} fotos)...")
        live_map, usage_text = build_live_map(frames, output / "mapa-folhas", briefing, avoid, target_duration)
        index_file.write_text(json.dumps(live_map, ensure_ascii=False, indent=2), encoding="utf-8")

    chosen = []
    for raw in live_map.get("segmentos", []):
        if not raw.get("usar"):
            continue
        start = max(0.0, float(raw["start"]) - interval)
        end = min(duration, float(raw["end"]) + interval)
        if any(a <= start and end <= b for a, b in ignore_intervals or []):
            continue  # o pedido mandou pular esse pedaço da live
        if end - start >= 5:
            chosen.append((start, end, str(raw.get("descricao", ""))))
    if not chosen:
        return output, [], live_map.get("resumo", "")

    total = sum(end - start for start, end, _ in chosen)
    step = max(4.0, round(total / 300))  # ~300 fotos no total para o zoom
    candidates = []
    for index, (start, end, description) in enumerate(chosen, 1):
        progress(0.35 + 0.3 * index / len(chosen), f"Zoom no trecho {index} de {len(chosen)}: {description[:60]}")
        zoom = sample_frames(path, output / "zoom" / f"{start:.0f}-{end:.0f}-{step:.0f}", step, start, end - start)
        silent = sum(max(0.0, min(end, b) - max(start, a)) for a, b in muted)
        if silent > 0.5 * (end - start):
            description += " [ATENÇÃO: este trecho está sem áudio na live original]"
        candidates.append(Candidate(
            id=f"segmento-{index:02d}", start=start, end=end, score=1.0,
            previews=[str(f) for _, f in zoom], frame_times=[t for t, _ in zoom], description=description,
        ))

    if transcription_enabled():
        progress(0.7, "Transcrevendo a fala dos trechos escolhidos...")
        wav = extract_mono_audio(path, Path("cache") / output.name / "mono.wav") \
            if not (Path("cache") / output.name / "mono.wav").exists() else Path("cache") / output.name / "mono.wav"
        texts = transcribe_windows(wav, [(c.start, c.end) for c in candidates], max_chars=6000, with_times=True)
        for candidate, text in zip(candidates, texts):
            candidate.transcript = text

    (output / "candidates.json").write_text(
        json.dumps([asdict(c) for c in candidates], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "analise.json").write_text(json.dumps({
        "segundos": round(time.monotonic() - started), "mapa_uso": usage_text,
    }, ensure_ascii=False), encoding="utf-8")
    return output, candidates, muted_warning(output) + live_map.get("resumo", "")


def muted_warning(output: Path) -> str:
    """Aviso legível dos trechos mudos da live, ou texto vazio."""
    try:
        muted = json.loads((output / "mudo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not muted:
        return ""
    clock = lambda s: f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"
    ranges = ", ".join(f"{clock(a)}–{clock(b)}" for a, b in muted)
    return f"⚠️ A live original não tem áudio em: {ranges}. Os cortes nesses trechos sairão mudos. "


def plan_with_ai(output: Path, candidates: list[Candidate], briefing: str, avoid: str, target_duration: float,
                 aspect: str = "16:9") -> ReviewPlan:
    started = time.monotonic()
    plan = build_review_plan(candidates, briefing, target_duration, avoid=avoid, aspect=aspect)
    write_publication(output, plan.publication, [asdict(item) for item in plan.items], aspect)
    log_run(output, candidates, plan, briefing, avoid, target_duration, time.monotonic() - started)
    (output / "ia-plan.json").write_text(json.dumps({
        "provider": plan.provider,
        "briefing": briefing,
        "ignorar": avoid,
        "summary": plan.summary,
        "usage": plan.usage,
        "approved": [asdict(item) for item in plan.items],
        "rejected": plan.rejected,
        "publication": plan.publication,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan


def video_path(output: Path) -> str:
    return json.loads((output / "project.json").read_text(encoding="utf-8"))["video_path"]


def export_plan(output: Path, items: list[PlanItem] | list[dict], aspect: str, shorts: dict | None = None,
                notes: list[str] | None = None, progress=None) -> Path:
    from .export.ffmpeg import export_cuts
    from .export.transitions import join_with_transitions

    project = json.loads((output / "project.json").read_text(encoding="utf-8"))
    rows = [item if isinstance(item, dict) else asdict(item) for item in items]
    if not rows:
        raise RuntimeError("Nenhum trecho aprovado para exportar.")
    cuts = [Cut(start=float(row["start"]), end=float(row["end"]), score=float(row.get("confidence", 1.0))) for row in rows]

    stamp = datetime.now().strftime("%H%M%S")
    if aspect == "9:16" and shorts is None:
        from .export.shorts import load_settings
        shorts = load_settings()
    focuses = [float(row.get("focus", 0.5)) for row in rows]
    clips = export_cuts(project["video_path"], cuts, output / f"clips-{stamp}", aspect, "precise",
                        focuses=focuses, shorts=shorts, notes=notes, progress=progress)
    return join_with_transitions(clips, [row.get("transition", "corte") for row in rows], output / f"video-final-{stamp}.mp4")


HISTORY = Path("data") / "historico.md"


def _minutes(seconds: float) -> str:
    return f"{int(seconds // 60)}min{int(seconds % 60):02d}s"


def _read_map_usage(output: Path) -> str:
    try:
        return json.loads((output / "analise.json").read_text(encoding="utf-8")).get("mapa_uso", "")
    except (OSError, ValueError):
        return ""


def log_run(output: Path, candidates: list[Candidate], plan: ReviewPlan, briefing: str, avoid: str,
            target_duration: float, ai_seconds: float) -> None:
    """Acrescenta a execução em data/historico.md, para comparar resultados e custos com o tempo."""
    try:
        project = json.loads((output / "project.json").read_text(encoding="utf-8"))
        analysis = json.loads((output / "analise.json").read_text(encoding="utf-8")).get("segundos")
    except (OSError, ValueError):
        project, analysis = {}, None
    total = sum(item.end - item.start for item in plan.items)
    lines = [
        f"## {datetime.now():%Y-%m-%d %H:%M} — {Path(project.get('video_path', output.name)).name}",
        "",
        f"- **Live:** {_minutes(project.get('duration', 0))} · **pasta:** `{output}`",
        f"- **Pedido:** {briefing or '(vazio)'}",
        f"- **Ignorar:** {avoid or '(vazio)'}",
        f"- **Alvo:** {_minutes(target_duration)} · **gerado:** {len(plan.items)} trechos, {_minutes(total)}",
        f"- **Tempo:** análise local {_minutes(analysis) if analysis else 'reaproveitada'} · IA {_minutes(ai_seconds)}",
        f"- **IA:** {plan.provider} · plano: {plan.usage}",
        *( [f"- **Mapa da live:** {map_usage}"] if (map_usage := _read_map_usage(output)) else [] ),
        f"- **Candidatos:** {len(candidates)}, de {_minutes(min((c.start for c in candidates), default=0))} "
        f"a {_minutes(max((c.end for c in candidates), default=0))} da live",
        *( [f"- **Áudio:** {warning}"] if (warning := muted_warning(output)) else [] ),
        f"- **Resumo da IA:** {plan.summary}",
        "- **Opinião:** _(preencher)_",
        "",
    ]
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as handle:
        if handle.tell() == 0:
            handle.write("# Histórico de cortes\n\nUma entrada por análise. Preencha a opinião depois de ver o vídeo.\n\n")
        handle.write("\n" + "\n".join(lines) + "\n")


def chapters(items: list[dict]) -> list[tuple[float, str]]:
    """Início de cada trecho no vídeo final, já descontando a sobreposição das transições."""
    from .export.transitions import TRANSITIONS

    result, position = [], 0.0
    for index, item in enumerate(items):
        if index > 0:
            choice = TRANSITIONS.get(item.get("transition", "corte"))
            position -= choice[1] if choice else 0.0
        result.append((max(0.0, position), item.get("chapter") or item.get("kind", "")))
        position += float(item["end"]) - float(item["start"])
    return result


def publication_text(publication: dict, items: list[dict], aspect: str) -> str:
    """Texto pronto para copiar: títulos, descrição, capítulos (vídeo horizontal) e hashtags."""
    if not publication:
        return ""
    lines = ["## Títulos", ""] + [f"{i}. {title}" for i, title in enumerate(publication.get("titles", []), 1)]
    lines += ["", "## Descrição", "", publication.get("description", "").strip()]
    marks = chapters(items)
    # O YouTube só mostra capítulos com 3 ou mais, começando em 0:00 e com pelo menos 10 s cada.
    long_enough = all(b[0] - a[0] >= 10 for a, b in zip(marks, marks[1:]))
    if aspect != "9:16" and len(marks) >= 3 and long_enough:
        lines += [""] + [f"{int(t // 60)}:{int(t % 60):02d} {name}" for t, name in marks]
    hashtags = " ".join(publication.get("hashtags", []))
    if hashtags:
        lines += ["", hashtags]
    covers = [c for c in publication.get("covers", []) if isinstance(c, dict) and c.get("text")]
    if covers:
        lines += ["", "## Ideias de capa", ""] + [f"{i}. {c['text']} — {c.get('why', '')}" for i, c in enumerate(covers, 1)]
    return "\n".join(lines)


def write_publication(output: Path, publication: dict, items: list[dict], aspect: str) -> str:
    text = publication_text(publication, items, aspect)
    if text:
        (output / "publicacao.md").write_text(text + "\n", encoding="utf-8")
    return text


def make_publication_covers(output: Path, publication: dict, items: list[dict], aspect: str,
                            notes: list[str] | None = None) -> list[dict]:
    """3 capas. A IA escolhe as cenas olhando as 12 mais fortes (uma imagem só, ~2 mil tokens);
    desligue com PAJAU_CAPA_IA=false. Sem IA, usa as ideias de capa que vieram no plano."""
    from .ai.config import env_flag
    from .export.covers import make_covers, scene_candidates
    notes = notes if notes is not None else []
    video, folder = video_path(output), output / "capas"
    ideas = (publication or {}).get("covers") or []
    if env_flag("PAJAU_CAPA_IA", True):
        try:
            scenes = scene_candidates(video, items, folder / "cenas")
            if scenes:
                from .ai.covers_ai import pick_covers
                titles = (publication or {}).get("titles") or []
                picked, usage = pick_covers(scenes, folder / "cenas", titles[0] if titles else "")
                if picked:
                    ideas = picked
                    notes.append(f"Capas escolhidas pela IA · {usage}")
        except Exception as error:
            notes.append(f"Capas feitas sem a IA ({error})")
    try:
        return make_covers(video, ideas, items, folder, aspect)
    except Exception as error:
        notes.append(f"Não deu para montar as capas: {error}")
        return []
