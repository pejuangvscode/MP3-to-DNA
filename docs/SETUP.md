# Setup

Two environments are involved:

| Environment | Used for | GPU |
|---|---|---|
| Windows (current) | Fase 0–1: token scheme and DNA codec | not needed |
| WSL2 | Fase 2 onward: basic-pitch transcription and full pipeline runs | RTX 4050 |

Fase 1 is pure integer and bit manipulation, so it develops and tests entirely
on Windows. WSL2 is only required once transcription enters the picture.

---

## 1. Windows — Fase 0–1

Python 3.11.3 is already installed, along with `numpy`, `tensorflow`,
`basic-pitch`, `librosa`, `soundfile`, `mido`, `pretty_midi` and `mir_eval`.

Three packages are still missing. Install them:

```bash
python -m pip install "reedsolo>=1.7.0" "biopython>=1.83" "music21>=9.1.0"
```

Then pin what actually got installed, so `requirements.txt` records exact
versions rather than lower bounds:

```bash
python -m pip show reedsolo biopython music21 | findstr /R "^Name ^Version"
```

Verify the design constants load and self-check:

```bash
python -c "from src import config; print('config OK', config.OLIGO_TOTAL_NT, 'nt/oligo')"
```

### MP3 decoding

`ffmpeg` is not installed on this machine. It is probably not needed:
`soundfile` 0.14 bundles libsndfile 1.2, which reads MP3 natively. Confirm:

```bash
python -c "import soundfile as sf; print('libsndfile', sf.__libsndfile_version__); print('MP3 supported:', 'MP3' in sf.available_formats())"
```

If that prints `MP3 supported: False`, install ffmpeg and the preprocessing
module will fall back to it:

```bash
winget install --id Gyan.FFmpeg -e
```

---

## 2. WSL2 — Fase 2 onward

TensorFlow 2.15 on native Windows is a CPU-only build (`is_built_with_cuda()`
returns `False`); NVIDIA GPU support ended with TF 2.10. Running inference on
the RTX 4050 therefore means running the pipeline under WSL2.

### 2.1 Install WSL2

WSL is not installed yet. In an **administrator** PowerShell:

```bash
wsl --install
```

Reboot when prompted, then set the Ubuntu username and password on first launch.

The Windows NVIDIA driver (596.36, already installed) provides the GPU to WSL —
do **not** install an NVIDIA driver inside the Linux distro.

### 2.2 Python environment inside WSL

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
python3 -m venv ~/.venvs/mp3dna
source ~/.venvs/mp3dna/bin/activate
```

Install TensorFlow with CUDA **before** the rest, so the CUDA runtime packages
come along; the pinned `tensorflow==2.15.0` in `requirements.txt` is then already
satisfied and pip leaves it alone:

```bash
pip install "tensorflow[and-cuda]==2.15.0"
pip install -r requirements.txt
```

### 2.3 Verify the GPU is visible

```bash
python -c "import tensorflow as tf; print(tf.config.list_physical_devices('GPU'))"
```

A non-empty list means the GPU is in use. Record the TensorFlow, CUDA and cuDNN
versions this reports — Bab IV has to state them, and Tabel 3.3 needs a row for
the WSL2 environment.

### 2.4 Reaching the project from WSL

The repository stays where it is; WSL sees it under `/mnt/c`:

```bash
cd "/mnt/c/dari laptop lama/TA1/source_code"
```

FL Studio stays on Windows. Export the corpus into `data/audio` and
`data/ground_truth` as usual and WSL picks the files up from the same paths.

> Cross-filesystem access through `/mnt/c` is slower than the native Linux
> filesystem. Irrelevant at this corpus size (nine samples, up to two minutes),
> so keeping one copy of the data beats keeping two in sync.

---

## 3. Determinism

Tabel 3.2 requires identical output for identical input. Two things follow:

- The codec derives its scrambling keystream from SHA-256, not from Python's
  `random`, whose stream carries no cross-version guarantee.
- GPU kernels are not bit-reproducible in general. Transcription output is
  therefore treated as an input to the deterministic part of the pipeline: the
  determinism test covers quantisation onward, and transcription output is
  cached per sample so a rerun compares like with like.
