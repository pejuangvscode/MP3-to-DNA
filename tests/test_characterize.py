"""Corpus measurements that the dataset table depends on."""

from __future__ import annotations

from typing import NamedTuple

import pytest

from src.characterize import attacks, polyphony, terciles


class Note(NamedTuple):
    pitch: int
    start: float
    end: float


def test_a_single_line_has_polyphony_one():
    notes = [Note(60, 0.0, 1.0), Note(62, 1.0, 2.0), Note(64, 2.0, 3.0)]
    mean, peak = polyphony(notes)
    assert mean == pytest.approx(1.0)
    assert peak == 1


def test_back_to_back_notes_do_not_count_as_overlapping():
    """A note-off and the next note-on at the same instant are not a chord."""
    _, peak = polyphony([Note(60, 0.0, 1.0), Note(62, 1.0, 2.0)])
    assert peak == 1


def test_polyphony_is_weighted_by_time_sounding():
    # a triad for one second, then a single note for one second
    notes = [Note(60, 0.0, 1.0), Note(64, 0.0, 1.0), Note(67, 0.0, 2.0)]
    mean, peak = polyphony(notes)
    assert peak == 3
    assert mean == pytest.approx(2.0)


def test_silence_does_not_dilute_polyphony():
    notes = [Note(60, 0.0, 1.0), Note(64, 0.0, 1.0), Note(60, 5.0, 6.0), Note(64, 5.0, 6.0)]
    mean, _ = polyphony(notes)
    assert mean == pytest.approx(2.0)


def test_near_simultaneous_onsets_form_one_attack():
    notes = [Note(60, 0.000, 1.0), Note(64, 0.012, 1.0), Note(67, 0.500, 1.0)]
    groups = attacks(notes, window=0.030)
    assert [len(group) for group in groups] == [2, 1]


def test_a_rolled_chord_wider_than_the_window_is_not_one_attack():
    notes = [Note(60, 0.00, 1.0), Note(64, 0.05, 1.0), Note(67, 0.10, 1.0)]
    assert len(attacks(notes, window=0.030)) == 3


def test_tercile_boundaries_split_the_corpus_in_three():
    low, high = terciles([float(v) for v in range(9)])
    assert (low, high) == (3.0, 6.0)
