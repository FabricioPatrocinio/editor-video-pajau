from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np


def extract_mono_audio(video: str | Path, output: str | Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg não encontrado. Instale o pacote ffmpeg.")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        ffmpeg, "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(output),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output


def audio_energy(wav_path: str | Path, duration: float) -> tuple[np.ndarray, np.ndarray]:
    """Return 1-second RMS and local-z-score curves; chunks are streamed."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg não encontrado.")

    process = subprocess.Popen([
        ffmpeg, "-v", "error", "-i", str(wav_path), "-f", "s16le", "-ac", "1", "-ar", "16000", "pipe:1",
    ], stdout=subprocess.PIPE)

    rms = []
    seconds = int(np.ceil(duration))
    block_size = 16000 * 2
    for _ in range(seconds):
        chunk = process.stdout.read(block_size)
        if not chunk:
            break
        samples = np.frombuffer(chunk, dtype="<i2").astype(np.float32)
        rms.append(float(np.sqrt(np.mean(samples * samples)) / 32768.0))
    process.stdout.close()
    process.wait()

    rms_array = np.array(rms, dtype=np.float32)
    if rms_array.size == 0:
        return np.zeros(seconds, dtype=np.float32), np.zeros(seconds, dtype=np.float32)

    kernel = np.ones(min(60, max(1, seconds))) / min(60, max(1, seconds))
    moving = np.convolve(rms_array, kernel, mode="same")
    centered = rms_array - moving
    scale = np.std(centered) + 1e-6
    zscore = centered / scale
    return rms_array, zscore


def detect_silence(wav_path: str | Path, threshold_db: float = -35.0, min_duration: float = 0.5) -> list[tuple[float, float]]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg não encontrado.")
    result = subprocess.run([
        ffmpeg, "-v", "info", "-i", str(wav_path), "-af",
        f"silencedetect=noise={threshold_db}dB:d={min_duration}", "-f", "null", "-",
    ], capture_output=True, text=True)
    text = result.stderr
    starts = []
    ends = []
    import re
    for value in re.findall(r"silence_start: ([0-9.]+)", text):
        starts.append(float(value))
    for value in re.findall(r"silence_end: ([0-9.]+)", text):
        ends.append(float(value))
    intervals = [(starts[i], ends[i]) for i in range(min(len(starts), len(ends)))]
    return intervals


def find_muted_ranges(video: str | Path, min_seconds: float = 20.0) -> list[tuple[float, float]]:
    """Trechos em silêncio digital total (áudio mudo na gravação ou silenciado pela plataforma)."""
    import re

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    run = subprocess.run(
        [ffmpeg, "-nostats", "-i", str(video), "-vn", "-af", f"silencedetect=noise=-80dB:d={min_seconds}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", run.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", run.stderr)]
    if len(ends) < len(starts):  # mudo até o fim do arquivo
        duration = re.search(r"Duration: (\d+):(\d+):([0-9.]+)", run.stderr)
        total = int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3]) if duration else starts[-1]
        ends.append(total)
    return list(zip(starts, ends))
