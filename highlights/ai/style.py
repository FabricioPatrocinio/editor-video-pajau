"""Seu estilo salvo ("Meu estilo"), que vai junto em toda análise.

Fica em data/estilo.json (fora do Git). Vai em toda análise, então o briefing do dia pode ser curto.
"""
from __future__ import annotations

import json
from pathlib import Path

STYLE_FILE = Path("data") / "estilo.json"

VIDEO_TYPES = ["Melhores momentos", "Só vitórias contra bosses", "Engraçados", "Resumo da live", "Short vertical"]
MOMENT_TYPES = ["Vitória em boss", "Morte engraçada", "Reação forte", "Jogada difícil", "Papo com o chat", "Raiva / rage"]
ORDERS = ["Ordem da live", "Mais forte primeiro", "IA decide"]


def load_style() -> dict:
    try:
        data = json.loads(STYLE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data.setdefault("estilo", "")
    return data


def _save(data: dict) -> None:
    STYLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STYLE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_style_text(text: str) -> None:
    data = load_style()
    data["estilo"] = text.strip()
    _save(data)


def style_prompt() -> str:
    data = load_style()
    lines = []
    if data["estilo"]:
        lines.append(f"Estilo fixo do canal: {data['estilo']}")
    return "\n".join(lines)


def compose_briefing(game: str, video_type: str, moments: list[str], order: str, extra: str) -> str:
    parts = []
    if game.strip():
        parts.append(f"Jogo/conteúdo: {game.strip()}.")
    if video_type:
        parts.append(f"Tipo de vídeo: {video_type}.")
    if moments:
        parts.append("Priorizar: " + ", ".join(moments) + ".")
    if order:
        parts.append(f"Ordem: {order}.")
    if extra.strip():
        parts.append(extra.strip())
    return " ".join(parts)
