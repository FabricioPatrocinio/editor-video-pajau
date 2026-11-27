"""Fotos pequenas em intervalos regulares, para a IA "olhar" a live sem assistir ao vídeo."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def _ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise RuntimeError("ffmpeg não encontrado. Instale com: sudo apt install ffmpeg")
    return binary


def sample_frames(
    video: str | Path,
    out_dir: Path,
    interval: float,
    start: float = 0.0,
    duration: float | None = None,
    width: int = 256,
    fast: bool = False,
) -> list[tuple[float, Path]]:
    """Uma foto a cada `interval` segundos. Retorna [(segundo na live, caminho)].

    fast=True decodifica só quadros-chave: muito mais rápido para a live inteira,
    com precisão de ~1–2 s, suficiente para o mapa.
    """
    index_file = out_dir / "frames.json"
    if index_file.exists():
        return [(t, Path(p)) for t, p in json.loads(index_file.read_text(encoding="utf-8"))]

    out_dir.mkdir(parents=True, exist_ok=True)
    command = [_ffmpeg(), "-y", "-v", "error"]
    if fast:
        command += ["-skip_frame", "nokey"]
    if start > 0:
        command += ["-ss", f"{start:.2f}"]
    command += ["-i", str(video)]
    if duration is not None:
        command += ["-t", f"{duration:.2f}"]
    command += [
        "-vf", f"fps=1/{interval},scale={width}:-2", "-fps_mode", "vfr", "-q:v", "5",
        str(out_dir / "f_%05d.jpg"),
    ]
    subprocess.run(command, check=True)

    files = sorted(out_dir.glob("f_*.jpg"))
    frames = [(round(start + i * interval, 1), path) for i, path in enumerate(files)]
    index_file.write_text(json.dumps([(t, str(p)) for t, p in frames]), encoding="utf-8")
    return frames
