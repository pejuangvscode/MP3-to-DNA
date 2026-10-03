"""Quantised notes <-> feature tokens <-> packed bytes (Subbab 3.3.3, 3.3.4).

Two token types share one stream, told apart by a leading type bit: a 22-bit
note token, and a 17-bit reference token standing in for a run of earlier
tokens. Onsets are stored as deltas, not absolute positions, so identical
phrases produce identical tokens wherever they occur -- without that, repeat
detection finds nothing.

Pure integer arithmetic, no audio and no model, and the one part of the pipeline
that must be exactly lossless.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, NamedTuple, Sequence, Union

from src import config as cfg
from src.bitio import BitReader, BitWriter


class QuantizedNote(NamedTuple):
    """A note after grid alignment (Tabel 3.6)."""

    pitch: int  # 0..127
    position: int  # onset in grid units from the start
    duration: int  # grid units, 1..64


class NoteToken(NamedTuple):
    """Tabel 3.8, 22 bits."""

    pitch: int  # 0..127
    delta: int  # grid units since the previous note, 0..255
    duration: int  # 1..64


class ReferenceToken(NamedTuple):
    """Tabel 3.9, 17 bits."""

    distance: int  # tokens to look back, 1..1024
    length: int  # tokens to copy, 2..65


Token = Union[NoteToken, ReferenceToken]


class TokenStats(NamedTuple):
    note_tokens: int
    reference_tokens: int
    total_tokens: int
    payload_bits: int  # before byte padding
    payload_bytes: int


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


def notes_to_tokens(notes: Sequence[QuantizedNote]) -> list[NoteToken]:
    """Delta-encode onsets. Notes must arrive sorted by position then pitch."""
    tokens: list[NoteToken] = []
    previous_position = 0

    for note in notes:
        tokens.append(
            NoteToken(note.pitch, note.position - previous_position, note.duration)
        )
        previous_position = note.position

    return tokens


def tokens_to_notes(tokens: Iterable[NoteToken]) -> list[QuantizedNote]:
    """Rebuild absolute positions from deltas."""
    notes: list[QuantizedNote] = []
    position = 0
    for token in tokens:
        position += token.delta
        notes.append(QuantizedNote(token.pitch, position, token.duration))
    return notes


def compress(tokens: Sequence[NoteToken]) -> list[Token]:
    """LZ77 back-references over the token stream, greedy longest match.

    Tokens match only when pitch, delta and duration are all equal, so expansion
    always reproduces the original exactly. A phrase that repeats musically but
    enters after a different rest has a different first delta and will not
    match; that only costs savings, never correctness.

    Matches may run past the current position. The decoder copies one token at a
    time out of the output it is building, so a reference whose distance is
    shorter than its length keeps reading tokens the copy just wrote.
    """
    output: list[Token] = []
    # (token, next token) -> ascending positions. Keyed on a pair because the
    # minimum match is two tokens.
    chain: dict[tuple[NoteToken, NoteToken], list[int]] = {}
    count = len(tokens)
    position = 0

    while position < count:
        best_length = 0
        best_distance = 0

        if position + 1 < count:
            key = (tokens[position], tokens[position + 1])
            limit = min(cfg.LZ77_MAX_MATCH, count - position)
            # most recent first, so distance grows and we can stop at the window
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
                        break

        if best_length >= cfg.LZ77_MIN_MATCH:
            output.append(ReferenceToken(best_distance, best_length))
            advance = best_length
        else:
            output.append(tokens[position])
            advance = 1

        # positions inside a reference still exist in the expanded stream, so
        # they remain valid match targets
        for scanned in range(position, position + advance):
            if scanned + 1 < count:
                chain.setdefault(
                    (tokens[scanned], tokens[scanned + 1]), []
                ).append(scanned)

        position += advance

    return output


def expand(tokens: Iterable[Token]) -> list[NoteToken]:
    """Undo compress(). Copies one token at a time out of the growing output,
    which is what lets distance < length unroll a repeating figure.
    """
    output: list[NoteToken] = []

    for token in tokens:
        if isinstance(token, NoteToken):
            output.append(token)
            continue

        start = len(output) - token.distance
        for step in range(token.length):
            output.append(output[start + step])

    return output


def pack(tokens: Sequence[Token], tempo: int, grid_code: int) -> tuple[bytes, int]:
    """Serialise header and tokens. Returns the bytes and the unpadded bit count."""
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
    """Returns tokens, tempo, grid code, bits consumed.

    Trailing bytes are ignored: the header states how many tokens follow, which
    makes the stream self-delimiting and lets the DNA layer pad freely.
    """
    reader = BitReader(data)
    reader.read(cfg.HEADER_VERSION_BITS)
    tempo = reader.read(cfg.HEADER_TEMPO_BITS) + cfg.TEMPO_OFFSET
    grid_code = reader.read(cfg.HEADER_GRID_BITS)
    token_count = reader.read(cfg.HEADER_TOKEN_COUNT_BITS)
    reader.read(cfg.HEADER_PADDING_BITS)

    tokens: list[Token] = []
    for _ in range(token_count):
        if reader.read(cfg.TOKEN_TYPE_BITS) == cfg.TOKEN_TYPE_NOTE:
            pitch = reader.read(cfg.NOTE_PITCH_BITS)
            delta = reader.read(cfg.NOTE_DELTA_BITS)
            duration = reader.read(cfg.NOTE_DURATION_BITS)
            tokens.append(NoteToken(pitch, delta, duration + cfg.NOTE_DURATION_OFFSET))
        else:
            distance = reader.read(cfg.REF_DISTANCE_BITS)
            length = reader.read(cfg.REF_LENGTH_BITS)
            tokens.append(
                ReferenceToken(
                    distance + cfg.REF_DISTANCE_OFFSET,
                    length + cfg.REF_LENGTH_OFFSET,
                )
            )

    return tokens, tempo, grid_code, reader.bit_position


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
    """Quantised notes -> packed bytes. Turning off repeat detection is how
    Subbab 3.3.5 isolates what LZ77 contributes: run twice, compare.
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
