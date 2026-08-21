"""Decoding path: FASTA in, MIDI out.

Runs the encoding stages in reverse: primers trimmed, bases mapped back to
trits, trits to bits, payloads unscrambled and reordered by index,
Reed-Solomon decoded, tokens unpacked and expanded, notation written.

Nothing outside the FASTA file is needed. Tempo and grid resolution travel in
the token header, so a sequence read back in isolation still reconstructs.

    python -m src.decode --input song.fasta --output reconstructed.mid
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from src import config as cfg
from src import dna_codec as codec
from src import notation, reconstruct
from src.tokenizer import DecodedTokens, decode_bytes


@dataclass(frozen=True)
class DecodeResult:
    midi_path: Path
    musicxml_path: Path | None
    oligo_count: int
    total_bases: int
    tokens: DecodedTokens


def run(
    fasta_path: str | Path,
    output_midi: str | Path,
    write_musicxml: bool = True,
) -> DecodeResult:
    """Read a FASTA file and reconstruct notation from it."""
    fasta_path = Path(fasta_path)
    if not fasta_path.is_file():
        raise FileNotFoundError(f"no such FASTA file: {fasta_path}")

    output_midi = Path(output_midi)
    output_midi.parent.mkdir(parents=True, exist_ok=True)

    oligos = codec.read_fasta(fasta_path)
    if not oligos:
        raise ValueError(f"{fasta_path.name} contains no sequences")

    tokens = decode_bytes(codec.decode(oligos))
    reconstruct.to_midi(
        tokens.notes, output_midi, tokens.tempo, tokens.grid_code
    )

    musicxml_path = None
    if write_musicxml:
        musicxml_path = notation.write_from_quantized(
            tokens.notes,
            output_midi.with_suffix(".musicxml"),
            tokens.tempo,
            tokens.grid_code,
            title=f"{fasta_path.stem} reconstructed",
        )

    return DecodeResult(
        midi_path=output_midi,
        musicxml_path=musicxml_path,
        oligo_count=len(oligos),
        total_bases=len(oligos) * cfg.OLIGO_TOTAL_NT,
        tokens=tokens,
    )


def summarise(result: DecodeResult) -> str:
    stats = result.tokens.stats
    subdivision = 4 * cfg.GRID_SUBDIVISIONS[result.tokens.grid_code]
    return "\n".join(
        [
            f"read         {result.oligo_count} oligos, {result.total_bases} bases",
            f"header       tempo {result.tokens.tempo} BPM, "
            f"grid 1/{subdivision}",
            f"tokens       {stats.total_tokens} "
            f"({stats.note_tokens} note + {stats.reference_tokens} reference)",
            f"expanded     {len(result.tokens.notes)} notes",
            f"written      {result.midi_path}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.decode",
        description="Reconstruct MIDI notation from a FASTA sequence.",
    )
    parser.add_argument("--input", required=True, type=Path, help="FASTA file")
    parser.add_argument("--output", required=True, type=Path, help="MIDI file")
    parser.add_argument("--no-musicxml", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = run(args.input, args.output, write_musicxml=not args.no_musicxml)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(summarise(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
