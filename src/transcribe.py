"""Automatic music transcription with basic-pitch (Tabel 3.5, Subbab 3.3.2).

The pre-trained model is used as it stands: no training, no fine-tuning, no
change to its architecture, as the research scope requires. Output is a note
list at the note level of Subbab 2.7.1 -- pitch, start, end -- which is exactly
what tokenisation needs.

Results are cached per audio file and parameter set. Model inference is the one
stage of the pipeline that is not bit-reproducible, especially on GPU, so
caching lets the deterministic stages downstream be rerun and compared against
identical input (Tabel 3.2).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, Sequence

from src import config as cfg


class TranscriptionError(RuntimeError):
    """Transcription could not be produced."""


class TranscribedNote(NamedTuple):
    """One note as the model reports it, in seconds."""

    pitch: int  # MIDI note number
    start: float
    end: float
    amplitude: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class TranscriptionParams:
    """Inference parameters, recorded so results stay attributable."""

    onset_threshold: float = cfg.ONSET_THRESHOLD
    frame_threshold: float = cfg.FRAME_THRESHOLD
    minimum_note_length_ms: float = cfg.MINIMUM_NOTE_LENGTH_MS

    def fingerprint(self) -> str:
        payload = (
            f"{self.onset_threshold}|{self.frame_threshold}|"
            f"{self.minimum_note_length_ms}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def as_dict(self) -> dict[str, float]:
        return {
            "onset_threshold": self.onset_threshold,
            "frame_threshold": self.frame_threshold,
            "minimum_note_length_ms": self.minimum_note_length_ms,
        }


@dataclass(frozen=True)
class Transcription:
    notes: tuple[TranscribedNote, ...]
    params: TranscriptionParams
    source_path: Path
    from_cache: bool = False

    @property
    def note_count(self) -> int:
        return len(self.notes)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def _sorted_notes(raw: Sequence[tuple]) -> tuple[TranscribedNote, ...]:
    """basic-pitch note events -> our note tuples, in a stable order.

    Events arrive as (start, end, pitch, amplitude, pitch_bends). Pitch bends
    are dropped: the token scheme stores integer MIDI note numbers, so bend
    information has nowhere to go and would be discarded at quantisation
    anyway.
    """
    notes = [
        TranscribedNote(
            pitch=int(pitch),
            start=float(start),
            end=float(end),
            amplitude=float(amplitude),
        )
        for start, end, pitch, amplitude, *_ in raw
    ]
    # The model does not guarantee an order; sorting here makes every later
    # stage reproducible.
    notes.sort(key=lambda note: (note.start, note.pitch, note.end))
    return tuple(notes)


def transcribe(
    audio_path: str | Path,
    params: TranscriptionParams | None = None,
    midi_path: str | Path | None = None,
) -> Transcription:
    """Run basic-pitch over an audio file.

    `midi_path`, when given, receives the model's own MIDI output. That file is
    the input to comparison path B2 of Tabel 3.12, which encodes transcribed
    MIDI without quantisation or tokenisation to separate what transcription
    contributes from what the token scheme contributes.
    """
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise TranscriptionError(f"no such audio file: {audio_path}")
    params = params or TranscriptionParams()

    # Imported here rather than at module scope: loading basic-pitch pulls in
    # TensorFlow, which costs seconds and prints banners. Modules that only
    # need the data types above should not pay for it.
    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import predict
    except ImportError as exc:  # pragma: no cover - environment problem
        raise TranscriptionError(f"basic-pitch is not available: {exc}") from exc

    _, midi_data, note_events = predict(
        audio_path,
        ICASSP_2022_MODEL_PATH,
        onset_threshold=params.onset_threshold,
        frame_threshold=params.frame_threshold,
        minimum_note_length=params.minimum_note_length_ms,
    )

    if midi_path is not None:
        midi_path = Path(midi_path)
        midi_path.parent.mkdir(parents=True, exist_ok=True)
        midi_data.write(str(midi_path))

    return Transcription(
        notes=_sorted_notes(note_events),
        params=params,
        source_path=audio_path,
    )


def transcribe_cached(
    audio_path: str | Path,
    cache_dir: str | Path,
    params: TranscriptionParams | None = None,
    midi_path: str | Path | None = None,
) -> Transcription:
    """Transcribe, reusing a stored result when the input has not changed.

    The cache key covers both the audio file's contents and the inference
    parameters, so changing either forces a fresh run.
    """
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise TranscriptionError(f"no such audio file: {audio_path}")
    params = params or TranscriptionParams()

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / (
        f"{audio_path.stem}.{_file_digest(audio_path)}.{params.fingerprint()}.json"
    )

    if cache_file.is_file():
        stored = json.loads(cache_file.read_text())
        return Transcription(
            notes=tuple(TranscribedNote(*note) for note in stored["notes"]),
            params=params,
            source_path=audio_path,
            from_cache=True,
        )

    result = transcribe(audio_path, params, midi_path)
    cache_file.write_text(
        json.dumps(
            {
                "source": audio_path.name,
                "params": params.as_dict(),
                "notes": [list(note) for note in result.notes],
            },
            indent=1,
        )
    )
    return result


def describe(transcription: Transcription) -> dict[str, float | int | str]:
    """Per-sample transcription facts for Bab IV."""
    notes = transcription.notes
    if not notes:
        return {"file": transcription.source_path.name, "notes": 0}
    durations = [note.duration for note in notes]
    return {
        "file": transcription.source_path.name,
        "notes": len(notes),
        "pitch_min": min(note.pitch for note in notes),
        "pitch_max": max(note.pitch for note in notes),
        "shortest_note_ms": round(min(durations) * 1000, 2),
        "median_note_ms": round(sorted(durations)[len(durations) // 2] * 1000, 2),
        "span_s": round(max(note.end for note in notes), 3),
    }
