"""Bit packing (Subbab 2.8.5). Token fields are not multiples of eight bits, so
they are written end to end and the stream is cut into bytes afterwards, with
only the last byte padded. MSB first.
"""

from __future__ import annotations


class BitWriter:
    """Packs unsigned integer fields into a bit stream.

    >>> w = BitWriter()
    >>> w.write(0b101, 3)
    >>> w.write(0b11, 2)
    >>> w.to_bytes().hex()      # 10111 padded to 10111000
    'b8'
    """

    __slots__ = ("_buf", "_cur", "_nbits", "_total")

    def __init__(self) -> None:
        self._buf = bytearray()
        self._cur = 0  # bits accumulated but not yet flushed to _buf
        self._nbits = 0  # how many bits are in _cur, always < 8
        self._total = 0

    def write(self, value: int, width: int) -> None:
        for shift in range(width - 1, -1, -1):
            self._cur = (self._cur << 1) | ((value >> shift) & 1)
            self._nbits += 1
            if self._nbits == 8:
                self._buf.append(self._cur)
                self._cur = 0
                self._nbits = 0
        self._total += width

    @property
    def bit_length(self) -> int:
        """Bits written, excluding padding."""
        return self._total

    @property
    def padding_bits(self) -> int:
        return (-self._total) % 8

    def to_bytes(self) -> bytes:
        if self._nbits == 0:
            return bytes(self._buf)
        return bytes(self._buf) + bytes([self._cur << (8 - self._nbits)])


class BitReader:
    """Reads fields back out of a bit stream.

    >>> BitReader(bytes.fromhex("b8")).read(3)
    5
    """

    __slots__ = ("_data", "_pos")

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0  # position in bits

    def read(self, width: int) -> int:
        value = 0
        for _ in range(width):
            byte = self._data[self._pos >> 3]
            value = (value << 1) | ((byte >> (7 - (self._pos & 7))) & 1)
            self._pos += 1
        return value

    @property
    def bit_position(self) -> int:
        return self._pos

    @property
    def bits_remaining(self) -> int:
        return len(self._data) * 8 - self._pos
