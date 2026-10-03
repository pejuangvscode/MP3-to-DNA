"""The three measurements that decide whether the system worked (Subbab 3.3.5).

    efficiency   how many bases were saved, and by which stage
    compliance   whether every oligo meets the biological constraints
    accuracy     how much musical information survived the round trip

Efficiency and accuracy pull against each other: the saving is bought with
transcription and quantisation, both lossy. Reporting either alone would say
nothing useful, which is why Subbab 3.2.1 makes both the success criteria.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from src import config as cfg
from src import dna_codec as codec

# (pitch, start, end) in MIDI note number and seconds
Note = tuple[int, float, float]


# --- efficiency (Persamaan 3.3 to 3.6) ---

@dataclass(frozen=True)
class EfficiencyReport:
    """Base counts and the saving decomposed by its source."""

    bases_pipeline: int
    bases_direct: int  # B1
    bases_symbolic: int  # B2
    bases_theoretical: int | None  # B3, context only

    total_saving_pct: float  # Persamaan 3.3
    transcription_contribution_pct: float  # Persamaan 3.4
    token_scheme_contribution_pct: float  # Persamaan 3.5

    payload_bits: int

    @property
    def effective_density(self) -> float:
        """Persamaan 2.2, for the pipeline path."""
        return self.payload_bits / self.bases_pipeline

    @property
    def constraint_and_redundancy_cost_pct(self) -> float | None:
        """How much B3's freedom from constraints and parity would have saved."""
        if self.bases_theoretical is None:
            return None
        return (1 - self.bases_theoretical / self.bases_pipeline) * 100.0


def efficiency(
    bases_pipeline: int,
    bases_direct: int,
    bases_symbolic: int,
    payload_bits: int,
    bases_theoretical: int | None = None,
) -> EfficiencyReport:
    """Split the saving into a transcription part and a token-scheme part. The
    two are multiplicative, not additive (Persamaan 3.6), and the identity is
    checked rather than assumed.
    """
    total = (1 - bases_pipeline / bases_direct) * 100.0
    transcription = (1 - bases_symbolic / bases_direct) * 100.0
    token_scheme = (1 - bases_pipeline / bases_symbolic) * 100.0

    return EfficiencyReport(
        bases_pipeline=bases_pipeline,
        bases_direct=bases_direct,
        bases_symbolic=bases_symbolic,
        bases_theoretical=bases_theoretical,
        total_saving_pct=total,
        transcription_contribution_pct=transcription,
        token_scheme_contribution_pct=token_scheme,
        payload_bits=payload_bits,
    )


# --- constraint compliance (Subbab 3.3.5) ---

@dataclass(frozen=True)
class ComplianceReport:
    """Whether the output could actually be synthesised and read back."""

    oligo_count: int
    gc_mean: float
    gc_min: float
    gc_max: float
    gc_in_range_fraction: float
    max_homopolymer: int
    rejection_rate: float  # oligos that needed rescrambling, per oligo

    @property
    def compliant(self) -> bool:
        return (
            self.gc_in_range_fraction == 1.0
            and self.max_homopolymer <= cfg.HOMOPOLYMER_MAX
        )


def compliance(
    oligos: Sequence[str], rescramble_count: int = 0
) -> ComplianceReport:
    """GC content and homopolymer length over every oligo. Both are guaranteed
    by construction, so this verifies the implementation, not the method.
    """
    gc_values = [codec.gc_fraction(oligo) for oligo in oligos]
    in_range = sum(1 for gc in gc_values if cfg.GC_MIN <= gc <= cfg.GC_MAX)

    return ComplianceReport(
        oligo_count=len(oligos),
        gc_mean=float(np.mean(gc_values)),
        gc_min=min(gc_values),
        gc_max=max(gc_values),
        gc_in_range_fraction=in_range / len(oligos),
        max_homopolymer=max(codec.max_homopolymer(oligo) for oligo in oligos),
        rejection_rate=rescramble_count / len(oligos),
    )


# --- reconstruction accuracy (Subbab 2.9, Subbab 3.3.5) ---

@dataclass(frozen=True)
class AccuracyScores:
    """Note-level metrics in the two variants Subbab 3.3.5 asks for."""

    precision: float  # onset and pitch only
    recall: float
    f_measure: float

    precision_with_offset: float  # onset, pitch and offset
    recall_with_offset: float
    f_measure_with_offset: float

    reference_notes: int
    estimated_notes: int


def _to_mir_eval(notes: Sequence[Note]) -> tuple[np.ndarray, np.ndarray]:
    """Note list -> intervals in seconds and pitches in Hz (Persamaan 2.14)."""
    intervals = np.array([[start, end] for _, start, end in notes], dtype=float)
    pitches = np.array(
        [440.0 * 2.0 ** ((pitch - 69) / 12.0) for pitch, _, _ in notes], dtype=float
    )
    return intervals, pitches


def accuracy(reference: Sequence[Note], estimated: Sequence[Note]) -> AccuracyScores:
    """mir_eval note-level metrics. Tolerances are the library defaults, stated
    explicitly because loose tolerances inflate the numbers: 50 ms on onset,
    50 cents on pitch, and for the offset variant the larger of 20% of the
    reference duration and 50 ms.
    """
    import mir_eval

    if not estimated:
        # mir_eval cannot score an empty estimate; every reference note is a
        # miss, which is precisely zero on all three metrics.
        return AccuracyScores(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, len(reference), 0)

    ref_intervals, ref_pitches = _to_mir_eval(reference)
    est_intervals, est_pitches = _to_mir_eval(estimated)

    onset_only = mir_eval.transcription.precision_recall_f1_overlap(
        ref_intervals,
        ref_pitches,
        est_intervals,
        est_pitches,
        onset_tolerance=cfg.ONSET_TOLERANCE_S,
        pitch_tolerance=cfg.PITCH_TOLERANCE_CENTS,
        offset_ratio=None,
    )
    with_offset = mir_eval.transcription.precision_recall_f1_overlap(
        ref_intervals,
        ref_pitches,
        est_intervals,
        est_pitches,
        onset_tolerance=cfg.ONSET_TOLERANCE_S,
        pitch_tolerance=cfg.PITCH_TOLERANCE_CENTS,
        offset_ratio=cfg.OFFSET_RATIO,
        offset_min_tolerance=cfg.OFFSET_MIN_TOLERANCE_S,
    )

    return AccuracyScores(
        precision=onset_only[0],
        recall=onset_only[1],
        f_measure=onset_only[2],
        precision_with_offset=with_offset[0],
        recall_with_offset=with_offset[1],
        f_measure_with_offset=with_offset[2],
        reference_notes=len(reference),
        estimated_notes=len(estimated),
    )


# --- error decomposition (Tabel 3.13) ---

@dataclass(frozen=True)
class ErrorDecomposition:
    """Which module lost what. A single end-to-end score cannot say, so each
    stage boundary is measured with the previous stage's output as reference.
    """

    transcription: AccuracyScores  # reference MIDI vs transcription output
    quantization: AccuracyScores  # transcription output vs expanded tokens
    overall: AccuracyScores  # reference MIDI vs final reconstruction
    codec_lossless: bool | None  # None when it could not be checked

    @property
    def summary(self) -> list[dict[str, object]]:
        """Tabel 3.13 as rows. The codec row is None when losslessness was not
        verified -- printing 1.0 unchecked would assert the decisive claim.
        """
        codec_score = (
            None if self.codec_lossless is None else float(self.codec_lossless)
        )
        return [
            {
                "module": "Transkripsi musik otomatis",
                "reference": "Notasi MIDI acuan",
                "estimate": "Keluaran modul transkripsi",
                "f_measure": round(self.transcription.f_measure, 4),
            },
            {
                "module": "Kuantisasi",
                "reference": "Keluaran modul transkripsi",
                "estimate": "Notasi hasil ekspansi token",
                "f_measure": round(self.quantization.f_measure, 4),
            },
            {
                "module": "Pengodean dan pembacaan balik DNA",
                "reference": "Token sebelum pengodean",
                "estimate": "Token hasil pembacaan balik",
                "f_measure": codec_score,
            },
            {
                "module": "Keseluruhan sistem",
                "reference": "Notasi MIDI acuan",
                "estimate": "Notasi hasil rekonstruksi akhir",
                "f_measure": round(self.overall.f_measure, 4),
            },
        ]


def decompose(
    reference: Sequence[Note],
    transcribed: Sequence[Note],
    reconstructed: Sequence[Note],
    codec_lossless: bool | None,
) -> ErrorDecomposition:
    """`codec_lossless` compares the token stream before encoding with the one
    recovered after; pass None when that comparison was not made. False means an
    implementation defect, not a limitation of the method, and invalidates every
    other number here.
    """
    return ErrorDecomposition(
        transcription=accuracy(reference, transcribed),
        quantization=accuracy(transcribed, reconstructed),
        overall=accuracy(reference, reconstructed),
        codec_lossless=codec_lossless,
    )


# --- command line ---

def main(argv: list[str] | None = None) -> int:
    """Report one sample's metrics.

    python -m src.evaluate --reference truth.mid --reconstructed out.mid \\
        --fasta song.fasta [--mp3 song.mp3] [--transcribed-midi t.mid]
    """
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        prog="python -m src.evaluate",
        description="Measure efficiency, constraint compliance and accuracy.",
    )
    parser.add_argument("--reference", required=True, type=Path, help="ground truth MIDI")
    parser.add_argument(
        "--reconstructed", required=True, type=Path, help="MIDI from src.decode"
    )
    parser.add_argument("--fasta", required=True, type=Path, help="the encoded sequence")
    parser.add_argument(
        "--mp3", type=Path, help="original audio, for comparison path B1"
    )
    parser.add_argument(
        "--transcribed-midi",
        type=Path,
        help="the model's own MIDI, for comparison path B2 and the error "
        "decomposition of Tabel 3.13",
    )
    args = parser.parse_args(argv)

    from src import baselines
    from src.reconstruct import read_midi
    reference = read_midi(args.reference)
    reconstructed = read_midi(args.reconstructed)
    oligos = codec.read_fasta(args.fasta)

    lines: list[str] = []
    checked = compliance(oligos)
    lines += [
        "--- compliance (Tabel 3.2) ---",
        f"  {checked.oligo_count} oligos | GC {checked.gc_min:.3f}"
        f"..{checked.gc_max:.3f}, mean {checked.gc_mean:.4f} | "
        f"in range {checked.gc_in_range_fraction:.1%}",
        f"  max homopolymer {checked.max_homopolymer} | "
        f"compliant: {checked.compliant}",
    ]

    bases_pipeline = len(oligos) * cfg.OLIGO_TOTAL_NT
    if args.mp3 and args.transcribed_midi:
        direct = baselines.direct(args.mp3)
        symbolic = baselines.symbolic(args.transcribed_midi)
        report = efficiency(
            bases_pipeline,
            direct.total_bases,
            symbolic.total_bases,
            payload_bits=0,  # unknown from the FASTA alone
            bases_theoretical=baselines.theoretical(direct.input_bytes).total_bases,
        )
        lines += [
            "",
            "--- efficiency (Persamaan 3.3 to 3.6) ---",
            f"  pipeline   {report.bases_pipeline:>12,} bases",
            f"  B1 direct  {report.bases_direct:>12,} bases",
            f"  B2 symbolic{report.bases_symbolic:>12,} bases",
            f"  B3 theory  {report.bases_theoretical:>12,} bases",
            f"  total saving             {report.total_saving_pct:8.3f} %",
            f"    from transcription     "
            f"{report.transcription_contribution_pct:8.3f} %",
            f"    from the token scheme  "
            f"{report.token_scheme_contribution_pct:8.3f} %",
        ]
    else:
        lines += [
            "",
            f"  pipeline {bases_pipeline:,} bases "
            "(pass --mp3 and --transcribed-midi for the full decomposition)",
        ]

    if args.transcribed_midi:
        transcribed = read_midi(args.transcribed_midi)
        # None unless src.encode left a payload manifest beside the FASTA.
        lossless = codec.verify_lossless(args.fasta)
        decomposed = decompose(
            reference, transcribed, reconstructed, codec_lossless=lossless
        )
        lines += ["", "--- error decomposition (Tabel 3.13) ---"]
        for row in decomposed.summary:
            score = row["f_measure"]
            shown = "not verified" if score is None else f"F = {score:.4f}"
            lines.append(f"  {row['module']:<36} {shown}")
        if lossless is False:
            lines.append(
                "  WARNING: the round trip is not lossless. This is an "
                "implementation defect and invalidates every figure above."
            )
        scores = decomposed.overall
    else:
        scores = accuracy(reference, reconstructed)

    lines += [
        "",
        "--- accuracy (Subbab 2.9) ---",
        f"  onset+pitch   P {scores.precision:.4f}  R {scores.recall:.4f}  "
        f"F {scores.f_measure:.4f}",
        f"  with offset   P {scores.precision_with_offset:.4f}  "
        f"R {scores.recall_with_offset:.4f}  "
        f"F {scores.f_measure_with_offset:.4f}",
        f"  reference {scores.reference_notes} notes, "
        f"estimated {scores.estimated_notes} notes",
    ]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
