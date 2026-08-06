"""Repeatability of the deterministic half of the pipeline (Tabel 3.2).

Everything from tokenisation onward must produce byte-identical output for
identical input. The scrambling keystream is the one place where that could
quietly break, so it is pinned to a stored digest as well: a change to the
generator changes every sequence the study reports, and should have to be a
deliberate edit rather than a side effect of a library upgrade.
"""

from __future__ import annotations

import hashlib
import random

from src import config as cfg
from src import dna_codec as codec
from src.tokenizer import QuantizedNote, encode_notes


def corpus_notes() -> list[QuantizedNote]:
    rng = random.Random(4242)
    notes: list[QuantizedNote] = []
    position = 0
    for _ in range(400):
        notes.append(
            QuantizedNote(rng.randrange(48, 84), position, rng.randrange(1, 17))
        )
        position += rng.randrange(1, 9)
    return notes


def test_token_encoding_is_repeatable():
    notes = corpus_notes()
    assert encode_notes(notes, 120).data == encode_notes(notes, 120).data


def test_dna_encoding_is_repeatable():
    data = encode_notes(corpus_notes(), 120).data
    assert codec.encode(data).oligos == codec.encode(data).oligos


def test_keystream_is_pinned():
    """Golden value for the SHA-256 keystream (Subbab 2.3.5)."""
    stream = codec.scramble(bytes(cfg.OLIGO_DATA_BYTES), 0, 0)
    assert stream.hex() == (
        "8d62d26d5705f1b824e31bc191a0d1f40c24dfd18ac63cc23d0babaad5"
    ), "scrambling keystream changed; every reported sequence changes with it"


def test_pipeline_output_is_pinned():
    """Golden digest of the FASTA produced for a fixed note sequence."""
    data = encode_notes(corpus_notes(), 120).data
    joined = "\n".join(codec.encode(data).oligos).encode()
    assert hashlib.sha256(joined).hexdigest() == (
        "2b236d6cfe7130e7c04ea2c9138982484aed192b5042e25c926250af5212b2a0"
    ), "pipeline output changed; confirm the change was intended"
