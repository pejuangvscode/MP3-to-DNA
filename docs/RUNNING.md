# Running the pipeline

Every command below is run from the repository root
(`C:\dari laptop lama\TA1\source_code`) with the project's Python 3.11.

---

## Quick start

Once the corpus exists, the whole study is three commands:

```bash
python -m pytest tests/ -q
```

```bash
python -m src.corpus --data-dir data
```

```bash
python -m src.experiment --data-dir data --output results
```

The first proves the implementation still behaves, the second proves the corpus
is usable, and the third produces every table Bab IV reports. Run them in that
order: a corpus problem found after the experiments means running them again.

---

## 1. Check the installation

```bash
python -c "from src import config; print('config OK', config.OLIGO_TOTAL_NT, 'nt/oligo')"
```

If that prints, the design constants are self-consistent and the package
imports. For dependencies and the optional WSL2 GPU setup, see
[SETUP.md](SETUP.md).

Run the test suite before trusting any result:

```bash
python -m pytest tests/ -q
```

Expect **206 passed, 1 skipped**. The skip is a test that would need to
synthesise an MP3, which libsndfile can read but not write.

Most tests are fast. Five touch the transcription model and are marked `slow`;
skip them while iterating:

```bash
python -m pytest tests/ -q -m "not slow"
```

---

## 2. Prepare the corpus

Nine samples composed in FL Studio, each exported twice. The full
specification, including the tempo limits and the Latin-square layout, is in
[CORPUS.md](CORPUS.md). In short:

```
data/audio/<name>.mp3           the recording
data/ground_truth/<name>.mid    the reference notation
data/corpus.csv                 the manifest
```

`data/corpus.csv` lists one row per sample:

```csv
sample,tempo,durasi,kerapatan,pengulangan
s1_pendek_rendah,120,pendek,rendah,rendah
```

The tempo column is taken as known from the FL Studio project, not estimated.
A wrong value here misaligns every note.

---

## 3. Validate the corpus

```bash
python -m src.corpus --data-dir data
```

This checks each sample against what the pipeline can actually represent and
reports what it measured — note count, density, and how much repetition
detection really saves. It exits non-zero if anything is wrong.

Fix everything it reports before going further.

---

## 4. Run the experiments

```bash
python -m src.experiment --data-dir data --output results
```

One sample at a time: encode, verify the round trip, check determinism, decode,
measure compliance, count bases against all three comparison paths, and score
accuracy against the reference.

Useful options:

| Option | Effect |
|---|---|
| `--only s1 s4` | run just those samples, by manifest name |
| `--output results/run2` | write somewhere else, leaving the previous run intact |
| `--grid 1` | use a 1/8 grid instead of the default 1/16 |

Transcription is cached under `results/work/cache`, keyed on the audio file's
contents and the inference parameters. A second run reuses it, so re-running is
cheap and compares like with like. Changing either the audio or a parameter
forces a fresh transcription automatically.

---

## 5. Read the output

```
results/
  summary.md                       six tables, ready to paste into the report
  per_sample.csv                   one row per sample, every measured column
  fasta/<name>.fasta               the encoded sequence
  fasta/<name>.fasta.payload.json  length and digest, so losslessness is checkable
  reconstructed/<name>.mid         notation recovered from the sequence
  reconstructed/<name>.musicxml    the same, as notation
  work/<name>.prepared.wav         mono 22050 Hz audio the model saw
  work/<name>.transcribed.mid      the model's own output — comparison path B2
  work/<name>.musicxml             quantised notation
  work/cache/                      cached transcriptions
```

`summary.md` carries six tables:

| Table | What it answers |
|---|---|
| Efisiensi | how many bases were saved, and how much came from transcription versus the token scheme |
| Kepatuhan | whether every oligo meets the GC and homopolymer constraints |
| Sumbangan deteksi pengulangan | what LZ77 contributed, at both token and base level |
| Akurasi rekonstruksi | precision, recall and F-measure against the reference |
| Dekomposisi error | which module lost what (Tabel 3.13) |
| Keterulangan dan waktu | determinism and wall-clock time per sample |

**Read the repeat-detection table carefully.** Token saving and base saving are
different numbers, and the gap is not musical. Reed-Solomon rounds every payload
up to a whole 255-byte codeword, so removing tokens can push a sample across a
codeword boundary and drop the base count far more than the token count fell —
on the test file, 14.96% fewer tokens produced 29.03% fewer bases. To describe
what the mechanism itself does, quote the **token** figure. The base figure
mixes the mechanism with codeword rounding.

---

## 6. Running a single file

The three commands from the README work standalone, without a manifest.

**Encode.** Tempo is required and is taken as known; tempo estimation is out of
scope.

```bash
python -m src.encode --input song.mp3 --tempo 120 --output song.fasta
```

**Decode.** Needs nothing but the FASTA: tempo and grid resolution travel in the
token header.

```bash
python -m src.decode --input song.fasta --output reconstructed.mid
```

**Evaluate.** Compliance and accuracy work with the first three arguments; add
the last two for the full efficiency decomposition and the error breakdown.

```bash
python -m src.evaluate --reference truth.mid --reconstructed reconstructed.mid --fasta song.fasta --mp3 song.mp3 --transcribed-midi work/song.transcribed.mid
```

### Options worth knowing

| Option | Where | Effect |
|---|---|---|
| `--no-repeat-detection` | encode | disables LZ77, to measure what it contributes |
| `--offset auto` | encode | applies the measured onset shift instead of ignoring it |
| `--offset 25` | encode | applies a fixed shift in milliseconds |
| `--grid 0..3` | encode, corpus, experiment | 1/4, 1/8, 1/16 (default), 1/24 |
| `--no-musicxml` | encode, decode | skips notation export, which is the slowest artefact |

`--offset` defaults to `none`, which is quantisation exactly as Subbab 3.3.4
defines it. The measured offset is always reported either way, so compensating
stays a visible, deliberate choice rather than a silent correction.

---

## 7. When something goes wrong

| Message | Cause and fix |
|---|---|
| `minimum_note_length (60.0 ms) is not shorter than one grid unit` | Tempo is 250 BPM or faster, so a 1/16 note falls below what the model will emit. Slow the piece down or use a coarser grid. |
| `rest of N grid units exceeds the 255-unit limit` | A gap longer than about 15 bars. The token scheme cannot span it; shorten the rest. |
| `N oligos exceeds the 65536 addressable by a 2-byte index` | Only comparison path B1 hits this, on files over roughly 1.59 MiB. The experiment runner counts those bases arithmetically instead of building them, so this is not an error there. |
| `reference notes sit N ms off a M ms grid` | The manifest tempo does not match the project, or the piece contains triplets. |
| `audio is X s but the reference MIDI ends at Y s` | The two exports came from different states of the FL Studio project. Export both again. |
| `transcription found no notes` | Silent or near-silent audio, or thresholds set too high. Check `leading_silence_s` in the output. |
| `token round trip is not lossless` | An implementation defect, not a limitation of the method. Every other figure for that sample is void until it is fixed. Run the test suite. |
| `no manifest at data/corpus.csv` | See section 2. |
| `no reference notation at ...` | The sample has no ground-truth MIDI. Efficiency and compliance still work; accuracy cannot be measured. |

---

## 8. Regenerating everything from scratch

Results are reproducible: the codec derives its scrambling keystream from
SHA-256 rather than from Python's `random`, so identical input yields
byte-identical sequences across machines and versions. Transcription is the one
stage that is not bit-reproducible, which is why it is cached.

To force a completely fresh run, delete the results directory, including the
cache:

```bash
rm -rf results
```

```bash
python -m src.experiment --data-dir data --output results
```

On the test file this takes about 33 seconds for 132 seconds of audio, most of
it transcription. Nine samples of up to two minutes should finish in a few
minutes.
