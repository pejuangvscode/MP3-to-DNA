"""Choose the onset threshold on the dev split, so the test split stays unseen.

The onset threshold decides how strong the model's activation must be before a
note is emitted, and it is the parameter the whole pipeline is most sensitive
to. Picking it on the same material the result is reported on turns the headline
accuracy into a fitted number, which is why the corpus carries a dev/test split
and why this refuses to sweep the test half without being told twice.

Only transcription, quantisation and scoring are run here, not the DNA stages.
That is not a shortcut: the codec is verified lossless, so the reconstructed
notes equal the quantised notes and the F-measure is identical either way. It is
also the right signal to calibrate on, because base count is fixed by Reed
Solomon codeword granularity over most of the useful threshold range and so
carries no information about the threshold at all.

    python -m src.calibrate --data-dir data/slakh --split dev
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from src import config as cfg
from src import evaluate, preprocess
from src.corpus import CorpusSample, load_manifest
from src.quantize import quantize, to_seconds
from src.reconstruct import read_midi
from src.transcribe import TranscriptionParams, transcribe_cached

DEFAULT_SWEEP = (0.30, 0.40, 0.50, 0.60, 0.70, 0.80)


@dataclass(frozen=True)
class Point:
    """One threshold measured over one sample."""

    threshold: float
    sample: str
    inst_class: str
    reference_notes: int
    transcribed_notes: int
    quantized_notes: int
    f_measure: float
    precision: float
    recall: float
    f_measure_offset: float


@dataclass(frozen=True)
class Aggregate:
    """One threshold summarised over the whole split."""

    threshold: float
    samples: int
    mean_f: float
    sd_f: float
    median_f: float
    mean_precision: float
    mean_recall: float
    mean_f_offset: float
    mean_notes_ratio: float  # transcribed / reference, 1.0 is neither over nor under


def prepare(sample: CorpusSample, work_dir: Path) -> Path:
    """Decode to the mono 22050 Hz wav the model is given.

    Done exactly as `encode.run` does it, because a threshold measured on
    anything else would not carry over to the run it is meant to configure.
    Hoisted out of `measure` so a sweep pays the resampling once per sample
    rather than once per threshold.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    audio = preprocess.load(sample.audio_path)
    return preprocess.write_wav(audio, work_dir / f"{sample.name}.prepared.wav")


def measure(
    sample: CorpusSample, threshold: float, work_dir: Path, prepared: Path
) -> Point:
    """Transcribe at one threshold and score against the reference."""
    params = TranscriptionParams(onset_threshold=threshold)
    transcription = transcribe_cached(prepared, work_dir / "cache", params=params)
    report = quantize(transcription.notes, sample.tempo, sample.grid_code)
    estimated = to_seconds(report.notes, sample.tempo, sample.grid_code)
    reference = read_midi(sample.midi_path)
    scores = evaluate.accuracy(reference, estimated)

    return Point(
        threshold=threshold,
        sample=sample.name,
        inst_class=sample.inst_class,
        reference_notes=len(reference),
        transcribed_notes=transcription.note_count,
        quantized_notes=len(report.notes),
        f_measure=scores.f_measure,
        precision=scores.precision,
        recall=scores.recall,
        f_measure_offset=scores.f_measure_with_offset,
    )


def summarise(points: list[Point], threshold: float) -> Aggregate:
    chosen = [point for point in points if point.threshold == threshold]
    scores = [point.f_measure for point in chosen]
    ratios = [
        point.transcribed_notes / point.reference_notes
        for point in chosen
        if point.reference_notes
    ]
    return Aggregate(
        threshold=threshold,
        samples=len(chosen),
        mean_f=statistics.fmean(scores),
        sd_f=statistics.stdev(scores) if len(scores) > 1 else 0.0,
        median_f=statistics.median(scores),
        mean_precision=statistics.fmean([p.precision for p in chosen]),
        mean_recall=statistics.fmean([p.recall for p in chosen]),
        mean_f_offset=statistics.fmean([p.f_measure_offset for p in chosen]),
        mean_notes_ratio=statistics.fmean(ratios) if ratios else 0.0,
    )


def sweep(
    data_dir: str | Path,
    out_dir: str | Path,
    thresholds: tuple[float, ...] = DEFAULT_SWEEP,
    split: str = "dev",
) -> tuple[list[Point], list[Aggregate]]:
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    samples = [s for s in load_manifest(data_dir) if s.split == split]

    points: list[Point] = []
    total = len(thresholds) * len(samples)
    done = 0
    for sample in samples:
        prepared = prepare(sample, out_dir / "work")
        for threshold in thresholds:
            done += 1
            print(
                f"[{done}/{total}] {sample.name}  onset {threshold:.2f} ...",
                flush=True,
            )
            points.append(measure(sample, threshold, out_dir / "work", prepared))

    aggregates = [summarise(points, threshold) for threshold in thresholds]

    with open(out_dir / "sweep_per_sample.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "threshold", "sample", "inst_class", "reference_notes",
                "transcribed_notes", "quantized_notes", "precision", "recall",
                "f_measure", "f_measure_offset",
            ]
        )
        for point in points:
            writer.writerow(
                [
                    f"{point.threshold:.2f}", point.sample, point.inst_class,
                    point.reference_notes, point.transcribed_notes,
                    point.quantized_notes, round(point.precision, 4),
                    round(point.recall, 4), round(point.f_measure, 4),
                    round(point.f_measure_offset, 4),
                ]
            )

    with open(out_dir / "sweep_summary.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "threshold", "samples", "mean_f", "sd_f", "median_f",
                "mean_precision", "mean_recall", "mean_f_offset", "mean_notes_ratio",
            ]
        )
        for row in aggregates:
            writer.writerow(
                [
                    f"{row.threshold:.2f}", row.samples, round(row.mean_f, 4),
                    round(row.sd_f, 4), round(row.median_f, 4),
                    round(row.mean_precision, 4), round(row.mean_recall, 4),
                    round(row.mean_f_offset, 4), round(row.mean_notes_ratio, 3),
                ]
            )

    return points, aggregates


def _plateau(aggregates: list[Aggregate]) -> list[Aggregate]:
    """Every threshold whose mean F is within one standard error of the best.

    The sweep on a single sample produced a plateau rather than a peak, so
    naming one winner overstates how sharply the data chooses. Anything inside
    the noise band is reported as an equally defensible choice.
    """
    best = max(aggregates, key=lambda row: row.mean_f)
    margin = best.sd_f / max(1, best.samples) ** 0.5
    return [row for row in aggregates if row.mean_f >= best.mean_f - margin]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.calibrate",
        description="Sweep the onset threshold on the dev split.",
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data/slakh"))
    parser.add_argument("--output", type=Path, default=Path("results/calibration"))
    parser.add_argument(
        "--thresholds", type=float, nargs="*", default=list(DEFAULT_SWEEP)
    )
    parser.add_argument("--split", default="dev")
    parser.add_argument(
        "--i-mean-it",
        action="store_true",
        help="required to sweep any split other than dev",
    )
    args = parser.parse_args(argv)

    if args.split != "dev" and not args.i_mean_it:
        print(
            f"refusing to sweep the {args.split!r} split: calibrating on the data "
            "the result is reported on is what the dev split exists to prevent. "
            "Pass --i-mean-it if that is genuinely what you want.",
            file=sys.stderr,
        )
        return 2

    points, aggregates = sweep(
        args.data_dir, args.output, tuple(args.thresholds), args.split
    )
    if not points:
        print(f"no samples in the {args.split!r} split", file=sys.stderr)
        return 1

    lines = [
        f"onset threshold sweep over {aggregates[0].samples} {args.split} samples",
        "",
        " onset   mean F      SD   median   mean P   mean R   F+off   notes/ref",
    ]
    best = max(aggregates, key=lambda row: row.mean_f)
    plateau = {row.threshold for row in _plateau(aggregates)}
    for row in aggregates:
        mark = "<-- best" if row is best else ("   ~" if row.threshold in plateau else "")
        lines.append(
            f"  {row.threshold:.2f}   {row.mean_f:.4f}  {row.sd_f:.4f}   "
            f"{row.median_f:.4f}   {row.mean_precision:.4f}   {row.mean_recall:.4f}  "
            f"{row.mean_f_offset:.4f}   {row.mean_notes_ratio:7.3f}  {mark}"
        )

    within = sorted(plateau)
    lines += [
        "",
        f"best mean F {best.mean_f:.4f} at onset {best.threshold:.2f}",
        "within one standard error of it: "
        + ", ".join(f"{value:.2f}" for value in within),
        "",
        f"config currently has ONSET_THRESHOLD = {cfg.ONSET_THRESHOLD}",
    ]
    if abs(best.threshold - cfg.ONSET_THRESHOLD) > 1e-9:
        lines.append(
            f"to report on the test split at the calibrated value, pass "
            f"--onset-threshold {best.threshold:.2f} to src.experiment rather than "
            "editing config, so the calibrated run stays distinguishable"
        )
    lines.append(f"tables written to {args.output / 'sweep_summary.csv'}")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
