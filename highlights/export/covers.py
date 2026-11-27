"""Capas: foto em resolução cheia de uma cena escolhida + texto grande com contorno. Tudo local, sem IA."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

SIZES = {"16:9": (1280, 720), "9:16": (1080, 1920)}
FONTS = [
    str(Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Anton-Regular.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
YELLOW, WHITE, BLACK = (255, 225, 77), (255, 255, 255), (0, 0, 0)


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
        max_width, size = int(width * 0.9), int(height * (0.2 if aspect == "16:9" else 0.11))
        while True:
            font = _font(size)
            lines = _wrap(draw, text, font, max_width)
            if (len(lines) <= 2 and all(draw.textlength(line, font=font) <= max_width for line in lines)) or size < 24:
                break
            size = int(size * 0.9)
        line_height = int(size * 1.12)
        y = height - int(height * 0.06) - line_height * len(lines)
        stroke = max(3, size // 12)
        for number, line in enumerate(lines):
            x = (width - draw.textlength(line, font=font)) / 2
            # Sombra deslocada para o texto "saltar" da imagem; 1ª linha branca, a última amarela.
            draw.text((x + stroke, y + stroke * 1.5), line, font=font, fill=BLACK, stroke_width=stroke, stroke_fill=BLACK)
            color = YELLOW if number == len(lines) - 1 else WHITE
            draw.text((x, y), line, font=font, fill=color, stroke_width=stroke, stroke_fill=BLACK)
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


def sharpest_near(video: str | Path, seconds: float, items: list[dict], window: float = 1.5) -> float:
    """A IA aponta o segundo vendo fotos pequenas; aqui o PC olha em volta (±1,5 s, dentro do trecho)
    e fica com o quadro mais nítido e forte, para a capa não sair borrada. Sem IA."""
    import tempfile
    import numpy as np
    item = next((i for i in items if i["start"] <= seconds <= i["end"]), None)
    low = max(item["start"] if item else 0.0, seconds - window)
    high = min(item["end"] if item else seconds + window, seconds + window)
    if high - low < 0.5:
        return seconds
    with tempfile.TemporaryDirectory() as tmp:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        subprocess.run([ffmpeg, "-v", "error", "-ss", f"{low:.2f}", "-t", f"{high - low:.2f}", "-i", str(video),
                        "-vf", "fps=4,scale=320:-2", "-q:v", "4", f"{tmp}/q-%02d.jpg"], check=True)
        frames = sorted(Path(tmp).glob("q-*.jpg"))
        if not frames:
            return seconds
        data = [_frame_scores(path) for path in frames]
    rank = lambda values: np.argsort(np.argsort(values)) / max(1, len(values) - 1)
    sharp, color, contrast = (rank(np.array([d[i] for d in data])) for i in range(3))
    scores = [0.5 * sharp[i] + 0.25 * color[i] + 0.25 * contrast[i] - max(0.0, 50 - d[3]) / 25
              for i, d in enumerate(data)]
    return low + int(np.argmax(scores)) / 4


def make_covers(video: str | Path, ideas: list[dict], items: list[dict], folder: Path, aspect: str) -> list[dict]:
    """Gera até 3 capas. Sem ideias da IA, usa o meio dos primeiros trechos com o nome do capítulo."""
    if not ideas:
        ideas = [{"time": (i["start"] + i["end"]) / 2, "text": i.get("chapter", ""), "why": i.get("reason", "")}
                 for i in items[:3]]
    covers = []
    for number, idea in enumerate(ideas[:3], 1):
        seconds = sharpest_near(video, _scene_time(idea.get("time"), items), items)
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


# ---------------- Cenas candidatas: o PC acha as mais fortes, você (ou a IA) escolhe ----------------

def _frame_scores(path: Path) -> tuple[float, float, float, float, "np.ndarray"]:
    import numpy as np
    rgb = np.asarray(Image.open(path).convert("RGB"), dtype=float)
    gray = rgb.mean(axis=2)
    laplace = 4 * gray[1:-1, 1:-1] - gray[:-2, 1:-1] - gray[2:, 1:-1] - gray[1:-1, :-2] - gray[1:-1, 2:]
    rg, yb = rgb[..., 0] - rgb[..., 1], 0.5 * (rgb[..., 0] + rgb[..., 1]) - rgb[..., 2]
    colorful = np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean())
    small = np.asarray(Image.open(path).convert("L").resize((16, 9)), dtype=float)
    return laplace.var(), colorful, gray.std(), gray.mean(), small


def scene_candidates(video: str | Path, items: list[dict], folder: Path, count: int = 12) -> list[dict]:
    """As cenas mais chamativas dos trechos do vídeo: nítidas, coloridas, com contraste e sem repetir.
    Tudo medido no seu PC, sem IA."""
    import numpy as np
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("cena-*.jpg"):
        old.unlink()
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    frames: list[tuple[float, Path, int]] = []
    for number, item in enumerate(items):
        duration = max(1.0, item["end"] - item["start"])
        step = max(1.0, duration / 30)  # até 30 fotos por trecho
        subprocess.run([ffmpeg, "-v", "error", "-y", "-ss", f"{item['start']:.2f}", "-t", f"{duration:.2f}",
                        "-i", str(video), "-vf", f"fps=1/{step:.3f},scale=320:-2", "-q:v", "4",
                        str(folder / f"cena-{number:02d}-%03d.jpg")], check=True)
        for index, path in enumerate(sorted(folder.glob(f"cena-{number:02d}-*.jpg"))):
            frames.append((item["start"] + index * step, path, number))
    if not frames:
        return []

    data = [_frame_scores(path) for _, path, _ in frames]
    rank = lambda values: np.argsort(np.argsort(values)) / max(1, len(values) - 1)
    sharp, color, contrast = (rank(np.array([d[i] for d in data])) for i in range(3))
    scores = []
    for i, d in enumerate(data):
        brightness = d[3]
        penalty = max(0.0, 50 - brightness) / 25 + max(0.0, brightness - 215) / 25  # escuro ou estourado demais
        scores.append(0.4 * sharp[i] + 0.3 * color[i] + 0.3 * contrast[i] - penalty)

    # Reveza entre os trechos (a melhor de cada um, depois a 2ª melhor...), para não vir tudo da mesma luta.
    queues = [[int(i) for i in np.argsort(scores)[::-1] if frames[i][2] == number] for number in range(len(items))]
    chosen: list[int] = []
    while len(chosen) < count and any(queues):
        for queue in queues:
            while queue:
                i = queue.pop(0)
                time, thumb = frames[i][0], data[i][4]
                # Sem repetir: longe no tempo e visualmente diferente das já escolhidas.
                if not any(abs(time - frames[j][0]) < 4 or np.abs(thumb - data[j][4]).mean() < 10 for j in chosen):
                    chosen.append(i)
                    break
            if len(chosen) == count:
                break
    scenes = [{"time": frames[i][0], "path": str(frames[i][1])} for i in sorted(chosen, key=lambda j: frames[j][0])]
    (folder / "cenas.json").write_text(json.dumps(scenes, ensure_ascii=False, indent=1), encoding="utf-8")
    return scenes


def use_scene(folder: Path, number: int, video: str | Path, seconds: float) -> list[dict]:
    """Troca a foto de uma capa por outra cena, mantendo o texto. Sem IA."""
    data = json.loads((folder / "capas.json").read_text(encoding="utf-8"))
    cover = data["covers"][number - 1]
    frame = grab_frame(video, seconds, Path(cover["frame"]))
    render_cover(frame, cover["text"], Path(cover["path"]), data["aspect"])
    cover["time"] = seconds
    (folder / "capas.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data["covers"]
