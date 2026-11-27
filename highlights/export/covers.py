"""Capas: foto em resolução cheia de uma cena escolhida + texto grande com contorno. Tudo local, sem IA."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

SIZES = {"16:9": (1280, 720), "9:16": (1080, 1920)}
FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
YELLOW, BLACK = (255, 225, 77), (0, 0, 0)


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def grab_frame(video: str | Path, seconds: float, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", f"{max(0.0, seconds):.2f}", "-i", str(video),
                    "-frames:v", "1", "-q:v", "2", str(path)], check=True)
    return path


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        test = f"{lines[-1]} {word}" if lines else word
        if lines and draw.textlength(test, font=font) <= max_width:
            lines[-1] = test
        else:
            lines.append(word)
    return lines


def render_cover(frame: Path, text: str, output: Path, aspect: str = "16:9") -> Path:
    width, height = SIZES.get(aspect, SIZES["16:9"])
    image = ImageOps.fit(Image.open(frame).convert("RGB"), (width, height), Image.LANCZOS)
    image = ImageEnhance.Brightness(image).enhance(1.1)
    image = ImageEnhance.Color(ImageEnhance.Contrast(image).enhance(1.12)).enhance(1.25)

    text = " ".join(text.upper().split())
    if text:
        # Faixa escura embaixo para o texto ler bem em qualquer cena.
        shade = Image.new("L", (1, height))
        for y in range(height):
            shade.putpixel((0, y), int(200 * max(0.0, (y / height - 0.45) / 0.55)))
        image.paste(Image.new("RGB", (width, height), BLACK), (0, 0), shade.resize((width, height)))

        draw = ImageDraw.Draw(image)
        max_width, size = int(width * 0.9), int(height * (0.15 if aspect == "16:9" else 0.085))
        while True:
            font = _font(size)
            lines = _wrap(draw, text, font, max_width)
            if (len(lines) <= 2 and all(draw.textlength(line, font=font) <= max_width for line in lines)) or size < 24:
                break
            size = int(size * 0.9)
        line_height = int(size * 1.08)
        y = height - int(height * 0.06) - line_height * len(lines)
        for line in lines:
            x = (width - draw.textlength(line, font=font)) / 2
            draw.text((x, y), line, font=font, fill=YELLOW, stroke_width=max(3, size // 11), stroke_fill=BLACK)
            y += line_height

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "JPEG", quality=92)
    return output


def _scene_time(seconds, items: list[dict]) -> float:
    """Usa o segundo da IA se ele cair num trecho do vídeo; senão, o meio do primeiro trecho."""
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        seconds = -1.0
    if any(item["start"] <= seconds <= item["end"] for item in items):
        return seconds
    return (items[0]["start"] + items[0]["end"]) / 2 if items else 0.0


def make_covers(video: str | Path, ideas: list[dict], items: list[dict], folder: Path, aspect: str) -> list[dict]:
    """Gera até 3 capas. Sem ideias da IA, usa o meio dos primeiros trechos com o nome do capítulo."""
    if not ideas:
        ideas = [{"time": (i["start"] + i["end"]) / 2, "text": i.get("chapter", ""), "why": i.get("reason", "")}
                 for i in items[:3]]
    covers = []
    for number, idea in enumerate(ideas[:3], 1):
        seconds = _scene_time(idea.get("time"), items)
        frame = grab_frame(video, seconds, folder / f"cena-{number}.jpg")
        path = render_cover(frame, str(idea.get("text", "")), folder / f"capa-{number}.jpg", aspect)
        covers.append({"path": str(path), "frame": str(frame), "time": seconds,
                       "text": str(idea.get("text", "")), "why": str(idea.get("why", ""))})
    (folder / "capas.json").write_text(json.dumps({"aspect": aspect, "covers": covers}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    return covers


def retext_cover(folder: Path, number: int, text: str) -> list[dict]:
    """Troca o texto de uma capa já gerada (não chama a IA)."""
    data = json.loads((folder / "capas.json").read_text(encoding="utf-8"))
    cover = data["covers"][number - 1]
    render_cover(Path(cover["frame"]), text, Path(cover["path"]), data["aspect"])
    cover["text"] = text
    (folder / "capas.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data["covers"]
