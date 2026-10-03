"""Token stream -> MIDI (Tabel 3.5)."""

from __future__ import annotations

import pytest

from src import config as cfg
from src.quantize import quantize, to_seconds
from src.reconstruct import RECONSTRUCTION_VELOCITY, read_midi, to_midi
from src.tokenizer import QuantizedNote

NOTES = [
    QuantizedNote(60, 0, 4),
    QuantizedNote(64, 4, 4),
    QuantizedNote(67, 8, 8),
    QuantizedNote(72, 16, 4),
]


def test_midi_carries_the_notes(tmp_path):
    path = to_midi(NOTES, tmp_path / "out.mid", tempo=120)
    recovered = read_midi(path)

    assert [pitch for pitch, _, _ in recovered] == [note.pitch for note in NOTES]
    expected = to_seconds(NOTES, 120)
    for (_, start, end), (_, ref_start, ref_end) in zip(recovered, expected):
        assert start == pytest.approx(ref_start, abs=0.005)
        assert end == pytest.approx(ref_end, abs=0.005)


def test_grid_positions_survive_a_trip_through_midi(tmp_path):
    """MIDI tick resolution is far finer than the grid, so nothing moves."""

    class Timed:
        def __init__(self, pitch, start, end):
            self.pitch, self.start, self.end = pitch, start, end

    path = to_midi(NOTES, tmp_path / "out.mid", tempo=120)
    requantised = quantize([Timed(*note) for note in read_midi(path)], 120)
    assert list(requantised.notes) == NOTES


@pytest.mark.parametrize("tempo", [40, 96, 120, 180, 295])
def test_every_representable_tempo_round_trips(tmp_path, tempo):
    class Timed:
        def __init__(self, pitch, start, end):
            self.pitch, self.start, self.end = pitch, start, end

    path = to_midi(NOTES, tmp_path / f"{tempo}.mid", tempo=tempo)
    requantised = quantize([Timed(*note) for note in read_midi(path)], tempo)
    assert list(requantised.notes) == NOTES


def test_velocity_is_fixed_because_tokens_do_not_store_it(tmp_path):
    """Tabel 3.8 has no velocity field, so humanised velocity is discarded."""
    import pretty_midi

    path = to_midi(NOTES, tmp_path / "out.mid", tempo=120)
    midi = pretty_midi.PrettyMIDI(str(path))
    velocities = {note.velocity for note in midi.instruments[0].notes}
    assert velocities == {RECONSTRUCTION_VELOCITY}


def test_reconstruction_is_a_single_track(tmp_path):
    """Tokens carry no channel, so two instruments come back merged."""
    import pretty_midi

    path = to_midi(NOTES, tmp_path / "out.mid", tempo=120)
    assert len(pretty_midi.PrettyMIDI(str(path)).instruments) == 1


def test_simultaneous_notes_are_kept(tmp_path):
    chord = [QuantizedNote(60, 0, 4), QuantizedNote(64, 0, 4), QuantizedNote(67, 0, 4)]
    path = to_midi(chord, tmp_path / "chord.mid", tempo=120)
    recovered = read_midi(path)
    assert len(recovered) == 3
    assert [pitch for pitch, _, _ in recovered] == [60, 64, 67]
    assert all(start == pytest.approx(0.0, abs=1e-6) for _, start, _ in recovered)


def test_notes_come_back_sorted(tmp_path):
    path = to_midi(NOTES, tmp_path / "out.mid", tempo=120)
    recovered = read_midi(path)
    assert recovered == sorted(recovered, key=lambda n: (n[1], n[0], n[2]))


def test_drum_tracks_are_skipped(tmp_path):
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(initial_tempo=120.0)
    pitched = pretty_midi.Instrument(program=0)
    pitched.notes.append(pretty_midi.Note(80, 60, 0.0, 0.5))
    drums = pretty_midi.Instrument(program=0, is_drum=True)
    drums.notes.append(pretty_midi.Note(80, 36, 0.0, 0.5))
    midi.instruments.extend([pitched, drums])

    path = tmp_path / "mixed.mid"
    midi.write(str(path))
    assert [pitch for pitch, _, _ in read_midi(path)] == [60]


def test_full_decode_path(tmp_path):
    """Tokens off the wire, through DNA, back to notation."""
    from src import dna_codec as codec
    from src.tokenizer import decode_bytes, encode_notes

    encoded = encode_notes(NOTES, 120)
    report = codec.encode(encoded.data)
    decoded = decode_bytes(codec.decode(report.oligos))

    assert list(decoded.notes) == NOTES
    path = to_midi(
        decoded.notes, tmp_path / "final.mid", decoded.tempo, decoded.grid_code
    )
    assert len(read_midi(path)) == len(NOTES)
