"""Preparing the Slakh stem subset into an encodable corpus."""

from __future__ import annotations

from typing import NamedTuple

import pretty_midi
import pytest

from src import config as cfg
from src.quantize import quantize
from src.slakh import (
    DURATION_LEVELS,
    MAGNITUDE_LEVELS,
    _constant_tempo,
    _fit_grid,
    _split_points,
    _tercile_levels,
)


class Note(NamedTuple):
    pitch: int
    start: float
    end: float


def on_grid(tempo: int, grid_code: int, positions: list[int], duration: int = 1):
    """Notes sitting exactly on the grid of `tempo` and `grid_code`."""
    delta = cfg.grid_unit_seconds(tempo, grid_code)
    return [
        Note(60, position * delta, (position + duration) * delta)
        for position in positions
    ]


def midi_with_tempi(tempi: list[float]) -> pretty_midi.PrettyMIDI:
    """A MIDI file carrying the given sequence of tempo events."""
    midi = pretty_midi.PrettyMIDI(initial_tempo=tempi[0])
    for index, tempo in enumerate(tempi[1:], start=1):
        # pretty_midi exposes tempo changes only through the underlying ticks
        midi._tick_scales.append(
            (midi.time_to_tick(index * 1.0), 60.0 / (tempo * midi.resolution))
        )
    midi._update_tick_to_time(midi.time_to_tick(len(tempi) + 1))
    return midi


# --- tempo constancy ---

def test_a_single_tempo_is_constant():
    assert _constant_tempo(midi_with_tempi([120.0])) == 120


def test_a_tempo_repeated_is_still_constant():
    """Lakh MIDI restates the same tempo often; that is not a tempo map."""
    assert _constant_tempo(midi_with_tempi([120.0, 120.0, 120.0])) == 120


def test_a_changing_tempo_is_rejected():
    assert _constant_tempo(midi_with_tempi([120.0, 90.0])) is None


# --- grid and tempo fitting ---

def test_a_piece_in_sixteenths_fits_the_sixteenth_grid():
    notes = on_grid(120, 2, [0, 1, 2, 3, 4, 6, 8, 9, 10, 12])
    tempo, grid_code, ratio = _fit_grid(notes, 120)
    assert (tempo, grid_code) == (120, 2)
    assert ratio == pytest.approx(0.0, abs=1e-9)


def test_a_piece_in_triplets_prefers_the_triplet_grid():
    """Six subdivisions to the beat, which four cannot express."""
    notes = on_grid(120, 3, [0, 2, 4, 6, 8, 10, 12, 14, 16, 18])
    _, grid_code, ratio = _fit_grid(notes, 120)
    assert grid_code == 3
    assert ratio == pytest.approx(0.0, abs=1e-9)


def test_a_piece_notated_at_half_tempo_is_refitted_to_double():
    """The offbeats of a piece written at half speed fall between grid lines."""
    notes = on_grid(140, 2, [0, 1, 2, 3, 5, 7, 9, 11, 13, 15])
    tempo, _, ratio = _fit_grid(notes, 70)
    assert tempo == 140
    assert ratio == pytest.approx(0.0, abs=1e-9)


def test_fitting_never_leaves_the_tempo_field_range():
    notes = on_grid(280, 2, [0, 1, 2, 3, 4])
    tempo, _, _ = _fit_grid(notes, 280)
    assert cfg.MIN_TEMPO <= tempo <= cfg.MAX_TEMPO


# --- cutting at long rests ---

def test_a_rest_within_the_delta_field_is_not_cut():
    notes = on_grid(120, 2, [0, 1, cfg.MAX_DELTA_UNITS])
    assert _split_points(notes, 120, 2) == []


def test_a_rest_beyond_the_delta_field_is_cut():
    notes = on_grid(120, 2, [0, 1, 1 + cfg.MAX_DELTA_UNITS + 1])
    assert _split_points(notes, 120, 2) == [2]


def test_a_late_first_entry_is_cut():
    """The first delta is measured from zero, so a late entry overflows too."""
    notes = on_grid(120, 2, [cfg.MAX_DELTA_UNITS + 1, cfg.MAX_DELTA_UNITS + 2])
    assert _split_points(notes, 120, 2) == [0]


def test_cutting_on_a_grid_unit_preserves_the_fit():
    """Shifting a segment to its own timeline must not move it off the grid.

    A cut at an arbitrary second subtracts a fractional number of grid units
    from every onset, which puts the whole segment out of phase and undoes the
    tempo and grid fit.
    """
    tempo, grid_code = 120, 2
    unit = cfg.grid_unit_seconds(tempo, grid_code)
    notes = on_grid(tempo, grid_code, [40, 41, 42, 44, 46])

    aligned = int((notes[0].start - 1.0) / unit) * unit
    shifted = [Note(n.pitch, n.start - aligned, n.end - aligned) for n in notes]
    assert quantize(shifted, tempo, grid_code).rms_grid_error_ms == pytest.approx(0.0, abs=1e-6)

    off_grid = notes[0].start - 1.0 + unit / 2.0
    nudged = [Note(n.pitch, n.start - off_grid, n.end - off_grid) for n in notes]
    assert quantize(nudged, tempo, grid_code).rms_grid_error_ms > 1.0


# --- stratification ---

def test_terciles_populate_every_level():
    levels = _tercile_levels([float(value) for value in range(30)], MAGNITUDE_LEVELS)
    assert set(levels) == set(MAGNITUDE_LEVELS)
    assert len(levels) == 30


def test_terciles_order_low_to_high():
    levels = _tercile_levels([9.0, 1.0, 5.0], DURATION_LEVELS)
    assert levels == [DURATION_LEVELS[2], DURATION_LEVELS[0], DURATION_LEVELS[1]]


def test_terciles_of_nothing_is_nothing():
    assert _tercile_levels([], MAGNITUDE_LEVELS) == []
