from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import usage as usage_ledger
from .config import AISettings, check_ai_ready, load_ai_settings
from .prompt import MAP_JSON_INSTRUCTION, MAP_PROMPT, MAP_SCHEMA, SYSTEM_PROMPT
from .providers import AIProvider, ImagePart, Part, TextPart, get_provider
from .style import style_prompt
from ..export.sheets import build_sheets, build_timeline_sheets
from ..export.transitions import TRANSITIONS


@dataclass
class Candidate:
    id: str
    start: float
    end: float
    score: float
    previews: list[str]
    signals: dict[str, float] = field(default_factory=dict)
    transcript: str = ""
    # Quando preenchido, `previews` são fotos a cada poucos segundos e estes são os segundos de cada uma.
    frame_times: list[float] = field(default_factory=list)
    description: str = ""


def _focus(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


@dataclass
class PlanItem:
    id: str
    start: float
    end: float
    accepted: bool
    reason: str
    confidence: float
    kind: str
    transition: str = "corte"
    chapter: str = ""
    focus: float = 0.5  # onde está a ação na largura da tela (0 = esquerda, 1 = direita), para o Short


@dataclass
class ReviewPlan:
    items: list[PlanItem]
    rejected: list[dict]
    summary: str
    provider: str
    usage: str
    publication: dict = field(default_factory=dict)


def _clock(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _request_parts(
    candidates: list[Candidate],
    briefing: str,
    avoid: str,
    target_duration: float,
    max_image_candidates: int,
    aspect: str = "16:9",
) -> list[Part]:
    """Parte fixa (candidatos + imagens) primeiro, parte que muda (estilo + briefing) por último.

    Assim, refazer o plano com outro briefing reaproveita o cache da API e custa bem menos.
    """
    fixed = {
        "candidatos": [
            {
                "id": candidate.id,
                "start": round(candidate.start, 1),
                "end": round(candidate.end, 1),
                "duracao": round(candidate.end - candidate.start, 1),
                "posicao_na_live": f"{_clock(candidate.start)} - {_clock(candidate.end)}",
                "pontuacao_local": round(candidate.score, 3),
                "sinais": {name: round(value, 2) for name, value in sorted(candidate.signals.items()) if value > 0},
                "transcricao": candidate.transcript or None,
                **({"o_que_e": candidate.description} if candidate.description else {}),
            }
            for candidate in sorted(candidates, key=lambda item: item.start)
        ],
    }
    parts: list[Part] = [TextPart(json.dumps(fixed, ensure_ascii=False, indent=1))]

    with_images = sorted(candidates[:max_image_candidates], key=lambda item: item.start)
    first_preview = next((Path(p) for c in with_images for p in c.previews if Path(p).exists()), None)
    if first_preview is not None:
        short = [c for c in with_images if not c.frame_times]
        sheets = build_sheets(short, first_preview.parent.parent / "folhas") if short else []
        for candidate in with_images:
            if candidate.frame_times:
                frames = list(zip(candidate.frame_times, map(Path, candidate.previews)))
                sheets += build_timeline_sheets(frames, first_preview.parent.parent / "folhas", title=candidate.id)
        for description, sheet in sheets:
            parts.append(TextPart(description))
            parts.append(ImagePart(sheet))
    parts.append(TextPart("Fim dos candidatos.", cache=True))

    request = {
        "briefing": briefing.strip() or "Montar os melhores momentos da live.",
        "o_que_ignorar": avoid.strip() or "Nada além de loading, menus, pausas e silêncio.",
        "duracao_alvo_segundos": round(target_duration),
        "formato": "Short vertical 9:16" if aspect == "9:16" else "vídeo horizontal 16:9",
    }
    style = style_prompt()
    if style:
        parts.append(TextPart(style))
    parts.append(TextPart("Pedido do criador:\n" + json.dumps(request, ensure_ascii=False, indent=1)))
    return parts


def _validate(result: dict, candidates: list[Candidate], target_duration: float) -> list[PlanItem]:
    by_id = {candidate.id: candidate for candidate in candidates}
    raw_items = result.get("approved", result.get("aprovados", [])) or []
    raw_items = sorted(raw_items, key=lambda raw: (int(raw.get("order", 999) or 999)))

    plan: list[PlanItem] = []
    total = 0.0
    # A duração é decidida pela IA conforme o pedido (pode passar se você pedir); isto é só uma trava.
    limit = target_duration * 3
    for raw in raw_items:
        candidate_id = str(raw.get("id", ""))
        candidate = by_id.get(candidate_id)
        if not candidate:
            continue
        try:
            start = float(raw.get("start", candidate.start))
            end = float(raw.get("end", candidate.end))
            confidence = float(raw.get("confidence", raw.get("confianca", 0.5)))
        except (TypeError, ValueError):
            start, end, confidence = candidate.start, candidate.end, 0.5
        start = max(candidate.start, min(candidate.end, start))
        end = max(start, min(candidate.end, end))
        if end - start < 3:
            start, end = candidate.start, candidate.end
        if total + (end - start) > limit:
            continue
        if any(start < item.end and item.start < end for item in plan):
            continue  # sobreposto a um pedaço já aprovado
        plan.append(PlanItem(
            id=candidate_id,
            start=start,
            end=end,
            accepted=True,
            reason=str(raw.get("reason", raw.get("motivo", "Selecionado pela IA.")))[:400],
            confidence=max(0.0, min(1.0, confidence)),
            kind=str(raw.get("kind", raw.get("tipo", "momento_interessante")))[:80],
            transition=raw.get("transition") if raw.get("transition") in TRANSITIONS else "corte",
            chapter=str(raw.get("chapter", ""))[:80],
            focus=_focus(raw.get("focus")),
        ))
        total += end - start
    return plan


def prepare_request(
    candidates: Iterable[Candidate], briefing: str, target_duration: float, avoid: str, settings: AISettings,
    aspect: str = "16:9",
) -> tuple[list[Candidate], list[Part]]:
    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)[: settings.max_candidates]
    return ranked, _request_parts(ranked, briefing, avoid, target_duration, settings.max_image_candidates, aspect)


def plan_from_result(result: dict, ranked: list[Candidate], target_duration: float, provider: str, usage: str) -> ReviewPlan:
    return ReviewPlan(
        items=_validate(result, ranked, target_duration),
        rejected=[dict(item) for item in result.get("rejected", []) if isinstance(item, dict)],
        summary=str(result.get("summary", "")),
        provider=provider,
        usage=usage,
        publication=result.get("publication") if isinstance(result.get("publication"), dict) else {},
    )


def build_review_plan(
    candidates: Iterable[Candidate],
    briefing: str,
    target_duration: float,
    avoid: str = "",
    settings: AISettings | None = None,
    provider: AIProvider | None = None,
    aspect: str = "16:9",
) -> ReviewPlan:
    settings = settings or load_ai_settings()
    problem = check_ai_ready(settings)
    if problem and provider is None:
        raise RuntimeError(problem)
    usage_ledger.ensure_budget(settings.daily_limit_usd)

    ranked, parts = prepare_request(candidates, briefing, target_duration, avoid, settings, aspect)
    if not ranked:
        return ReviewPlan([], [], "Nenhum candidato para analisar.", settings.label, "")

    provider = provider or get_provider(settings)
    result, usage = provider.generate_plan(SYSTEM_PROMPT, parts)
    usage_ledger.record(usage)
    return plan_from_result(result, ranked, target_duration, settings.label, usage.text)


def build_map_from_index(
    index: dict,
    briefing: str,
    avoid: str,
    target_duration: float,
    settings: AISettings | None = None,
) -> tuple[dict, str]:
    """Novo vídeo da mesma live: escolhe os trechos pelo índice em texto (sem imagens, poucos milhares de tokens)."""
    from .prompt import INDEX_PROMPT
    settings = settings or load_ai_settings()
    problem = check_ai_ready(settings)
    if problem:
        raise RuntimeError(problem)
    usage_ledger.ensure_budget(settings.daily_limit_usd)
    entries = [{"start": s["start"], "end": s["end"], "descricao": s.get("descricao", "")}
               for s in index.get("segmentos", [])]
    parts: list[Part] = [TextPart("Índice da live:\n" + json.dumps(
        {"resumo": index.get("resumo", ""), "trechos": entries}, ensure_ascii=False, indent=1))]
    style = style_prompt()
    if style:
        parts.append(TextPart(style))
    parts.append(TextPart("Novo pedido do criador:\n" + json.dumps({
        "briefing": briefing.strip() or "Montar os melhores momentos da live.",
        "o_que_ignorar": avoid.strip() or "loading, menus, pausas",
        "duracao_alvo_segundos": round(target_duration),
    }, ensure_ascii=False, indent=1)))
    result, usage = get_provider(settings).generate_plan(INDEX_PROMPT, parts, MAP_SCHEMA, MAP_JSON_INSTRUCTION)
    usage_ledger.record(usage)
    return result, usage.text


def build_live_map(
    frames: list[tuple[float, Path]],
    sheets_dir: Path,
    briefing: str,
    avoid: str,
    target_duration: float,
    settings: AISettings | None = None,
) -> tuple[dict, str]:
    """Etapa 1: a IA olha a live inteira em miniaturas e aponta onde estão os trechos do pedido."""
    settings = settings or load_ai_settings()
    problem = check_ai_ready(settings)
    if problem:
        raise RuntimeError(problem)
    usage_ledger.ensure_budget(settings.daily_limit_usd)

    parts: list[Part] = []
    for description, sheet in build_timeline_sheets(frames, sheets_dir):
        parts += [TextPart(description), ImagePart(sheet)]
    parts.append(TextPart("Fim do mapa.", cache=True))
    style = style_prompt()
    if style:
        parts.append(TextPart(style))
    parts.append(TextPart("Pedido do criador:\n" + json.dumps({
        "briefing": briefing.strip() or "Montar os melhores momentos da live.",
        "o_que_ignorar": avoid.strip() or "loading, menus, pausas",
        "duracao_alvo_segundos": round(target_duration),
    }, ensure_ascii=False, indent=1)))

    result, usage = get_provider(settings).generate_plan(MAP_PROMPT, parts, MAP_SCHEMA, MAP_JSON_INSTRUCTION)
    usage_ledger.record(usage)
    return result, usage.text
