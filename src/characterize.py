"""Measure what the corpus contains, per sample and per instrument group.

    python -m src.characterize --data-dir data/slakh --split test
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path

import librosa
import numpy as np
import pretty_midi
import soundfile as sf

from src import preprocess
from src.quantize import quantize
from src.slakh import _stem_metadata
from src.tokenizer import compress, notes_to_tokens

# onsets closer than this are one attack, i.e. a chord
CHORD_WINDOW_S = 0.030
# frames quieter than this count as silence
SILENCE_DB = -60.0
FRAME = 2048
HOP = 512

NUMERIC = (
    "duration_s",
    "bitrate_kbps",
    "loudness_lufs",
    "active_ratio",
    "active_rms_dbfs",
    "peak_dbfs",
    "centroid_hz",
    "notes",
    "span_s",
    "density",
    "attacks_per_s",
    "polyphony_mean",
    "polyphony_max",
    "chord_share",
    "pitch_min",
    "pitch_max",
    "pitch_span",
    "duration_median_s",
    "duration_median_beats",
    "ioi_median_s",
    "velocity_mean",
    "velocity_sd",
    "tempo",
    "grid_error_ratio",
    "repetition_pct",
)


def polyphony(notes) -> tuple[float, int]:
    """Mean number of notes sounding while any note sounds, and the maximum."""
    # at a tie the note-off goes first, so back-to-back notes do not overlap
    events = sorted(
        [(note.start, 1) for note in notes] + [(note.end, -1) for note in notes]
    )
    active = peak = 0
    weighted = sounding = 0.0
    last = None
    for time, step in events:
        if last is not None and active > 0:
            weighted += active * (time - last)
            sounding += time - last
        active += step
        peak = max(peak, active)
        last = time
    return (weighted / sounding if sounding > 0 else 0.0), peak


def attacks(notes, window: float = CHORD_WINDOW_S) -> list[list]:
    """Group notes whose onsets fall within `window` of the group's first."""
    groups: list[list] = []
    for note in sorted(notes, key=lambda note: note.start):
        if groups and note.start - groups[-1][0].start <= window:
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups


def audio_features(path: Path) -> dict:
    """Format from the file as stored; signal from what the model is given."""
    info = sf.info(str(path))
    audio = preprocess.load(path)
    y, sr = audio.samples, audio.sample_rate

    rms = librosa.feature.rms(y=y, frame_length=FRAME, hop_length=HOP)[0]
    centroid = librosa.feature.spectral_centroid(
        y=y, sr=sr, n_fft=FRAME, hop_length=HOP
    )[0]
    frames = min(len(rms), len(centroid))
    rms, centroid = rms[:frames], centroid[:frames]
    active = 20.0 * np.log10(np.maximum(rms, 1e-10)) >= SILENCE_DB
    level = rms[active]

    return {
        "format": info.format,
        "subtype": info.subtype,
        "source_rate": info.samplerate,
        "channels": info.channels,
        "duration_s": audio.duration,
        "bitrate_kbps": path.stat().st_size * 8 / audio.duration / 1000.0,
        "peak_dbfs": 20.0 * math.log10(max(float(np.abs(y).max()), 1e-10)),
        "active_ratio": float(active.mean()),
        "active_rms_dbfs": (
            20.0 * math.log10(float(np.sqrt(np.mean(level ** 2))))
            if level.size
            else float("nan")
        ),
        "centroid_hz": float(np.median(centroid[active])) if active.any() else float("nan"),
    }


def content_features(midi_path: Path, tempo: int, grid_code: int) -> dict:
    """What the reference notation contains."""
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    notes = sorted(
        (note for inst in midi.instruments if not inst.is_drum for note in inst.notes),
        key=lambda note: (note.start, note.pitch),
    )
    span = max(note.end for note in notes) - min(note.start for note in notes)
    groups = attacks(notes)
    onsets = [group[0].start for group in groups]
    mean_poly, max_poly = polyphony(notes)
    pitches = [note.pitch for note in notes]
    velocities = [note.velocity for note in notes]
    duration_median = statistics.median(note.end - note.start for note in notes)

    report = quantize(notes, tempo, grid_code)
    tokens = notes_to_tokens(report.notes)

    return {
        "notes": len(notes),
        "span_s": span,
        "density": len(notes) / span,
        "attacks_per_s": len(groups) / span,
        "polyphony_mean": mean_poly,
        "polyphony_max": max_poly,
        "chord_share": sum(len(g) for g in groups if len(g) > 1) / len(notes),
        "pitch_min": min(pitches),
        "pitch_max": max(pitches),
        "pitch_span": max(pitches) - min(pitches),
        "duration_median_s": duration_median,
        "duration_median_beats": duration_median * tempo / 60.0,
        "ioi_median_s": float(np.median(np.diff(onsets))) if len(onsets) > 1 else 0.0,
        "velocity_mean": statistics.fmean(velocities),
        "velocity_sd": statistics.pstdev(velocities),
        "tempo": tempo,
        "grid": grid_code,
        "grid_error_ratio": report.rms_grid_error_ms / report.grid_unit_ms,
        "repetition_pct": (1 - len(compress(tokens)) / len(tokens)) * 100.0,
    }


def measure(row: dict, source: Path) -> dict:
    stem_id = row["sample"].split("_")[1]
    meta = _stem_metadata(source / row["source_track"], stem_id)
    features = {
        "sample": row["sample"],
        "split": row["split"],
        "inst_class": row["inst_class"],
        "program": meta.get("midi_program_name", ""),
        "plugin": meta.get("plugin_name", ""),
        "loudness_lufs": float(meta.get("integrated_loudness", "nan")),
    }
    features.update(audio_features(Path(row["audio_path"])))
    features.update(
        content_features(Path(row["midi_path"]), int(row["tempo"]), int(row["grid"]))
    )
    return features


def describe(values: list[float]) -> dict:
    values = [v for v in values if not math.isnan(v)]
    return {
        "mean": statistics.fmean(values),
        "sd": statistics.stdev(values) if len(values) > 1 else 0.0,
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def terciles(values: list[float]) -> tuple[float, float]:
    """The boundaries src.slakh used to label low, medium and high."""
    ordered = sorted(values)
    return ordered[len(ordered) // 3], ordered[2 * len(ordered) // 3]


def summarise(rows: list[dict], split: str) -> dict:
    chosen = [row for row in rows if split == "all" or row["split"] == split]
    groups = {"All": chosen}
    for inst in sorted({row["inst_class"] for row in chosen}):
        groups[inst] = [row for row in chosen if row["inst_class"] == inst]

    summary: dict = {"split": split, "groups": {}}
    for name, members in groups.items():
        summary["groups"][name] = {
            "n": len(members),
            "numeric": {key: describe([float(m[key]) for m in members]) for key in NUMERIC},
            "programs": Counter(m["program"] for m in members).most_common(),
            "plugins": len({m["plugin"] for m in members}),
            "format": Counter(
                f"{m['format']} {m['subtype']} {m['source_rate']} Hz {m['channels']} ch"
                for m in members
            ).most_common(),
            "grid": Counter(m["grid"] for m in members).most_common(),
        }

    # levels are assigned over the whole corpus, so the boundaries are too
    summary["level_boundaries"] = {
        "span_s": terciles([row["span_s"] for row in rows]),
        "density": terciles([row["density"] for row in rows]),
        "repetition_pct": terciles([row["repetition_pct"] for row in rows]),
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.characterize",
        description="Measure the properties of a prepared corpus.",
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data/slakh"))
    parser.add_argument("--source", type=Path, default=Path("new_dataset/slakh_subset"))
    parser.add_argument("--output", type=Path, default=Path("results/characterization"))
    parser.add_argument("--split", default="test", help="dev, test, or all")
    args = parser.parse_args(argv)

    manifest = list(csv.DictReader(open(args.data_dir / "corpus.csv", encoding="utf-8")))
    rows = []
    for index, row in enumerate(manifest, start=1):
        print(f"[{index}/{len(manifest)}] {row['sample']}", flush=True)
        rows.append(measure(row, args.source))

    args.output.mkdir(parents=True, exist_ok=True)
    with open(args.output / "per_sample.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = summarise(rows, args.split)
    (args.output / f"summary_{args.split}.json").write_text(
        json.dumps(summary, indent=1), encoding="utf-8"
    )

    names = list(summary["groups"])
    lines = [
        f"corpus characteristics, {args.split} split",
        "",
        f"{'feature':<22}" + "".join(
            f"{name + ' (n=' + str(summary['groups'][name]['n']) + ')':>30}" for name in names
        ),
    ]
    for key in NUMERIC:
        cells = []
        for name in names:
            s = summary["groups"][name]["numeric"][key]
            cells.append(f"{s['mean']:.2f} +- {s['sd']:.2f} [{s['min']:.2f}, {s['max']:.2f}]")
        lines.append(f"{key:<22}" + "".join(f"{cell:>30}" for cell in cells))

    for name in names:
        group = summary["groups"][name]
        lines += [
            "",
            f"{name}: {group['plugins']} rendering patches; format {group['format']}",
            "  programs: " + ", ".join(f"{p} {n}" for p, n in group["programs"]),
            "  grid codes: " + ", ".join(f"{g}:{n}" for g, n in group["grid"]),
        ]

    lines.append("")
    lines.append("level boundaries over the whole corpus (low < a <= medium < b <= high):")
    for key, (low, high) in summary["level_boundaries"].items():
        lines.append(f"  {key:<16} a = {low:.2f}   b = {high:.2f}")
    lines.append(f"written to {args.output}")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
