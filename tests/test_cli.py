"""Command line entry points and the corpus validator (Fase 4)."""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from src import config as cfg
from src import corpus, decode, dna_codec, encode
from src.reconstruct import read_midi, to_midi
from src.tokenizer import QuantizedNote, encode_notes

NOTES = [QuantizedNote(60 + (i % 12), i * 4, 4) for i in range(24)]


def write_fasta_for(notes, path, tempo=120):
    packed = encode_notes(notes, tempo).data
    report = dna_codec.encode(packed)
    dna_codec.write_fasta(report.oligos, path)
    return report


def write_audio(path, seconds=4.0, sample_rate=22050):
    """A tone written as WAV whatever the extension says: libsndfile sniffs
    content, so this stands in for an MP3 wherever only readable audio matters.
    """
    times = np.arange(int(seconds * sample_rate)) / sample_rate
    signal = (0.4 * np.sin(2 * np.pi * 440 * times)).astype(np.float32)
    sf.write(path, signal, sample_rate, format="WAV", subtype="FLOAT")
    return path


# --- decode ---

def test_decode_reconstructs_from_fasta_alone(tmp_path):
    """Tempo and grid travel in the token header, so nothing else is needed."""
    fasta = tmp_path / "song.fasta"
    write_fasta_for(NOTES, fasta, tempo=137)

    result = decode.run(fasta, tmp_path / "out.mid")
    assert result.tokens.tempo == 137
    assert list(result.tokens.notes) == NOTES
    assert result.midi_path.is_file()
    assert len(read_midi(result.midi_path)) == len(NOTES)


def test_decode_writes_musicxml_alongside(tmp_path):
    fasta = tmp_path / "song.fasta"
    write_fasta_for(NOTES, fasta)
    result = decode.run(fasta, tmp_path / "out.mid")
    assert result.musicxml_path is not None and result.musicxml_path.is_file()


def test_decode_can_skip_musicxml(tmp_path):
    fasta = tmp_path / "song.fasta"
    write_fasta_for(NOTES, fasta)
    assert decode.run(fasta, tmp_path / "out.mid", write_musicxml=False).musicxml_path is None


def test_decode_cli_succeeds(tmp_path, capsys):
    fasta = tmp_path / "song.fasta"
    write_fasta_for(NOTES, fasta)

    code = decode.main(
        ["--input", str(fasta), "--output", str(tmp_path / "out.mid"), "--no-musicxml"]
    )
    assert code == 0
    assert "written" in capsys.readouterr().out


# --- encode ---

@pytest.mark.slow
def test_encode_produces_a_decodable_fasta(tmp_path):
    audio = write_audio(tmp_path / "sample.wav", seconds=4.0)
    fasta = tmp_path / "sample.fasta"

    result = encode.run(audio, 120, fasta, work_dir=tmp_path / "work")
    assert result.fasta_path.is_file()
    assert result.transcribed_midi_path.is_file()  # comparison path B2 needs it
    assert result.musicxml_path is not None and result.musicxml_path.is_file()
    assert result.dna.oligo_count > 0

    decoded = decode.run(fasta, tmp_path / "out.mid", write_musicxml=False)
    assert list(decoded.tokens.notes) == list(result.quantization.notes)


@pytest.mark.slow
def test_encode_cli_round_trips(tmp_path, capsys):
    audio = write_audio(tmp_path / "sample.wav", seconds=4.0)
    fasta = tmp_path / "sample.fasta"

    assert encode.main(
        [
            "--input", str(audio),
            "--tempo", "120",
            "--output", str(fasta),
            "--work-dir", str(tmp_path / "work"),
            "--no-musicxml",
        ]
    ) == 0
    assert "written" in capsys.readouterr().out
    assert decode.main(
        ["--input", str(fasta), "--output", str(tmp_path / "out.mid"), "--no-musicxml"]
    ) == 0


@pytest.mark.slow
def test_repeat_detection_can_be_switched_off(tmp_path):
    """The two runs Subbab 3.3.5 compares to isolate what LZ77 contributes."""
    audio = write_audio(tmp_path / "sample.wav", seconds=4.0)

    with_lz = encode.run(audio, 120, tmp_path / "on.fasta", work_dir=tmp_path / "w")
    without = encode.run(
        audio,
        120,
        tmp_path / "off.fasta",
        work_dir=tmp_path / "w",
        use_repeat_detection=False,
    )
    assert without.tokens.stats.reference_tokens == 0
    assert with_lz.tokens.stats.total_tokens <= without.tokens.stats.total_tokens


# --- corpus validator ---

def build_corpus(tmp_path, rows, notes_by_sample, with_audio=True, tempo=120):
    (tmp_path / "audio").mkdir(parents=True, exist_ok=True)
    (tmp_path / "ground_truth").mkdir(parents=True, exist_ok=True)

    header = "sample,tempo,durasi,kerapatan,pengulangan\n"
    (tmp_path / "corpus.csv").write_text(header + "\n".join(rows) + "\n")

    for name, notes in notes_by_sample.items():
        to_midi(notes, tmp_path / "ground_truth" / f"{name}.mid", tempo)
        if with_audio:
            duration = max(n.position + n.duration for n in notes) * cfg.grid_unit_seconds(tempo)
            write_audio(tmp_path / "audio" / f"{name}.mp3", seconds=duration)
    return tmp_path


def test_a_well_formed_sample_passes(tmp_path):
    data = build_corpus(
        tmp_path, ["s1,120,pendek,rendah,rendah"], {"s1": NOTES}
    )
    check = corpus.check_all(data)[0]
    assert check.ok, check.problems
    assert check.facts["reference_notes"] == len(NOTES)
    assert check.facts["repetition_saving_pct"] >= 0


def test_repetition_is_measured(tmp_path):
    """The validator reports what each sample actually repeats."""
    repetitive = [QuantizedNote(60 + (i % 4), i * 4, 4) for i in range(64)]
    data = build_corpus(
        tmp_path,
        ["rep,120,pendek,rendah,tinggi", "var,120,pendek,rendah,rendah"],
        {"rep": repetitive, "var": NOTES},
    )
    by_name = {check.sample.name: check for check in corpus.check_all(data)}
    assert (
        by_name["rep"].facts["repetition_saving_pct"]
        > by_name["var"].facts["repetition_saving_pct"]
    )


def test_missing_audio_is_reported(tmp_path):
    data = build_corpus(
        tmp_path, ["s1,120,pendek,rendah,rendah"], {"s1": NOTES}, with_audio=False
    )
    check = corpus.check_all(data)[0]
    assert not check.ok
    assert any("missing audio" in problem for problem in check.problems)


def test_an_unrepresentable_tempo_is_reported(tmp_path):
    data = build_corpus(tmp_path, ["s1,400,pendek,rendah,rendah"], {"s1": NOTES})
    check = corpus.check_all(data)[0]
    assert any("outside" in problem for problem in check.problems)


def test_a_tempo_that_hides_short_notes_is_reported(tmp_path):
    data = build_corpus(tmp_path, ["s1,250,pendek,rendah,rendah"], {"s1": NOTES})
    check = corpus.check_all(data)[0]
    assert any("minimum_note_length" in problem for problem in check.problems)


def test_an_unknown_level_is_reported(tmp_path):
    data = build_corpus(tmp_path, ["s1,120,pendek,banyak,rendah"], {"s1": NOTES})
    check = corpus.check_all(data)[0]
    assert any("kerapatan" in problem for problem in check.problems)


def test_a_wrong_tempo_shows_up_as_grid_error(tmp_path):
    """The reference is written on the grid, so it must quantise cleanly."""
    data = build_corpus(tmp_path, ["s1,113,pendek,rendah,rendah"], {"s1": NOTES})
    check = corpus.check_all(data)[0]
    assert any("off a" in problem for problem in check.problems)


def test_audio_far_longer_than_the_notation_is_reported(tmp_path):
    data = build_corpus(tmp_path, ["s1,120,pendek,rendah,rendah"], {"s1": NOTES})
    write_audio(data / "audio" / "s1.mp3", seconds=60.0)  # re-export gone wrong
    check = corpus.check_all(data)[0]
    assert any("different states" in problem for problem in check.problems)


def test_audio_shorter_than_the_notation_is_reported(tmp_path):
    data = build_corpus(tmp_path, ["s1,120,pendek,rendah,rendah"], {"s1": NOTES})
    write_audio(data / "audio" / "s1.mp3", seconds=1.0)
    check = corpus.check_all(data)[0]
    assert any("missing music" in problem for problem in check.problems)


def test_a_normal_release_tail_is_accepted(tmp_path):
    """Audio outlasts the last note-off by release and reverb; that is normal."""
    data = build_corpus(tmp_path, ["s1,120,pendek,rendah,rendah"], {"s1": NOTES})
    midi_seconds = max(n.position + n.duration for n in NOTES) * cfg.grid_unit_seconds(120)
    write_audio(data / "audio" / "s1.mp3", seconds=midi_seconds + 2.0)
    check = corpus.check_all(data)[0]
    assert check.ok, check.problems


def test_cli_exit_code_reflects_failures(tmp_path, capsys):
    ok = build_corpus(tmp_path / "ok", ["s1,120,pendek,rendah,rendah"], {"s1": NOTES})
    assert corpus.main(["--data-dir", str(ok)]) == 0

    bad = build_corpus(
        tmp_path / "bad",
        ["s1,120,pendek,rendah,rendah"],
        {"s1": NOTES},
        with_audio=False,
    )
    assert corpus.main(["--data-dir", str(bad)]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_cli_reports_coverage_gaps(tmp_path, capsys):
    data = build_corpus(tmp_path, ["s1,120,pendek,rendah,rendah"], {"s1": NOTES})
    corpus.main(["--data-dir", str(data)])
    output = capsys.readouterr().out
    assert "coverage" in output
    assert "missing" in output
