"""Validate the test corpus before any experiment runs (Subbab 3.2.5, Tabel 3.4).

The corpus is composed by hand in FL Studio, so a wrong tempo, a missing export,
or a rest longer than the token scheme can encode is easy to introduce and would
surface as a strange result rather than an error. Also measures how much
repetition each sample actually carries.

    python -m src.corpus --data-dir data
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

from src import config as cfg

MANIFEST_COLUMNS = ("sample", "tempo", "durasi", "kerapatan", "pengulangan")

#: level at which sound after the last note-off counts as a note rather than a
#: release tail. A decaying release falls away steeply across thresholds while a
#: real note holds, so this separates the two without timing either.
TAIL_THRESHOLD_DB = -40.0

# Tabel 3.4 grades duration on its own scale, not the shared low/medium/high
DURATION_LEVELS = ("pendek", "sedang", "panjang")
MAGNITUDE_LEVELS = ("rendah", "sedang", "tinggi")

# (manifest column, attribute, permitted levels)
DIMENSIONS = (
    ("durasi", "duration_level", DURATION_LEVELS),
    ("kerapatan", "density_level", MAGNITUDE_LEVELS),
    ("pengulangan", "repetition_level", MAGNITUDE_LEVELS),
)


@dataclass(frozen=True)
class CorpusSample:
    """One manifest row, resolved to files on disk."""

    name: str
    tempo: int
    duration_level: str
    density_level: str
    repetition_level: str
    audio_path: Path
    midi_path: Path
    # the header carries 2 bits of grid resolution, so the grid is a per-sample
    # property; a piece in triplets needs a different one from a piece in
    # sixteenths, and forcing one grid on the whole corpus misaligns both
    grid_code: int = cfg.DEFAULT_GRID_CODE
    # which half of the corpus this belongs to; parameters are calibrated on
    # "dev" and reported on "test", so the two must never be mixed
    split: str = "test"
    inst_class: str = ""


@dataclass
class SampleCheck:
    sample: CorpusSample
    problems: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def _find_audio(data_dir: Path, name: str) -> Path:
    """The sample's audio, whatever container it came in.

    The hand-built corpus is MP3; the Slakh corpus is FLAC. libsndfile reads
    both, so the extension is a lookup detail rather than a format decision.
    """
    for suffix in (".mp3", ".flac", ".wav"):
        candidate = data_dir / "audio" / f"{name}{suffix}"
        if candidate.is_file():
            return candidate
    return data_dir / "audio" / f"{name}.mp3"


def load_manifest(data_dir: str | Path) -> list[CorpusSample]:
    """Read data/corpus.csv and resolve each row to its files."""
    data_dir = Path(data_dir)
    manifest = data_dir / "corpus.csv"
    samples: list[CorpusSample] = []
    with open(manifest, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = row["sample"].strip()
            tempo = int(row["tempo"])

            # a prepared corpus names its files explicitly, because segments cut
            # out of one source track do not follow the one-name-one-file rule
            audio = (row.get("audio_path") or "").strip()
            midi = (row.get("midi_path") or "").strip()

            samples.append(
                CorpusSample(
                    name=name,
                    tempo=tempo,
                    duration_level=(row["durasi"] or "").strip().lower(),
                    density_level=(row["kerapatan"] or "").strip().lower(),
                    repetition_level=(row["pengulangan"] or "").strip().lower(),
                    audio_path=Path(audio) if audio else _find_audio(data_dir, name),
                    midi_path=Path(midi) if midi else data_dir / "ground_truth" / f"{name}.mid",
                    grid_code=int(row.get("grid") or cfg.DEFAULT_GRID_CODE),
                    split=(row.get("split") or "test").strip().lower(),
                    inst_class=(row.get("inst_class") or "").strip(),
                )
            )

    return samples


def check_sample(sample: CorpusSample, grid_code: int | None = None) -> SampleCheck:
    """Check one sample is usable and measure what it contains.

    `grid_code` overrides the manifest, for sweeping one grid across the corpus.
    """
    grid_code = sample.grid_code if grid_code is None else grid_code
    from src import preprocess
    from src.quantize import quantize
    from src.reconstruct import read_midi
    from src.tokenizer import compress, notes_to_tokens

    check = SampleCheck(sample)

    for column, attribute, permitted in DIMENSIONS:
        value = getattr(sample, attribute)
        if value not in permitted:
            check.problems.append(
                f"{column} is {value!r}, expected one of {list(permitted)}"
            )

    if not cfg.MIN_TEMPO <= sample.tempo <= cfg.MAX_TEMPO:
        check.problems.append(
            f"tempo {sample.tempo} is outside the {cfg.MIN_TEMPO}..{cfg.MAX_TEMPO} "
            "BPM the token header can represent"
        )
        return check

    unit_ms = cfg.grid_unit_seconds(sample.tempo, grid_code) * 1000.0
    if cfg.MINIMUM_NOTE_LENGTH_MS >= unit_ms:
        check.problems.append(
            f"minimum_note_length ({cfg.MINIMUM_NOTE_LENGTH_MS:.0f} ms) is not "
            f"shorter than one grid unit at {sample.tempo} BPM ({unit_ms:.1f} ms)"
        )

    if not sample.audio_path.is_file():
        check.problems.append(f"missing audio: {sample.audio_path}")
    if not sample.midi_path.is_file():
        check.problems.append(f"missing reference MIDI: {sample.midi_path}")
    if check.problems and not sample.midi_path.is_file():
        return check

    reference = read_midi(sample.midi_path)
    if not reference:
        check.problems.append("reference MIDI contains no notes")
        return check

    midi_duration = max(note.end for note in reference)
    check.facts["reference_notes"] = len(reference)
    check.facts["midi_duration_s"] = round(midi_duration, 2)
    check.facts["note_density_per_s"] = round(len(reference) / midi_duration, 2)
    check.facts["pitch_range"] = (
        min(note.pitch for note in reference),
        max(note.pitch for note in reference),
    )

    if sample.audio_path.is_file():
        audio = preprocess.load(sample.audio_path)
        check.facts["audio_duration_s"] = round(audio.duration, 2)
        check.facts["leading_silence_s"] = round(preprocess.leading_silence(audio), 4)
        # one-sided: audio normally outlasts the last note-off by the release
        # and reverb tail, but running shorter means music is missing
        if audio.duration < midi_duration - 0.5:
            check.problems.append(
                f"audio ends at {audio.duration:.2f} s but the reference MIDI "
                f"runs to {midi_duration:.2f} s; the render is missing music"
            )
        else:
            # a stem that stops before the band does leaves a long but silent
            # tail, which is fine; a note the notation does not have is not.
            # Measured at note level rather than at the noise floor, because a
            # sampled instrument's release decays for seconds after note-off and
            # would otherwise read as unnotated music
            sounding_tail = audio.duration - preprocess.trailing_silence(
                audio, TAIL_THRESHOLD_DB
            )
            check.facts["sounding_tail_s"] = round(
                max(0.0, sounding_tail - midi_duration), 2
            )
            if sounding_tail > midi_duration + 5.0:
                check.problems.append(
                    f"audio still sounds at {sounding_tail:.2f} s against "
                    f"{midi_duration:.2f} s of notation; the two exports may come "
                    "from different states of the project"
                )

    quantised = quantize(reference, sample.tempo, grid_code)
    check.facts["quantised_notes"] = len(quantised.notes)
    check.facts["merged_notes"] = quantised.merged_count
    check.facts["clamped_durations"] = quantised.clamped_count
    check.facts["rms_grid_error_ms"] = quantised.rms_grid_error_ms

    # the reference comes off the piano roll, so it should sit on the grid; a
    # large error means the wrong tempo or triplets
    if quantised.rms_grid_error_ms > quantised.grid_unit_ms / 4:
        check.problems.append(
            f"reference notes sit {quantised.rms_grid_error_ms:.1f} ms off a "
            f"{quantised.grid_unit_ms:.1f} ms grid; check the tempo and that the "
            "piece contains no triplets"
        )

    tokens = notes_to_tokens(quantised.notes)
    compressed = compress(tokens)
    check.facts["tokens_plain"] = len(tokens)
    check.facts["tokens_compressed"] = len(compressed)
    check.facts["repetition_saving_pct"] = round(
        (1 - len(compressed) / len(tokens)) * 100.0, 1
    )

    if len(tokens) > cfg.MAX_TOKEN_COUNT:
        check.problems.append(
            f"{len(tokens)} tokens exceeds the {cfg.MAX_TOKEN_COUNT} the header "
            "can count"
        )

    # the delta field is 8 bits and nothing clamps it, so an overlong rest wraps
    # silently and still round-trips losslessly; the damage would surface as a
    # lower F-measure blamed on quantisation
    max_delta = max((token.delta for token in tokens), default=0)
    check.facts["max_delta_units"] = max_delta
    if max_delta > cfg.MAX_DELTA_UNITS:
        check.problems.append(
            f"a rest of {max_delta} grid units exceeds the {cfg.MAX_DELTA_UNITS} "
            "an 8-bit delta can hold; it would wrap silently, so cut the sample "
            "at its long rests"
        )

    check.facts["clamped_durations"] = quantised.clamped_count

    return check


def check_all(
    data_dir: str | Path, grid_code: int | None = None
) -> list[SampleCheck]:
    return [check_sample(sample, grid_code) for sample in load_manifest(data_dir)]


def _coverage(checks: list[SampleCheck]) -> list[str]:
    """Whether the corpus spans the three axes of Tabel 3.4."""
    lines = ["", "--- coverage (Tabel 3.4) ---"]
    for column, attribute, permitted in DIMENSIONS:
        seen = {getattr(check.sample, attribute) for check in checks}
        missing = [level for level in permitted if level not in seen]
        state = "complete" if not missing else f"missing {', '.join(missing)}"
        lines.append(f"  {column:<12} {state}")

    measured = [
        (check.sample.repetition_level, check.facts.get("repetition_saving_pct"))
        for check in checks
        if check.facts.get("repetition_saving_pct") is not None
    ]
    if measured:
        lines.append("")
        lines.append("  measured repetition, by declared level:")
        for level in MAGNITUDE_LEVELS:
            values = [value for name, value in measured if name == level]
            if values:
                lines.append(
                    f"    {level:<8} {min(values):5.1f} .. {max(values):5.1f} % "
                    f"token saving  (n={len(values)})"
                )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.corpus",
        description="Validate the test corpus against what the pipeline can encode.",
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--grid",
        type=int,
        default=None,
        choices=sorted(cfg.GRID_SUBDIVISIONS),
        help="override the per-sample grid recorded in the manifest",
    )
    args = parser.parse_args(argv)

    checks = check_all(args.data_dir, args.grid)

    lines: list[str] = []
    for check in checks:
        mark = "ok  " if check.ok else "FAIL"
        sample = check.sample
        lines.append(
            f"{mark} {sample.name:<22} {sample.tempo:3d} BPM  "
            f"1/{4 * cfg.GRID_SUBDIVISIONS[args.grid or sample.grid_code]:<2d}  "
            f"{sample.duration_level}/{sample.density_level}/"
            f"{sample.repetition_level}"
        )
        if check.facts:
            facts = check.facts
            lines.append(
                f"       {facts.get('reference_notes', '?')} notes, "
                f"{facts.get('midi_duration_s', '?')} s, "
                f"{facts.get('note_density_per_s', '?')} notes/s, "
                f"repetition saving {facts.get('repetition_saving_pct', '?')} %"
            )
        for problem in check.problems:
            lines.append(f"       - {problem}")

    lines += _coverage(checks)

    failed = [check for check in checks if not check.ok]
    lines += [
        "",
        f"{len(checks) - len(failed)} of {len(checks)} samples usable",
    ]
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
