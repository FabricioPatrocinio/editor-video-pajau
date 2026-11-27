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


def export_cuts(video: str | Path, cuts: list[Cut], output_dir: str | Path, aspect: str = "16:9", mode: str = "precise",
                focuses: list[float] | None = None, shorts: dict | None = None, notes: list[str] | None = None,
                progress=None) -> list[Path]:
    """Corta cada trecho. No 9:16 aplica o layout do Short e, se ligada, a legenda. Áudio sempre normalizado."""
    from .shorts import DEFAULTS, subtitles_ass, vertical_graph, video_size

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    video = Path(video).resolve()
    ffmpeg = _ffmpeg()
    vertical = aspect == "9:16"
    shorts = {**DEFAULTS, "subtitles": False, **(shorts or {})}
    width, height = video_size(video) if vertical and mode != "fast" else (0, 0)
    want_subtitles = vertical and mode != "fast" and bool(shorts.get("subtitles"))
    paths: list[Path] = []

    for index, cut in enumerate(cuts, 1):
        h = int(cut.start // 3600)
        m = int((cut.start % 3600) // 60)
        s = int(cut.start % 60)
        path = output_dir / f"clip_{index:02d}_{h:02d}h{m:02d}m{s:02d}s.mp4"
        command = [ffmpeg, "-y", "-v", "error", "-ss", str(cut.start), "-i", str(video), "-t", str(cut.duration)]
        if mode == "fast":
            command += ["-map", "0:v:0", "-map", "0:a?", "-c", "copy", str(path)]
            subprocess.run(command, check=True)
            paths.append(path)
            continue

        if vertical:
            focus = focuses[index - 1] if focuses and index - 1 < len(focuses) else 0.5
            graph = vertical_graph(width, height, shorts, focus)
        else:
            # Mantém a resolução da live (até 1080p): nunca piora um vídeo que já é bom.
            graph = "[0:v]scale=-2:'min(ih,1080)',setsar=1[v]"

        if want_subtitles:
            if progress:
                progress(index, len(cuts), "Escrevendo a legenda")
            words = _words(video, cut, notes)
            if words:
                name = f"clip_{index:02d}.ass"
                subtitles_ass(words, output_dir / name)
                graph = graph[:-3] + f"[raw];[raw]ass={name}[v]"
        elif progress:
            progress(index, len(cuts), "Cortando")

        command += ["-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", str(path)]
        # Roda dentro da pasta dos cortes: o filtro da legenda recebe só o nome do arquivo, sem caminho.
        subprocess.run(command, check=True, cwd=output_dir)
        paths.append(path)
    return paths


def _words(video: Path, cut: Cut, notes: list[str] | None) -> list:
    try:
        from ..analysis.transcribe import transcribe_words
        return transcribe_words(video, cut.start, cut.end)
    except Exception as error:
        message = f"Legenda desligada: {error}"
        if notes is not None and message not in notes:
            notes.append(message)
        return []


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
