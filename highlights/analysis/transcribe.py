"""Transcrição local, opcional, apenas dos trechos candidatos.

Usa faster-whisper na CPU. Ative com PAJAU_TRANSCRIBE=true no .env.
A transcrição é o que permite à IA entender o que foi dito ("consegui!", "morri de novo"),
então melhora bastante as escolhas. Nada de áudio é enviado para a API.
"""
from __future__ import annotations

import os
import wave
from pathlib import Path

import numpy as np

from ..ai.config import env_flag

_MODEL = None


def transcription_enabled() -> bool:
    return env_flag("PAJAU_TRANSCRIBE", False)


def _load_model():
    global _MODEL
    if _MODEL is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError(
                "PAJAU_TRANSCRIBE=true exige o pacote faster-whisper: pip install faster-whisper"
            ) from error
        size = os.getenv("PAJAU_WHISPER_MODEL", "small").strip() or "small"
        _MODEL = WhisperModel(size, device="cpu", compute_type="int8")
    return _MODEL


def _read_window(wav_path: Path, start: float, end: float) -> np.ndarray:
    with wave.open(str(wav_path), "rb") as audio:
        rate = audio.getframerate()
        audio.setpos(min(audio.getnframes(), int(start * rate)))
        frames = audio.readframes(max(0, int((end - start) * rate)))
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe_windows(
    wav_path: str | Path,
    windows: list[tuple[float, float]],
    language: str | None = None,
    max_chars: int = 700,
) -> list[str]:
    """Transcreve cada janela (início, fim) do WAV mono 16 kHz gerado pela análise."""
    model = _load_model()
    language = language or os.getenv("PAJAU_WHISPER_LANGUAGE", "pt").strip() or None
    texts: list[str] = []
    for start, end in windows:
        samples = _read_window(Path(wav_path), start, end)
        if samples.size == 0:
            texts.append("")
            continue
        segments, _ = model.transcribe(samples, language=language, vad_filter=True, beam_size=1)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        texts.append(text[:max_chars])
    return texts
