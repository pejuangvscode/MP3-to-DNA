"""Biological constraint compliance over every oligo (Tabel 3.2).

Compliance is guaranteed by construction, so these verify that the
implementation realises the guarantee, not that the method works.
"""

from __future__ import annotations

import random

import pytest

from src import config as cfg
from src import dna_codec as codec


def payload_of(oligo: str) -> str:
    return oligo[cfg.PRIMER_NT : cfg.PRIMER_NT + cfg.OLIGO_PAYLOAD_NT]


def sample_inputs() -> list[bytes]:
    """Inputs spanning the cases that break naive mappings (Subbab 2.3.1)."""
    rng = random.Random(2026)
    return [
        bytes(2000),  # all zero bytes -> AAAA under a naive mapping
        b"\xff" * 2000,  # all 0xFF -> TTTT, GC 0%
        bytes([0x55]) * 2000,
        bytes(range(256)) * 8,
        bytes(rng.randrange(256) for _ in range(4000)),
        bytes(rng.randrange(2) for _ in range(4000)),  # very low entropy
    ]


@pytest.mark.parametrize("data", sample_inputs(), ids=lambda d: f"{len(d)}B")
def test_every_oligo_meets_the_gc_window(data):
    for oligo in codec.encode(data).oligos:
        assert cfg.GC_MIN <= codec.gc_fraction(oligo) <= cfg.GC_MAX


@pytest.mark.parametrize("data", sample_inputs(), ids=lambda d: f"{len(d)}B")
def test_every_oligo_meets_the_homopolymer_limit(data):
    for oligo in codec.encode(data).oligos:
        assert codec.max_homopolymer(oligo) <= cfg.HOMOPOLYMER_MAX


@pytest.mark.parametrize("data", sample_inputs(), ids=lambda d: f"{len(d)}B")
def test_payload_is_free_of_homopolymers(data):
    """The rotating code guarantees this part outright (Subbab 3.3.4)."""
    for oligo in codec.encode(data).oligos:
        assert codec.max_homopolymer(payload_of(oligo)) == 1


def test_forward_junction_is_homopolymer_free():
    """The first payload base is rotated against the last primer base."""
    for data in sample_inputs():
        for oligo in codec.encode(data).oligos:
            assert oligo[cfg.PRIMER_NT - 1] != oligo[cfg.PRIMER_NT]


def test_whole_oligo_never_exceeds_a_run_of_two():
    """The one place a run of 1 cannot be guaranteed: the payload can end on
    the same base the fixed reverse primer starts with. Subbab 3.3.4 claims 1
    for the whole sequence, which holds everywhere else.
    """
    observed = 0
    for data in sample_inputs():
        for oligo in codec.encode(data).oligos:
            observed = max(observed, codec.max_homopolymer(oligo))
    assert observed <= cfg.EXPECTED_MAX_HOMOPOLYMER


def test_gc_screening_rejections_stay_rare():
    """Scrambling should centre GC near 50%, so rescrambling should be unusual."""
    report = codec.encode(bytes(range(256)) * 40)
    assert report.oligo_count > 100
    assert report.rescramble_count / report.oligo_count < 0.05


def test_primers_themselves_are_compliant():
    for primer in (cfg.PRIMER_FORWARD, cfg.PRIMER_REVERSE):
        assert len(primer) == cfg.PRIMER_NT
        assert cfg.GC_MIN <= codec.gc_fraction(primer) <= cfg.GC_MAX
        assert codec.max_homopolymer(primer) == 1


def test_no_common_restriction_site_appears():
    """Six-cutters without a doubled base; the rest cannot occur by design."""
    sites = {
        "XhoI": "CTCGAG",
        "SalI": "GTCGAC",
        "XbaI": "TCTAGA",
        "SacI": "GAGCTC",
        "SpeI": "ACTAGT",
        "PstI": "CTGCAG",
        "EcoRV": "GATATC",
    }
    for primer in (cfg.PRIMER_FORWARD, cfg.PRIMER_REVERSE):
        for name, site in sites.items():
            assert site not in primer, f"{name} site in primer"
