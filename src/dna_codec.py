"""Packed bytes <-> constraint-compliant DNA, written as FASTA (Subbab 3.3.4).

    Reed-Solomon -> fragmentation -> scrambling -> bit to trit ->
    rotating code -> GC screening -> primers

Compliance is by construction, not by filtering afterwards: the rotating code
always picks a base differing from its predecessor, and scrambling drives the
base distribution near uniform so GC settles around 50%. Screening only catches
the rare oligo that still falls outside the window.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import reedsolo
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from src import config as cfg

# written next to a FASTA so losslessness can be checked later
PAYLOAD_MANIFEST_SUFFIX = ".payload.json"


def gc_fraction(sequence: str) -> float:
    """Persamaan 2.4, as a fraction."""
    return (sequence.count("G") + sequence.count("C")) / len(sequence)


def max_homopolymer(sequence: str) -> int:
    if not sequence:
        return 0
    longest = run = 1
    for previous, current in zip(sequence, sequence[1:]):
        run = run + 1 if current == previous else 1
        longest = max(longest, run)
    return longest


def _keystream(index: int, seed_counter: int, length: int) -> bytes:
    """SHA-256 in counter mode. Not `random`, whose stream is not stable across
    Python versions; repeatability (Tabel 3.2) needs a generator fixed by
    algorithm, and the seed must be rebuildable from the oligo header.
    """
    seed = cfg.SCRAMBLE_DOMAIN + index.to_bytes(2, "big") + bytes([seed_counter])
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        stream += hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return bytes(stream[:length])


def scramble(data: bytes, index: int, seed_counter: int) -> bytes:
    """XOR with the keystream. Its own inverse."""
    keystream = _keystream(index, seed_counter, len(data))
    return bytes(a ^ b for a, b in zip(data, keystream))


def block_to_trits(block: bytes) -> list[int]:
    """16 bytes -> 81 trits, most significant first."""
    value = int.from_bytes(block, "big")
    trits = [0] * cfg.BLOCK_TRITS
    for position in range(cfg.BLOCK_TRITS - 1, -1, -1):
        trits[position] = value % 3
        value //= 3
    return trits


def trits_to_block(trits: Sequence[int]) -> bytes:
    value = 0
    for trit in trits:
        value = value * 3 + trit
    return value.to_bytes(cfg.BLOCK_BITS // 8, "big")


def trits_to_bases(trits: Sequence[int], seed_base: str) -> str:
    """Rotating code (Tabel 3.11): each base differs from the one before it."""
    previous = seed_base
    bases: list[str] = []
    for trit in trits:
        previous = cfg.ROTATION[previous][trit]
        bases.append(previous)
    return "".join(bases)


def bases_to_trits(sequence: str, seed_base: str) -> list[int]:
    previous = seed_base
    trits: list[int] = []
    for base in sequence:
        trits.append(cfg.DEROTATION[(previous, base)])
        previous = base
    return trits


def _payload_to_bases(payload: bytes) -> str:
    block_size = cfg.BLOCK_BITS // 8
    trits: list[int] = []
    for block in range(cfg.BLOCKS_PER_OLIGO):
        trits.extend(
            block_to_trits(payload[block * block_size : (block + 1) * block_size])
        )
    return trits_to_bases(trits, cfg.ROTATION_SEED_BASE)


def _bases_to_payload(sequence: str) -> bytes:
    trits = bases_to_trits(sequence, cfg.ROTATION_SEED_BASE)
    payload = bytearray()
    for block in range(cfg.BLOCKS_PER_OLIGO):
        payload += trits_to_block(
            trits[block * cfg.BLOCK_TRITS : (block + 1) * cfg.BLOCK_TRITS]
        )
    return bytes(payload)


def rs_encode(data: bytes) -> bytes:
    """Add parity, zero-padding the last codeword. Output is always a whole
    number of 255-byte codewords.
    """
    codec = reedsolo.RSCodec(cfg.RS_NSYM)
    padded = data + bytes((-len(data)) % cfg.RS_K)
    coded = bytearray()
    for start in range(0, len(padded), cfg.RS_K):
        coded += codec.encode(padded[start : start + cfg.RS_K])
    return bytes(coded)


def rs_decode(coded: bytes) -> bytes:
    """Strip parity, correcting up to 16 symbol errors per codeword.

    The result still carries rs_encode()'s zero padding, which is harmless: the
    token header says how many tokens follow, so the token layer stops first.
    """
    codec = reedsolo.RSCodec(cfg.RS_NSYM)
    data = bytearray()
    for start in range(0, len(coded), cfg.RS_N):
        decoded, _, _ = codec.decode(coded[start : start + cfg.RS_N])
        data += decoded
    return bytes(data)


@dataclass(frozen=True)
class EncodeReport:
    oligos: tuple[str, ...]
    input_bytes: int  # before RS
    coded_bytes: int  # after RS, the B of Persamaan 3.2
    total_bases: int
    rescramble_count: int  # GC screening rejections over all oligos

    @property
    def oligo_count(self) -> int:
        return len(self.oligos)

    @property
    def effective_density(self) -> float:
        """Persamaan 2.2: useful payload bits per synthesised base."""
        return (self.input_bytes * 8) / self.total_bases


def encode(data: bytes) -> EncodeReport:
    coded = rs_encode(data)
    chunk_count = -(-len(coded) // cfg.OLIGO_DATA_BYTES)

    oligos: list[str] = []
    rescrambles = 0

    for index in range(chunk_count):
        start = index * cfg.OLIGO_DATA_BYTES
        chunk = coded[start : start + cfg.OLIGO_DATA_BYTES]
        chunk = chunk.ljust(cfg.OLIGO_DATA_BYTES, b"\x00")

        for seed_counter in range(cfg.MAX_SCRAMBLE_ATTEMPTS):
            payload = (
                index.to_bytes(cfg.OLIGO_INDEX_BYTES, "big")
                + bytes([seed_counter])
                + scramble(chunk, index, seed_counter)
            )
            oligo = (
                cfg.PRIMER_FORWARD + _payload_to_bases(payload) + cfg.PRIMER_REVERSE
            )
            if cfg.GC_MIN <= gc_fraction(oligo) <= cfg.GC_MAX:
                break
            rescrambles += 1

        oligos.append(oligo)

    return EncodeReport(
        oligos=tuple(oligos),
        input_bytes=len(data),
        coded_bytes=len(coded),
        total_bases=len(oligos) * cfg.OLIGO_TOTAL_NT,
        rescramble_count=rescrambles,
    )


def decode(oligos: Sequence[str]) -> bytes:
    """Oligos -> the encoded byte stream, plus trailing zero padding.

    Order does not matter: each oligo carries its own index, as it must, since
    oligos sit in solution with no physical ordering (Subbab 2.1.4).
    """
    chunks: dict[int, bytes] = {}
    for oligo in oligos:
        payload = _bases_to_payload(
            oligo[cfg.PRIMER_NT : cfg.PRIMER_NT + cfg.OLIGO_PAYLOAD_NT]
        )
        index = int.from_bytes(payload[: cfg.OLIGO_INDEX_BYTES], "big")
        seed_counter = payload[cfg.OLIGO_INDEX_BYTES]
        chunks[index] = scramble(payload[cfg.SCRAMBLE_OFFSET :], index, seed_counter)

    reassembled = b"".join(chunks[index] for index in range(len(chunks)))

    # the last oligo is zero-padded, so this overshoots by under 29 bytes; only
    # one multiple of 255 can lie in that range
    coded_length = (len(reassembled) // cfg.RS_N) * cfg.RS_N
    return rs_decode(reassembled[:coded_length])


def write_fasta(oligos: Sequence[str], path) -> None:
    records = [
        SeqRecord(
            Seq(oligo),
            id=f"{cfg.FASTA_ID_PREFIX}_{index:05d}",
            description="",
        )
        for index, oligo in enumerate(oligos)
    ]
    with open(path, "w", newline="\n") as handle:
        SeqIO.write(records, handle, "fasta")


def read_fasta(path) -> list[str]:
    with open(path) as handle:
        return [str(record.seq).upper() for record in SeqIO.parse(handle, "fasta")]


def _manifest_path_for(fasta_path: Path) -> Path:
    return fasta_path.with_suffix(fasta_path.suffix + PAYLOAD_MANIFEST_SUFFIX)


def write_payload_manifest(fasta_path, data: bytes):
    """Store the payload length and digest. A FASTA alone cannot prove
    losslessness, since decoding always yields something.
    """
    manifest_path = _manifest_path_for(Path(fasta_path))
    manifest_path.write_text(
        json.dumps(
            {
                "payload_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
            indent=1,
        )
    )
    return manifest_path


def verify_lossless(fasta_path, manifest_path=None) -> bool | None:
    """None means unverified, not failed."""
    fasta_path = Path(fasta_path)
    manifest_path = Path(manifest_path or _manifest_path_for(fasta_path))
    if not manifest_path.is_file():
        return None

    manifest = json.loads(manifest_path.read_text())
    recovered = decode(read_fasta(fasta_path))[: manifest["payload_bytes"]]
    return hashlib.sha256(recovered).hexdigest() == manifest["sha256"]
