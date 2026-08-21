"""MP3 -> mono PCM at 22050 Hz (Tabel 3.5, Subbab 3.3.2).

basic-pitch converts everything to mono and resamples to 22050 Hz internally.
Doing it here instead makes the conversion explicit and measurable rather than
hidden inside the model, which is what Subbab 3.3.2 asks for, and gives the
pipeline one place to record what the decoder actually produced.

The module also measures leading silence. Encoding to MP3 and decoding back
introduces a small delay, and since the note-level onset tolerance is only
50 ms (Subbab 2.9.3), a systematic shift of even 25 ms eats half the budget
before transcription error is counted at all. Measuring it is the first step to
deciding whether it needs compensating; see :mod:`src.quantize`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from src import config as cfg


class PreprocessError(ValueError):
    """The audio file cannot be prepared for transcription."""


@dataclass(frozen=True)
class PreparedAudio:
    """Mono audio at the model's sample rate, plus what it came from."""

    samples: np.ndarray  # float32, one dimension
    sample_rate: int
    source_path: Path
    source_sample_rate: int
    source_channels: int

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate


def load(path: str | Path) -> PreparedAudio:
    """Decode an audio file to mono float32 at 22050 Hz.

    MP3 is read through libsndfile, which supports it from version 1.1, so no
    external ffmpeg is involved.
    """
    path = Path(path)
    if not path.is_file():
        raise PreprocessError(f"no such audio file: {path}")

    try:
        data, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    except Exception as exc:  # libsndfile raises several unrelated types
        raise PreprocessError(f"cannot decode {path.name}: {exc}") from exc

    if data.size == 0:
        raise PreprocessError(f"{path.name} contains no audio")

    channels = data.shape[1]
    # Averaging rather than taking one channel: a note panned hard to one side
    # would vanish entirely otherwise.
    mono = data.mean(axis=1) if channels > 1 else data[:, 0]

    if sample_rate != cfg.TARGET_SAMPLE_RATE:
        mono = librosa.resample(
            mono, orig_sr=sample_rate, target_sr=cfg.TARGET_SAMPLE_RATE
        )

    return PreparedAudio(
        samples=np.ascontiguousarray(mono, dtype=np.float32),
        sample_rate=cfg.TARGET_SAMPLE_RATE,
        source_path=path,
        source_sample_rate=sample_rate,
        source_channels=channels,
    )


def write_wav(audio: PreparedAudio, path: str | Path) -> Path:
    """Write prepared audio as a 32-bit float WAV.

    basic-pitch takes a file path rather than an array, so preprocessing has to
    land on disk before transcription can read it. Float rather than 16-bit PCM
    so this step adds no quantisation of its own.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio.samples, audio.sample_rate, subtype="FLOAT")
    return path


def leading_silence(audio: PreparedAudio, threshold_db: float = -60.0) -> float:
    """Seconds before the first sample louder than `threshold_db`.

    A diagnostic, not a correction. Reported per sample in Bab IV so any
    systematic onset shift introduced by MP3 encoding is visible rather than
    silently absorbed into the transcription error.
    """
    if audio.samples.size == 0:
        return 0.0
    threshold = 10.0 ** (threshold_db / 20.0)
    loud = np.flatnonzero(np.abs(audio.samples) >= threshold)
    if loud.size == 0:
        return audio.duration
    return float(loud[0]) / audio.sample_rate


def describe(audio: PreparedAudio) -> dict[str, float | int | str]:
    """Per-sample facts worth tabulating in Bab IV."""
    return {
        "file": audio.source_path.name,
        "source_sample_rate": audio.source_sample_rate,
        "source_channels": audio.source_channels,
        "sample_rate": audio.sample_rate,
        "duration_s": round(audio.duration, 4),
        "leading_silence_s": round(leading_silence(audio), 4),
        "peak": round(float(np.abs(audio.samples).max()), 6),
    }
