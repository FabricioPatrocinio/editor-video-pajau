"""Capas no estilo das miniaturas de jogos: zoom na ação, cores vivas, vinheta e texto enorme inclinado.

Tudo é desenhado no seu PC. A IA só diz qual cena usar, o texto, o lado do texto, a cor e a fonte.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

SIZES = {"16:9": (1280, 720), "9:16": (1080, 1920)}
FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
FONTS = {"anton": "Anton-Regular.ttf", "luckiest": "LuckiestGuy-Regular.ttf", "bangers": "Bangers-Regular.ttf"}
FONT_NAMES = {"anton": "Impacto", "luckiest": "Divertida", "bangers": "Quadrinho"}
COLORS = {"amarelo": (255, 214, 0), "laranja": (255, 122, 26), "ciano": (0, 229, 255), "vermelho": (255, 59, 48),
          "verde": (166, 255, 0), "rosa": (255, 64, 160)}
SIDES = ("esquerda", "direita", "baixo")
WHITE, BLACK = (255, 255, 255), (0, 0, 0)
STYLE_DEFAULTS = {"font": "anton", "color": "amarelo", "side": "direita", "focus": 0.5}


def _font(size: int, name: str = "anton") -> ImageFont.FreeTypeFont:
    path = FONTS_DIR / FONTS.get(name, FONTS["anton"])
    return ImageFont.truetype(str(path), size) if path.exists() else ImageFont.load_default(size)


def grab_frame(video: str | Path, seconds: float, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", f"{max(0.0, seconds):.2f}", "-i", str(video),
                    "-frames:v", "1", "-q:v", "2", str(path)], check=True)
    return path


def _lines(text: str) -> list[str]:
    """Até 2 linhas equilibradas: capa boa tem pouco texto e bem grande."""
    words = text.upper().split()
    if len(words) <= 2:
        return [" ".join(words)] if len(" ".join(words)) <= 12 or len(words) == 1 else words
    best = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return [" ".join(words[:best]), " ".join(words[best:])]


def _grade(image: Image.Image) -> Image.Image:
    image = ImageEnhance.Contrast(image).enhance(1.22)
    image = ImageEnhance.Color(image).enhance(1.4)
    image = ImageEnhance.Brightness(image).enhance(1.1)
    return image.filter(ImageFilter.UnsharpMask(radius=2, percent=90, threshold=2))


def _shade(width: int, height: int, side: str) -> Image.Image:
    """Máscara escura: vinheta nas bordas + degradê do lado onde vai o texto."""
    y, x = np.ogrid[:height, :width]
    distance = np.sqrt(((x - width / 2) / (width / 2)) ** 2 + ((y - height / 2) / (height / 2)) ** 2)
    mask = np.clip((distance - 0.55) / 0.75, 0, 1) * 160
    if side == "esquerda":
        mask = np.maximum(mask, np.clip(1 - x / (width * 0.62), 0, 1) * 200)
    elif side == "direita":
        mask = np.maximum(mask, np.clip((x - width * 0.38) / (width * 0.62), 0, 1) * 200)
    else:
        mask = np.maximum(mask, np.clip((y - height * 0.45) / (height * 0.55), 0, 1) * 210)
    return Image.fromarray(np.broadcast_to(mask, (height, width)).astype("uint8"))


def render_cover(frame: Path, text: str, output: Path, aspect: str = "16:9", font: str = "anton",
                 color: str = "amarelo", side: str = "direita", focus: float = 0.5) -> Path:
    width, height = SIZES.get(aspect, SIZES["16:9"])
    side = side if side in SIDES else "direita"
    if aspect == "9:16":
        side = "baixo"
    # Zoom leve na ação: o assunto fica do lado oposto ao texto.
    base = ImageOps.fit(Image.open(frame).convert("RGB"), (width, height), Image.LANCZOS,
                        centering=(max(0.0, min(1.0, focus)), 0.5))
    zoom = 1.15
    crop_w, crop_h = int(width / zoom), int(height / zoom)
    x = int(max(0, min(width - crop_w, focus * width - crop_w / 2)))
    image = _grade(base.crop((x, (height - crop_h) // 2, x + crop_w, (height + crop_h) // 2)).resize((width, height),
                                                                                                    Image.LANCZOS))
    image = Image.composite(Image.new("RGB", (width, height), BLACK), image, _shade(width, height, side))

    lines = _lines(" ".join(text.split()))
    if lines and lines[0]:
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        box_w = width * (0.9 if side == "baixo" else 0.5)
        box_h = height * (0.32 if aspect == "9:16" else 0.62)
        size = int(height * (0.1 if aspect == "9:16" else 0.24))
        while size > 40:
            fnt = _font(size, font)
            if max(draw.textlength(l, font=fnt) for l in lines) <= box_w and size * 1.05 * len(lines) <= box_h:
                break
            size = int(size * 0.94)
        fnt = _font(size, font)
        line_h = int(size * 1.04)
        top = (height - line_h * len(lines)) / 2 if side != "baixo" else height * (0.86 if aspect == "16:9" else 0.8) - line_h * len(lines)
        stroke = max(4, size // 9)
        accent = COLORS.get(color, COLORS["amarelo"])
        for number, line in enumerate(lines):
            line_w = draw.textlength(line, font=fnt)
            left = {"esquerda": width * 0.05, "direita": width * 0.95 - line_w}.get(side, (width - line_w) / 2)
            y = top + number * line_h
            fill = accent if number == len(lines) - 1 else WHITE
            # Sombra deslocada para o texto "saltar" da imagem.
            draw.text((left + stroke * 0.8, y + stroke * 1.3), line, font=fnt, fill=BLACK, stroke_width=stroke,
                      stroke_fill=BLACK)
            draw.text((left, y), line, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=BLACK)
        tilt = {"esquerda": 3, "direita": -3}.get(side, 2)
        center = {"esquerda": (width * 0.28, height / 2), "direita": (width * 0.72, height / 2)}.get(side, None)
        layer = layer.rotate(tilt, resample=Image.BICUBIC, center=center)
        image.paste(layer, (0, 0), layer)

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


def _style(idea: dict) -> dict:
    style = {**STYLE_DEFAULTS, **{k: idea[k] for k in STYLE_DEFAULTS if idea.get(k) is not None}}
    style["font"] = style["font"] if style["font"] in FONTS else "anton"
    style["color"] = style["color"] if style["color"] in COLORS else "amarelo"
    style["side"] = style["side"] if style["side"] in SIDES else "direita"
    try:
        style["focus"] = max(0.0, min(1.0, float(style["focus"])))
    except (TypeError, ValueError):
        style["focus"] = 0.5
    return style


def make_covers(video: str | Path, ideas: list[dict], items: list[dict], folder: Path, aspect: str) -> list[dict]:
    """Gera até 3 capas. Sem ideias da IA, usa o meio dos primeiros trechos com o nome do capítulo."""
    if not ideas:
        ideas = [{"time": (i["start"] + i["end"]) / 2, "text": i.get("chapter", ""), "why": i.get("reason", "")}
                 for i in items[:3]]
    covers = []
    for number, idea in enumerate(ideas[:3], 1):
        seconds = sharpest_near(video, _scene_time(idea.get("time"), items), items)
        frame = grab_frame(video, seconds, folder / f"cena-{number}.jpg")
        style = _style(idea)
        path = render_cover(frame, str(idea.get("text", "")), folder / f"capa-{number}.jpg", aspect, **style)
        covers.append({"path": str(path), "frame": str(frame), "time": seconds, "text": str(idea.get("text", "")),
                       "why": str(idea.get("why", "")), **style})
    _save(folder, {"aspect": aspect, "covers": covers})
    return covers


def _save(folder: Path, data: dict) -> None:
    (folder / "capas.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_covers(folder: Path) -> dict:
    try:
        return json.loads((folder / "capas.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"aspect": "16:9", "covers": []}


def restyle_cover(folder: Path, number: int, **changes) -> list[dict]:
    """Muda texto, fonte, cor ou lado de uma capa já feita. Sem IA, na hora."""
    data = load_covers(folder)
    cover = data["covers"][number - 1]
    cover.update({k: v for k, v in changes.items() if v is not None})
    style = _style(cover)
    cover.update(style)
    render_cover(Path(cover["frame"]), cover["text"], Path(cover["path"]), data["aspect"], **style)
    _save(folder, data)
    return data["covers"]


def retext_cover(folder: Path, number: int, text: str) -> list[dict]:
    return restyle_cover(folder, number, text=text)


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
    grab_frame(video, seconds, Path(cover["frame"]))
    cover["time"] = seconds
    _save(folder, data)
    return restyle_cover(folder, number)
