from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from . import usage as usage_ledger
from .config import AISettings, check_ai_ready, load_ai_settings
from .prompt import SYSTEM_PROMPT
from .providers import AIProvider, ImagePart, Part, TextPart, get_provider
from .style import style_prompt
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


@dataclass
class ReviewPlan:
    items: list[PlanItem]
    rejected: list[dict]
    summary: str
    provider: str
    usage: str


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
            }
            for candidate in sorted(candidates, key=lambda item: item.start)
        ],
    }
    parts: list[Part] = [TextPart(json.dumps(fixed, ensure_ascii=False, indent=1))]

    for candidate in candidates[:max_image_candidates]:
        images = [Path(path) for path in candidate.previews[:3] if Path(path).exists()]
        if not images:
            continue
        parts.append(TextPart(f"Imagens de {candidate.id} (início, meio e fim de {_clock(candidate.start)}):"))
        parts.extend(ImagePart(path) for path in images)
    parts.append(TextPart("Fim dos candidatos.", cache=True))

    request = {
        "briefing": briefing.strip() or "Montar os melhores momentos da live.",
        "o_que_ignorar": avoid.strip() or "Nada além de loading, menus, pausas e silêncio.",
        "duracao_alvo_segundos": round(target_duration),
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
    used: set[str] = set()
    total = 0.0
    # Pequena folga: a IA pode arredondar e não queremos descartar o último trecho por 2 segundos.
    limit = target_duration * 1.05
    for raw in raw_items:
        candidate_id = str(raw.get("id", ""))
        candidate = by_id.get(candidate_id)
        if not candidate or candidate_id in used:
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
        plan.append(PlanItem(
            id=candidate_id,
            start=start,
            end=end,
            accepted=True,
            reason=str(raw.get("reason", raw.get("motivo", "Selecionado pela IA.")))[:400],
            confidence=max(0.0, min(1.0, confidence)),
            kind=str(raw.get("kind", raw.get("tipo", "momento_interessante")))[:80],
            transition=raw.get("transition") if raw.get("transition") in TRANSITIONS else "corte",
        ))
        used.add(candidate_id)
        total += end - start
    return plan


def build_review_plan(
    candidates: Iterable[Candidate],
    briefing: str,
    target_duration: float,
    avoid: str = "",
    settings: AISettings | None = None,
    provider: AIProvider | None = None,
) -> ReviewPlan:
    settings = settings or load_ai_settings()
    problem = check_ai_ready(settings)
    if problem and provider is None:
        raise RuntimeError(problem)
    usage_ledger.ensure_budget(settings.daily_limit_usd)

    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)[: settings.max_candidates]
    if not ranked:
        return ReviewPlan([], [], "Nenhum candidato para analisar.", settings.label, "")

    parts = _request_parts(ranked, briefing, avoid, target_duration, settings.max_image_candidates)
    provider = provider or get_provider(settings)
    result, usage = provider.generate_plan(SYSTEM_PROMPT, parts)
    usage_ledger.record(usage)

    return ReviewPlan(
        items=_validate(result, ranked, target_duration),
        rejected=[dict(item) for item in result.get("rejected", []) if isinstance(item, dict)],
        summary=str(result.get("summary", "")),
        provider=settings.label,
        usage=usage.text,
    )
