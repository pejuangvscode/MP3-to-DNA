"""Audio preprocessing and transcription.

The only tests that touch real audio and the model. Since transcription output
is not bit-reproducible, these check plumbing and contracts, not exact notes.
"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from src import config as cfg
from src import preprocess
from src.transcribe import TranscriptionParams, transcribe_cached


def tone(path, frequency=440.0, seconds=1.0, sample_rate=44100, channels=1):
    """A pure tone written to disk, loud enough for the model to find."""
    times = np.arange(int(seconds * sample_rate)) / sample_rate
    wave = 0.5 * np.sin(2 * np.pi * frequency * times)
    envelope = np.minimum(1.0, np.minimum(times, seconds - times) * 40.0)
    signal = (wave * envelope).astype(np.float32)
    if channels > 1:
        signal = np.repeat(signal[:, None], channels, axis=1)
    sf.write(path, signal, sample_rate, subtype="FLOAT")
    return path


# --- preprocessing ---

def test_audio_is_resampled_to_the_model_rate(tmp_path):
    audio = preprocess.load(tone(tmp_path / "a.wav", sample_rate=44100))
    assert audio.sample_rate == cfg.TARGET_SAMPLE_RATE == 22050
    assert audio.source_sample_rate == 44100
    assert audio.samples.ndim == 1
    assert audio.duration == pytest.approx(1.0, abs=0.01)


def test_stereo_is_mixed_down_to_mono(tmp_path):
    audio = preprocess.load(tone(tmp_path / "s.wav", channels=2))
    assert audio.source_channels == 2
    assert audio.samples.ndim == 1


def test_channels_are_averaged_not_dropped(tmp_path):
    """A note panned hard to one channel must not vanish."""
    sample_rate = 22050
    left = 0.5 * np.sin(2 * np.pi * 440 * np.arange(sample_rate) / sample_rate)
    stereo = np.stack([left, np.zeros_like(left)], axis=1).astype(np.float32)
    path = tmp_path / "panned.wav"
    sf.write(path, stereo, sample_rate, subtype="FLOAT")

    audio = preprocess.load(path)
    assert np.abs(audio.samples).max() > 0.2


def test_leading_silence_is_measured(tmp_path):
    sample_rate = 22050
    silence = np.zeros(sample_rate // 2, dtype=np.float32)
    times = np.arange(sample_rate) / sample_rate
    signal = np.concatenate(
        [silence, (0.5 * np.sin(2 * np.pi * 440 * times)).astype(np.float32)]
    )
    path = tmp_path / "delayed.wav"
    sf.write(path, signal, sample_rate, subtype="FLOAT")

    audio = preprocess.load(path)
    assert preprocess.leading_silence(audio) == pytest.approx(0.5, abs=0.01)


def test_trailing_silence_is_measured(tmp_path):
    sample_rate = 22050
    times = np.arange(sample_rate) / sample_rate
    signal = np.concatenate(
        [
            (0.5 * np.sin(2 * np.pi * 440 * times)).astype(np.float32),
            np.zeros(sample_rate // 2, dtype=np.float32),
        ]
    )
    path = tmp_path / "tail.wav"
    sf.write(path, signal, sample_rate, subtype="FLOAT")

    audio = preprocess.load(path)
    assert preprocess.trailing_silence(audio) == pytest.approx(0.5, abs=0.01)


def test_a_decaying_tail_shortens_as_the_threshold_rises(tmp_path):
    """What separates a release tail from an unnotated note: a decay falls away
    steeply as the threshold rises, where a real note would hold.
    """
    sample_rate = 22050
    times = np.arange(2 * sample_rate) / sample_rate
    decay = np.exp(-times * 4.0)
    signal = (0.9 * decay * np.sin(2 * np.pi * 440 * times)).astype(np.float32)
    path = tmp_path / "decay.wav"
    sf.write(path, signal, sample_rate, subtype="FLOAT")

    audio = preprocess.load(path)
    quiet = audio.duration - preprocess.trailing_silence(audio, -60.0)
    loud = audio.duration - preprocess.trailing_silence(audio, -40.0)
    assert loud < quiet


def test_wav_written_for_the_model_reloads_unchanged(tmp_path):
    audio = preprocess.load(tone(tmp_path / "a.wav"))
    written = preprocess.write_wav(audio, tmp_path / "prepared.wav")

    reloaded = preprocess.load(written)
    assert reloaded.sample_rate == audio.sample_rate
    assert np.allclose(reloaded.samples, audio.samples, atol=1e-6)


def test_mp3_is_readable_without_ffmpeg(tmp_path):
    """libsndfile 1.1+ handles MP3, so the pipeline needs no external decoder."""
    if "MP3" not in sf.available_formats():
        pytest.skip("libsndfile build without MP3 support")
    path = tmp_path / "a.mp3"
    try:
        tone(path, sample_rate=44100)
    except Exception:  # read support does not imply write support
        pytest.skip("libsndfile cannot write MP3 in this build")

    audio = preprocess.load(path)
    assert audio.sample_rate == cfg.TARGET_SAMPLE_RATE
    assert audio.duration > 0.5


def test_describe_reports_the_facts_bab_iv_tabulates(tmp_path):
    audio = preprocess.load(tone(tmp_path / "a.wav"))
    described = preprocess.describe(audio)
    assert described["sample_rate"] == cfg.TARGET_SAMPLE_RATE
    assert described["source_channels"] == 1
    assert 0.0 < described["peak"] <= 1.0


# --- transcription ---

@pytest.mark.slow
def test_transcription_finds_a_sustained_tone(tmp_path):
    """A440 is MIDI note 69; the model should place a note near it."""
    audio = preprocess.load(tone(tmp_path / "a.wav", frequency=440.0, seconds=2.0))
    prepared = preprocess.write_wav(audio, tmp_path / "prepared.wav")

    result = transcribe_cached(prepared, tmp_path / "cache")
    assert result.note_count > 0
    assert any(abs(note.pitch - 69) <= 1 for note in result.notes)


@pytest.mark.slow
def test_notes_come_back_sorted(tmp_path):
    audio = preprocess.load(tone(tmp_path / "a.wav", seconds=2.0))
    prepared = preprocess.write_wav(audio, tmp_path / "prepared.wav")

    notes = transcribe_cached(prepared, tmp_path / "cache").notes
    assert list(notes) == sorted(notes, key=lambda n: (n.start, n.pitch, n.end))


@pytest.mark.slow
def test_cache_is_reused_and_matches(tmp_path):
    """Model output is not bit-reproducible, so it is cached (Tabel 3.2)."""
    audio = preprocess.load(tone(tmp_path / "a.wav", seconds=2.0))
    prepared = preprocess.write_wav(audio, tmp_path / "prepared.wav")
    cache = tmp_path / "cache"

    first = transcribe_cached(prepared, cache)
    second = transcribe_cached(prepared, cache)

    assert not first.from_cache
    assert second.from_cache
    assert first.notes == second.notes


@pytest.mark.slow
def test_changed_parameters_bypass_the_cache(tmp_path):
    audio = preprocess.load(tone(tmp_path / "a.wav", seconds=2.0))
    prepared = preprocess.write_wav(audio, tmp_path / "prepared.wav")
    cache = tmp_path / "cache"

    transcribe_cached(prepared, cache)
    other = transcribe_cached(
        prepared, cache, TranscriptionParams(onset_threshold=0.9)
    )
    assert not other.from_cache


@pytest.mark.slow
def test_midi_is_written_for_baseline_b2(tmp_path):
    """Comparison path B2 encodes the transcribed MIDI (Tabel 3.12)."""
    audio = preprocess.load(tone(tmp_path / "a.wav", seconds=2.0))
    prepared = preprocess.write_wav(audio, tmp_path / "prepared.wav")
    midi_path = tmp_path / "transcribed.mid"

    transcribe_cached(prepared, tmp_path / "cache", midi_path=midi_path)
    assert midi_path.is_file() and midi_path.stat().st_size > 0
