"""Encoding path: MP3 in, FASTA out.

Wires the six encoding modules of Tabel 3.5 together and writes the artefacts
Bab IV needs alongside the sequence itself: the model's own MIDI, which is the
input to comparison path B2, and MusicXML for reading.

    python -m src.encode --input song.mp3 --tempo 120 --output song.fasta
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from src import config as cfg
from src import dna_codec as codec
from src import notation, preprocess
from src.quantize import QuantizationReport, estimate_offset, quantize
from src.tokenizer import EncodedTokens
from src.transcribe import Transcription, TranscriptionParams, transcribe_cached


@dataclass(frozen=True)
class EncodeResult:
    """Everything one encoding run produced, for reporting and for Fase 5."""

    fasta_path: Path
    transcribed_midi_path: Path
    musicxml_path: Path | None
    audio: dict
    transcription: Transcription
    offset_ms: float
    offset_concentration: float
    quantization: QuantizationReport
    tokens: EncodedTokens
    dna: codec.EncodeReport


def run(
    audio_path: str | Path,
    tempo: int,
    output_fasta: str | Path,
    grid_code: int = cfg.DEFAULT_GRID_CODE,
    use_repeat_detection: bool = True,
    offset_seconds: float = 0.0,
    work_dir: str | Path | None = None,
    cache_dir: str | Path | None = None,
    params: TranscriptionParams | None = None,
    write_musicxml: bool = True,
) -> EncodeResult:
    """Run the encoding path end to end.

    `offset_seconds` is passed straight to quantisation and defaults to zero,
    which is the algorithm as Subbab 3.3.4 defines it. The measured offset is
    reported either way, so the decision to compensate stays visible.
    """
    audio_path = Path(audio_path)
    output_fasta = Path(output_fasta)
    output_fasta.parent.mkdir(parents=True, exist_ok=True)

    work_dir = Path(work_dir) if work_dir else output_fasta.parent / "work"
    cache_dir = Path(cache_dir) if cache_dir else work_dir / "cache"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Fails loudly if the tempo puts one grid unit below the model's minimum
    # note length, which would silently delete the shortest notes.
    cfg.assert_min_note_length_fits(tempo, grid_code)

    audio = preprocess.load(audio_path)
    prepared = preprocess.write_wav(audio, work_dir / f"{audio_path.stem}.prepared.wav")

    transcribed_midi = work_dir / f"{audio_path.stem}.transcribed.mid"
    transcription = transcribe_cached(
        prepared, cache_dir, params, midi_path=transcribed_midi
    )
    if not transcription.notes:
        raise ValueError(
            f"{audio_path.name}: transcription found no notes; check the tempo, "
            "the inference thresholds, and that the audio is not silent"
        )

    offset = estimate_offset(transcription.notes, tempo, grid_code)
    quantised = quantize(
        transcription.notes, tempo, grid_code, offset_seconds=offset_seconds
    )

    musicxml_path = None
    if write_musicxml:
        musicxml_path = notation.write_from_quantized(
            quantised.notes,
            work_dir / f"{audio_path.stem}.musicxml",
            tempo,
            grid_code,
            title=audio_path.stem,
        )

    tokens = encode_tokens(quantised, tempo, grid_code, use_repeat_detection)
    dna = codec.encode(tokens.data)
    codec.write_fasta(dna.oligos, output_fasta)
    # Lets src.evaluate check the round trip later instead of assuming it.
    codec.write_payload_manifest(output_fasta, tokens.data)

    return EncodeResult(
        fasta_path=output_fasta,
        transcribed_midi_path=transcribed_midi,
        musicxml_path=musicxml_path,
        audio=preprocess.describe(audio),
        transcription=transcription,
        offset_ms=offset.offset_ms,
        offset_concentration=offset.concentration,
        quantization=quantised,
        tokens=tokens,
        dna=dna,
    )


def encode_tokens(
    quantised: QuantizationReport,
    tempo: int,
    grid_code: int,
    use_repeat_detection: bool,
) -> EncodedTokens:
    """Tokenise a quantisation result. Split out so Fase 5 can rerun just this."""
    from src.tokenizer import encode_notes

    return encode_notes(
        quantised.notes, tempo, grid_code, use_repeat_detection=use_repeat_detection
    )


def summarise(result: EncodeResult) -> str:
    """One run as readable lines."""
    quantised, tokens, dna = result.quantization, result.tokens, result.dna
    return "\n".join(
        [
            f"audio        {result.audio['duration_s']} s, "
            f"{result.audio['source_channels']} ch @ "
            f"{result.audio['source_sample_rate']} Hz, "
            f"leading silence {result.audio['leading_silence_s']} s",
            f"transcribed  {result.transcription.note_count} notes",
            f"offset       {result.offset_ms:+.2f} ms measured "
            f"(concentration {result.offset_concentration:.3f}), "
            f"{quantised.offset_applied_s * 1000:+.2f} ms applied",
            f"quantised    {quantised.input_count} -> {len(quantised.notes)} notes, "
            f"grid {quantised.grid_unit_ms:.1f} ms, "
            f"rms error {quantised.rms_grid_error_ms:.2f} ms",
            f"tokens       {tokens.stats.total_tokens} "
            f"({tokens.stats.note_tokens} note + "
            f"{tokens.stats.reference_tokens} reference), "
            f"{tokens.stats.payload_bytes} bytes",
            f"dna          {dna.oligo_count} oligos, {dna.total_bases} bases, "
            f"{dna.rescramble_count} rescrambles, "
            f"{dna.effective_density:.4f} bit/base",
            f"written      {result.fasta_path}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.encode",
        description="Map an audio recording to constraint-compliant DNA (FASTA).",
    )
    parser.add_argument("--input", required=True, type=Path, help="MP3 or WAV file")
    parser.add_argument(
        "--tempo",
        required=True,
        type=int,
        help=f"tempo in BPM, {cfg.MIN_TEMPO}..{cfg.MAX_TEMPO}; taken as known "
        "from the DAW project, since tempo estimation is out of scope",
    )
    parser.add_argument("--output", required=True, type=Path, help="FASTA file")
    parser.add_argument(
        "--grid",
        type=int,
        default=cfg.DEFAULT_GRID_CODE,
        choices=sorted(cfg.GRID_SUBDIVISIONS),
        help="grid resolution code: 0=1/4, 1=1/8, 2=1/16, 3=1/24 (default 2)",
    )
    parser.add_argument(
        "--no-repeat-detection",
        action="store_true",
        help="disable LZ77, to measure what repeat detection contributes",
    )
    parser.add_argument(
        "--offset",
        default="none",
        help="onset compensation: 'none' (default, as Subbab 3.3.4 specifies), "
        "'auto' to apply the measured offset, or a value in milliseconds",
    )
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--no-musicxml", action="store_true")
    args = parser.parse_args(argv)

    offset_seconds = 0.0
    if args.offset != "none":
        if args.offset == "auto":
            offset_seconds = None  # resolved below, after transcription
        else:
            try:
                offset_seconds = float(args.offset) / 1000.0
            except ValueError:
                parser.error("--offset must be 'none', 'auto', or a number in ms")

    try:
        if offset_seconds is None:
            # Measure first, then rerun quantisation with the measurement.
            probe = run(
                args.input,
                args.tempo,
                args.output,
                args.grid,
                not args.no_repeat_detection,
                0.0,
                args.work_dir,
                args.cache_dir,
                write_musicxml=False,
            )
            offset_seconds = probe.offset_ms / 1000.0

        result = run(
            args.input,
            args.tempo,
            args.output,
            args.grid,
            not args.no_repeat_detection,
            offset_seconds,
            args.work_dir,
            args.cache_dir,
            write_musicxml=not args.no_musicxml,
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(summarise(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
