"""DNA codec: RS, scrambling, trit conversion, rotating code, FASTA."""

from __future__ import annotations

import random

import pytest

from src import config as cfg
from src import dna_codec as codec
from src import tokenizer


def random_bytes(rng: random.Random, length: int) -> bytes:
    return bytes(rng.randrange(256) for _ in range(length))


# --- bit to trit (Subbab 2.3.3) ---

def test_block_trit_round_trip():
    rng = random.Random(5)
    for _ in range(300):
        block = random_bytes(rng, cfg.BLOCK_BITS // 8)
        trits = codec.block_to_trits(block)
        assert len(trits) == cfg.BLOCK_TRITS
        assert all(0 <= trit <= 2 for trit in trits)
        assert codec.trits_to_block(trits) == block


def test_block_trit_extremes():
    for block in (bytes(16), b"\xff" * 16):
        assert codec.trits_to_block(codec.block_to_trits(block)) == block


# --- rotating code (Tabel 3.11) ---

def test_rotating_code_never_repeats_a_base():
    rng = random.Random(6)
    trits = [rng.randrange(3) for _ in range(500)]
    sequence = codec.trits_to_bases(trits, cfg.ROTATION_SEED_BASE)
    assert codec.max_homopolymer(sequence) == 1
    assert sequence[0] != cfg.ROTATION_SEED_BASE


def test_rotating_code_round_trip():
    rng = random.Random(8)
    trits = [rng.randrange(3) for _ in range(500)]
    sequence = codec.trits_to_bases(trits, cfg.ROTATION_SEED_BASE)
    assert codec.bases_to_trits(sequence, cfg.ROTATION_SEED_BASE) == trits


# --- reed-solomon (Subbab 2.4.3) ---

def test_rs_output_is_whole_codewords():
    rng = random.Random(12)
    for length in (1, 222, 223, 224, 1000):
        coded = codec.rs_encode(random_bytes(rng, length))
        assert len(coded) % cfg.RS_N == 0
        assert len(coded) == -(-length // cfg.RS_K) * cfg.RS_N


def test_rs_round_trip_recovers_data_plus_padding():
    rng = random.Random(13)
    data = random_bytes(rng, 500)
    recovered = codec.rs_decode(codec.rs_encode(data))
    assert recovered.startswith(data)
    assert len(recovered) == -(-len(data) // cfg.RS_K) * cfg.RS_K
    assert set(recovered[len(data) :]) <= {0}  # padding only


def test_rs_corrects_sixteen_symbol_errors():
    """Verifies Persamaan 2.11 for RS(255,223): floor((255-223)/2) = 16."""
    rng = random.Random(14)
    data = random_bytes(rng, cfg.RS_K)
    coded = bytearray(codec.rs_encode(data))

    for position in rng.sample(range(cfg.RS_N), 16):
        coded[position] ^= 0xFF

    assert codec.rs_decode(bytes(coded)) == data


# --- scrambling (Subbab 2.3.5) ---

def test_scrambling_is_its_own_inverse():
    rng = random.Random(15)
    data = random_bytes(rng, cfg.OLIGO_DATA_BYTES)
    assert codec.scramble(codec.scramble(data, 7, 3), 7, 3) == data


def test_scrambling_changes_with_index_and_seed_counter():
    data = bytes(cfg.OLIGO_DATA_BYTES)
    assert codec.scramble(data, 0, 0) != codec.scramble(data, 1, 0)
    assert codec.scramble(data, 0, 0) != codec.scramble(data, 0, 1)


def test_scrambling_flattens_a_run_of_zero_bytes():
    """The case Subbab 2.3.1 shows breaking the naive mapping."""
    scrambled = codec.scramble(bytes(cfg.OLIGO_DATA_BYTES), 0, 0)
    assert len(set(scrambled)) > 1


# --- oligo structure (Tabel 3.10) ---

def test_oligo_layout_matches_the_design():
    report = codec.encode(bytes(range(200)))
    for oligo in report.oligos:
        assert len(oligo) == cfg.OLIGO_TOTAL_NT == 202
        assert oligo.startswith(cfg.PRIMER_FORWARD)
        assert oligo.endswith(cfg.PRIMER_REVERSE)
        assert set(oligo) <= set(cfg.BASES)


def test_base_count_matches_persamaan_3_2():
    rng = random.Random(16)
    for length in (1, 29, 30, 223, 500):
        report = codec.encode(random_bytes(rng, length))
        assert report.total_bases == cfg.total_bases_for(report.coded_bytes)
        assert report.oligo_count == cfg.oligo_count_for(report.coded_bytes)


# --- whole codec ---

@pytest.mark.parametrize("length", [1, 4, 29, 32, 223, 255, 700, 5000])
def test_encode_decode_round_trip(length):
    rng = random.Random(length)
    data = random_bytes(rng, length)
    report = codec.encode(data)
    recovered = codec.decode(report.oligos)
    assert recovered.startswith(data)


def test_oligos_decode_in_any_order():
    """Oligos sit in solution unordered; each carries its own index."""
    rng = random.Random(17)
    data = random_bytes(rng, 900)
    report = codec.encode(data)

    shuffled = list(report.oligos)
    rng.shuffle(shuffled)
    assert codec.decode(shuffled).startswith(data)


def test_effective_density_stays_below_the_scheme_rate():
    """Persamaan 2.2: primers and address dilute the 1.58 bit/base scheme rate."""
    report = codec.encode(bytes(range(256)) * 8)
    assert 0 < report.effective_density < cfg.BLOCK_BITS / cfg.BLOCK_TRITS


# --- FASTA (Subbab 2.10.3) ---

def test_fasta_round_trip(tmp_path):
    rng = random.Random(18)
    data = random_bytes(rng, 700)
    report = codec.encode(data)

    path = tmp_path / "song.fasta"
    codec.write_fasta(report.oligos, path)
    assert list(codec.read_fasta(path)) == list(report.oligos)
    assert codec.decode(codec.read_fasta(path)).startswith(data)


def test_fasta_has_one_record_per_oligo(tmp_path):
    report = codec.encode(bytes(range(256)) * 4)
    path = tmp_path / "song.fasta"
    codec.write_fasta(report.oligos, path)

    text = path.read_text()
    assert text.count(">") == report.oligo_count
    assert f">{cfg.FASTA_ID_PREFIX}_00000" in text
