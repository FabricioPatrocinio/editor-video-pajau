"""Short vertical: layout, legenda na tela e prévia. Tudo local, sem IA.

A IA só manda o "focus" de cada trecho (onde está a ação), junto com o plano que ela já faz.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

SETTINGS_FILE = Path("data") / "shorts.json"
LAYOUTS = {
    "Tela cheia, focando a ação": "cheio",
    "Câmera em cima, jogo embaixo": "camera",
    "Vídeo inteiro com fundo desfocado": "inteiro",
}
CORNERS = ["inferior direito", "inferior esquerdo", "superior direito", "superior esquerdo"]
DEFAULTS = {"layout": "cheio", "corner": "inferior direito", "camera_size": 25, "subtitles": True}

W, H = 1080, 1920
CAMERA_HEIGHT = 640  # parte de cima no layout "câmera"; o jogo fica com os 1280 de baixo
# A parte de baixo e a lateral direita ficam cobertas pelos botões do Shorts/TikTok/Reels.
SUBTITLE_BOTTOM_MARGIN = 560
SUBTITLE_SIDE_MARGIN = 140


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def save_settings(settings: dict) -> dict:
    settings = {**DEFAULTS, **{k: v for k, v in settings.items() if k in DEFAULTS}}
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


def _crop_around(width: int, height: int, aspect: float, focus: float) -> str:
    """Recorte vertical da altura toda, centrado no foco da ação, sem sair da imagem."""
    crop_w = min(width, _even(height * aspect))
    x = int(max(0, min(width - crop_w, focus * width - crop_w / 2)))
    return f"crop={crop_w}:{height}:{x}:0"


def camera_rect(width: int, height: int, corner: str, size_pct: float) -> tuple[int, int, int, int]:
    """Onde a câmera está na live: canto + largura em % (câmeras costumam ser 16:9)."""
    cam_w = _even(width * max(10, min(60, size_pct)) / 100)
    cam_h = min(height, _even(cam_w * 9 / 16))
    x = width - cam_w if "direito" in corner else 0
    y = height - cam_h if "inferior" in corner else 0
    return x, y, cam_w, cam_h


def vertical_graph(width: int, height: int, settings: dict, focus: float = 0.5) -> str:
    """Filtro do FFmpeg que sai em [v], 1080x1920, a partir de [0:v]."""
    layout = settings.get("layout", "cheio")
    if layout == "inteiro":
        return ("[0:v]split=2[in][bg];[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                "boxblur=20:10[blur];[in]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
                "[blur][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")
    if layout == "camera":
        x, y, cam_w, cam_h = camera_rect(width, height, settings.get("corner", "inferior direito"),
                                         float(settings.get("camera_size", 25)))
        # Recorta o centro da câmera no formato da faixa de cima, sem distorcer.
        target = W / CAMERA_HEIGHT
        if cam_w / cam_h > target:
            new_w = _even(cam_h * target)
            x, cam_w = x + (cam_w - new_w) // 2, new_w
        else:
            new_h = _even(cam_w / target)
            y, cam_h = y + (cam_h - new_h) // 2, new_h
        game = _crop_around(width, height, W / (H - CAMERA_HEIGHT), focus)
        return (f"[0:v]split=2[c][g];[c]crop={cam_w}:{cam_h}:{x}:{y},scale={W}:{CAMERA_HEIGHT},setsar=1[top];"
                f"[g]{game},scale={W}:{H - CAMERA_HEIGHT},setsar=1[bot];[top][bot]vstack[v]")
    return f"[0:v]{_crop_around(width, height, W / H, focus)},scale={W}:{H},setsar=1[v]"


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


def subtitles_ass(words: list[tuple[float, float, str]], path: Path) -> Path:
    """Legenda .ass: branca com contorno, e cada palavra fica amarela quando é falada."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pajau,DejaVu Sans,96,&H004DE1FF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,7,0,2,{SUBTITLE_SIDE_MARGIN},{SUBTITLE_SIDE_MARGIN},{SUBTITLE_BOTTOM_MARGIN},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for chunk in _chunks(words):
        start, end = chunk[0][0], max(chunk[-1][1], chunk[0][0] + 0.4)
        parts, cursor = [], start
        for word_start, word_end, text in chunk:
            # \k = tempo (centésimos) até a palavra acender; o atraso antes dela entra junto.
            parts.append(f"{{\\k{max(1, int(round((word_end - cursor) * 100)))}}}{text.upper()}")
            cursor = word_end
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Pajau,,0,0,0,,{' '.join(parts)}")
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def preview_frame(video: str | Path, seconds: float, settings: dict, output: Path, focus: float = 0.5) -> Path:
    """Uma foto de como o Short vai ficar, para conferir o layout antes de gerar."""
    width, height = video_size(video)
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", f"{max(0.0, seconds):.2f}", "-i", str(video),
                    "-filter_complex", vertical_graph(width, height, settings, focus), "-map", "[v]",
                    "-frames:v", "1", "-q:v", "3", str(output)], check=True)
    return output
