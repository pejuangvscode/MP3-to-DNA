"""MusicXML export (Subbab 2.6.5).

Bab I lists MusicXML among the pipeline's representations, and the Batasan
Masalah names it as the symbolic form extracted from audio. basic-pitch emits
MIDI rather than MusicXML, so this module produces it.

MusicXML sits deliberately *outside* the data path. Tokens are built from the
quantised note list, not from MusicXML, so this stage adds no lossy step of its
own and cannot affect the token round-trip. It writes an artefact for reading
and for the report; nothing downstream reads it back.

A property of the format constrains where it can sit. MusicXML records written
notation, so every duration has to be expressible as a note value; it has no way
to write a note lasting 0.371 of a beat. Raw transcription output is continuous
in time and therefore cannot be notated as it stands -- music21 rejects it
outright. Notation is only possible at or after quantisation.

Report revisions required:
  - Tabel 3.5 lists eight modules and does not yet include this one.
  - Bab I, methodology step 2, places MusicXML notation *before* quantisation
    (transcribe -> notate -> quantise). That ordering cannot be implemented,
    for the reason above. MusicXML has to follow quantisation, which is also
    why Bab III uses MIDI throughout: MIDI stores performance events and takes
    arbitrary times, MusicXML stores notation and does not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from src import config as cfg
from src.quantize import TimedNote
from src.tokenizer import QuantizedNote

#: Every corpus sample is written in 4/4 (Subbab 3.2.5).
DEFAULT_TIME_SIGNATURE = "4/4"

#: Notes below this go on a bass staff, the rest on a treble staff. Middle C,
#: the usual place to split a piano grand staff.
#:
#: Transcription output spans a wide range and stacks several notes at once, and
#: forcing that onto one staff produces ledger lines in both directions and
#: every voice crowded into a single system. Splitting does not reduce the
#: polyphony, but it does stop the two halves of the range fighting for the same
#: staff. Set to None to keep everything on one staff.
DEFAULT_SPLIT_PITCH = 60

#: Notes shorter than this in quarter lengths would round to a zero-length
#: element, which MusicXML has no way to write. A 1/64 note is far below the
#: 1/16 grid, so this only ever catches degenerate input.
MIN_QUARTER_LENGTH = 1.0 / 16.0


class NotationError(ValueError):
    """The note list cannot be written as notation."""


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

    `quantize_divisors`, when given, snaps offsets and durations onto note
    values music21 can write. Needed for continuous input; harmless but
    unnecessary for input that already sits on the grid.

    `split_pitch` puts low notes on a bass staff and the rest on a treble staff,
    but only when the material actually crosses it; a melody that sits entirely
    on one side stays on one staff.
    """
    # music21 is slow to import, so it is loaded only when notation is actually
    # written rather than on every `import src.notation`.
    from music21 import clef, metadata, meter, note, stream
    from music21 import tempo as m21tempo

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    for pitch, offset, duration in events:
        if duration < MIN_QUARTER_LENGTH:
            raise NotationError(
                f"note at offset {offset:.3f} has duration {duration:.4f} "
                "quarter lengths, too short to notate"
            )

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
    try:
        score.write("musicxml", fp=str(path))
    except Exception as exc:  # music21 raises its own exception hierarchy
        raise NotationError(
            f"music21 could not notate this score: {exc}. Durations must be "
            "expressible as note values; continuous times need quantising first."
        ) from exc
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
    if not notes:
        raise NotationError("nothing to notate: the note list is empty")

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
    """Write transcription output as MusicXML, snapped to notatable values.

    This is the artefact Bab I describes as symbolic notation obtained directly
    from audio. It cannot be a verbatim rendering of the model's output: the
    times basic-pitch reports are continuous, and MusicXML has no way to write
    them. Offsets and durations are therefore snapped to the grid resolution by
    music21 before the file is written.

    The snapping is music21's own, applied to the raw times, and is independent
    of :mod:`src.quantize`. The two need not agree note for note, and neither
    feeds the token path, so any difference between them affects only what the
    notation looks like.
    """
    if not notes:
        raise NotationError("nothing to notate: the note list is empty")

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
