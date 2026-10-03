"""Efficiency, compliance and accuracy metrics (Subbab 3.3.5, Tabel 3.13)."""

from __future__ import annotations

import pytest

from src import baselines
from src import config as cfg
from src import dna_codec as codec
from src import evaluate
from src.evaluate import accuracy, compliance, decompose, efficiency

REFERENCE = [(60, 0.0, 0.5), (64, 0.5, 1.0), (67, 1.0, 1.5)]


# --- efficiency (Persamaan 3.3 to 3.6) ---

def test_saving_matches_persamaan_3_3():
    report = efficiency(
        bases_pipeline=250, bases_direct=1000, bases_symbolic=500, payload_bits=800
    )
    assert report.total_saving_pct == pytest.approx(75.0)


def test_contributions_match_persamaan_3_4_and_3_5():
    report = efficiency(
        bases_pipeline=250, bases_direct=1000, bases_symbolic=500, payload_bits=800
    )
    assert report.transcription_contribution_pct == pytest.approx(50.0)
    assert report.token_scheme_contribution_pct == pytest.approx(50.0)


def test_contributions_are_multiplicative_not_additive():
    """Persamaan 3.6. Adding 50% and 50% would wrongly give 100%."""
    report = efficiency(
        bases_pipeline=250, bases_direct=1000, bases_symbolic=500, payload_bits=800
    )
    combined = (1 - report.transcription_contribution_pct / 100) * (
        1 - report.token_scheme_contribution_pct / 100
    )
    assert combined == pytest.approx(1 - report.total_saving_pct / 100)
    assert report.total_saving_pct != pytest.approx(
        report.transcription_contribution_pct
        + report.token_scheme_contribution_pct
    )


def test_effective_density_matches_persamaan_2_2():
    report = efficiency(
        bases_pipeline=1000, bases_direct=5000, bases_symbolic=2000, payload_bits=800
    )
    assert report.effective_density == pytest.approx(0.8)


def test_theoretical_path_is_optional_context():
    without = efficiency(250, 1000, 500, 800)
    assert without.constraint_and_redundancy_cost_pct is None

    with_b3 = efficiency(250, 1000, 500, 800, bases_theoretical=200)
    assert with_b3.constraint_and_redundancy_cost_pct == pytest.approx(20.0)


# --- compliance ---

def test_compliance_over_real_oligos():
    report = codec.encode(bytes(range(256)) * 4)
    checked = compliance(report.oligos, report.rescramble_count)

    assert checked.oligo_count == report.oligo_count
    assert checked.gc_in_range_fraction == 1.0
    assert checked.max_homopolymer <= cfg.HOMOPOLYMER_MAX
    assert checked.compliant


def test_compliance_flags_a_violating_sequence():
    bad = ["A" * cfg.OLIGO_TOTAL_NT]
    checked = compliance(bad)
    assert not checked.compliant
    assert checked.gc_in_range_fraction == 0.0
    assert checked.max_homopolymer == cfg.OLIGO_TOTAL_NT


def test_rejection_rate_is_per_oligo():
    report = codec.encode(bytes(range(256)) * 4)
    checked = compliance(report.oligos, rescramble_count=report.oligo_count)
    assert checked.rejection_rate == pytest.approx(1.0)


# --- accuracy (Subbab 2.9) ---

def test_identical_note_lists_score_one():
    scores = accuracy(REFERENCE, REFERENCE)
    assert scores.f_measure == pytest.approx(1.0)
    assert scores.f_measure_with_offset == pytest.approx(1.0)


def test_a_shift_beyond_the_onset_tolerance_scores_zero():
    """Tolerance is 50 ms (Subbab 2.9.3); 200 ms is well outside it."""
    shifted = [(pitch, start + 0.2, end + 0.2) for pitch, start, end in REFERENCE]
    assert accuracy(REFERENCE, shifted).f_measure == pytest.approx(0.0)


def test_a_shift_inside_the_onset_tolerance_still_matches():
    nudged = [(pitch, start + 0.02, end + 0.02) for pitch, start, end in REFERENCE]
    assert accuracy(REFERENCE, nudged).f_measure == pytest.approx(1.0)


def test_offset_variant_is_stricter_than_onset_only():
    """Right onsets, wrong durations: onset-only passes, the offset variant does not."""
    stretched = [(pitch, start, start + 3.0) for pitch, start, _ in REFERENCE]
    scores = accuracy(REFERENCE, stretched)
    assert scores.f_measure == pytest.approx(1.0)
    assert scores.f_measure_with_offset < scores.f_measure


def test_a_missed_note_lowers_recall_not_precision():
    scores = accuracy(REFERENCE, REFERENCE[:2])
    assert scores.precision == pytest.approx(1.0)
    assert scores.recall == pytest.approx(2 / 3)


def test_a_spurious_note_lowers_precision_not_recall():
    scores = accuracy(REFERENCE, REFERENCE + [(72, 2.0, 2.5)])
    assert scores.recall == pytest.approx(1.0)
    assert scores.precision == pytest.approx(3 / 4)


def test_wrong_pitch_is_not_matched():
    wrong = [(pitch + 3, start, end) for pitch, start, end in REFERENCE]
    assert accuracy(REFERENCE, wrong).f_measure == pytest.approx(0.0)


def test_empty_estimate_scores_zero():
    scores = accuracy(REFERENCE, [])
    assert (scores.precision, scores.recall, scores.f_measure) == (0.0, 0.0, 0.0)
    assert scores.estimated_notes == 0


# --- error decomposition (Tabel 3.13) ---

def test_decomposition_reports_every_stage():
    transcribed = [(pitch, start + 0.01, end) for pitch, start, end in REFERENCE]
    reconstructed = [(pitch, start + 0.02, end) for pitch, start, end in REFERENCE]

    decomposed = decompose(REFERENCE, transcribed, reconstructed, codec_lossless=True)
    rows = decomposed.summary

    assert len(rows) == 4
    assert rows[2]["f_measure"] == 1.0  # the DNA stage must be exactly lossless
    assert decomposed.overall.f_measure == pytest.approx(1.0)


def test_a_lossy_codec_shows_as_failure_in_the_table():
    decomposed = decompose(REFERENCE, REFERENCE, REFERENCE, codec_lossless=False)
    assert decomposed.summary[2]["f_measure"] == 0.0


def test_an_unverified_codec_is_not_reported_as_lossless():
    """Reporting 1.0 unchecked would assert the decisive claim of Subbab 3.2.3."""
    decomposed = decompose(REFERENCE, REFERENCE, REFERENCE, codec_lossless=None)
    assert decomposed.summary[2]["f_measure"] is None


def test_round_trip_verification_against_a_payload_manifest(tmp_path):
    data = bytes(range(256)) * 3
    report = codec.encode(data)
    fasta = tmp_path / "song.fasta"
    codec.write_fasta(report.oligos, fasta)

    assert codec.verify_lossless(fasta) is None  # no manifest yet

    codec.write_payload_manifest(fasta, data)
    assert codec.verify_lossless(fasta) is True


def test_verification_catches_a_corrupted_sequence(tmp_path):
    data = bytes(range(256)) * 3
    report = codec.encode(data)
    fasta = tmp_path / "song.fasta"
    codec.write_fasta(report.oligos, fasta)
    codec.write_payload_manifest(fasta, b"something else entirely")

    assert codec.verify_lossless(fasta) is False


# --- baselines (Tabel 3.12) ---

def test_theoretical_baseline_is_two_bits_per_base():
    result = baselines.theoretical(1000)
    assert result.total_bases == 4000  # 8000 bits / 2 bits per base
    assert result.effective_density == pytest.approx(2.0)


def test_baseline_file_goes_through_the_real_codec(tmp_path):
    path = tmp_path / "sample.bin"
    path.write_bytes(bytes(range(256)) * 4)

    result = baselines.encode_file(path, "test")
    assert result.total_bases == codec.encode(path.read_bytes()).total_bases


def test_pipeline_and_baselines_share_the_codec():
    """Tabel 3.12 requires the same DNA scheme on every path."""
    data = bytes(range(256)) * 2
    assert baselines.pipeline(data).total_bases == codec.encode(data).total_bases


def test_efficiency_over_a_real_encoding(tmp_path):
    """The three paths wired together as Bab IV will report them."""
    from src.tokenizer import QuantizedNote, encode_notes

    notes = [QuantizedNote(60 + (i % 12), i * 4, 4) for i in range(64)]
    packed = encode_notes(notes, 120).data

    pipeline = baselines.pipeline(packed)
    direct = baselines.theoretical(200_000)  # stands in for an MP3
    symbolic = baselines.theoretical(2_000)  # stands in for transcribed MIDI

    report = efficiency(
        pipeline.total_bases,
        direct.total_bases,
        symbolic.total_bases,
        payload_bits=len(packed) * 8,
    )
    assert 0 < report.total_saving_pct < 100
    assert report.effective_density > 0
