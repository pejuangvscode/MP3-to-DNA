"""MusicXML export. An artefact, not a pipeline stage: nothing reads it back,
so these confirm it is valid notation and that it stays off the critical path.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from src import config as cfg
from src.notation import write_from_quantized, write_from_transcribed
from src.tokenizer import QuantizedNote


class Note(NamedTuple):
    pitch: int
    start: float
    end: float


QUANTISED = [
    QuantizedNote(60, 0, 4),
    QuantizedNote(64, 4, 4),
    QuantizedNote(67, 8, 4),
    QuantizedNote(72, 12, 4),
]


def parsed_pitches(path):
    from music21 import converter

    score = converter.parse(str(path))
    return [element.pitch.midi for element in score.flatten().notes]


def test_quantised_notes_become_readable_notation(tmp_path):
    path = write_from_quantized(QUANTISED, tmp_path / "q.musicxml", tempo=120)
    assert path.is_file()
    assert parsed_pitches(path) == [note.pitch for note in QUANTISED]


def test_grid_units_map_to_the_right_note_values(tmp_path):
    """Four 1/16 units make one quarter note at the default resolution."""
    from music21 import converter

    path = write_from_quantized(
        [QuantizedNote(60, 0, 4)], tmp_path / "one.musicxml", tempo=120
    )
    element = converter.parse(str(path)).flatten().notes[0]
    assert element.quarterLength == pytest.approx(1.0)


def test_eighth_resolution_halves_the_note_value(tmp_path):
    from music21 import converter

    path = write_from_quantized(
        [QuantizedNote(60, 0, 1)], tmp_path / "eighth.musicxml", tempo=120, grid_code=1
    )
    element = converter.parse(str(path)).flatten().notes[0]
    assert element.quarterLength == pytest.approx(0.5)


def test_transcribed_notes_become_readable_notation(tmp_path):
    notes = [Note(60, 0.0, 0.5), Note(64, 0.5, 1.0), Note(67, 1.0, 2.0)]
    path = write_from_transcribed(notes, tmp_path / "t.musicxml", tempo=120)
    assert parsed_pitches(path) == [60, 64, 67]


def test_tempo_is_carried_into_the_file(tmp_path):
    path = write_from_quantized(QUANTISED, tmp_path / "tempo.musicxml", tempo=96)
    assert "96" in path.read_text()


def test_wide_range_material_is_split_across_two_staves(tmp_path):
    """Transcription spans a wide range; one staff means ledger lines both ways."""
    from music21 import converter

    wide = [QuantizedNote(40, 0, 4), QuantizedNote(84, 4, 4)]
    path = write_from_quantized(wide, tmp_path / "wide.musicxml", tempo=120)
    assert len(converter.parse(str(path)).parts) == 2
    assert parsed_pitches(path) == [40, 84]


def test_narrow_range_material_stays_on_one_staff(tmp_path):
    from music21 import converter

    path = write_from_quantized(QUANTISED, tmp_path / "narrow.musicxml", tempo=120)
    assert len(converter.parse(str(path)).parts) == 1


def test_splitting_can_be_disabled(tmp_path):
    from music21 import converter
    from src.notation import _write

    events = [(40, 0.0, 1.0), (84, 1.0, 1.0)]
    path = _write(
        events, tmp_path / "one.musicxml", 120, "t", "4/4", split_pitch=None
    )
    assert len(converter.parse(str(path)).parts) == 1


def test_notation_does_not_touch_the_token_path(tmp_path):
    """Writing notation must not alter the notes tokenisation will see."""
    from src.tokenizer import encode_notes

    before = encode_notes(QUANTISED, 120).data
    write_from_quantized(QUANTISED, tmp_path / "side.musicxml", tempo=120)
    assert encode_notes(QUANTISED, 120).data == before
