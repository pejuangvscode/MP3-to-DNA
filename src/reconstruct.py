"""Recovered tokens -> MIDI (Tabel 3.5).

The last stage of the decoding path. Grid positions become seconds again using
the tempo carried in the token header, so reconstruction needs nothing beyond
what the DNA sequence itself supplied.

Two things the token scheme does not store, and therefore cannot restore:

*Velocity.* Tabel 3.8 has no field for it, so every reconstructed note gets one
fixed value. Subbab 3.2.5 has FL Studio's humanisation vary onset *and*
velocity, so the velocity variation is discarded here. Subbab 2.8.2 maps the
lossy stages to transcription and quantisation; velocity is a third, lost at
tokenisation. It changes no reported metric, since note-level evaluation
(Subbab 2.9.1) matches on pitch and timing only.

*Instrument separation.* Tokens carry no channel, so the two instruments of a
corpus sample come back merged into one track. Again harmless for the metrics,
which compare flat note lists, but it means the reconstructed MIDI is not a
score.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple, Sequence

import pretty_midi

from src import config as cfg
from src.quantize import to_seconds
from src.tokenizer import QuantizedNote

#: Fixed velocity for every reconstructed note, mid-range in MIDI's 1..127.
RECONSTRUCTION_VELOCITY = 80

#: Acoustic grand piano. Arbitrary: the token scheme stores no instrument.
RECONSTRUCTION_PROGRAM = 0


class ReconstructionError(ValueError):
    """The token stream cannot be turned into notation."""


class MidiNote(NamedTuple):
    """A note read from a MIDI file, in seconds.

    Named fields so it drops straight into :func:`src.quantize.quantize`, which
    reads `.pitch`, `.start` and `.end`; still a plain tuple for the evaluation
    code, which unpacks it positionally.
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
    if not notes:
        raise ReconstructionError("nothing to reconstruct: the note list is empty")

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
    """Read a MIDI file as a flat, sorted list of (pitch, start, end) in seconds.

    Instruments are merged, matching how note-level evaluation treats them
    (Subbab 2.7.4: polyphonic transcription reports every sounding note without
    attributing it to a source). Drum tracks are skipped, having no pitch in the
    usual sense.
    """
    path = Path(path)
    if not path.is_file():
        raise ReconstructionError(f"no such MIDI file: {path}")

    try:
        midi = pretty_midi.PrettyMIDI(str(path))
    except Exception as exc:
        raise ReconstructionError(f"cannot read {path.name}: {exc}") from exc

    notes = [
        MidiNote(int(note.pitch), float(note.start), float(note.end))
        for instrument in midi.instruments
        if not instrument.is_drum
        for note in instrument.notes
    ]
    notes.sort(key=lambda item: (item.start, item.pitch, item.end))
    return notes
