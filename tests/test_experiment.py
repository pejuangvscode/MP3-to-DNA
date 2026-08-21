"""The corpus experiment runner (Fase 5, Tabel 3.14)."""

from __future__ import annotations

import csv

import numpy as np
import pytest
import soundfile as sf

from src import config as cfg
from src import experiment
from src.reconstruct import to_midi
from src.tokenizer import QuantizedNote

TEMPO = 120


def render(notes, path, sample_rate=22050, tempo=TEMPO):
    """Sine tones at the notes' pitches, so transcription has something to find."""
    unit = cfg.grid_unit_seconds(tempo)
    total = int((max(n.position + n.duration for n in notes) + 1) * unit * sample_rate)
    signal = np.zeros(total, dtype=np.float32)
    for note in notes:
        start = int(note.position * unit * sample_rate)
        length = int(note.duration * unit * sample_rate)
        times = np.arange(length) / sample_rate
        envelope = np.minimum(1.0, np.minimum(times, length / sample_rate - times) * 60.0)
        frequency = 440.0 * 2.0 ** ((note.pitch - 69) / 12.0)
        signal[start : start + length] += (
            0.45 * np.sin(2 * np.pi * frequency * times) * envelope
        ).astype(np.float32)
    sf.write(path, np.clip(signal, -1.0, 1.0), sample_rate, format="WAV", subtype="FLOAT")
    return path


def build_corpus(root, samples, with_reference=True):
    """A miniature corpus laid out the way src.corpus expects."""
    (root / "audio").mkdir(parents=True, exist_ok=True)
    (root / "ground_truth").mkdir(parents=True, exist_ok=True)

    rows = ["sample,tempo,durasi,kerapatan,pengulangan"]
    for name, notes, levels in samples:
        render(notes, root / "audio" / f"{name}.mp3")
        if with_reference:
            to_midi(notes, root / "ground_truth" / f"{name}.mid", TEMPO)
        rows.append(f"{name},{TEMPO},{levels}")
    (root / "corpus.csv").write_text("\n".join(rows) + "\n")
    return root


def phrase(bars=4, start_pitch=60):
    """A repeating four-note figure, so repeat detection has something to find."""
    pitches = [start_pitch, start_pitch + 4, start_pitch + 7, start_pitch + 12]
    return [
        QuantizedNote(pitch, (bar * 4 + index) * 4, 4)
        for bar in range(bars)
        for index, pitch in enumerate(pitches)
    ]


@pytest.mark.slow
def test_runner_produces_every_table(tmp_path):
    data = build_corpus(
        tmp_path / "data",
        [("s1", phrase(), "pendek,rendah,tinggi")],
    )
    results = experiment.run_all(data, tmp_path / "results")
    assert len(results) == 1

    summary = experiment.write_tables(results, tmp_path / "results")
    text = summary.read_text(encoding="utf-8")
    for heading in (
        "Efisiensi",
        "Kepatuhan batasan biologis",
        "Sumbangan deteksi pengulangan",
        "Akurasi rekonstruksi",
        "Dekomposisi error",
        "Keterulangan",
    ):
        assert heading in text, f"missing section: {heading}"


@pytest.mark.slow
def test_per_sample_csv_carries_the_key_columns(tmp_path):
    data = build_corpus(tmp_path / "data", [("s1", phrase(), "pendek,rendah,tinggi")])
    results = experiment.run_all(data, tmp_path / "results")
    experiment.write_tables(results, tmp_path / "results")

    with open(tmp_path / "results" / "per_sample.csv", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    for column in (
        "bases_pipeline",
        "bases_b1_direct",
        "bases_b2_symbolic",
        "saving_token_scheme_pct",
        "gc_mean",
        "max_homopolymer",
        "lossless",
        "deterministic",
        "tokens_plain",
        "tokens_lz77",
        "f_measure",
    ):
        assert column in rows[0], f"missing column: {column}"


@pytest.mark.slow
def test_round_trip_and_determinism_hold(tmp_path):
    data = build_corpus(tmp_path / "data", [("s1", phrase(), "pendek,rendah,tinggi")])
    row = experiment.run_all(data, tmp_path / "results")[0].row

    assert row["lossless"] is True
    assert row["deterministic"] is True
    assert row["compliant"] is True
    assert row["max_homopolymer"] <= cfg.HOMOPOLYMER_MAX


@pytest.mark.slow
def test_repeat_detection_contribution_is_measured(tmp_path):
    data = build_corpus(tmp_path / "data", [("s1", phrase(bars=8), "pendek,rendah,tinggi")])
    row = experiment.run_all(data, tmp_path / "results")[0].row

    assert row["tokens_lz77"] < row["tokens_plain"]
    assert row["token_saving_pct"] > 0
    assert row["bases_no_lz77"] >= row["bases_pipeline"]


@pytest.mark.slow
def test_a_missing_reference_is_reported_but_does_not_stop_the_run(tmp_path):
    """Efficiency and compliance survive; only accuracy needs the reference."""
    data = build_corpus(
        tmp_path / "data",
        [("s1", phrase(), "pendek,rendah,tinggi")],
        with_reference=False,
    )
    result = experiment.run_all(data, tmp_path / "results")[0]

    assert not result.ok
    assert any("no reference notation" in problem for problem in result.problems)
    assert result.row["bases_pipeline"] > 0
    assert result.row["compliant"] is True
    assert "f_measure" not in result.row


@pytest.mark.slow
def test_only_filter_selects_a_subset(tmp_path):
    data = build_corpus(
        tmp_path / "data",
        [
            ("s1", phrase(), "pendek,rendah,tinggi"),
            ("s2", phrase(start_pitch=55), "sedang,sedang,rendah"),
        ],
    )
    results = experiment.run_all(data, tmp_path / "results", only=["s2"])
    assert [result.sample.name for result in results] == ["s2"]


def test_an_unknown_sample_name_is_rejected(tmp_path):
    data = build_corpus(tmp_path / "data", [("s1", phrase(), "pendek,rendah,tinggi")])
    with pytest.raises(ValueError, match="no sample matched"):
        experiment.run_all(data, tmp_path / "results", only=["nope"])


def test_markdown_table_renders_missing_values(tmp_path):
    lines = experiment._markdown_table(
        [{"a": 1}], [("a", "A"), ("missing", "Missing")]
    )
    assert lines[0] == "| A | Missing |"
    assert lines[2] == "| 1 | - |"
