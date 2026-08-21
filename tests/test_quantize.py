"""Grid alignment (Tabel 3.6, Subbab 3.3.4)."""

from __future__ import annotations

import math
import random
from typing import NamedTuple

import pytest

from src import config as cfg
from src.quantize import (
    QuantizedNote,
    estimate_offset,
    grid_to_seconds,
    quantize,
    to_seconds,
)


class Note(NamedTuple):
    pitch: int
    start: float
    end: float


def on_grid(tempo: int, units: list[tuple[int, int, int]]) -> list[Note]:
    """Notes placed exactly on the grid, from (pitch, position, duration)."""
    delta = cfg.grid_unit_seconds(tempo)
    return [
        Note(pitch, position * delta, (position + duration) * delta)
        for pitch, position, duration in units
    ]


# ---------------------------------------------------------------------------
# Grid unit (Persamaan 3.1)
# ---------------------------------------------------------------------------


def test_grid_unit_matches_persamaan_3_1():
    assert cfg.grid_unit_seconds(120, 2) == pytest.approx(0.125)
    assert cfg.grid_unit_seconds(120, 1) == pytest.approx(0.25)
    assert cfg.grid_unit_seconds(60, 2) == pytest.approx(0.25)


def test_grid_conversion_round_trips():
    for position in (0, 1, 17, 255):
        seconds = grid_to_seconds(position, 120)
        assert round(seconds / cfg.grid_unit_seconds(120)) == position


# ---------------------------------------------------------------------------
# Rounding
# ---------------------------------------------------------------------------


def test_notes_already_on_the_grid_are_unchanged():
    units = [(60, 0, 4), (64, 4, 4), (67, 8, 8)]
    report = quantize(on_grid(120, units), 120)
    assert list(report.notes) == [QuantizedNote(*u) for u in units]
    assert report.rms_grid_error_ms == pytest.approx(0.0, abs=1e-6)


def test_deviation_below_half_a_unit_rounds_away():
    """Quantisation is lossy exactly here (Subbab 2.6.3)."""
    delta = cfg.grid_unit_seconds(120)
    nudged = [Note(60, 4 * delta + 0.4 * delta, 8 * delta)]
    report = quantize(nudged, 120)
    assert report.notes[0].position == 4
    assert report.max_grid_error_ms == pytest.approx(0.4 * delta * 1000, rel=1e-6)


def test_deviation_above_half_a_unit_moves_to_the_next_position():
    delta = cfg.grid_unit_seconds(120)
    nudged = [Note(60, 4 * delta + 0.6 * delta, 8 * delta)]
    assert quantize(nudged, 120).notes[0].position == 5


def test_duration_is_clamped_to_the_field_range():
    delta = cfg.grid_unit_seconds(120)
    notes = [
        Note(60, 0.0, 0.01 * delta),  # far below one unit
        Note(72, 10 * delta, 10 * delta + 500 * delta),  # far above 64 units
    ]
    report = quantize(notes, 120)
    durations = sorted(note.duration for note in report.notes)
    assert durations == [cfg.MIN_DURATION_UNITS, cfg.MAX_DURATION_UNITS]
    assert report.clamped_count == 2


# ---------------------------------------------------------------------------
# Ordering and merging
# ---------------------------------------------------------------------------


def test_notes_are_sorted_by_position_then_pitch():
    notes = on_grid(120, [(72, 8, 4), (60, 4, 4), (67, 4, 4), (62, 0, 4)])
    positions = [(note.position, note.pitch) for note in quantize(notes, 120).notes]
    assert positions == sorted(positions)


def test_notes_sharing_pitch_and_position_merge_to_the_longest():
    notes = on_grid(120, [(60, 4, 2), (60, 4, 8), (60, 4, 5)])
    report = quantize(notes, 120)
    assert len(report.notes) == 1
    assert report.notes[0] == QuantizedNote(60, 4, 8)
    assert report.merged_count == 2


def test_simultaneous_notes_of_different_pitch_are_kept():
    """Corpus samples use two instruments, so chords must survive."""
    notes = on_grid(120, [(60, 4, 4), (64, 4, 4), (67, 4, 4)])
    report = quantize(notes, 120)
    assert len(report.notes) == 3
    assert report.merged_count == 0
    assert [note.pitch for note in report.notes] == [60, 64, 67]


def test_merged_notes_stay_tokenisable():
    """Zero deltas from simultaneous notes are legal; the field is unsigned."""
    from src.tokenizer import notes_to_tokens

    report = quantize(on_grid(120, [(60, 4, 4), (64, 4, 4)]), 120)
    tokens = notes_to_tokens(report.notes)
    assert tokens[1].delta == 0


# ---------------------------------------------------------------------------
# Offset measurement
# ---------------------------------------------------------------------------


def test_a_common_shift_is_recovered():
    """The shape an MP3 codec delay would take (Subbab 2.9.3)."""
    delta = cfg.grid_unit_seconds(120)
    shift = 0.025  # 25 ms, about what LAME adds
    notes = [Note(60, position * delta + shift, (position + 2) * delta) for position in range(0, 40, 2)]

    estimate = estimate_offset(notes, 120)
    assert estimate.offset_s == pytest.approx(shift, abs=1e-9)
    assert estimate.concentration > 0.99


def test_scattered_onsets_give_a_weak_estimate():
    rng = random.Random(31)
    delta = cfg.grid_unit_seconds(120)
    notes = [Note(60, rng.uniform(0, 40) * delta, 1.0) for _ in range(400)]
    assert estimate_offset(notes, 120).concentration < 0.3


def test_applying_the_offset_removes_the_shift():
    delta = cfg.grid_unit_seconds(120)
    shift = 0.03
    notes = [Note(60, position * delta + shift, (position + 2) * delta) for position in range(0, 40, 2)]

    uncompensated = quantize(notes, 120)
    compensated = quantize(notes, 120, offset_seconds=estimate_offset(notes, 120).offset_s)

    assert compensated.rms_grid_error_ms < uncompensated.rms_grid_error_ms
    assert compensated.rms_grid_error_ms == pytest.approx(0.0, abs=1e-6)


def test_offset_defaults_to_off():
    """Subbab 3.3.4 defines quantisation as plain rounding, with no offset."""
    delta = cfg.grid_unit_seconds(120)
    notes = [Note(60, 4 * delta + 0.03, 8 * delta)]
    assert quantize(notes, 120).offset_applied_s == 0.0
    assert quantize(notes, 120).max_grid_error_ms == pytest.approx(30.0, rel=1e-6)


def test_offset_estimate_of_an_empty_list_is_zero():
    assert estimate_offset([], 120) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# Round trip and validation
# ---------------------------------------------------------------------------


def test_seconds_round_trip():
    units = [(60, 0, 4), (64, 4, 4), (67, 12, 8)]
    report = quantize(on_grid(120, units), 120)
    seconds = to_seconds(report.notes, 120)
    assert list(report.notes) == list(quantize([Note(*s) for s in seconds], 120).notes)


def test_tempo_outside_the_header_range_is_rejected():
    with pytest.raises(ValueError, match="tempo"):
        quantize([], cfg.MAX_TEMPO + 1)


def test_unknown_grid_code_is_rejected():
    with pytest.raises(ValueError, match="grid resolution"):
        quantize([], 120, grid_code=9)


def test_pitch_outside_the_midi_range_is_rejected():
    with pytest.raises(ValueError, match="pitch"):
        quantize([Note(200, 0.0, 1.0)], 120)


@pytest.mark.parametrize("grid_code", sorted(cfg.GRID_SUBDIVISIONS))
def test_every_grid_resolution_round_trips(grid_code):
    rng = random.Random(grid_code)
    delta = cfg.grid_unit_seconds(120, grid_code)
    positions = sorted(rng.sample(range(200), 40))
    notes = [Note(60 + (p % 12), p * delta, (p + 2) * delta) for p in positions]

    report = quantize(notes, 120, grid_code=grid_code)
    assert [note.position for note in report.notes] == positions
    assert report.rms_grid_error_ms == pytest.approx(0.0, abs=1e-6)
