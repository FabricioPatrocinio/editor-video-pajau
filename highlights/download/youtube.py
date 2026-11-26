from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def _run(command: list[str]) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout


def probe_video(path: str | Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe não encontrado. Instale o ffmpeg.")
    raw = _run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    data = json.loads(raw)
    return {"duration": float(data["format"]["duration"])}


def download_media(source: str, output_dir: str | Path) -> tuple[Path, Optional[dict]]:
    """Download a YouTube URL or validate a local media file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not (source.startswith("http://") or source.startswith("https://")):
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Vídeo não encontrado: {path}")
        return path, None

    yt_dlp = shutil.which("yt-dlp")
    if not yt_dlp:
        raise RuntimeError("yt-dlp não encontrado. Instale com: pip install yt-dlp")

    template = str(output_dir / "%(title)s [%(id)s].%(ext)s")
    command = [
        yt_dlp, "--no-playlist", "--write-info-json", "--write-subs",
        "--sub-langs", "live_chat", "--convert-subs", "json",
        "-f", "bv*+ba/b", "-o", template, source,
    ]
    subprocess.run(command, check=True)

    info_files = list(output_dir.glob("*.info.json"))
    if not info_files:
        raise RuntimeError("Não foi possível obter metadados do download")
    info_path = max(info_files, key=lambda p: p.stat().st_mtime)
    info = json.loads(info_path.read_text(encoding="utf-8"))

    videos = [p for p in output_dir.iterdir() if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}]
    if not videos:
        raise RuntimeError("O download não produziu um arquivo de vídeo")
    video = max(videos, key=lambda p: p.stat().st_mtime)
    return video, info
