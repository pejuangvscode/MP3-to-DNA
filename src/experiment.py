"""Run the whole corpus and produce the tables of Tabel 3.14 in one command, so
results can be regenerated rather than transcribed by hand from scattered runs.

Per sample: encode, verify the round trip, check determinism, decode, measure
compliance, count bases against the three comparison paths, score accuracy. The
round-trip check comes first, and a failure is reported as such rather than
folded into the metrics.

    python -m src.experiment --data-dir data --output results
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from src import baselines, config as cfg
from src import dna_codec as codec
from src import decode as decode_path
from src import encode as encode_path
from src import evaluate
from src.corpus import CorpusSample, load_manifest
from src.reconstruct import read_midi
from src.transcribe import TranscriptionParams


@dataclass
class SampleResult:
    """One sample's measurements."""

    sample: CorpusSample
    row: dict
    problems: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


def _timed(function, *args, **kwargs):
    started = time.perf_counter()
    value = function(*args, **kwargs)
    return value, time.perf_counter() - started


def run_sample(
    sample: CorpusSample,
    out_dir: Path,
    grid_code: int | None = None,
    params: TranscriptionParams | None = None,
) -> SampleResult:
    """Encode, decode and measure one sample.

    `grid_code` overrides the manifest, for sweeping one grid across the corpus.
    `params` overrides the transcription thresholds, which is how a value
    calibrated on the dev split is carried over to the test split.
    """
    grid_code = sample.grid_code if grid_code is None else grid_code
    problems: list[str] = []
    row: dict = {
        "sample": sample.name,
        "tempo": sample.tempo,
        "durasi": sample.duration_level,
        "kerapatan": sample.density_level,
        "pengulangan": sample.repetition_level,
    }

    work = out_dir / "work"
    fasta = out_dir / "fasta" / f"{sample.name}.fasta"
    midi_out = out_dir / "reconstructed" / f"{sample.name}.mid"

    started = time.perf_counter()

    # --- encode ---
    encoded, encode_seconds = _timed(
        encode_path.run,
        sample.audio_path,
        sample.tempo,
        fasta,
        grid_code=grid_code,
        work_dir=work,
        cache_dir=work / "cache",
        params=params,
        write_musicxml=True,
        name=sample.name,
    )
    row.update(
        {
            "audio_duration_s": encoded.audio["duration_s"],
            "leading_silence_s": encoded.audio["leading_silence_s"],
            "mp3_bytes": sample.audio_path.stat().st_size,
            "transcribed_notes": encoded.transcription.note_count,
            "offset_ms": round(encoded.offset_ms, 3),
            "offset_concentration": round(encoded.offset_concentration, 4),
            "quantized_notes": len(encoded.quantization.notes),
            "merged_notes": encoded.quantization.merged_count,
            "clamped_durations": encoded.quantization.clamped_count,
            "rms_grid_error_ms": encoded.quantization.rms_grid_error_ms,
            "grid_unit_ms": round(encoded.quantization.grid_unit_ms, 2),
            "tokens_lz77": encoded.tokens.stats.total_tokens,
            "note_tokens": encoded.tokens.stats.note_tokens,
            "reference_tokens": encoded.tokens.stats.reference_tokens,
            "payload_bytes": encoded.tokens.stats.payload_bytes,
            "oligos": encoded.dna.oligo_count,
            "bases_pipeline": encoded.dna.total_bases,
            "rescrambles": encoded.dna.rescramble_count,
            "encode_s": round(encode_seconds, 2),
        }
    )

    # --- repeat detection contribution (Subbab 3.3.5) ---
    plain = encode_path.encode_tokens(
        encoded.quantization, sample.tempo, grid_code, use_repeat_detection=False
    )
    row["tokens_plain"] = plain.stats.total_tokens
    row["payload_bytes_plain"] = plain.stats.payload_bytes
    row["token_saving_pct"] = round(
        (1 - encoded.tokens.stats.total_tokens / plain.stats.total_tokens) * 100.0, 2
    ) if plain.stats.total_tokens else 0.0
    plain_dna = codec.encode(plain.data)
    row["bases_no_lz77"] = plain_dna.total_bases
    row["base_saving_from_lz77_pct"] = round(
        (1 - encoded.dna.total_bases / plain_dna.total_bases) * 100.0, 2
    )

    # --- round trip, before anything else is believed ---
    lossless = codec.verify_lossless(fasta)
    row["lossless"] = lossless
    if lossless is not True:
        problems.append(
            "token round trip is not lossless; every figure for this sample is "
            "suspect (Subbab 3.2.3)"
        )

    # --- determinism (Tabel 3.2) ---
    repeat = codec.encode(encoded.tokens.data)
    deterministic = repeat.oligos == encoded.dna.oligos
    row["deterministic"] = deterministic
    if not deterministic:
        problems.append("a second encoding produced different sequences")

    # --- decode ---
    decoded, decode_seconds = _timed(
        decode_path.run, fasta, midi_out, write_musicxml=True
    )
    row["decode_s"] = round(decode_seconds, 2)
    row["reconstructed_notes"] = len(decoded.tokens.notes)
    if list(decoded.tokens.notes) != list(encoded.quantization.notes):
        problems.append("reconstructed notes differ from the quantised notes")

    # --- compliance ---
    oligos = codec.read_fasta(fasta)
    checked = evaluate.compliance(oligos, encoded.dna.rescramble_count)
    row.update(
        {
            "gc_mean": round(checked.gc_mean, 4),
            "gc_min": round(checked.gc_min, 4),
            "gc_max": round(checked.gc_max, 4),
            "gc_in_range": round(checked.gc_in_range_fraction, 4),
            "max_homopolymer": checked.max_homopolymer,
            "rejection_rate": round(checked.rejection_rate, 4),
            "compliant": checked.compliant,
        }
    )
    if not checked.compliant:
        problems.append("some oligos violate the biological constraints")

    # --- efficiency (Tabel 3.12) ---
    # counted, not built: this path is never decoded, and a two-minute MP3
    # needs more oligos than the 2-byte index can address
    direct = baselines.encode_file(sample.audio_path, "B1 direct", materialize=False)
    symbolic = baselines.symbolic(encoded.transcribed_midi_path)
    theoretical = baselines.theoretical(direct.input_bytes)
    report = evaluate.efficiency(
        encoded.dna.total_bases,
        direct.total_bases,
        symbolic.total_bases,
        payload_bits=encoded.tokens.stats.payload_bytes * 8,
        bases_theoretical=theoretical.total_bases,
    )
    row.update(
        {
            "bases_b1_direct": direct.total_bases,
            "bases_b2_symbolic": symbolic.total_bases,
            "bases_b3_theoretical": theoretical.total_bases,
            "b1_addressable": direct.addressable,
            "saving_total_pct": round(report.total_saving_pct, 4),
            "saving_transcription_pct": round(report.transcription_contribution_pct, 4),
            "saving_token_scheme_pct": round(report.token_scheme_contribution_pct, 4),
            "effective_density": round(report.effective_density, 4),
        }
    )

    # --- accuracy (Subbab 2.9), only where a reference exists ---
    if sample.midi_path.is_file():
        reference = read_midi(sample.midi_path)
        transcribed = read_midi(encoded.transcribed_midi_path)
        reconstructed = read_midi(midi_out)
        decomposed = evaluate.decompose(
            reference, transcribed, reconstructed, codec_lossless=lossless
        )
        scores = decomposed.overall
        row.update(
            {
                "reference_notes": len(reference),
                "precision": round(scores.precision, 4),
                "recall": round(scores.recall, 4),
                "f_measure": round(scores.f_measure, 4),
                "precision_offset": round(scores.precision_with_offset, 4),
                "recall_offset": round(scores.recall_with_offset, 4),
                "f_measure_offset": round(scores.f_measure_with_offset, 4),
                "f_transcription": round(decomposed.transcription.f_measure, 4),
                "f_quantization": round(decomposed.quantization.f_measure, 4),
            }
        )
    else:
        problems.append(
            f"no reference notation at {sample.midi_path}; accuracy cannot be "
            "measured for this sample"
        )

    row["total_s"] = round(time.perf_counter() - started, 2)
    return SampleResult(sample, row, problems)


def run_all(
    data_dir: str | Path,
    out_dir: str | Path,
    grid_code: int | None = None,
    only: Sequence[str] | None = None,
    split: str | None = None,
    params: TranscriptionParams | None = None,
) -> list[SampleResult]:
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    samples = load_manifest(data_dir)
    if split:
        samples = [sample for sample in samples if sample.split == split]
    if only:
        wanted = set(only)
        samples = [sample for sample in samples if sample.name in wanted]

    results: list[SampleResult] = []
    for index, sample in enumerate(samples, start=1):
        print(f"[{index}/{len(samples)}] {sample.name} ...", flush=True)
        results.append(run_sample(sample, out_dir, grid_code, params))
    return results


# --- tables ---

def _markdown_table(rows: list[dict], columns: list[tuple[str, str]]) -> list[str]:
    """Rows as a markdown table, given (key, heading) pairs."""
    headings = [heading for _, heading in columns]
    lines = [
        "| " + " | ".join(headings) + " |",
        "|" + "|".join("---" for _ in headings) + "|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(row.get(key, "-")) for key, _ in columns)
            + " |"
        )
    return lines


def write_tables(results: list[SampleResult], out_dir: str | Path) -> Path:
    """Write the per-sample CSV and the summary tables."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [result.row for result in results if len(result.row) > 1]

    csv_path = out_dir / "per_sample.csv"
    if rows:
        columns: list[str] = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
        with open(csv_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    lines = ["# Hasil eksperimen", ""]

    lines += ["## Efisiensi (Tabel 3.12, Persamaan 3.3-3.6)", ""]
    lines += _markdown_table(
        rows,
        [
            ("sample", "Sampel"),
            ("bases_pipeline", "Pipeline"),
            ("bases_b1_direct", "B1 langsung"),
            ("bases_b2_symbolic", "B2 simbolik"),
            ("bases_b3_theoretical", "B3 teoretis"),
            ("saving_total_pct", "Hemat total %"),
            ("saving_transcription_pct", "Sumb. transkripsi %"),
            ("saving_token_scheme_pct", "Sumb. skema token %"),
            ("effective_density", "bit/basa"),
        ],
    )

    lines += ["", "## Kepatuhan batasan biologis (Tabel 3.2)", ""]
    lines += _markdown_table(
        rows,
        [
            ("sample", "Sampel"),
            ("oligos", "Oligo"),
            ("gc_mean", "GC rerata"),
            ("gc_min", "GC min"),
            ("gc_max", "GC maks"),
            ("gc_in_range", "Dalam rentang"),
            ("max_homopolymer", "Homopolymer maks"),
            ("rejection_rate", "Tingkat penolakan"),
            ("compliant", "Patuh"),
        ],
    )

    lines += ["", "## Sumbangan deteksi pengulangan (Subbab 3.3.5)", ""]
    lines += _markdown_table(
        rows,
        [
            ("sample", "Sampel"),
            ("pengulangan", "Taraf"),
            ("tokens_plain", "Token tanpa LZ77"),
            ("tokens_lz77", "Token dengan LZ77"),
            ("token_saving_pct", "Hemat token %"),
            ("bases_no_lz77", "Basa tanpa LZ77"),
            ("bases_pipeline", "Basa dengan LZ77"),
            ("base_saving_from_lz77_pct", "Hemat basa %"),
        ],
    )

    lines += ["", "## Akurasi rekonstruksi (Subbab 2.9)", ""]
    lines += _markdown_table(
        rows,
        [
            ("sample", "Sampel"),
            ("reference_notes", "Not acuan"),
            ("reconstructed_notes", "Not rekonstruksi"),
            ("precision", "P"),
            ("recall", "R"),
            ("f_measure", "F"),
            ("f_measure_offset", "F (dgn offset)"),
        ],
    )

    lines += ["", "## Dekomposisi error (Tabel 3.13)", ""]
    lines += _markdown_table(
        rows,
        [
            ("sample", "Sampel"),
            ("f_transcription", "F transkripsi"),
            ("f_quantization", "F kuantisasi"),
            ("lossless", "Codec lossless"),
            ("f_measure", "F keseluruhan"),
        ],
    )

    lines += ["", "## Keterulangan dan waktu proses (Tabel 3.2)", ""]
    lines += _markdown_table(
        rows,
        [
            ("sample", "Sampel"),
            ("audio_duration_s", "Durasi audio s"),
            ("deterministic", "Deterministik"),
            ("encode_s", "Encode s"),
            ("decode_s", "Decode s"),
            ("total_s", "Total s"),
        ],
    )

    failed = [result for result in results if not result.ok]
    if failed:
        lines += ["", "## Catatan", ""]
        for result in failed:
            for problem in result.problems:
                lines.append(f"- **{result.sample.name}**: {problem}")

    summary_path = out_dir / "summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.experiment",
        description="Run the corpus and write the tables Bab IV reports.",
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument(
        "--grid",
        type=int,
        default=None,
        choices=sorted(cfg.GRID_SUBDIVISIONS),
        help="override the per-sample grid recorded in the manifest",
    )
    parser.add_argument(
        "--only", nargs="*", help="run only these samples, by name"
    )
    parser.add_argument(
        "--split", default=None, help="run only this split of the corpus, dev or test"
    )
    parser.add_argument(
        "--onset-threshold",
        type=float,
        default=None,
        help=f"override the onset threshold (config: {cfg.ONSET_THRESHOLD})",
    )
    parser.add_argument(
        "--frame-threshold",
        type=float,
        default=None,
        help=f"override the frame threshold (config: {cfg.FRAME_THRESHOLD})",
    )
    args = parser.parse_args(argv)

    params = None
    if args.onset_threshold is not None or args.frame_threshold is not None:
        params = TranscriptionParams(
            onset_threshold=(
                cfg.ONSET_THRESHOLD if args.onset_threshold is None else args.onset_threshold
            ),
            frame_threshold=(
                cfg.FRAME_THRESHOLD if args.frame_threshold is None else args.frame_threshold
            ),
        )

    results = run_all(
        args.data_dir, args.output, args.grid, args.only, args.split, params
    )
    summary = write_tables(results, args.output)

    usable = [result for result in results if result.ok]
    print()
    print(f"{len(usable)} of {len(results)} samples completed without problems")
    print(f"tables written to {summary} and {args.output / 'per_sample.csv'}")

    for result in results:
        for problem in result.problems:
            print(f"  {result.sample.name}: {problem}")

    return 0 if len(usable) == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
