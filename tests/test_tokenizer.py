"""Token scheme, repeat detection, and bit packing (Subbab 3.3.3, 3.3.4).

The round-trip tests verify the requirement Subbab 3.2.3 calls decisive: tokens
recovered after decoding must be bit-identical to those before encoding.
"""

from __future__ import annotations

import random

import pytest

from src import config as cfg
from src.tokenizer import (
    NoteToken,
    QuantizedNote,
    ReferenceToken,
    compress,
    decode_bytes,
    encode_notes,
    expand,
    notes_to_tokens,
    pack,
    tokens_to_notes,
    unpack,
)


def make_phrase(start: int = 0) -> list[QuantizedNote]:
    """A four-note figure, one bar at 1/16 resolution."""
    return [
        QuantizedNote(60, start + 0, 4),
        QuantizedNote(64, start + 4, 4),
        QuantizedNote(67, start + 8, 4),
        QuantizedNote(72, start + 12, 4),
    ]


def random_notes(rng: random.Random, count: int) -> list[QuantizedNote]:
    notes: list[QuantizedNote] = []
    position = rng.randrange(0, 16)
    for _ in range(count):
        notes.append(
            QuantizedNote(
                rng.randrange(36, 96),
                position,
                rng.randrange(1, cfg.MAX_DURATION_UNITS + 1),
            )
        )
        position += rng.randrange(0, 17)
    return notes


# --- delta encoding ---

def test_first_delta_is_the_absolute_position():
    tokens = notes_to_tokens([QuantizedNote(60, 12, 4)])
    assert tokens == [NoteToken(60, 12, 4)]


def test_identical_phrases_produce_identical_tokens():
    """The property repeat detection depends on (Subbab 3.3.3)."""
    early = notes_to_tokens(make_phrase(0))
    later = notes_to_tokens(make_phrase(64))
    # The very first delta differs because it carries the absolute onset; from
    # the second note on, the two phrases are token-for-token identical.
    assert early[1:] == later[1:]


def test_delta_round_trip():
    rng = random.Random(11)
    notes = random_notes(rng, 200)
    assert tokens_to_notes(notes_to_tokens(notes)) == notes


# --- repeat detection ---

def test_repeated_phrase_becomes_a_reference():
    notes = make_phrase(0) + make_phrase(16)
    tokens = notes_to_tokens(notes)
    compressed = compress(tokens)

    assert any(isinstance(token, ReferenceToken) for token in compressed)
    assert len(compressed) < len(tokens)
    assert expand(compressed) == tokens


def test_reference_shorter_than_its_length_unrolls_correctly():
    """Distance below length is legal, and lets a repeating figure collapse to
    a single reference.
    """
    unit = [NoteToken(60, 4, 2), NoteToken(62, 2, 2)]
    tokens = unit * 10
    compressed = compress(tokens)

    references = [t for t in compressed if isinstance(t, ReferenceToken)]
    assert references, "a periodic sequence should compress"
    assert min(r.distance for r in references) < max(r.length for r in references)
    assert expand(compressed) == tokens


def test_compression_never_grows_the_stream():
    """A 17-bit reference always replaces at least 44 bits of note tokens."""
    rng = random.Random(7)
    for _ in range(50):
        tokens = notes_to_tokens(random_notes(rng, rng.randrange(2, 300)))
        compressed = compress(tokens)
        plain_bits = len(tokens) * cfg.NOTE_TOKEN_BITS
        compressed_bits = sum(
            cfg.NOTE_TOKEN_BITS
            if isinstance(token, NoteToken)
            else cfg.REFERENCE_TOKEN_BITS
            for token in compressed
        )
        assert compressed_bits <= plain_bits
        assert expand(compressed) == tokens


def test_references_stay_inside_the_window_and_length_limits():
    rng = random.Random(3)
    tokens = notes_to_tokens(random_notes(rng, 400)) * 4
    for token in compress(tokens):
        if isinstance(token, ReferenceToken):
            assert 1 <= token.distance <= cfg.LZ77_WINDOW
            assert cfg.LZ77_MIN_MATCH <= token.length <= cfg.LZ77_MAX_MATCH


# --- packing ---

def test_header_occupies_exactly_four_bytes():
    data, bits = pack([], 120, cfg.DEFAULT_GRID_CODE)
    assert bits == cfg.HEADER_BITS == 32
    assert len(data) == 4


def test_pack_unpack_round_trip():
    tokens = [NoteToken(60, 0, 4), ReferenceToken(1, 2), NoteToken(72, 255, 64)]
    data, _ = pack(tokens, 137, 3)
    recovered, tempo, grid_code, _ = unpack(data)
    assert recovered == tokens
    assert (tempo, grid_code) == (137, 3)


def test_field_extremes_survive_packing():
    tokens = [
        NoteToken(cfg.MIN_PITCH, 0, cfg.MIN_DURATION_UNITS),
        NoteToken(cfg.MAX_PITCH, cfg.MAX_DELTA_UNITS, cfg.MAX_DURATION_UNITS),
        ReferenceToken(1, cfg.LZ77_MIN_MATCH),
        ReferenceToken(cfg.LZ77_WINDOW, cfg.LZ77_MAX_MATCH),
    ]
    data, _ = pack(tokens, cfg.MIN_TEMPO, 0)
    assert unpack(data)[0] == tokens

    data, _ = pack(tokens, cfg.MAX_TEMPO, 3)
    assert unpack(data)[1] == cfg.MAX_TEMPO


def test_trailing_bytes_are_ignored():
    """The header's token count makes the stream self-delimiting.

    The DNA layer pads with zeros, and decoding has to see past that.
    """
    tokens = [NoteToken(60, 0, 4), NoteToken(64, 4, 4)]
    data, _ = pack(tokens, 120, cfg.DEFAULT_GRID_CODE)
    assert unpack(data + bytes(64))[0] == tokens


# --- whole module ---

@pytest.mark.parametrize("use_repeat_detection", [True, False])
def test_notes_survive_the_full_token_round_trip(use_repeat_detection):
    rng = random.Random(99)
    notes = random_notes(rng, 500)
    encoded = encode_notes(
        notes, 120, use_repeat_detection=use_repeat_detection
    )
    decoded = decode_bytes(encoded.data)

    assert list(decoded.notes) == notes
    assert decoded.tempo == 120
    assert decoded.grid_code == cfg.DEFAULT_GRID_CODE


def test_repeat_detection_shrinks_a_repetitive_piece():
    """The measurement Subbab 3.3.5 uses to isolate what LZ77 contributes."""
    notes: list[QuantizedNote] = []
    for bar in range(32):
        notes.extend(make_phrase(bar * 16))

    with_lz77 = encode_notes(notes, 120, use_repeat_detection=True)
    without = encode_notes(notes, 120, use_repeat_detection=False)

    assert with_lz77.stats.reference_tokens > 0
    assert without.stats.reference_tokens == 0
    assert with_lz77.stats.total_tokens < without.stats.total_tokens
    assert len(with_lz77.data) < len(without.data)
    assert list(decode_bytes(with_lz77.data).notes) == notes
