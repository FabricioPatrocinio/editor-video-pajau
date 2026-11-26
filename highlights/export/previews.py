from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..models import Cut


def generate_cut_previews(video: str | Path, cuts: list[Cut], output_dir: str | Path) -> list[list[str]]:
    """Generate 3 lightweight JPEG previews per cut (start, middle, end)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg não encontrado")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    all_paths: list[list[str]] = []

    for index, cut in enumerate(cuts, 1):
        cut_paths: list[str] = []
        for frame_name, timestamp in (
            ("start", cut.start),
            ("middle", cut.start + cut.duration * 0.5),
            ("end", max(cut.start, cut.end - 1.0)),
        ):
            path = output_dir / f"clip_{index:02d}_{frame_name}.jpg"
            subprocess.run([
                ffmpeg, "-y", "-v", "error", "-ss", f"{timestamp:.3f}", "-i", str(video),
                "-frames:v", "1", "-vf", "scale=480:-1", str(path),
            ], check=True)
            cut_paths.append(str(path))
        cut.preview_paths = cut_paths
        all_paths.append(cut_paths)
    return all_paths
