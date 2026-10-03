"""MP3 -> mono PCM at 22050 Hz, the rate basic-pitch resamples to internally.

Doing it here rather than letting the model do it silently makes the conversion
measurable, and gives one place to record leading silence: MP3 codec delay
shifts every onset, and the note-level onset tolerance is only 50 ms.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from src import config as cfg


@dataclass(frozen=True)
class PreparedAudio:
    """Mono audio at the model's sample rate, plus its provenance."""

    samples: np.ndarray  # float32, one dimension
    sample_rate: int
    source_path: Path
    source_sample_rate: int
    source_channels: int

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate


def load(path: str | Path) -> PreparedAudio:
    """Decode to mono float32 at 22050 Hz. libsndfile handles MP3 directly."""
    path = Path(path)
    data, sample_rate = sf.read(path, dtype="float32", always_2d=True)

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
    """basic-pitch takes a path, not an array, so preprocessing has to land on
    disk first. Float rather than 16-bit PCM adds no quantisation of its own.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, audio.samples, audio.sample_rate, subtype="FLOAT")
    return path


def leading_silence(audio: PreparedAudio, threshold_db: float = -60.0) -> float:
    """Seconds before the first sample louder than `threshold_db`. Diagnostic
    only, so an MP3-induced onset shift stays visible instead of disappearing
    into the transcription error.
    """
    threshold = 10.0 ** (threshold_db / 20.0)
    loud = np.flatnonzero(np.abs(audio.samples) >= threshold)
    if loud.size == 0:
        return audio.duration
    return float(loud[0]) / audio.sample_rate


def trailing_silence(audio: PreparedAudio, threshold_db: float = -60.0) -> float:
    """Seconds after the last sample louder than `threshold_db`.

    Separates a long but silent tail, which is normal for a stem that stops
    before the band does, from a tail that still carries sound and therefore
    means the audio and the reference notation disagree.
    """
    threshold = 10.0 ** (threshold_db / 20.0)
    loud = np.flatnonzero(np.abs(audio.samples) >= threshold)
    if loud.size == 0:
        return audio.duration
    return audio.duration - float(loud[-1] + 1) / audio.sample_rate


def describe(audio: PreparedAudio) -> dict[str, float | int | str]:
    """Per-sample facts for the results table."""
    return {
        "file": audio.source_path.name,
        "source_sample_rate": audio.source_sample_rate,
        "source_channels": audio.source_channels,
        "sample_rate": audio.sample_rate,
        "duration_s": round(audio.duration, 4),
        "leading_silence_s": round(leading_silence(audio), 4),
        "peak": round(float(np.abs(audio.samples).max()), 6),
    }
