"""Junta os clipes aplicando a transição escolhida (pela IA ou por você) antes de cada um."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

# nome usado no plano -> (filtro xfade do FFmpeg, duração em segundos)
TRANSITIONS: dict[str, tuple[str, float] | None] = {
    "corte": None,
    "fade": ("fade", 0.5),
    "fade_preto": ("fadeblack", 0.8),
    "deslizar": ("slideleft", 0.4),
}


def _probe(clip: Path) -> tuple[float, bool]:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    data = json.loads(subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(clip)],
        check=True, capture_output=True, text=True,
    ).stdout)
    has_audio = any(stream.get("codec_type") == "audio" for stream in data.get("streams", []))
    return float(data["format"]["duration"]), has_audio


def join_with_transitions(clips: list[Path], transitions: list[str], output: Path) -> Path:
    """transitions[i] é a entrada do clipe i (a do primeiro é ignorada)."""
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    output.parent.mkdir(parents=True, exist_ok=True)
    probes = [_probe(clip) for clip in clips]
    wanted = [TRANSITIONS.get(name) for name in transitions[1:]]

    if len(clips) == 1 or not all(has_audio for _, has_audio in probes) or not any(wanted):
        concat = output.parent / "concat.txt"
        concat.write_text("".join(f"file '{clip.resolve().as_posix()}'\n" for clip in clips), encoding="utf-8")
        subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
                        "-c", "copy", str(output)], check=True)
        return output

    command = [ffmpeg, "-y", "-v", "error"]
    filters = []
    for index, clip in enumerate(clips):
        command += ["-i", str(clip)]
        filters.append(f"[{index}:v]fps=30,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v{index}]")
        filters.append(f"[{index}:a]aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS[a{index}]")

    video, audio, length = "[v0]", "[a0]", probes[0][0]
    for index in range(1, len(clips)):
        clip_length = probes[index][0]
        choice = wanted[index - 1]
        out_v, out_a = f"[vx{index}]", f"[ax{index}]"
        if choice is None:
            filters.append(f"{video}{audio}[v{index}][a{index}]concat=n=2:v=1:a=1{out_v}{out_a}")
            length += clip_length
        else:
            name, duration = choice
            duration = min(duration, length / 3, clip_length / 3)
            filters.append(f"{video}[v{index}]xfade=transition={name}:duration={duration:.3f}:offset={length - duration:.3f}{out_v}")
            filters.append(f"{audio}[a{index}]acrossfade=d={duration:.3f}{out_a}")
            length += clip_length - duration
        video, audio = out_v, out_a

    command += ["-filter_complex", ";".join(filters), "-map", video, "-map", audio,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", str(output)]
    subprocess.run(command, check=True)
    return output


def make_preview(video: str | Path, start: float, end: float, output: Path) -> Path:
    """Prévia leve (360p) de um trecho, só para revisão na interface."""
    if output.exists():
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    subprocess.run([
        ffmpeg, "-y", "-v", "error", "-ss", f"{start:.2f}", "-i", str(video), "-t", f"{max(1.0, end - start):.2f}",
        "-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(output),
    ], check=True)
    return output
