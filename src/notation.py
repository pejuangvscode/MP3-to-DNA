"""MusicXML export (Subbab 2.6.5). basic-pitch emits MIDI, so this module
produces the notation Bab I calls for.

Deliberately outside the data path: tokens are built from the quantised note
list, not from MusicXML, so this adds no lossy step and cannot affect the token
round-trip.

The format constrains where it can sit. MusicXML records written notation, so
every duration must be expressible as a note value -- it cannot write a note
lasting 0.371 of a beat. Raw transcription output is continuous in time and
music21 rejects it outright, so notation is only possible at or after
quantisation. Bab I methodology step 2 places it before, which cannot be
implemented, and Tabel 3.5 does not list this module yet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from src import config as cfg
from src.quantize import TimedNote
from src.tokenizer import QuantizedNote

# every corpus sample is in 4/4
DEFAULT_TIME_SIGNATURE = "4/4"

# middle C: notes below it go on a bass staff. None keeps one staff.
DEFAULT_SPLIT_PITCH = 60

# shorter than this rounds to a zero-length element, which MusicXML cannot write
MIN_QUARTER_LENGTH = 1.0 / 16.0


def _write(
    events: Sequence[tuple[int, float, float]],
    path: str | Path,
    tempo: float,
    title: str,
    time_signature: str,
    quantize_divisors: tuple[int, ...] | None = None,
    split_pitch: int | None = DEFAULT_SPLIT_PITCH,
) -> Path:
    """Build a score from (pitch, offset, duration) in quarter lengths.

    `quantize_divisors` snaps onto note values music21 can write, needed for
    continuous input. `split_pitch` puts low notes on a bass staff, but only
    when the material actually crosses it.
    """
    # music21 is slow to import, so it is loaded only when notation is actually
    # written rather than on every `import src.notation`.
    from music21 import clef, metadata, meter, note, stream
    from music21 import tempo as m21tempo

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    pitches = [pitch for pitch, _, _ in events]
    use_two_staves = (
        split_pitch is not None
        and min(pitches) < split_pitch <= max(pitches)
    )

    score = stream.Score()
    score.insert(0, metadata.Metadata(title=title))

    treble = stream.Part()
    parts = [treble]
    if use_two_staves:
        bass = stream.Part()
        bass.insert(0.0, clef.BassClef())
        parts.append(bass)

    for part in parts:
        part.insert(0.0, m21tempo.MetronomeMark(number=tempo))
        part.insert(0.0, meter.TimeSignature(time_signature))

    for pitch, offset, duration in events:
        target = (
            parts[1] if use_two_staves and pitch < split_pitch else treble
        )
        target.insert(offset, note.Note(midi=pitch, quarterLength=duration))

    for part in parts:
        if quantize_divisors:
            part.quantize(
                quarterLengthDivisors=quantize_divisors,
                processOffsets=True,
                processDurations=True,
                inPlace=True,
            )
        score.insert(0, part)
    score.write("musicxml", fp=str(path))
    return path


def write_from_quantized(
    notes: Sequence[QuantizedNote],
    path: str | Path,
    tempo: float,
    grid_code: int = cfg.DEFAULT_GRID_CODE,
    title: str = "Quantised transcription",
    time_signature: str = DEFAULT_TIME_SIGNATURE,
) -> Path:
    """Write grid-aligned notes as MusicXML.

    One grid unit is one beat divided by the resolution's subdivision count, so
    at the 1/16 resolution it is a quarter of a quarter note.
    """
    units_per_quarter = cfg.GRID_SUBDIVISIONS[grid_code]
    events = [
        (
            note.pitch,
            note.position / units_per_quarter,
            note.duration / units_per_quarter,
        )
        for note in notes
    ]
    return _write(events, path, tempo, title, time_signature)


def write_from_transcribed(
    notes: Sequence[TimedNote],
    path: str | Path,
    tempo: float,
    grid_code: int = cfg.DEFAULT_GRID_CODE,
    title: str = "Transcription",
    time_signature: str = DEFAULT_TIME_SIGNATURE,
) -> Path:
    """Transcription output as MusicXML, snapped to notatable values.

    Not a verbatim rendering: basic-pitch reports continuous times and MusicXML
    cannot write them, so music21 snaps offsets and durations to the grid first.
    That snapping is music21's own and need not agree with src.quantize note for
    note; neither feeds the token path, so any difference only affects how the
    notation looks.
    """
    seconds_per_quarter = 60.0 / tempo
    events = [
        (
            int(round(note.pitch)),
            note.start / seconds_per_quarter,
            max(note.end - note.start, 0.0) / seconds_per_quarter,
        )
        for note in notes
    ]
    return _write(
        events,
        path,
        tempo,
        title,
        time_signature,
        quantize_divisors=(cfg.GRID_SUBDIVISIONS[grid_code],),
    )
