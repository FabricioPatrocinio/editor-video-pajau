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


# Frases que o Whisper "inventa" em trechos de música ou silêncio.
HALLUCINATIONS = (
    "amara.org", "legendas pela comunidade", "legenda adriana", "obrigado por assistir",
    "inscreva-se", "se inscreva", "ative o sininho", "transcrição e legendas",
)


def _is_hallucination(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in HALLUCINATIONS)


def transcribe_windows(
    wav_path: str | Path,
    windows: list[tuple[float, float]],
    language: str | None = None,
    max_chars: int = 700,
    with_times: bool = False,
) -> list[str]:
    """Transcreve cada janela (início, fim) do WAV mono 16 kHz gerado pela análise.

    with_times=True devolve linhas "[t=5020] fala", com o segundo na live, para cortes precisos.
    """
    model = _load_model()
    language = language or os.getenv("PAJAU_WHISPER_LANGUAGE", "pt").strip() or None
    texts: list[str] = []
    for start, end in windows:
        samples = _read_window(Path(wav_path), start, end)
        if samples.size == 0:
            texts.append("")
            continue
        segments, _ = model.transcribe(samples, language=language, vad_filter=True, beam_size=1)
        pieces = []
        for segment in segments:
            spoken = segment.text.strip()
            if not spoken or _is_hallucination(spoken):
                continue
            pieces.append(f"[t={start + segment.start:.0f}] {spoken}" if with_times else spoken)
        texts.append(("\n" if with_times else " ").join(pieces)[:max_chars])
    return texts


def transcribe_words(video: str | Path, start: float, end: float) -> list[tuple[float, float, str]]:
    """Palavras faladas num trecho do vídeo, com tempo relativo ao início do trecho. Para a legenda."""
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    raw = subprocess.run([ffmpeg, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", str(video),
                          "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size == 0:
        return []
    language = os.getenv("PAJAU_WHISPER_LANGUAGE", "pt").strip() or None
    segments, _ = _load_model().transcribe(samples, language=language, vad_filter=True, beam_size=1,
                                           word_timestamps=True)
    words = []
    for segment in segments:
        if _is_hallucination(segment.text):
            continue
        for word in segment.words or []:
            text = word.word.strip()
            if text:
                words.append((float(word.start), float(word.end), text))
    return words
