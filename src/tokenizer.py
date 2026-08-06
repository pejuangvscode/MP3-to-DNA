"""Quantised notes <-> feature tokens <-> packed bytes.

Implements the token scheme of Subbab 3.3.3 and the repeat detection of
Subbab 3.3.4. Two token types share one stream, told apart by a leading type
bit: a note token (22 bits) carrying one note, and a reference token (17 bits)
standing in for a run of earlier tokens.

Note onsets are stored as a delta against the previous note rather than as an
absolute position. That is what makes two musically identical phrases produce
identical token sequences wherever they occur, which repeat detection depends
on (Subbab 3.3.3).

The whole module is integer arithmetic: no audio, no model, no I/O. It is the
part of the pipeline that has to be exactly lossless, so it is also the part
that is tested first (Subbab 3.2.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, NamedTuple, Sequence, Union

from src import config as cfg
from src.bitio import BitReader, BitWriter


class TokenRangeError(ValueError):
    """A value does not fit the field width the token scheme allots it."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class QuantizedNote(NamedTuple):
    """One note after grid alignment (Tabel 3.6)."""

    pitch: int  # MIDI note number, 0..127
    position: int  # onset in grid units from the start, non-negative
    duration: int  # length in grid units, 1..64


class NoteToken(NamedTuple):
    """A single note (Tabel 3.8, 22 bits)."""

    pitch: int  # 0..127
    delta: int  # grid units since the previous note, 0..255
    duration: int  # 1..64


class ReferenceToken(NamedTuple):
    """A back-reference to earlier tokens (Tabel 3.9, 17 bits)."""

    distance: int  # tokens to look back, 1..1024
    length: int  # tokens to copy, 2..65


Token = Union[NoteToken, ReferenceToken]


class TokenStats(NamedTuple):
    """Counts behind the efficiency figures of Subbab 3.3.5."""

    note_tokens: int
    reference_tokens: int
    total_tokens: int
    payload_bits: int  # header plus tokens, before byte padding
    payload_bytes: int  # what actually reaches the DNA codec


@dataclass(frozen=True)
class EncodedTokens:
    data: bytes
    tokens: tuple[Token, ...]
    stats: TokenStats


@dataclass(frozen=True)
class DecodedTokens:
    notes: tuple[QuantizedNote, ...]
    tempo: int
    grid_code: int
    tokens: tuple[Token, ...]
    stats: TokenStats


# ---------------------------------------------------------------------------
# Delta encoding
# ---------------------------------------------------------------------------


def notes_to_tokens(notes: Sequence[QuantizedNote]) -> list[NoteToken]:
    """Turn quantised notes into note tokens, onsets as deltas.

    Notes must already be sorted by position then pitch, as the quantisation
    step of Subbab 3.3.4 leaves them.
    """
    tokens: list[NoteToken] = []
    previous_position = 0

    for index, note in enumerate(notes):
        if not cfg.MIN_PITCH <= note.pitch <= cfg.MAX_PITCH:
            raise TokenRangeError(
                f"note {index}: pitch {note.pitch} is outside "
                f"{cfg.MIN_PITCH}..{cfg.MAX_PITCH}"
            )
        if not cfg.MIN_DURATION_UNITS <= note.duration <= cfg.MAX_DURATION_UNITS:
            raise TokenRangeError(
                f"note {index}: duration {note.duration} is outside "
                f"{cfg.MIN_DURATION_UNITS}..{cfg.MAX_DURATION_UNITS} grid units; "
                "quantisation should have clamped it"
            )

        delta = note.position - previous_position
        if delta < 0:
            raise TokenRangeError(
                f"note {index}: position {note.position} precedes the previous "
                f"note at {previous_position}; notes must be sorted by position"
            )
        if delta > cfg.MAX_DELTA_UNITS:
            # No token can span a longer rest, and the scheme has no filler
            # token to break one up. Bab III treats this range as far beyond
            # what is needed; if a real sample ever trips it, the fix is a
            # schema change (an extra token type) reported in Bab IV, not a
            # silent clamp, which would shift every later onset.
            raise TokenRangeError(
                f"note {index}: rest of {delta} grid units exceeds the "
                f"{cfg.MAX_DELTA_UNITS}-unit limit of the delta field "
                f"({cfg.NOTE_DELTA_BITS} bits)"
            )

        tokens.append(NoteToken(note.pitch, delta, note.duration))
        previous_position = note.position

    return tokens


def tokens_to_notes(tokens: Iterable[NoteToken]) -> list[QuantizedNote]:
    """Rebuild absolute positions from delta-encoded note tokens."""
    notes: list[QuantizedNote] = []
    position = 0
    for token in tokens:
        position += token.delta
        notes.append(QuantizedNote(token.pitch, position, token.duration))
    return notes


# ---------------------------------------------------------------------------
# Repeat detection (Subbab 3.3.4)
# ---------------------------------------------------------------------------


def compress(tokens: Sequence[NoteToken]) -> list[Token]:
    """Replace repeated runs with back-references, LZ77 style.

    Greedy longest match, as specified: at each position take the longest run
    within the sliding window, emit a reference for it, and jump past it;
    otherwise emit the note token and advance by one.

    Two tokens match only when pitch, delta and duration are all equal, so
    expansion always reproduces the original exactly. A phrase that repeats
    musically but enters after a different rest has a different first delta and
    will not match. That failure is conservative: it costs savings, never
    correctness (Subbab 3.3.4).

    Matches may run past the current position. That is deliberate and matches
    the LZ77 property noted in Subbab 2.8.4: the decoder copies one token at a
    time out of the output it is building, so a reference whose distance is
    shorter than its length keeps reading tokens the copy itself just wrote.
    """
    output: list[Token] = []
    # (token, next token) -> positions where that pair starts, ascending.
    # Keyed on a pair because the minimum match is two tokens.
    chain: dict[tuple[NoteToken, NoteToken], list[int]] = {}
    count = len(tokens)
    position = 0

    while position < count:
        best_length = 0
        best_distance = 0

        if position + 1 < count:
            key = (tokens[position], tokens[position + 1])
            limit = min(cfg.LZ77_MAX_MATCH, count - position)
            # Most recent candidate first, so distance grows as we iterate and
            # we can stop as soon as it leaves the window.
            for candidate in reversed(chain.get(key, ())):
                distance = position - candidate
                if distance > cfg.LZ77_WINDOW:
                    break
                length = 0
                while (
                    length < limit
                    and tokens[candidate + length] == tokens[position + length]
                ):
                    length += 1
                if length > best_length:
                    best_length, best_distance = length, distance
                    if best_length == cfg.LZ77_MAX_MATCH:
                        break  # cannot do better

        if best_length >= cfg.LZ77_MIN_MATCH:
            output.append(ReferenceToken(best_distance, best_length))
            advance = best_length
        else:
            output.append(tokens[position])
            advance = 1

        # Every position just consumed exists in the expanded stream, so it can
        # serve as a future match target even when it sat inside a reference.
        for scanned in range(position, position + advance):
            if scanned + 1 < count:
                chain.setdefault(
                    (tokens[scanned], tokens[scanned + 1]), []
                ).append(scanned)

        position += advance

    return output


def expand(tokens: Iterable[Token]) -> list[NoteToken]:
    """Undo :func:`compress`, copying one token at a time.

    Copying token by token out of the growing output is what lets a reference
    whose distance is shorter than its length unroll a repeating figure.
    """
    output: list[NoteToken] = []

    for index, token in enumerate(tokens):
        if isinstance(token, NoteToken):
            output.append(token)
            continue

        if token.distance > len(output):
            raise TokenRangeError(
                f"token {index}: reference reaches {token.distance} tokens back "
                f"but only {len(output)} have been produced"
            )
        start = len(output) - token.distance
        for step in range(token.length):
            output.append(output[start + step])

    return output


# ---------------------------------------------------------------------------
# Bit packing (Tabel 3.7, 3.8, 3.9)
# ---------------------------------------------------------------------------


def pack(tokens: Sequence[Token], tempo: int, grid_code: int) -> tuple[bytes, int]:
    """Serialise header and tokens into bytes.

    Returns the bytes and the bit count before padding, which the efficiency
    figures need.
    """
    if not isinstance(tempo, int):
        raise TokenRangeError(f"tempo must be an integer BPM, got {tempo!r}")
    if not cfg.MIN_TEMPO <= tempo <= cfg.MAX_TEMPO:
        raise TokenRangeError(
            f"tempo {tempo} is outside the header range "
            f"{cfg.MIN_TEMPO}..{cfg.MAX_TEMPO} BPM"
        )
    if grid_code not in cfg.GRID_SUBDIVISIONS:
        raise TokenRangeError(f"unknown grid resolution code {grid_code}")
    if len(tokens) > cfg.MAX_TOKEN_COUNT:
        raise TokenRangeError(
            f"{len(tokens)} tokens exceeds the {cfg.MAX_TOKEN_COUNT} the header "
            f"can count in {cfg.HEADER_TOKEN_COUNT_BITS} bits"
        )

    writer = BitWriter()
    writer.write(cfg.SCHEMA_VERSION, cfg.HEADER_VERSION_BITS)
    writer.write(tempo - cfg.TEMPO_OFFSET, cfg.HEADER_TEMPO_BITS)
    writer.write(grid_code, cfg.HEADER_GRID_BITS)
    writer.write(len(tokens), cfg.HEADER_TOKEN_COUNT_BITS)
    writer.write(0, cfg.HEADER_PADDING_BITS)

    for token in tokens:
        if isinstance(token, NoteToken):
            writer.write(cfg.TOKEN_TYPE_NOTE, cfg.TOKEN_TYPE_BITS)
            writer.write(token.pitch, cfg.NOTE_PITCH_BITS)
            writer.write(token.delta, cfg.NOTE_DELTA_BITS)
            writer.write(
                token.duration - cfg.NOTE_DURATION_OFFSET, cfg.NOTE_DURATION_BITS
            )
        else:
            writer.write(cfg.TOKEN_TYPE_REFERENCE, cfg.TOKEN_TYPE_BITS)
            writer.write(
                token.distance - cfg.REF_DISTANCE_OFFSET, cfg.REF_DISTANCE_BITS
            )
            writer.write(token.length - cfg.REF_LENGTH_OFFSET, cfg.REF_LENGTH_BITS)

    return writer.to_bytes(), writer.bit_length


def unpack(data: bytes) -> tuple[list[Token], int, int, int]:
    """Read back header and tokens.

    Returns tokens, tempo, grid code, and the bit count consumed. Trailing
    bytes are ignored: the header states how many tokens follow, which makes
    the stream self-delimiting and lets the DNA layer pad freely.
    """
    reader = BitReader(data)
    version = reader.read(cfg.HEADER_VERSION_BITS)
    if version != cfg.SCHEMA_VERSION:
        raise TokenRangeError(
            f"token schema version {version}, expected {cfg.SCHEMA_VERSION}"
        )
    tempo = reader.read(cfg.HEADER_TEMPO_BITS) + cfg.TEMPO_OFFSET
    grid_code = reader.read(cfg.HEADER_GRID_BITS)
    token_count = reader.read(cfg.HEADER_TOKEN_COUNT_BITS)
    reader.read(cfg.HEADER_PADDING_BITS)

    tokens: list[Token] = []
    for index in range(token_count):
        try:
            if reader.read(cfg.TOKEN_TYPE_BITS) == cfg.TOKEN_TYPE_NOTE:
                pitch = reader.read(cfg.NOTE_PITCH_BITS)
                delta = reader.read(cfg.NOTE_DELTA_BITS)
                duration = reader.read(cfg.NOTE_DURATION_BITS)
                tokens.append(
                    NoteToken(pitch, delta, duration + cfg.NOTE_DURATION_OFFSET)
                )
            else:
                distance = reader.read(cfg.REF_DISTANCE_BITS)
                length = reader.read(cfg.REF_LENGTH_BITS)
                tokens.append(
                    ReferenceToken(
                        distance + cfg.REF_DISTANCE_OFFSET,
                        length + cfg.REF_LENGTH_OFFSET,
                    )
                )
        except EOFError as exc:
            raise TokenRangeError(
                f"stream ended while reading token {index} of {token_count}"
            ) from exc

    return tokens, tempo, grid_code, reader.bit_position


# ---------------------------------------------------------------------------
# Whole-module entry points
# ---------------------------------------------------------------------------


def _stats(tokens: Sequence[Token], bits: int, data: bytes) -> TokenStats:
    notes = sum(1 for token in tokens if isinstance(token, NoteToken))
    return TokenStats(
        note_tokens=notes,
        reference_tokens=len(tokens) - notes,
        total_tokens=len(tokens),
        payload_bits=bits,
        payload_bytes=len(data),
    )


def encode_notes(
    notes: Sequence[QuantizedNote],
    tempo: int,
    grid_code: int = cfg.DEFAULT_GRID_CODE,
    use_repeat_detection: bool = True,
) -> EncodedTokens:
    """Quantised notes -> packed bytes.

    `use_repeat_detection` switches LZ77 off, which is how Subbab 3.3.5
    isolates what repeat detection contributes: run the same corpus twice and
    compare token counts.
    """
    note_tokens = notes_to_tokens(notes)
    tokens: list[Token] = (
        compress(note_tokens) if use_repeat_detection else list(note_tokens)
    )
    data, bits = pack(tokens, tempo, grid_code)
    return EncodedTokens(data, tuple(tokens), _stats(tokens, bits, data))


def decode_bytes(data: bytes) -> DecodedTokens:
    """Packed bytes -> quantised notes."""
    tokens, tempo, grid_code, bits = unpack(data)
    notes = tokens_to_notes(expand(tokens))
    return DecodedTokens(
        notes=tuple(notes),
        tempo=tempo,
        grid_code=grid_code,
        tokens=tuple(tokens),
        stats=_stats(tokens, bits, data),
    )
