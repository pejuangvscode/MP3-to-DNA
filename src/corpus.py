"""Check the test corpus before any experiment is run (Subbab 3.2.5, Tabel 3.4).

The corpus is composed by hand in FL Studio, so mistakes are easy to make and
expensive to find later: a tempo typed wrong, an export missing, a rest longer
than the token scheme can encode. Every one of those would surface as a strange
result rather than as an error, halfway through Bab IV.

This module checks each sample against what the pipeline can actually represent,
and measures the repetition each one carries, so the corpus can be shown to vary
along the dimension Tabel 3.4 calls the most important.

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

#: Tabel 3.4 grades duration on its own scale, not the shared low/medium/high
#: one the other two dimensions use.
DURATION_LEVELS = ("pendek", "sedang", "panjang")
MAGNITUDE_LEVELS = ("rendah", "sedang", "tinggi")

#: (manifest column, attribute on CorpusSample, permitted levels)
DIMENSIONS = (
    ("durasi", "duration_level", DURATION_LEVELS),
    ("kerapatan", "density_level", MAGNITUDE_LEVELS),
    ("pengulangan", "repetition_level", MAGNITUDE_LEVELS),
)


@dataclass(frozen=True)
class CorpusSample:
    """One row of the manifest, resolved to files on disk."""

    name: str
    tempo: int
    duration_level: str
    density_level: str
    repetition_level: str
    audio_path: Path
    midi_path: Path


@dataclass
class SampleCheck:
    sample: CorpusSample
    problems: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def load_manifest(data_dir: str | Path) -> list[CorpusSample]:
    """Read data/corpus.csv and resolve each row to its audio and MIDI files."""
    data_dir = Path(data_dir)
    manifest = data_dir / "corpus.csv"
    if not manifest.is_file():
        raise FileNotFoundError(
            f"no manifest at {manifest}. See docs/CORPUS.md for the format."
        )

    samples: list[CorpusSample] = []
    with open(manifest, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = set(MANIFEST_COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(
                f"{manifest.name} is missing columns: {', '.join(sorted(missing))}"
            )

        for line, row in enumerate(reader, start=2):
            name = (row["sample"] or "").strip()
            if not name:
                raise ValueError(f"{manifest.name} line {line}: empty sample name")
            try:
                tempo = int(row["tempo"])
            except (TypeError, ValueError):
                raise ValueError(
                    f"{manifest.name} line {line}: tempo {row['tempo']!r} "
                    "is not an integer"
                ) from None

            samples.append(
                CorpusSample(
                    name=name,
                    tempo=tempo,
                    duration_level=(row["durasi"] or "").strip().lower(),
                    density_level=(row["kerapatan"] or "").strip().lower(),
                    repetition_level=(row["pengulangan"] or "").strip().lower(),
                    audio_path=data_dir / "audio" / f"{name}.mp3",
                    midi_path=data_dir / "ground_truth" / f"{name}.mid",
                )
            )

    if not samples:
        raise ValueError(f"{manifest.name} lists no samples")
    return samples


def check_sample(
    sample: CorpusSample, grid_code: int = cfg.DEFAULT_GRID_CODE
) -> SampleCheck:
    """Verify one sample is usable, and measure what it contains."""
    from src import preprocess
    from src.quantize import quantize
    from src.reconstruct import read_midi
    from src.tokenizer import TokenRangeError, compress, notes_to_tokens

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

    try:
        cfg.assert_min_note_length_fits(sample.tempo, grid_code)
    except ValueError as exc:
        check.problems.append(str(exc))

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
        # The two exports must describe the same music. The test is one-sided:
        # audio always outlasts the final note-off by the instrument's release
        # and any reverb tail, so running longer is normal and only a large
        # excess is suspicious. Running *shorter* means the render is missing
        # music the reference contains.
        if audio.duration < midi_duration - 0.5:
            check.problems.append(
                f"audio ends at {audio.duration:.2f} s but the reference MIDI "
                f"runs to {midi_duration:.2f} s; the render is missing music"
            )
        elif audio.duration > midi_duration + 5.0:
            check.problems.append(
                f"audio is {audio.duration:.2f} s against {midi_duration:.2f} s "
                "of notation; the tail is longer than a release can explain, so "
                "the two exports may come from different states of the project"
            )

    quantised = quantize(reference, sample.tempo, grid_code)
    check.facts["quantised_notes"] = len(quantised.notes)
    check.facts["merged_notes"] = quantised.merged_count
    check.facts["clamped_durations"] = quantised.clamped_count
    check.facts["rms_grid_error_ms"] = quantised.rms_grid_error_ms

    # The reference is written on the piano roll, so it should sit exactly on
    # the grid. A large error means the tempo is wrong or the piece uses
    # figures the grid cannot express, such as triplets (Subbab 3.2.5).
    if quantised.rms_grid_error_ms > quantised.grid_unit_ms / 4:
        check.problems.append(
            f"reference notes sit {quantised.rms_grid_error_ms:.1f} ms off a "
            f"{quantised.grid_unit_ms:.1f} ms grid; check the tempo and that the "
            "piece contains no triplets"
        )

    try:
        tokens = notes_to_tokens(quantised.notes)
    except TokenRangeError as exc:
        check.problems.append(f"does not fit the token scheme: {exc}")
        return check

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

    return check


def check_all(
    data_dir: str | Path, grid_code: int = cfg.DEFAULT_GRID_CODE
) -> list[SampleCheck]:
    return [check_sample(sample, grid_code) for sample in load_manifest(data_dir)]


def _coverage(checks: list[SampleCheck]) -> list[str]:
    """Whether the corpus actually spans the three axes of Tabel 3.4."""
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
        default=cfg.DEFAULT_GRID_CODE,
        choices=sorted(cfg.GRID_SUBDIVISIONS),
    )
    args = parser.parse_args(argv)

    try:
        checks = check_all(args.data_dir, args.grid)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    lines: list[str] = []
    for check in checks:
        mark = "ok  " if check.ok else "FAIL"
        sample = check.sample
        lines.append(
            f"{mark} {sample.name:<16} {sample.tempo:3d} BPM  "
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
