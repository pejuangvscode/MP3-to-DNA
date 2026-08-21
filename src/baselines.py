"""The three comparison paths of Tabel 3.12.

Measuring savings against one baseline only would confuse two different things:
that transcription replaces a signal with a symbol stream, and that the token
scheme then compresses that stream. Both shrink the base count, and the report
needs them apart.

    B1, direct       raw MP3 bytes through the same DNA codec
    B2, symbolic     transcribed MIDI bytes through the same DNA codec
    B3, theoretical  2 bits per base, no constraints, no error correction

B2 is the decisive one. Without it, the measured saving cannot be told apart
from the fact that a MIDI file is smaller than an MP3, which was never in doubt
and is not this study's contribution.

B3 stands outside the decomposition. It is context: how many bases go to
satisfying the biological constraints and carrying redundancy, rather than to
data.
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
    the oligo index can address. See :func:`encode_file` for why that matters.
    """
    coded = -(-input_bytes // cfg.RS_K) * cfg.RS_N
    return coded, cfg.oligo_count_for(coded), cfg.total_bases_for(coded)


def encode_file(
    path: str | Path, name: str, materialize: bool | None = None
) -> BaselineResult:
    """Count the bases a file's raw bytes would need in DNA.

    Used for B1 and B2, both of which go through exactly the codec the pipeline
    uses, so the comparison isolates payload size and nothing else.

    The base count comes from Persamaan 3.2 either way. The oligos themselves
    are built when they can be, which double-checks the arithmetic against the
    real codec, but that is not always possible: a 2-byte oligo index
    (Tabel 3.10) addresses 65536 oligos, or about 1.59 MiB of payload, which at
    192 kbps is only 69 seconds of MP3. Tabel 3.4 asks for two-minute samples,
    so B1 for the longest ones cannot be built at all.

    Counting them anyway is legitimate: Tabel 3.12 uses these paths to compare
    base counts, never to decode. The addressing limit is a separate design
    parameter, and `addressable` records when it was exceeded.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")

    data = path.read_bytes()
    if not data:
        raise ValueError(f"{path.name} is empty")

    coded, oligo_count, total_bases = count_bases(len(data))
    addressable = oligo_count <= cfg.MAX_OLIGO_COUNT
    if materialize is None:
        materialize = addressable
    if materialize and not addressable:
        raise ValueError(
            f"{path.name} needs {oligo_count:,} oligos, more than the "
            f"{cfg.MAX_OLIGO_COUNT:,} a {cfg.OLIGO_INDEX_BYTES}-byte index can "
            "address; pass materialize=False to count bases without building them"
        )

    if materialize:
        report = codec.encode(data)
        # The arithmetic and the codec must agree; a mismatch means one of them
        # is wrong about the oligo layout.
        assert report.total_bases == total_bases, (
            f"Persamaan 3.2 gives {total_bases} bases but the codec produced "
            f"{report.total_bases}"
        )

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
    if input_bytes <= 0:
        raise ValueError("input_bytes must be positive")
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
    if not packed_tokens:
        raise ValueError("packed token stream is empty")
    report = codec.encode(packed_tokens)
    return BaselineResult(
        name="pipeline",
        source=source,
        input_bytes=len(packed_tokens),
        total_bases=report.total_bases,
        oligo_count=report.oligo_count,
    )
