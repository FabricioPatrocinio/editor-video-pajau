"""A IA escolhe as 3 melhores capas olhando UMA imagem com as cenas numeradas.

É uma chamada pequena e opcional (botão na tela): uns 1,5 mil tokens no total.
"""
from __future__ import annotations

from pathlib import Path

from . import usage as usage_ledger
from .config import load_ai_settings
from .providers import ImagePart, TextPart, get_provider

COVER_PROMPT = """\
Você é especialista em capas (thumbnails) de vídeos de jogos para YouTube e Shorts.
A imagem tem cenas numeradas de um vídeo. Escolha as 3 que fariam as pessoas clicarem:
ação clara e legível mesmo pequena, personagem ou boss bem visível, momento de impacto, cores fortes.
Evite cena confusa, escura, borrada, menu ou interface tomando a tela.
Para cada uma, escreva o texto que vai em letras grandes sobre a foto: 2 a 5 palavras, em português do
Brasil, que despertem curiosidade sem mentir e sem repetir o título. Em "why", uma frase curta.
"""

COVER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "covers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"number": {"type": "integer"}, "text": {"type": "string"}, "why": {"type": "string"}},
                "required": ["number", "text", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["covers"],
    "additionalProperties": False,
}

COVER_JSON = 'Responda só com JSON: {"covers": [{"number": 1, "text": "...", "why": "..."}]}'


def pick_covers(sheet: Path, scenes: list[dict], context: str) -> tuple[list[dict], str]:
    """Devolve as ideias de capa (com o segundo da cena) e o texto de uso de tokens."""
    settings = load_ai_settings()
    usage_ledger.ensure_budget(settings.daily_limit_usd)
    parts = [TextPart(f"Sobre o vídeo: {context or 'gameplay'}\nCenas numeradas de 1 a {len(scenes)}:"),
             ImagePart(sheet)]
    result, usage = get_provider(settings).generate_plan(COVER_PROMPT, parts, COVER_SCHEMA, COVER_JSON)
    usage_ledger.record(usage)
    ideas = []
    for raw in result.get("covers", [])[:3]:
        try:
            scene = scenes[int(raw["number"]) - 1]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        ideas.append({"time": scene["time"], "text": str(raw.get("text", ""))[:60], "why": str(raw.get("why", ""))})
    return ideas, usage.text
