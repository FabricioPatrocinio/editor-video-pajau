"""Short vertical: layout, legenda na tela e prévia. Tudo local, sem IA.

A IA só manda o "focus" de cada trecho (onde está a ação), junto com o plano que ela já faz.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

SETTINGS_FILE = Path("data") / "shorts.json"
FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
LAYOUTS = {
    "Jogo em destaque": "jogo",
    "Câmera em cima, jogo embaixo": "camera",
}
CORNERS = ["inferior direito", "inferior esquerdo", "superior direito", "superior esquerdo"]
# zoom: 0 = vídeo inteiro (faixa no meio), 100 = tela cheia. follow = o recorte acompanha a ação.
DEFAULTS = {"layout": "jogo", "zoom": 35, "follow": True, "corner": "inferior direito", "camera_size": 25,
            "subtitles": True, "aspect": "16:9"}  # aspect: o último formato escolhido na tela

W, H = 1080, 1920
CAMERA_HEIGHT = 640  # parte de cima no layout "câmera"; o jogo fica com os 1280 de baixo
# A parte de baixo e a lateral direita ficam cobertas pelos botões do Shorts/TikTok/Reels.
SUBTITLE_BOTTOM_MARGIN = 560
SUBTITLE_SIDE_MARGIN = 140


def _clean(data: dict) -> dict:
    data = dict(data)
    # Layouts antigos viram o "jogo" com o zoom equivalente.
    if data.get("layout") == "cheio":
        data.update(layout="jogo", zoom=100)
    elif data.get("layout") == "inteiro":
        data.update(layout="jogo", zoom=0)
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def load_settings() -> dict:
    try:
        return _clean(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(settings: dict) -> dict:
    settings = _clean(settings)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings


def video_size(video: str | Path) -> tuple[int, int]:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout
    width, height = out.strip().split(",")[:2]
    return int(width), int(height)


def _even(value: float) -> int:
    return max(2, int(value) // 2 * 2)


def track_action(video: str | Path, start: float, end: float, prior: float = 0.5, fps: int = 4) -> list[tuple[float, float]]:
    """Onde está o movimento na largura da tela, segundo a segundo (0 = esquerda, 1 = direita).

    Compara quadros pequenos (160 px, cinza) e acha o centro do que mudou. Roda no PC, sem IA.
    O resultado é suavizado para a "câmera" andar devagar, sem tremer.
    """
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    raw = subprocess.run([ffmpeg, "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-t", f"{max(0.5, end - start):.3f}",
                          "-i", str(video), "-vf", f"fps={fps},scale=160:90,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8)
    if frames.size < 160 * 90 * 2:
        return [(0.0, prior)]
    frames = frames[: frames.size // (160 * 90) * 160 * 90].reshape(-1, 90, 160).astype(np.int16)
    columns = np.abs(np.diff(frames, axis=0)).sum(axis=1).astype(float)  # movimento por coluna
    positions = np.arange(160) / 159
    centers, last = [], prior
    for energy in columns:
        energy = np.where(energy > energy.mean(), energy - energy.mean(), 0)  # só o que se destaca
        if energy.sum() > 300:
            last = float((energy * positions).sum() / energy.sum())
        centers.append(0.7 * last + 0.3 * prior)  # a sugestão da IA segura o recorte quando o movimento é confuso
    window = fps * 2
    smooth = np.convolve(np.pad(centers, window // 2, mode="edge"), np.ones(window) / window, mode="valid")
    points = [(float(t), float(smooth[min(len(smooth) - 1, int(t * fps))])) for t in np.arange(0, len(smooth) / fps, 1.0)]
    # Limita a velocidade: no máximo 15% da largura por segundo.
    for i in range(1, len(points)):
        t, value = points[i]
        previous = points[i - 1][1]
        points[i] = (t, previous + max(-0.15, min(0.15, value - previous)))
    return points


def _crop_x(width: int, crop_w: int, focus: float, track: list[tuple[float, float]] | None) -> str:
    """Posição x do recorte: fixa no foco, ou uma expressão que anda junto com a ação."""
    to_x = lambda center: int(max(0, min(width - crop_w, center * width - crop_w / 2)))
    if not track or len(track) < 2 or max(c for _, c in track) - min(c for _, c in track) < 0.03:
        return str(to_x(track[0][1] if track else focus))
    xs = [(t, to_x(c)) for t, c in track]
    expression = str(xs[-1][1])
    for (t0, x0), (t1, x1) in reversed(list(zip(xs, xs[1:]))):
        expression = f"if(lt(t,{t1:.2f}),{x0}+({x1 - x0})*(t-{t0:.2f})/{t1 - t0:.2f},{expression})"
    return f"'{expression}'"


def _game_crop(width: int, height: int, aspect: float, focus: float, track=None) -> str:
    """Recorte da altura toda no formato pedido, centrado na ação."""
    crop_w = min(width, _even(height * aspect))
    return f"crop={crop_w}:{height}:{_crop_x(width, crop_w, focus, track)}:0"


def camera_rect(width: int, height: int, corner: str, size_pct: float) -> tuple[int, int, int, int]:
    """Onde a câmera está na live: canto + largura em % (câmeras costumam ser 16:9)."""
    cam_w = _even(width * max(10, min(60, size_pct)) / 100)
    cam_h = min(height, _even(cam_w * 9 / 16))
    x = width - cam_w if "direito" in corner else 0
    y = height - cam_h if "inferior" in corner else 0
    return x, y, cam_w, cam_h


def game_box(width: int, height: int, zoom: float) -> tuple[float, int]:
    """Formato do recorte do jogo e altura da faixa no Short, a partir do zoom (0 a 100)."""
    source = width / height
    aspect = source - max(0.0, min(1.0, zoom / 100)) * (source - W / H)
    return aspect, min(H, _even(W / aspect))


def vertical_graph(width: int, height: int, settings: dict, focus: float = 0.5, track=None) -> str:
    """Filtro do FFmpeg que sai em [v], 1080x1920, a partir de [0:v]."""
    settings = _clean(settings)
    if settings["layout"] == "camera":
        x, y, cam_w, cam_h = camera_rect(width, height, settings["corner"], float(settings["camera_size"]))
        # Recorta o centro da câmera no formato da faixa de cima, sem distorcer.
        target = W / CAMERA_HEIGHT
        if cam_w / cam_h > target:
            new_w = _even(cam_h * target)
            x, cam_w = x + (cam_w - new_w) // 2, new_w
        else:
            new_h = _even(cam_w / target)
            y, cam_h = y + (cam_h - new_h) // 2, new_h
        game = _game_crop(width, height, W / (H - CAMERA_HEIGHT), focus, track)
        return (f"[0:v]split=2[c][g];[c]crop={cam_w}:{cam_h}:{x}:{y},scale={W}:{CAMERA_HEIGHT},setsar=1[top];"
                f"[g]{game},scale={W}:{H - CAMERA_HEIGHT},setsar=1[bot];[top][bot]vstack[v]")

    aspect, box_h = game_box(width, height, float(settings["zoom"]))
    game = f"{_game_crop(width, height, aspect, focus, track)},scale={W}:{box_h},setsar=1"
    if box_h >= H:
        return f"[0:v]{game}[v]"
    # Fundo: o próprio vídeo, desfocado e mais escuro (desfocar pequeno e ampliar é bem mais rápido).
    return (f"[0:v]split=2[a][b];[b]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
            f"boxblur=8:4,scale={W}:{H},eq=brightness=-0.12,setsar=1[bg];[a]{game}[fg];"
            f"[bg][fg]overlay=0:(H-h)/2[v]")


def _ass_time(seconds: float) -> str:
    centis = int(round(max(0.0, seconds) * 100))
    hours, rest = divmod(centis, 360000)
    minutes, rest = divmod(rest, 6000)
    return f"{hours}:{minutes:02d}:{rest // 100:02d}.{rest % 100:02d}"


def _chunks(words: list[tuple[float, float, str]], max_words: int = 3, max_chars: int = 16, gap: float = 0.6):
    """Agrupa as palavras em blocos curtos, que dão para ler de relance no celular."""
    chunk: list[tuple[float, float, str]] = []
    for word in words:
        too_long = len(" ".join(w[2] for w in chunk + [word])) > max_chars
        sentence_ended = bool(chunk) and chunk[-1][2][-1:] in ".?!,;:"
        if chunk and (len(chunk) >= max_words or too_long or sentence_ended or word[0] - chunk[-1][1] > gap):
            yield chunk
            chunk = []
        chunk.append(word)
    if chunk:
        yield chunk


CAPTION_FONT = "Archivo Black"
YELLOW_ASS = "&H4DE1FF&"  # amarelo em BGR, o formato do .ass


def caption_top(width: int, height: int, settings: dict) -> int | None:
    """Se sobra faixa escura embaixo do jogo, a legenda vai nela (mais legível). Senão, posição padrão."""
    settings = _clean(settings)
    if settings["layout"] != "jogo":
        return None
    _, box_h = game_box(width, height, float(settings["zoom"]))
    top = (H + box_h) // 2 + 30
    # A partir de ~1520 px os botões e o título do app cobrem a tela; uma linha de legenda tem ~110 px.
    return top if top <= 1400 else None


def subtitles_ass(words: list[tuple[float, float, str]], path: Path, top: int | None = None) -> Path:
    """Legenda .ass no estilo dos Shorts: blocos curtos que entram com um "pop", e a palavra
    falada fica amarela e maior. Usa a fonte Archivo Black que vem com o projeto."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pajau,{CAPTION_FONT},88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,1,0,1,8,4,{2 if top is None else 8},{SUBTITLE_SIDE_MARGIN},{SUBTITLE_SIDE_MARGIN},{SUBTITLE_BOTTOM_MARGIN if top is None else top},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for chunk in _chunks(words):
        chunk_end = max(chunk[-1][1], chunk[0][0] + 0.4)
        for index, (word_start, _, _) in enumerate(chunk):
            start = chunk[0][0] if index == 0 else word_start
            end = chunk[index + 1][0] if index + 1 < len(chunk) else chunk_end
            if end <= start:
                continue
            text = " ".join(
                f"{{\\c{YELLOW_ASS}\\fscx112\\fscy112}}{word.upper()}{{\\r}}" if i == index else word.upper()
                for i, (_, _, word) in enumerate(chunk)
            )
            pop = "{\\fscx80\\fscy80\\t(0,90,\\fscx100\\fscy100)}" if index == 0 else ""
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Pajau,,0,0,0,,{pop}{text}")
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def copy_fonts(folder: Path) -> None:
    """Põe as fontes do projeto ao lado da legenda (o FFmpeg as procura pela pasta)."""
    folder.mkdir(parents=True, exist_ok=True)
    for font in FONTS_DIR.glob("*.ttf"):
        target = folder / font.name
        if not target.exists():
            shutil.copy(font, target)


def preview_frame(video: str | Path, seconds: float, settings: dict, output: Path, focus: float = 0.5) -> Path:
    """Uma foto de como o Short vai ficar, para conferir o layout antes de gerar."""
    width, height = video_size(video)
    settings = _clean(settings)
    track = None
    if settings["follow"]:
        # Mede o movimento nos 3 segundos antes da foto, como no vídeo de verdade.
        points = track_action(video, max(0.0, seconds - 3), seconds, focus)
        track = [(0.0, points[-1][1])]
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", f"{max(0.0, seconds):.2f}", "-i", str(video),
                    "-filter_complex", vertical_graph(width, height, settings, focus, track), "-map", "[v]",
                    "-frames:v", "1", "-q:v", "3", str(output)], check=True)
    return output
