# Building the test corpus

The corpus is composed by hand in FL Studio rather than taken from recordings,
so the reference notation is exact by construction: what is written on the piano
roll is what sounds in the render, with no alignment or manual annotation step
that could put errors into the ground truth itself (Subbab 3.2.5).

Nine samples. Every one exports twice, from the same project state:

| Export | Goes to | Role |
|---|---|---|
| MIDI | `data/ground_truth/<name>.mid` | reference notation, and input to comparison path B2 |
| MP3 | `data/audio/<name>.mp3` | input to the pipeline, and to comparison path B1 |

---

## 1. What every sample must satisfy

These are not style preferences. Each one is a limit of the token scheme or of
the pipeline's assumptions, and breaking it produces either an error or a
misleading result.

| Rule | Why |
|---|---|
| 4/4 time, one fixed tempo throughout | The header stores a single tempo (Tabel 3.7); tempo estimation is out of scope |
| Tempo between 40 and 249 BPM | Below 40 the header cannot store it; at 250 and above a 1/16 note falls under the model's minimum note length |
| No triplets or other figures off the 1/16 grid | The grid cannot express them, so they would quantise to the wrong position |
| At most two instruments | Isolates the token mapping from source separation (Batasan Masalah) |
| No rest longer than 15 bars between consecutive notes | The delta field holds 255 grid units (Tabel 3.8) |
| No note longer than 4 bars | Durations are clamped at 64 grid units (Tabel 3.6) |
| No pitched percussion on a drum channel | Drum tracks are skipped when the reference is read |

Notes written on the piano roll land exactly on the grid, which would make
quantisation look perfect for a reason that has nothing to do with the method.
**Apply FL Studio's humanisation before rendering the MP3**, varying onset and
velocity, so the audio carries the timing irregularity of real playing and the
quantisation module actually does something (Subbab 3.2.5).

Velocity variation is discarded by the token scheme, which stores no velocity
field. It still matters: it changes the audio the model hears.

---

## 2. The nine samples

Tabel 3.4 varies three dimensions at three levels each. Testing every
combination would need 27 samples; nine suffice if they are arranged as a Latin
square, where each level of each dimension appears exactly three times and no
level of repetition repeats within a row or column. Repetition is the dimension
that matters most, since it drives the mechanism the study proposes, and this
layout keeps it balanced against the other two.

| | kerapatan rendah | kerapatan sedang | kerapatan tinggi |
|---|---|---|---|
| **durasi pendek** (±30 s) | pengulangan rendah | pengulangan sedang | pengulangan tinggi |
| **durasi sedang** (±1 min) | pengulangan sedang | pengulangan tinggi | pengulangan rendah |
| **durasi panjang** (±2 min) | pengulangan tinggi | pengulangan rendah | pengulangan sedang |

Rough guidance for the levels:

- **Kerapatan** — low is about 1 note per second, medium about 3, high about 6.
- **Pengulangan** — low means phrases rarely recur; high means a short motif
  repeats through most of the piece. Aim for a real contrast: the validator
  measures what you actually achieved and reports it per level, so the three
  levels should come out clearly separated.

Repetition only counts when it is *exact*. A phrase that returns transposed, or
after a different rest, produces a different token sequence and will not match
(Subbab 3.3.4). Copy and paste phrases rather than replaying them.

---

## 3. Naming and the manifest

Name the files consistently; the stem ties the audio to its reference.

```
data/audio/s1_pendek_rendah.mp3
data/ground_truth/s1_pendek_rendah.mid
```

Then list every sample in `data/corpus.csv`:

```csv
sample,tempo,durasi,kerapatan,pengulangan
s1_pendek_rendah,120,pendek,rendah,rendah
s2_pendek_sedang,120,pendek,sedang,sedang
s3_pendek_tinggi,120,pendek,tinggi,tinggi
s4_sedang_rendah,110,sedang,rendah,sedang
s5_sedang_sedang,110,sedang,sedang,tinggi
s6_sedang_tinggi,110,sedang,tinggi,rendah
s7_panjang_rendah,100,panjang,rendah,tinggi
s8_panjang_sedang,100,panjang,sedang,rendah
s9_panjang_tinggi,100,panjang,tinggi,sedang
```

The tempo column is what the pipeline uses. It is taken as known from the
project rather than estimated, so it has to match the FL Studio project exactly
— a wrong value here misaligns every note and shows up as quantisation error.

---

## 4. Validate before running anything

```bash
python -m src.corpus --data-dir data
```

This checks every sample against the rules above and reports what it measured:
note count, density, and how much repetition detection actually saves. It also
reports whether the corpus covers all three levels of each dimension.

Two checks are worth understanding, because they catch the mistakes that would
otherwise survive into the results:

**Grid error on the reference.** The reference comes from the piano roll, so it
should sit exactly on the grid. If the validator reports it sitting far off, the
tempo in the manifest is wrong or the piece contains triplets. Either way the
quantisation error reported in Bab IV would be measuring the mistake rather than
the method.

**Audio and MIDI duration mismatch.** If the two differ by more than a second,
the exports came from different states of the project, and the reference no
longer describes the audio.

Fix everything the validator reports before encoding. A corpus problem found in
Bab IV means rerunning every experiment.
