"""Align transcribed notes to the rhythmic grid (Tabel 3.6, Subbab 3.3.4).

Replaces real-valued times with small integers, and makes identical phrases
produce identical integer sequences, without which repeat detection cannot fire.
Lossy: deviations under half a grid unit disappear in the rounding, which is why
Tabel 3.13 attributes part of the reconstruction error here.

Offset estimation is a measurement only, not applied by default.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple, Protocol, Sequence

from src import config as cfg
from src.tokenizer import QuantizedNote


class TimedNote(Protocol):
    """Anything with a pitch and a start and end in seconds."""

    pitch: int
    start: float
    end: float


class OffsetEstimate(NamedTuple):
    """How far the onsets sit off the grid as a whole."""

    offset_s: float  # subtract this from onsets to centre them on the grid
    concentration: float  # 0 = no common phase, 1 = every onset shifted alike

    @property
    def offset_ms(self) -> float:
        return self.offset_s * 1000.0


@dataclass(frozen=True)
class QuantizationReport:
    """Quantised notes plus what the rounding cost."""

    notes: tuple[QuantizedNote, ...]
    tempo: int
    grid_code: int
    input_count: int
    merged_count: int  # notes absorbed by the duplicate merge of step (d)
    clamped_count: int  # durations that hit either end of the 1..64 limits
    # counted apart because the two ends mean different things: rounding a
    # sub-unit note up to 1 is ordinary quantisation, while truncating a held
    # note at 64 discards duration the scheme cannot express
    truncated_count: int
    rms_grid_error_ms: float
    max_grid_error_ms: float
    offset_applied_s: float

    @property
    def grid_unit_ms(self) -> float:
        return cfg.grid_unit_seconds(self.tempo, self.grid_code) * 1000.0


def grid_to_seconds(
    position: int, tempo: float, grid_code: int = cfg.DEFAULT_GRID_CODE
) -> float:
    """Grid units back to seconds."""
    return position * cfg.grid_unit_seconds(tempo, grid_code)


def estimate_offset(
    notes: Sequence[TimedNote],
    tempo: float,
    grid_code: int = cfg.DEFAULT_GRID_CODE,
) -> OffsetEstimate:
    """Circular mean of onset phases, measuring a shift common to every note.

    MP3 coding delays every sample by a constant, so onsets arrive late as a
    group, and that can eat half the 50 ms onset tolerance before transcription
    error is counted at all.

    Diagnostic only: Subbab 3.3.4 defines quantisation as plain rounding, and
    quantize() follows that by default. `concentration` is the resultant length
    of the phase vectors -- near 1 the onsets share one offset, near 0 the mean
    means little.
    """
    if not notes:
        return OffsetEstimate(0.0, 0.0)

    delta = cfg.grid_unit_seconds(tempo, grid_code)
    angles = [2.0 * math.pi * ((note.start / delta) % 1.0) for note in notes]
    sin_mean = sum(math.sin(angle) for angle in angles) / len(angles)
    cos_mean = sum(math.cos(angle) for angle in angles) / len(angles)

    concentration = math.hypot(sin_mean, cos_mean)
    if concentration < 1e-12:
        return OffsetEstimate(0.0, 0.0)

    mean_angle = math.atan2(sin_mean, cos_mean)  # (-pi, pi]
    return OffsetEstimate(mean_angle / (2.0 * math.pi) * delta, concentration)


def quantize(
    notes: Sequence[TimedNote],
    tempo: int,
    grid_code: int = cfg.DEFAULT_GRID_CODE,
    offset_seconds: float = 0.0,
) -> QuantizationReport:
    """The four steps of Subbab 3.3.4: derive the grid unit from the tempo,
    round pitch and times, sort by position then pitch, and merge notes sharing
    a pitch and position by keeping the longest duration.

    `offset_seconds` is subtracted before rounding; zero is the algorithm as the
    report defines it.
    """
    delta = cfg.grid_unit_seconds(tempo, grid_code)

    # (b) round each note into integers.
    longest: dict[tuple[int, int], int] = {}
    clamped = 0
    truncated = 0
    errors: list[float] = []

    for note in notes:
        start = note.start - offset_seconds
        end = note.end - offset_seconds

        pitch = int(round(note.pitch))

        # a negative position needs an offset larger than the first onset
        position = max(0, int(round(start / delta)))

        raw_duration = int(round((end - start) / delta))
        duration = min(max(raw_duration, cfg.MIN_DURATION_UNITS), cfg.MAX_DURATION_UNITS)
        if duration != raw_duration:
            clamped += 1
            if raw_duration > cfg.MAX_DURATION_UNITS:
                truncated += 1

        errors.append((start - position * delta) * 1000.0)

        # (d) merge in place rather than in a second pass
        key = (pitch, position)
        longest[key] = max(longest.get(key, 0), duration)

    # (c) sort by position, then pitch.
    quantised = tuple(
        QuantizedNote(pitch, position, duration)
        for (pitch, position), duration in sorted(
            longest.items(), key=lambda item: (item[0][1], item[0][0])
        )
    )

    input_count = len(notes)
    rms = math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else 0.0

    return QuantizationReport(
        notes=quantised,
        tempo=tempo,
        grid_code=grid_code,
        input_count=input_count,
        merged_count=input_count - len(quantised),
        clamped_count=clamped,
        truncated_count=truncated,
        rms_grid_error_ms=round(rms, 4),
        max_grid_error_ms=round(max((abs(e) for e in errors), default=0.0), 4),
        offset_applied_s=offset_seconds,
    )


def to_seconds(
    notes: Sequence[QuantizedNote],
    tempo: float,
    grid_code: int = cfg.DEFAULT_GRID_CODE,
) -> list[tuple[int, float, float]]:
    """Quantised notes back to (pitch, start, end) in seconds."""
    delta = cfg.grid_unit_seconds(tempo, grid_code)
    return [
        (note.pitch, note.position * delta, (note.position + note.duration) * delta)
        for note in notes
    ]
