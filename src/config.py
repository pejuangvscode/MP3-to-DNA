"""Design constants from Bab III. Single source of truth: no other module
hardcodes these.
"""

from __future__ import annotations

SCHEMA_VERSION = 1

# --- audio ---

TARGET_SAMPLE_RATE = 22050  # what basic-pitch resamples to internally
TARGET_CHANNELS = 1

# --- basic-pitch inference (Tabel 2.5) ---

# TODO: raised from the default 0.5, but tuned on one sample. Recalibrate over
# the full corpus. Sweep in docs/HASIL-EKSPERIMEN.md.
ONSET_THRESHOLD = 0.6

FRAME_THRESHOLD = 0.3

# below the default 127.70 ms, which exceeds a 1/16 note at 120 BPM
MINIMUM_NOTE_LENGTH_MS = 60.0

# --- rhythmic grid (Persamaan 3.1, Tabel 3.7) ---

# 2-bit code -> subdivisions per beat
GRID_SUBDIVISIONS = {
    0: 1,  # 1/4
    1: 2,  # 1/8
    2: 4,  # 1/16
    3: 6,  # 1/24
}
DEFAULT_GRID_CODE = 2

# --- quantised note (Tabel 3.6) ---

MIN_PITCH = 0
MAX_PITCH = 127
MIN_DURATION_UNITS = 1
MAX_DURATION_UNITS = 64  # longer durations are clamped

# --- header, 32 bits (Tabel 3.7) ---

HEADER_VERSION_BITS = 4
HEADER_TEMPO_BITS = 8
HEADER_GRID_BITS = 2
HEADER_TOKEN_COUNT_BITS = 16
HEADER_PADDING_BITS = 2
HEADER_BITS = (
    HEADER_VERSION_BITS
    + HEADER_TEMPO_BITS
    + HEADER_GRID_BITS
    + HEADER_TOKEN_COUNT_BITS
    + HEADER_PADDING_BITS
)

TEMPO_OFFSET = 40  # tempo stored as BPM - 40, giving 40..295
MIN_TEMPO = TEMPO_OFFSET
MAX_TEMPO = TEMPO_OFFSET + (1 << HEADER_TEMPO_BITS) - 1

MAX_TOKEN_COUNT = (1 << HEADER_TOKEN_COUNT_BITS) - 1

# --- note token, 22 bits (Tabel 3.8) ---

TOKEN_TYPE_BITS = 1
TOKEN_TYPE_NOTE = 0
TOKEN_TYPE_REFERENCE = 1

NOTE_PITCH_BITS = 7  # 0..127
NOTE_DELTA_BITS = 8  # 0..255 grid units since the previous note
NOTE_DURATION_BITS = 6  # stored as duration - 1, giving 1..64
NOTE_TOKEN_BITS = (
    TOKEN_TYPE_BITS + NOTE_PITCH_BITS + NOTE_DELTA_BITS + NOTE_DURATION_BITS
)

MAX_DELTA_UNITS = (1 << NOTE_DELTA_BITS) - 1
NOTE_DURATION_OFFSET = 1

# --- reference token, 17 bits (Tabel 3.9) ---

REF_DISTANCE_BITS = 10  # stored as distance - 1, giving 1..1024
REF_LENGTH_BITS = 6  # stored as length - 2, giving 2..65
REFERENCE_TOKEN_BITS = TOKEN_TYPE_BITS + REF_DISTANCE_BITS + REF_LENGTH_BITS

REF_DISTANCE_OFFSET = 1
REF_LENGTH_OFFSET = 2

# --- LZ77 (Subbab 3.3.4) ---

LZ77_WINDOW = 1 << REF_DISTANCE_BITS  # 1024 tokens
LZ77_MIN_MATCH = REF_LENGTH_OFFSET  # 2
LZ77_MAX_MATCH = REF_LENGTH_OFFSET + (1 << REF_LENGTH_BITS) - 1  # 65

# --- Reed-Solomon outer code (Subbab 2.4.3) ---

RS_N = 255
RS_K = 223
RS_NSYM = RS_N - RS_K  # 32 parity symbols, corrects 16 symbol errors

RS_RATE = RS_K / RS_N  # 0.87451; the report rounds it to 0.875

# TODO: the padding on the last codeword is synthesised too, so any payload
# under 223 bytes still costs 9 oligos. Fix is a shortened RS code.

# --- oligo layout (Tabel 3.10) ---

OLIGO_PAYLOAD_BYTES = 32
OLIGO_INDEX_BYTES = 2
OLIGO_SEED_COUNTER_BYTES = 1  # incremented on each GC screening rejection
OLIGO_DATA_BYTES = (
    OLIGO_PAYLOAD_BYTES - OLIGO_INDEX_BYTES - OLIGO_SEED_COUNTER_BYTES
)  # 29

OLIGO_PAYLOAD_NT = 162
PRIMER_NT = 20
OLIGO_TOTAL_NT = PRIMER_NT + OLIGO_PAYLOAD_NT + PRIMER_NT  # 202

# caps a file at 1.59 MiB of payload, or 69 s of MP3 at 192 kbps. Path B1 goes
# over that; baselines.count_bases() counts those without building oligos.
MAX_OLIGO_COUNT = 1 << (OLIGO_INDEX_BYTES * 8)
MAX_CODED_BYTES = MAX_OLIGO_COUNT * OLIGO_DATA_BYTES

# --- scrambling (Subbab 2.3.5) ---

# index and seed counter stay in the clear; the decoder needs them to rebuild
# the seed before it can undo the XOR
SCRAMBLE_OFFSET = OLIGO_INDEX_BYTES + OLIGO_SEED_COUNTER_BYTES
SCRAMBLE_LENGTH = OLIGO_DATA_BYTES

# Frozen: changing this changes every sequence the study reports.
SCRAMBLE_DOMAIN = b"mp3-to-dna/scramble/v1"

# --- bit to trit (Subbab 2.3.3) ---

BLOCK_BITS = 128
BLOCK_TRITS = 81  # 3**81 > 2**128; 128/81 = 1.5802 bit/trit, 99.7% of capacity
BLOCKS_PER_OLIGO = 2  # 32 bytes -> 162 trits -> 162 nt

# --- rotating code (Tabel 3.11) ---

BASES = ("A", "C", "G", "T")

# previous base -> base for trit 0, 1, 2. Never maps back to the previous base.
ROTATION = {
    "A": ("C", "G", "T"),
    "C": ("G", "T", "A"),
    "G": ("T", "A", "C"),
    "T": ("A", "C", "G"),
}

DEROTATION = {
    (prev, base): trit
    for prev, row in ROTATION.items()
    for trit, base in enumerate(row)
}

# --- biological constraints (Subbab 2.2, Tabel 3.2) ---

GC_MIN = 0.40
GC_MAX = 0.60
HOMOPOLYMER_MAX = 3

MAX_SCRAMBLE_ATTEMPTS = 1 << (OLIGO_SEED_COUNTER_BYTES * 8)

# --- primers (Tabel 3.10) ---

# both 50% GC with no repeated adjacent base
PRIMER_FORWARD = "ACGTAGCTAGCATGCATCGA"
PRIMER_REVERSE = "TGCATCGATCGTACGATGCA"

ROTATION_SEED_BASE = PRIMER_FORWARD[-1]  # rotates the first payload base

# not 1: the last payload base can equal the reverse primer's first base
EXPECTED_MAX_HOMOPOLYMER = 2

# --- FASTA ---

FASTA_LINE_WIDTH = 60
FASTA_ID_PREFIX = "oligo"

# --- evaluation (Subbab 2.9.3) ---

# mir_eval defaults, stated explicitly because loose tolerances inflate results
ONSET_TOLERANCE_S = 0.050
PITCH_TOLERANCE_CENTS = 50.0
OFFSET_RATIO = 0.20
OFFSET_MIN_TOLERANCE_S = 0.050

THEORETICAL_BITS_PER_BASE = 2.0  # comparison path B3


def grid_unit_seconds(tempo_bpm: float, grid_code: int = DEFAULT_GRID_CODE) -> float:
    """Length of one grid unit in seconds (Persamaan 3.1)."""
    return 60.0 / (GRID_SUBDIVISIONS[grid_code] * tempo_bpm)


def oligo_count_for(coded_bytes: int) -> int:
    return -(-coded_bytes // OLIGO_DATA_BYTES)


def total_bases_for(coded_bytes: int) -> int:
    """Persamaan 3.2. `coded_bytes` is measured after RS expansion."""
    return oligo_count_for(coded_bytes) * OLIGO_TOTAL_NT
