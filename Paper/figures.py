"""Build the paper's figures: Figs. 1 and 2 from the codec itself, Fig. 3 from results.

    python Paper/figures.py
    python Paper/figures.py --figure 3 --results results/slakh_test_v2 --characterization results/characterization_v2
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent

CEILING = 1.0044
CODEWORD_BYTES = 223

INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
SURFACE = "#ffffff"
LOSSY = "#e4e3df"
# categorical slots 1 and 2, validated all-pairs; shape repeats identity for print
SERIES = {"Piano": ("#2a78d6", "o"), "Guitar": ("#eb6834", "^")}


def canvas(width: float, height: float):
    """A figure whose data coordinates are inches, so layout reads as measurements."""
    fig = plt.figure(figsize=(width, height))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.axis("off")
    return fig, ax


def save(fig, name: str) -> None:
    fig.savefig(OUT / f"{name}.pdf")
    fig.savefig(OUT / f"{name}.png", dpi=300)
    plt.close(fig)
    print(f"written {OUT / (name + '.pdf')} and {name}.png")


def arrow(ax, start, end, connection="arc3") -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            connectionstyle=connection,
            mutation_scale=7,
            linewidth=0.7,
            color=MUTED,
            shrinkA=0,
            shrinkB=0,
        )
    )


def bracket(ax, x_start, x_end, y, label, facing="up", size=6.5) -> None:
    """A thin bracket whose end ticks point at what it groups, label on the far side."""
    tick = 0.035 if facing == "up" else -0.035
    ax.plot([x_start, x_start, x_end, x_end], [y + tick, y, y, y + tick],
            color=MUTED, linewidth=0.6)
    ax.text((x_start + x_end) / 2, y - 0.03 if facing == "up" else y + 0.03, label,
            ha="center", va="top" if facing == "up" else "bottom",
            fontsize=size, color=MUTED, linespacing=1.1)


# --- Fig. 1: the codec, as src/encode.py, src/dna_codec.py and src/decode.py run it ---

# encoder stages left to right; the decoder stage that inverts each sits beneath it
ENCODER = (
    ("Pre-processing", "mono, 22.05 kHz", "lossy"),
    ("Transcription", "basic-pitch,\nnotes in seconds", "lossy"),
    ("Quantisation", "grid positions\nand durations", "lossy"),
    ("Tokenisation", "deltas, LZ77,\n22/17-bit tokens", "process"),
    ("Outer code", "RS(255, 223)\nover GF(2$^8$)", "process"),
    ("Oligo payload", "index, seed,\nscrambled data", "process"),
    ("Inner code", "81-trit blocks,\nrotating code", "process"),
    ("FASTA", "202-nt oligos\nwith primers", "terminal"),
)
DECODER = (
    None,
    None,
    ("MIDI", "quantised notes", "terminal"),
    ("Detokenisation", "expand LZ77,\ndeltas to notes", "process"),
    ("Outer decode", "RS decoding", "process"),
    ("Payload decode", "descramble,\norder by index", "process"),
    ("Inner decode", "strip primers,\nrotating decode", "process"),
    ("DNA channel", "synthesis, storage,\nsequencing", "channel"),
)
# (first column, last column, label): the subsections of Section III each group is in
GROUPS = (
    (0, 2, "Transcription and quantisation\nSec. III-A"),
    (3, 3, "Tokens\nSec. III-B"),
    (4, 6, "DNA encoding\nSec. III-C"),
)


def stage(ax, x, y, w, h, title, detail, kind) -> None:
    rounded = kind == "terminal"
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0,rounding_size=0.06" if rounded else "square,pad=0",
            facecolor=LOSSY if kind == "lossy" else SURFACE,
            edgecolor=MUTED,
            linewidth=0.9 if rounded else 0.6,
            linestyle=(0, (3, 2)) if kind == "channel" else "-",
        )
    )
    lines = detail.count("\n") + 1
    title_y = y + h / 2 + 0.055 * lines
    ax.text(x + w / 2, title_y, title, ha="center", va="center",
            fontsize=7, fontweight="bold", color=INK)
    ax.text(x + w / 2, title_y - 0.075, detail, ha="center", va="top",
            fontsize=6.5, color=INK, linespacing=1.15)


def architecture() -> None:
    width, height = 7.16, 1.86
    gutter, margin, gap = 0.17, 0.02, 0.12
    columns = len(ENCODER)
    w = (width - gutter - margin - gap * (columns - 1)) / columns
    h = 0.52
    enc_y, dec_y = 1.0, 0.06

    fig, ax = canvas(width, height)
    left = [gutter + i * (w + gap) for i in range(columns)]
    centre = [x + w / 2 for x in left]

    for y, label in ((enc_y, "Encoder"), (dec_y, "Decoder")):
        ax.text(0.07, y + h / 2, label, rotation=90, ha="center", va="center",
                fontsize=7, fontweight="bold", color=MUTED)

    for i, (title, detail, kind) in enumerate(ENCODER):
        stage(ax, left[i], enc_y, w, h, title, detail, kind)
        if i:
            arrow(ax, (left[i] - gap, enc_y + h / 2), (left[i], enc_y + h / 2))

    for i, spec in enumerate(DECODER):
        if spec is None:
            continue
        stage(ax, left[i], dec_y, w, h, *spec)
        # the decoder runs right to left
        if i < columns - 1 and DECODER[i + 1] is not None:
            arrow(ax, (left[i + 1], dec_y + h / 2), (left[i] + w, dec_y + h / 2))

    # FASTA down into the channel
    arrow(ax, (centre[-1], enc_y), (centre[-1], dec_y + h))

    # which subsection of the text describes each group, between the two rows
    for first, last, label in GROUPS:
        bracket(ax, left[first], left[last] + w, enc_y - 0.08, label, facing="up")

    # inputs
    top = enc_y + h
    for column, label in ((0, "Audio (MP3, FLAC)"), (2, "Tempo, grid")):
        ax.text(centre[column], height - 0.03, label, ha="center", va="top",
                fontsize=6.5, color=INK)
        arrow(ax, (centre[column], height - 0.15), (centre[column], top))

    # GC screening: an oligo outside 40-60 % goes back for the next seed
    arrow(ax, (centre[6], top), (centre[5], top), connection="arc3,rad=0.35")
    ax.text((centre[5] + centre[6]) / 2, height - 0.03,
            "GC outside 40–60 %: next seed", ha="center", va="top",
            fontsize=6.5, color=INK)

    # legend in the empty lower left, where the lossy stages have no inverse
    entries = (
        ("lossy stage, not inverted", LOSSY, "-", "square,pad=0"),
        ("lossless stage, inverted below", SURFACE, "-", "square,pad=0"),
        ("file (FASTA, MIDI)", SURFACE, "-", "round,pad=0,rounding_size=0.03"),
        ("simulated without errors", SURFACE, (0, (3, 2)), "square,pad=0"),
    )
    for row, (label, fill, dash, shape) in enumerate(entries):
        y = dec_y + h - 0.12 - row * 0.13
        ax.add_patch(FancyBboxPatch((left[0], y), 0.16, 0.09, boxstyle=shape,
                                    facecolor=fill, edgecolor=MUTED, linewidth=0.6,
                                    linestyle=dash))
        ax.text(left[0] + 0.22, y + 0.045, label, va="center", fontsize=6.5, color=INK)

    save(fig, "fig1")


# --- Fig. 2: token formats, oligonucleotide layout, and a repeat ---

HEADER_FIELDS = (("version", 4), ("tempo $-$ 40", 8), ("grid", 2), ("token count", 16), ("pad", 2))
NOTE_FIELDS = (("0", 1), ("pitch", 7), ("delta", 8), ("duration $-$ 1", 6))
REFERENCE_FIELDS = (("1", 1), ("distance $-$ 1", 10), ("length $-$ 2", 6))

# a four-note motif played twice, as src/tokenizer.py encodes it:
# (pitch, delta, duration) per note, then the LZ77 reference that replaces the repeat
MOTIF = ((60, 2, 2), (64, 2, 2), (67, 2, 2), (64, 2, 2))
ONSETS = (2, 4, 6, 8, 10, 12, 14, 16)

# horizontal frame shared by every row: labels | bars | totals
LABEL_X, BAR_X0, BAR_X1, TOTAL_X = 0.02, 0.58, 3.10, 3.16


def cell(ax, x, y, w, h, fill=SURFACE) -> None:
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="square,pad=0",
                                facecolor=fill, edgecolor=MUTED, linewidth=0.6))


def bitfield(ax, x, y, h, fields, scale, unit="") -> float:
    """Fields side by side at `scale` inches per unit; returns the right edge."""
    for name, size in fields:
        w = size * scale
        cell(ax, x, y, w, h)
        # a field too narrow to also carry its size shows only its name
        if w < 0.14:
            ax.text(x + w / 2, y + h / 2, name, ha="center", va="center",
                    fontsize=6, color=INK)
        else:
            ax.text(x + w / 2, y + h * 0.66, name, ha="center", va="center",
                    fontsize=6, color=INK)
            ax.text(x + w / 2, y + h * 0.28, f"{size}{unit}", ha="center", va="center",
                    fontsize=6, color=MUTED)
        x += w
    return x


def row_label(ax, y, text) -> None:
    ax.text(LABEL_X, y, text, ha="left", va="center", fontsize=6.5, color=INK,
            linespacing=1.1)


def total(ax, y, text) -> None:
    ax.text(TOTAL_X, y, text, ha="left", va="center", fontsize=6.5, color=MUTED)


def ruler(ax, x, y, units, scale, every=8) -> None:
    ax.plot([x, x + units * scale], [y, y], color=MUTED, linewidth=0.5)
    for unit in range(units + 1):
        major = unit % every == 0
        ax.plot([x + unit * scale] * 2, [y, y + (0.04 if major else 0.018)],
                color=MUTED, linewidth=0.5)
        if major:
            ax.text(x + unit * scale, y + 0.055, str(unit), ha="center", va="bottom",
                    fontsize=5.5, color=MUTED)


def layout() -> None:
    width, height = 3.5, 3.06
    span = BAR_X1 - BAR_X0
    fig, ax = canvas(width, height)

    def title(y, text):
        ax.text(LABEL_X, y, text, ha="left", va="center", fontsize=7, color=INK)

    # (a) token formats, one bit scale for all three so their lengths compare
    bit = span / 32
    title(2.99, "(a) Header and token formats")
    ruler(ax, BAR_X0, 2.75, 32, bit)
    total(ax, 2.78, "bit")
    for y, label, fields, bits in ((2.49, "Header", HEADER_FIELDS, 32),
                                   (2.23, "Note\ntoken", NOTE_FIELDS, 22),
                                   (1.97, "Reference\ntoken", REFERENCE_FIELDS, 17)):
        row_label(ax, y + 0.1, label)
        bitfield(ax, BAR_X0, y, 0.2, fields, bit)
        total(ax, y + 0.1, f"{bits} bits")

    # (b) oligonucleotide, then its payload in bytes
    title(1.83, "(b) Oligonucleotide layout")
    nt = span / 202
    row_label(ax, 1.57, "Oligo")
    bitfield(ax, BAR_X0, 1.47, 0.2,
             (("primer", 20), ("payload, rotating code", 162), ("primer", 20)), nt, " nt")
    total(ax, 1.57, "202 nt")
    for x, end in ((BAR_X0, "5′"), (BAR_X1, "3′")):
        ax.text(x, 1.69, end, ha="center", va="bottom", fontsize=6, color=MUTED)

    byte = span / 32
    row_label(ax, 1.20, "Payload")
    bitfield(ax, BAR_X0, 1.11, 0.18,
             (("idx", 2), ("s", 1), ("data, scrambled", 29)), byte, " B")
    total(ax, 1.20, "32 B")
    for top_x, bottom_x in ((BAR_X0 + 20 * nt, BAR_X0), (BAR_X0 + 182 * nt, BAR_X1)):
        ax.plot([top_x, bottom_x], [1.47, 1.29], color=MUTED, linewidth=0.5,
                linestyle=(0, (2, 2)))
    ax.text(BAR_X0 + span / 2, 1.38, "32 B = 2 × 128 bits → 2 × 81 trits → 162 nt",
            ha="center", va="center", fontsize=6, color=MUTED)

    # (c) the repeat, drawn to one bit scale so the saving shows as length;
    # shading marks the repeated material and the reference that replaces it
    title(0.975, "(c) A motif played twice; tokens as (pitch, delta, duration)")
    scale = span / (8 * 22)
    note_w = 22 * scale
    plain_y, lz_y, row_h = 0.54, 0.04, 0.18

    split = BAR_X0 + 4 * note_w
    bracket(ax, BAR_X0, split - 0.02, plain_y + row_h + 0.045, "motif",
            facing="down", size=6)
    bracket(ax, split + 0.02, BAR_X1, plain_y + row_h + 0.045,
            "repeat: identical tokens", facing="down", size=6)

    row_label(ax, plain_y + row_h / 2, "Plain")
    for i, (pitch, delta, duration) in enumerate(MOTIF + MOTIF):
        x = BAR_X0 + i * note_w
        cell(ax, x, plain_y, note_w, row_h, LOSSY if i >= 4 else SURFACE)
        ax.text(x + note_w / 2, plain_y + row_h / 2, f"{pitch},{delta},{duration}",
                ha="center", va="center", fontsize=5.5, color=INK)
        ax.text(x + note_w / 2, plain_y - 0.065, str(ONSETS[i]), ha="center",
                va="center", fontsize=5.5, color=MUTED)
    ax.text(LABEL_X, plain_y - 0.065, "onset", ha="left", va="center",
            fontsize=5.5, color=MUTED)
    total(ax, plain_y + row_h / 2, "176 bits")

    row_label(ax, lz_y + row_h / 2, "LZ77")
    for i, (pitch, delta, duration) in enumerate(MOTIF):
        x = BAR_X0 + i * note_w
        cell(ax, x, lz_y, note_w, row_h)
        ax.text(x + note_w / 2, lz_y + row_h / 2, f"{pitch},{delta},{duration}",
                ha="center", va="center", fontsize=5.5, color=INK)
    ref_x, ref_w = BAR_X0 + 4 * note_w, 17 * scale
    cell(ax, ref_x, lz_y, ref_w, row_h, LOSSY)
    ax.text(ref_x + ref_w / 2, lz_y + row_h / 2, "4,4", ha="center", va="center",
            fontsize=5.5, color=INK)
    arrow(ax, (ref_x + ref_w / 2, lz_y + row_h), (BAR_X0 + 0.02, lz_y + row_h),
          connection="arc3,rad=0.22")
    ax.text(ref_x + ref_w + 0.07, lz_y + row_h / 2,
            "reference (4, 4):\ncopy 4 tokens from 4 back", ha="left", va="center",
            fontsize=6, color=INK, linespacing=1.1)
    total(ax, lz_y + row_h / 2, "105 bits")

    save(fig, "fig2")


# --- Fig. 3: granularity and the repetition lost to transcription ---

def load(results_dir: Path, character_dir: Path) -> list[dict]:
    results = {
        r["sample"]: r
        for r in csv.DictReader(open(results_dir / "per_sample.csv", encoding="utf-8"))
    }
    character = {
        r["sample"]: r
        for r in csv.DictReader(open(character_dir / "per_sample.csv", encoding="utf-8"))
    }
    return [
        {
            "inst": character[name]["inst_class"],
            "payload": int(results[name]["payload_bytes"]),
            "density": float(results[name]["effective_density"]),
            "reference_rep": float(character[name]["repetition_pct"]),
            "transcribed_rep": float(results[name]["token_saving_pct"]),
        }
        for name in results
    ]


def style(ax) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.5, linestyle="-")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
        ax.spines[side].set_linewidth(0.6)
    ax.tick_params(colors=MUTED, labelcolor=INK, width=0.6, length=2.5)


def scatter(ax, rows, x, y) -> None:
    for inst, (color, marker) in SERIES.items():
        chosen = [row for row in rows if row["inst"] == inst]
        ax.scatter(
            [row[x] for row in chosen],
            [row[y] for row in chosen],
            s=14,
            marker=marker,
            color=color,
            edgecolors=SURFACE,
            linewidths=0.4,
            label=f"{inst} (n = {len(chosen)})",
            zorder=3,
        )


def results_figure(results_dir: Path, character_dir: Path) -> None:
    rows = load(results_dir, character_dir)
    fig, (left, right) = plt.subplots(1, 2, figsize=(3.5, 1.85))

    style(left)
    left.set_xscale("log")
    left.axhline(CEILING, color=MUTED, linewidth=0.7, zorder=2)
    left.axvline(CODEWORD_BYTES, color=MUTED, linewidth=0.7, linestyle=(0, (2, 2)), zorder=2)
    scatter(left, rows, "payload", "density")
    left.text(1300, CEILING + 0.02, "ceiling 1.004", color=INK, fontsize=6, va="bottom")
    left.text(CODEWORD_BYTES * 1.12, 0.33, "223 B", color=INK, fontsize=6, va="bottom")
    left.set_xlim(60, 20000)
    left.set_ylim(0.3, 1.1)
    left.set_xlabel("Payload after LZ77 (bytes)")
    left.set_ylabel("Effective density (bit/base)")
    left.set_title("(a)", fontsize=7, color=INK, loc="left", pad=3)

    style(right)
    right.plot([0, 100], [0, 100], color=MUTED, linewidth=0.7, zorder=2)
    scatter(right, rows, "reference_rep", "transcribed_rep")
    right.text(62, 88, "no loss", color=INK, fontsize=6, rotation=38)
    right.set_xlim(0, 100)
    right.set_ylim(0, 100)
    right.set_xlabel("Token saving, reference (%)")
    right.set_ylabel("Token saving, transcribed (%)")
    right.set_title("(b)", fontsize=7, color=INK, loc="left", pad=3)

    handles, labels = left.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, 1.02),
        handletextpad=0.3,
        columnspacing=1.2,
        labelcolor=INK,
    )
    fig.tight_layout(pad=0.3, w_pad=0.8, rect=(0, 0, 1, 0.92))
    save(fig, "fig3")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python Paper/figures.py")
    parser.add_argument("--figure", choices=("1", "2", "3", "all"), default="all")
    parser.add_argument("--results", type=Path, default=ROOT / "results" / "slakh_test_v2")
    parser.add_argument(
        "--characterization", type=Path, default=ROOT / "results" / "characterization_v2"
    )
    args = parser.parse_args()

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
            "font.size": 7,
            "axes.labelsize": 7,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "legend.fontsize": 6.5,
            "pdf.fonttype": 42,
        }
    )
    if args.figure in ("1", "all"):
        architecture()
    if args.figure in ("2", "all"):
        layout()
    if args.figure in ("3", "all"):
        results_figure(args.results, args.characterization)


if __name__ == "__main__":
    main()
