from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..models import Cut


def _ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise RuntimeError("ffmpeg não encontrado. Instale com: sudo apt install ffmpeg")
    return binary


def export_cuts(video: str | Path, cuts: list[Cut], output_dir: str | Path, aspect: str = "16:9", mode: str = "precise") -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg()
    paths: list[Path] = []

    for index, cut in enumerate(cuts, 1):
        h = int(cut.start // 3600)
        m = int((cut.start % 3600) // 60)
        s = int(cut.start % 60)
        path = output_dir / f"clip_{index:02d}_{h:02d}h{m:02d}m{s:02d}s.mp4"
        # Mantém a resolução da live (até 1080p): nunca piora um vídeo que já é bom.
        vf = ["scale=-2:'min(ih,1080)'"]
        if aspect == "9:16":
            vf = [
                "split=2[in][bg];[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:10[blur];",
                "[in]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[blur][fg]overlay=(W-w)/2:(H-h)/2",
            ]
        filter_arg = "".join(vf)

        command = [ffmpeg, "-y", "-v", "error"]
        if mode == "fast":
            command += ["-ss", str(cut.start), "-i", str(video), "-t", str(cut.duration), "-map", "0:v:0", "-map", "0:a?", "-c", "copy"]
        else:
            command += ["-ss", str(cut.start), "-i", str(video), "-t", str(cut.duration), "-vf", filter_arg, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"]
        command.append(str(path))
        subprocess.run(command, check=True)
        paths.append(path)
    return paths


def export_compilation(clips: list[Path], output: str | Path, crossfade: float = 0.0) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg()
    concat = output.parent / "concat.txt"
    concat.write_text("".join(f"file '{path.resolve().as_posix()}'\n" for path in clips), encoding="utf-8")

    if crossfade > 0:
        command = [ffmpeg, "-y", "-v", "error"]
        for clip in clips:
            command += ["-i", str(clip)]
        filters = []
        if len(clips) == 1:
            command += ["-c", "copy", str(output)]
        else:
            current = "[0:v]"
            for index in range(1, len(clips)):
                next_label = f"[v{index}]"
                if index == 1:
                    filters.append(f"[0:v][1:v]xfade=transition=fade:duration={crossfade}:offset=0[v1]")
                else:
                    filters.append(f"[v{index-1}][{index}:v]xfade=transition=fade:duration={crossfade}:offset=0[{next_label[1:-1]}]")
            command += ["-filter_complex", ";".join(filters), "-map", "[" + next_label[1:-1] + "]", "-c:v", "libx264", str(output)]
    else:
        command = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(output)]

    subprocess.run(command, check=True)
    return output
