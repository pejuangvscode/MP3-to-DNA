"""Packed bytes <-> constraint-compliant DNA, written as FASTA.

Implements the seven-stage encoder of Subbab 3.3.4 and Gambar 3.3:

    Reed-Solomon -> fragmentation -> scrambling -> bit to trit ->
    rotating code -> GC screening -> primers

Constraint compliance is by construction, not by filtering after the fact. The
rotating code picks a base that always differs from its predecessor, so the
payload can carry no homopolymer at all; scrambling drives the base
distribution near uniform so GC content settles around 50%, and screening
catches the rare oligo that still falls outside the window.

Decoding runs the same stages in reverse. Since the study injects no errors,
the whole path is lossless at sequence level.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

import reedsolo
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from src import config as cfg


class DNACodecError(ValueError):
    """The sequence or byte stream does not match what the codec expects."""


# ---------------------------------------------------------------------------
# Sequence measurements (Subbab 2.2, Subbab 3.3.5)
# ---------------------------------------------------------------------------


def gc_fraction(sequence: str) -> float:
    """Proportion of G and C bases (Persamaan 2.4, expressed as a fraction)."""
    if not sequence:
        raise DNACodecError("GC content of an empty sequence is undefined")
    return (sequence.count("G") + sequence.count("C")) / len(sequence)


def max_homopolymer(sequence: str) -> int:
    """Length of the longest run of one repeated base."""
    if not sequence:
        return 0
    longest = run = 1
    for previous, current in zip(sequence, sequence[1:]):
        run = run + 1 if current == previous else 1
        longest = max(longest, run)
    return longest


# ---------------------------------------------------------------------------
# Scrambling (Subbab 2.3.5, Subbab 3.3.4)
# ---------------------------------------------------------------------------


def _keystream(index: int, seed_counter: int, length: int) -> bytes:
    """Pseudo-random bytes for one oligo, derived from its own header.

    SHA-256 in counter mode rather than `random`, whose stream is not
    guaranteed stable across Python versions. Repeatability (Tabel 3.2) needs a
    generator fixed by algorithm, and the seed has to be rebuildable from the
    index and seed counter that travel in the clear inside the oligo.
    """
    seed = cfg.SCRAMBLE_DOMAIN + index.to_bytes(2, "big") + bytes([seed_counter])
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        stream += hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        counter += 1
    return bytes(stream[:length])


def scramble(data: bytes, index: int, seed_counter: int) -> bytes:
    """XOR `data` with the keystream. Its own inverse."""
    keystream = _keystream(index, seed_counter, len(data))
    return bytes(a ^ b for a, b in zip(data, keystream))


# ---------------------------------------------------------------------------
# Bit to trit (Subbab 2.3.3, Subbab 3.3.4)
# ---------------------------------------------------------------------------


def block_to_trits(block: bytes) -> list[int]:
    """16 bytes (128 bits) -> 81 trits, most significant trit first."""
    if len(block) * 8 != cfg.BLOCK_BITS:
        raise DNACodecError(
            f"block must be {cfg.BLOCK_BITS // 8} bytes, got {len(block)}"
        )
    value = int.from_bytes(block, "big")
    trits = [0] * cfg.BLOCK_TRITS
    for position in range(cfg.BLOCK_TRITS - 1, -1, -1):
        trits[position] = value % 3
        value //= 3
    return trits


def trits_to_block(trits: Sequence[int]) -> bytes:
    """81 trits -> 16 bytes. Inverse of :func:`block_to_trits`."""
    if len(trits) != cfg.BLOCK_TRITS:
        raise DNACodecError(f"expected {cfg.BLOCK_TRITS} trits, got {len(trits)}")
    value = 0
    for trit in trits:
        if not 0 <= trit <= 2:
            raise DNACodecError(f"trit out of range: {trit}")
        value = value * 3 + trit
    if value >= 1 << cfg.BLOCK_BITS:
        # 3**81 exceeds 2**128, so some trit strings have no 128-bit preimage.
        # Valid data never lands there; reaching it means corruption.
        raise DNACodecError("trit block does not represent a 128-bit value")
    return value.to_bytes(cfg.BLOCK_BITS // 8, "big")


# ---------------------------------------------------------------------------
# Rotating code (Tabel 3.11)
# ---------------------------------------------------------------------------


def trits_to_bases(trits: Sequence[int], seed_base: str) -> str:
    """Map trits to bases, each one differing from the base before it."""
    previous = seed_base
    bases: list[str] = []
    for trit in trits:
        if not 0 <= trit <= 2:
            raise DNACodecError(f"trit out of range: {trit}")
        previous = cfg.ROTATION[previous][trit]
        bases.append(previous)
    return "".join(bases)


def bases_to_trits(sequence: str, seed_base: str) -> list[int]:
    """Recover trits from bases. Inverse of :func:`trits_to_bases`."""
    previous = seed_base
    trits: list[int] = []
    for offset, base in enumerate(sequence):
        try:
            trits.append(cfg.DEROTATION[(previous, base)])
        except KeyError:
            raise DNACodecError(
                f"position {offset}: base {base!r} cannot follow {previous!r} "
                "under the rotating code"
            ) from None
        previous = base
    return trits


def _payload_to_bases(payload: bytes) -> str:
    if len(payload) != cfg.OLIGO_PAYLOAD_BYTES:
        raise DNACodecError(
            f"payload must be {cfg.OLIGO_PAYLOAD_BYTES} bytes, got {len(payload)}"
        )
    block_size = cfg.BLOCK_BITS // 8
    trits: list[int] = []
    for block in range(cfg.BLOCKS_PER_OLIGO):
        trits.extend(
            block_to_trits(payload[block * block_size : (block + 1) * block_size])
        )
    return trits_to_bases(trits, cfg.ROTATION_SEED_BASE)


def _bases_to_payload(sequence: str) -> bytes:
    if len(sequence) != cfg.OLIGO_PAYLOAD_NT:
        raise DNACodecError(
            f"payload must be {cfg.OLIGO_PAYLOAD_NT} nt, got {len(sequence)}"
        )
    trits = bases_to_trits(sequence, cfg.ROTATION_SEED_BASE)
    payload = bytearray()
    for block in range(cfg.BLOCKS_PER_OLIGO):
        payload += trits_to_block(
            trits[block * cfg.BLOCK_TRITS : (block + 1) * cfg.BLOCK_TRITS]
        )
    return bytes(payload)


# ---------------------------------------------------------------------------
# Reed-Solomon outer code (Subbab 2.4.3)
# ---------------------------------------------------------------------------


def rs_encode(data: bytes) -> bytes:
    """Add parity, zero-padding the final codeword as Subbab 3.3.4 specifies.

    Output is always a whole number of 255-byte codewords.
    """
    codec = reedsolo.RSCodec(cfg.RS_NSYM)
    padded = data + bytes((-len(data)) % cfg.RS_K)
    coded = bytearray()
    for start in range(0, len(padded), cfg.RS_K):
        coded += codec.encode(padded[start : start + cfg.RS_K])
    return bytes(coded)


def rs_decode(coded: bytes) -> bytes:
    """Strip parity, correcting up to 16 symbol errors per codeword.

    The returned stream still carries the zero padding added by
    :func:`rs_encode`. That is harmless: the token header states how many
    tokens follow, so the token layer stops before the padding.
    """
    if len(coded) % cfg.RS_N:
        raise DNACodecError(
            f"coded stream of {len(coded)} bytes is not a whole number of "
            f"{cfg.RS_N}-byte codewords"
        )
    codec = reedsolo.RSCodec(cfg.RS_NSYM)
    data = bytearray()
    for start in range(0, len(coded), cfg.RS_N):
        try:
            decoded, _, _ = codec.decode(coded[start : start + cfg.RS_N])
        except reedsolo.ReedSolomonError as exc:
            raise DNACodecError(
                f"codeword at byte {start} is beyond correction: {exc}"
            ) from exc
        data += decoded
    return bytes(data)


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EncodeReport:
    """Everything Bab IV needs to report about one encoding run."""

    oligos: tuple[str, ...]
    input_bytes: int  # before Reed-Solomon
    coded_bytes: int  # after Reed-Solomon, the B of Persamaan 3.2
    total_bases: int
    rescramble_count: int  # GC screening rejections, summed over all oligos

    @property
    def oligo_count(self) -> int:
        return len(self.oligos)

    @property
    def effective_density(self) -> float:
        """Useful payload bits per synthesised base (Persamaan 2.2)."""
        return (self.input_bytes * 8) / self.total_bases


def encode(data: bytes) -> EncodeReport:
    """Packed token bytes -> oligos."""
    if not data:
        raise DNACodecError("nothing to encode: input is empty")
    coded = rs_encode(data)
    chunk_count = -(-len(coded) // cfg.OLIGO_DATA_BYTES)  # ceil
    if chunk_count > cfg.MAX_OLIGO_COUNT:
        raise DNACodecError(
            f"{chunk_count} oligos exceeds the {cfg.MAX_OLIGO_COUNT} addressable "
            f"by a {cfg.OLIGO_INDEX_BYTES}-byte index"
        )

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
        else:
            raise DNACodecError(
                f"oligo {index}: GC content stayed outside "
                f"{cfg.GC_MIN:.0%}..{cfg.GC_MAX:.0%} after "
                f"{cfg.MAX_SCRAMBLE_ATTEMPTS} scrambling attempts"
            )

        oligos.append(oligo)

    return EncodeReport(
        oligos=tuple(oligos),
        input_bytes=len(data),
        coded_bytes=len(coded),
        total_bases=len(oligos) * cfg.OLIGO_TOTAL_NT,
        rescramble_count=rescrambles,
    )


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------


def decode(oligos: Sequence[str]) -> bytes:
    """Oligos -> the byte stream that was encoded, plus trailing zero padding.

    Oligos may arrive in any order; each carries its own index, as they must,
    since oligos sit in solution without physical ordering (Subbab 2.1.4).
    """
    if not oligos:
        raise DNACodecError("no oligos to decode")

    chunks: dict[int, bytes] = {}
    for position, oligo in enumerate(oligos):
        if len(oligo) != cfg.OLIGO_TOTAL_NT:
            raise DNACodecError(
                f"oligo {position}: expected {cfg.OLIGO_TOTAL_NT} nt, "
                f"got {len(oligo)}"
            )
        if not oligo.startswith(cfg.PRIMER_FORWARD):
            raise DNACodecError(f"oligo {position}: forward primer does not match")
        if not oligo.endswith(cfg.PRIMER_REVERSE):
            raise DNACodecError(f"oligo {position}: reverse primer does not match")

        payload = _bases_to_payload(
            oligo[cfg.PRIMER_NT : cfg.PRIMER_NT + cfg.OLIGO_PAYLOAD_NT]
        )
        index = int.from_bytes(payload[: cfg.OLIGO_INDEX_BYTES], "big")
        seed_counter = payload[cfg.OLIGO_INDEX_BYTES]
        if index in chunks:
            raise DNACodecError(f"oligo index {index} appears more than once")
        chunks[index] = scramble(payload[cfg.SCRAMBLE_OFFSET :], index, seed_counter)

    missing = set(range(len(chunks))) - chunks.keys()
    if missing:
        raise DNACodecError(
            f"missing oligo indices: {sorted(missing)[:10]}"
            f"{' ...' if len(missing) > 10 else ''}"
        )

    reassembled = b"".join(chunks[index] for index in range(len(chunks)))

    # The final oligo is zero-padded up to 29 bytes, so the reassembled stream
    # is a little longer than the coded stream. The coded length is a whole
    # number of 255-byte codewords and the overshoot is under 29 bytes, so only
    # one multiple of 255 can lie in that range: the original length.
    coded_length = (len(reassembled) // cfg.RS_N) * cfg.RS_N
    if coded_length == 0:
        raise DNACodecError(
            f"reassembled {len(reassembled)} bytes, too short for one "
            f"{cfg.RS_N}-byte codeword"
        )
    return rs_decode(reassembled[:coded_length])


# ---------------------------------------------------------------------------
# FASTA I/O (Subbab 2.10.3)
# ---------------------------------------------------------------------------


def write_fasta(oligos: Sequence[str], path) -> None:
    """Write one FASTA record per oligo."""
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
    """Read oligo sequences back, uppercased."""
    with open(path) as handle:
        return [str(record.seq).upper() for record in SeqIO.parse(handle, "fasta")]


# ---------------------------------------------------------------------------
# Round-trip verification
# ---------------------------------------------------------------------------

#: Written next to a FASTA file so losslessness can be checked later.
PAYLOAD_MANIFEST_SUFFIX = ".payload.json"


def write_payload_manifest(fasta_path, data: bytes):
    """Record what went in, so what comes out can be checked against it.

    Subbab 3.2.3 makes bit-identical recovery the decisive requirement, and a
    FASTA file alone cannot prove it: decoding always yields *something*. This
    stores the payload length and digest so the claim can actually be tested
    rather than assumed.
    """
    import json
    from pathlib import Path

    fasta_path = Path(fasta_path)
    manifest_path = fasta_path.with_suffix(fasta_path.suffix + PAYLOAD_MANIFEST_SUFFIX)
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
    """Decode a FASTA and compare it against its payload manifest.

    Returns None when no manifest exists, which means unverified rather than
    failed. Callers must not report the codec stage as lossless in that case.
    """
    import json
    from pathlib import Path

    fasta_path = Path(fasta_path)
    manifest_path = Path(
        manifest_path
        or fasta_path.with_suffix(fasta_path.suffix + PAYLOAD_MANIFEST_SUFFIX)
    )
    if not manifest_path.is_file():
        return None

    manifest = json.loads(manifest_path.read_text())
    recovered = decode(read_fasta(fasta_path))[: manifest["payload_bytes"]]
    return hashlib.sha256(recovered).hexdigest() == manifest["sha256"]
