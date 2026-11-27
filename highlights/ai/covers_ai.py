"""A IA escolhe as 3 capas olhando UMA imagem com as cenas mais fortes, numeradas.

Roda sozinha ao gerar o vídeo. Chamada pequena: uns 2 mil tokens pela API.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from ..export.covers import COLORS, FONTS, _font
from . import usage as usage_ledger
from .config import load_ai_settings
from .providers import ImagePart, TextPart, get_provider

COVER_PROMPT = f"""\
Você é designer de capas (thumbnails) de vídeos de jogos no YouTube, das que fazem as pessoas clicarem.
A imagem tem cenas numeradas de um vídeo. Monte as 3 melhores capas:
- Cena: assunto claro e grande (rosto, personagem ou boss em destaque), momento de impacto, cores fortes.
  Evite cena confusa, escura, borrada, com menu ou interface tomando a tela. Cada capa com uma cena diferente.
- "text": 2 a 4 palavras em português do Brasil, que despertem curiosidade ou emoção sem mentir
  e sem repetir o título. Capa boa tem pouco texto.
- "side": onde vai o texto, "esquerda", "direita" ou "baixo", sempre do lado oposto ao assunto,
  para não cobrir o rosto ou o boss.
- "focus": onde está o assunto na largura da cena, de 0 (esquerda) a 1 (direita).
- "color": cor de destaque do texto que mais contraste com a cena: {", ".join(COLORS)}.
- "font": {", ".join(FONTS)} (anton = impacto/sério, luckiest = divertida, bangers = quadrinho/ação).
- "why": uma frase curta dizendo por que essa capa chama o clique.
"""

COVER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "covers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "text": {"type": "string"},
                    "side": {"type": "string", "enum": ["esquerda", "direita", "baixo"]},
                    "focus": {"type": "number"},
                    "color": {"type": "string", "enum": list(COLORS)},
                    "font": {"type": "string", "enum": list(FONTS)},
                    "why": {"type": "string"},
                },
                "required": ["number", "text", "side", "focus", "color", "font", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["covers"],
    "additionalProperties": False,
}

COVER_JSON = ('Responda só com JSON: {"covers": [{"number": 1, "text": "...", "side": "direita", "focus": 0.3, '
              '"color": "amarelo", "font": "anton", "why": "..."}]}')


def scenes_sheet(scenes: list[dict], output: Path) -> Path:
    """Folha única com as cenas numeradas (4 por linha), para a IA ver tudo numa imagem só."""
    columns, width, height = 4, 320, 180
    rows = (len(scenes) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * width, rows * height), (0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    font = _font(44)
    for number, scene in enumerate(scenes, 1):
        x, y = (number - 1) % columns * width, (number - 1) // columns * height
        sheet.paste(ImageOps.fit(Image.open(scene["path"]).convert("RGB"), (width, height)), (x, y))
        draw.text((x + 10, y + 6), str(number), font=font, fill=(255, 214, 0), stroke_width=4, stroke_fill=(0, 0, 0))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "JPEG", quality=80)
    return output


def pick_covers(scenes: list[dict], folder: Path, context: str) -> tuple[list[dict], str]:
    """Devolve as ideias de capa (com o segundo da cena) e o texto de uso de tokens."""
    settings = load_ai_settings()
    usage_ledger.ensure_budget(settings.daily_limit_usd)
    sheet = scenes_sheet(scenes, folder / "folha.jpg")
    parts = [TextPart(f"Sobre o vídeo: {context or 'gameplay'}\nCenas numeradas de 1 a {len(scenes)}:"),
             ImagePart(sheet)]
    result, usage = get_provider(settings).generate_plan(COVER_PROMPT, parts, COVER_SCHEMA, COVER_JSON)
    usage_ledger.record(usage)
    ideas, used = [], set()
    for raw in result.get("covers", []):
        try:
            number = int(raw["number"])
            scene = scenes[number - 1]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        if number in used:
            continue
        used.add(number)
        ideas.append({**{k: raw.get(k) for k in ("text", "side", "focus", "color", "font", "why")},
                      "time": scene["time"]})
        if len(ideas) == 3:
            break
    return ideas, usage.text
