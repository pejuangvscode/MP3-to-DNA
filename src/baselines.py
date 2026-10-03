"""The three comparison paths of Tabel 3.12.

    B1 direct       raw MP3 bytes through the same DNA codec
    B2 symbolic     transcribed MIDI bytes through the same DNA codec
    B3 theoretical  2 bits per base, no constraints, no error correction

B2 is the decisive one: without it the measured saving cannot be told apart from
the fact that a MIDI file is smaller than an MP3, which was never in doubt. B3
stands outside the decomposition, as context for what the constraints and the
redundancy cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from src import config as cfg
from src import dna_codec as codec


@dataclass(frozen=True)
class BaselineResult:
    """Base count for one comparison path."""

    name: str
    source: str
    input_bytes: int
    total_bases: int
    oligo_count: int  # zero for the theoretical path, which has no oligos
    materialized: bool = True  # whether the oligos were actually built
    addressable: bool = True  # whether a 2-byte oligo index can span them

    @property
    def effective_density(self) -> float:
        """Payload bits per synthesised base (Persamaan 2.2)."""
        return (self.input_bytes * 8) / self.total_bases


def count_bases(input_bytes: int) -> tuple[int, int, int]:
    """Coded bytes, oligos and total bases for a payload, by Persamaan 3.2.

    Pure arithmetic: no oligo is built, so this works for payloads larger than
    the oligo index can address. See encode_file() for why that matters.
    """
    coded = -(-input_bytes // cfg.RS_K) * cfg.RS_N
    return coded, cfg.oligo_count_for(coded), cfg.total_bases_for(coded)


def encode_file(
    path: str | Path, name: str, materialize: bool | None = None
) -> BaselineResult:
    """Count the bases a file would need in DNA, for B1 and B2.

    The count always comes from Persamaan 3.2. Oligos are built as well when
    they fit, which cross-checks the arithmetic against the real codec, but a
    two-minute MP3 needs more oligos than the 2-byte index can address. Counting
    without building is legitimate here since Tabel 3.12 never decodes these
    paths; `addressable` records when the limit was passed.
    """
    path = Path(path)
    data = path.read_bytes()

    coded, oligo_count, total_bases = count_bases(len(data))
    addressable = oligo_count <= cfg.MAX_OLIGO_COUNT
    if materialize is None:
        materialize = addressable

    if materialize:
        report = codec.encode(data)
    return BaselineResult(
        name=name,
        source=path.name,
        input_bytes=len(data),
        total_bases=total_bases,
        oligo_count=oligo_count,
        materialized=materialize,
        addressable=addressable,
    )


def direct(mp3_path: str | Path) -> BaselineResult:
    """B1: the naive storage path, raw MP3 bytes into DNA."""
    return encode_file(mp3_path, "B1 direct")


def symbolic(midi_path: str | Path) -> BaselineResult:
    """B2: transcribed MIDI, without quantisation or tokenisation."""
    return encode_file(midi_path, "B2 symbolic")


def theoretical(input_bytes: int, source: str = "-") -> BaselineResult:
    """B3: two bits per base, the absolute ceiling for a four-letter alphabet.

    No constraint compliance and no error correction, so this is not a system
    anyone could build (Subbab 2.3.1). It says what the constraints and the
    redundancy cost.
    """
    bases = math.ceil(input_bytes * 8 / cfg.THEORETICAL_BITS_PER_BASE)
    return BaselineResult(
        name="B3 theoretical",
        source=source,
        input_bytes=input_bytes,
        total_bases=bases,
        oligo_count=0,
    )


def pipeline(packed_tokens: bytes, source: str = "-") -> BaselineResult:
    """The proposed path, for comparison on the same footing as the baselines."""
    report = codec.encode(packed_tokens)
    return BaselineResult(
        name="pipeline",
        source=source,
        input_bytes=len(packed_tokens),
        total_bases=report.total_bases,
        oligo_count=report.oligo_count,
    )
