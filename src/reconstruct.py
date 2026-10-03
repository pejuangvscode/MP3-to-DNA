"""Recovered tokens -> MIDI. Grid positions become seconds again using the tempo
from the token header, so nothing outside the sequence is needed.

Two things the token scheme cannot restore. Velocity has no field in Tabel 3.8,
so every note gets one fixed value and FL Studio's humanised velocity is lost.
Tokens carry no channel, so a two-instrument sample comes back merged into one
track. Neither affects note-level metrics, which match on pitch and timing.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple, Sequence

import pretty_midi

from src import config as cfg
from src.quantize import to_seconds
from src.tokenizer import QuantizedNote

# fixed, since the token scheme stores no velocity
RECONSTRUCTION_VELOCITY = 80

# arbitrary: the token scheme stores no instrument either
RECONSTRUCTION_PROGRAM = 0


class MidiNote(NamedTuple):
    """Named fields so it feeds quantize() directly, still a plain tuple so the
    evaluation code can unpack it positionally.
    """

    pitch: int
    start: float
    end: float


def to_midi(
    notes: Sequence[QuantizedNote],
    path: str | Path,
    tempo: int,
    grid_code: int = cfg.DEFAULT_GRID_CODE,
    velocity: int = RECONSTRUCTION_VELOCITY,
    program: int = RECONSTRUCTION_PROGRAM,
) -> Path:
    """Write quantised notes as a single-track MIDI file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    midi = pretty_midi.PrettyMIDI(initial_tempo=float(tempo))
    instrument = pretty_midi.Instrument(program=program)
    for pitch, start, end in to_seconds(notes, tempo, grid_code):
        instrument.notes.append(
            pretty_midi.Note(velocity=velocity, pitch=pitch, start=start, end=end)
        )
    midi.instruments.append(instrument)
    midi.write(str(path))
    return path


def read_midi(path: str | Path) -> list[MidiNote]:
    """Flat sorted (pitch, start, end) in seconds. Instruments are merged, as
    note-level evaluation treats them; drum tracks are skipped.
    """
    midi = pretty_midi.PrettyMIDI(str(Path(path)))

    notes = [
        MidiNote(int(note.pitch), float(note.start), float(note.end))
        for instrument in midi.instruments
        if not instrument.is_drum
        for note in instrument.notes
    ]
    notes.sort(key=lambda item: (item.start, item.pitch, item.end))
    return notes
