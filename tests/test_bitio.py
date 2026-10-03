"""Bit writer and reader (Subbab 2.8.5)."""

from __future__ import annotations

import random

import pytest

from src.bitio import BitReader, BitWriter


def test_fields_read_back_as_written():
    writer = BitWriter()
    writer.write(0b101, 3)
    writer.write(0b11, 2)
    assert writer.bit_length == 5
    assert writer.to_bytes() == bytes([0b10111000])  # padded to a byte

    reader = BitReader(writer.to_bytes())
    assert reader.read(3) == 0b101
    assert reader.read(2) == 0b11


def test_fields_of_odd_width_pack_without_gaps():
    """22-bit and 17-bit tokens must sit end to end, not on byte boundaries."""
    writer = BitWriter()
    writer.write(1, 22)
    writer.write(1, 17)
    assert writer.bit_length == 39
    assert len(writer.to_bytes()) == 5  # 39 bits -> 5 bytes, 1 bit of padding
    assert writer.padding_bits == 1


def test_random_field_sequence_round_trips():
    rng = random.Random(20260806)
    for _ in range(200):
        fields = [
            (rng.randrange(1 << width), width)
            for width in (rng.randrange(1, 17) for _ in range(rng.randrange(1, 40)))
        ]
        writer = BitWriter()
        for value, width in fields:
            writer.write(value, width)

        reader = BitReader(writer.to_bytes())
        assert [(reader.read(width), width) for _, width in fields] == fields


def test_zero_width_is_a_no_op():
    writer = BitWriter()
    writer.write(0, 0)
    assert writer.bit_length == 0
    assert writer.to_bytes() == b""


