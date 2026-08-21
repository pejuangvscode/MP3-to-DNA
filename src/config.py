"""Design constants for the MP3-to-DNA pipeline.

Every constant here is fixed by Bab III of the thesis. Each block cites the
subsection or table it comes from, so the code and the report can be checked
against each other. Nothing in this module reads files or has side effects
beyond the self-check at the bottom, which runs on import.

Where the implementation deviates from the report, the deviation is marked
DEVIATION and states what has to be revised in the report.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

#: Token format version written into the header (Tabel 3.7). Bump on any
#: change to a field width or to the meaning of a field.
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Audio preprocessing (Subbab 3.3.2, Tabel 3.5)
# ---------------------------------------------------------------------------

#: basic-pitch converts all input to mono and resamples to 22050 Hz internally
#: (Bittner dkk. 2022). Preprocessing matches that target so the conversion is
#: explicit and auditable rather than hidden inside the model.
TARGET_SAMPLE_RATE = 22050
TARGET_CHANNELS = 1

# ---------------------------------------------------------------------------
# basic-pitch inference parameters (Tabel 2.5, Subbab 3.3.2)
# ---------------------------------------------------------------------------

#: PROVISIONAL, raised from the library default of 0.5. Calibrated on a single
#: sample, which is not enough to justify it.
#:
#: At 0.5 the model was too generous on sample a1: precision 0.844 against
#: recall 0.942, the signature of a threshold set too low (Subbab 2.7.5). A
#: sweep gave:
#:
#:     onset  notes      P       R       F
#:     0.30     122   0.5246  0.9275  0.6702
#:     0.50      77   0.8442  0.9420  0.8904
#:     0.60      73   0.9041  0.9565  0.9296
#:     0.70      71   0.9155  0.9420  0.9286
#:     0.80      63   0.9048  0.8261  0.8636
#:
#: Recall rises along with precision because mir_eval matches one to one
#: (Subbab 2.9.1), so a spurious note can take the pairing a correct note
#: needed; removing spurious notes helps both.
#:
#: THIS VALUE IS TUNED ON THE ONLY SAMPLE THAT EXISTS. With one sample there is
#: no way to tell whether 0.6 generalises or merely suits a1, and a parameter
#: chosen from the results it is later used to produce cannot be defended.
#: Before Bab IV: rerun the sweep across all nine corpus samples, pick one value
#: that works throughout, and report the sweep itself as part of the results
#: rather than presenting the figure as if it had been fixed in advance.
ONSET_THRESHOLD = 0.6

FRAME_THRESHOLD = 0.3

#: DEVIATION from the library default of 127.70 ms.
#:
#: A 1/16 note lasts 60/(4*T) seconds, which is 125 ms at 120 BPM and 107 ms at
#: 140 BPM -- both below the default. Keeping the default would make basic-pitch
#: discard every 1/16 note in the corpus, so recall would collapse for a reason
#: that has nothing to do with the method under test. The value below sits under
#: the shortest grid unit the corpus uses while still rejecting the very short
#: spurious notes the model emits.
#:
#: Report revision required: Subbab 3.3.2 currently states that all inference
#: parameters follow the library defaults. Tabel 2.5 itself stays correct, since
#: it documents the library defaults rather than the values used here.
#:
#: This is a starting value; it gets calibrated against the corpus in Bab IV and
#: the final figure is reported there. Use :func:`assert_min_note_length_fits`
#: to check it against a given tempo and grid.
MINIMUM_NOTE_LENGTH_MS = 60.0

# ---------------------------------------------------------------------------
# Rhythmic grid (Persamaan 3.1, Tabel 3.7)
# ---------------------------------------------------------------------------

#: 2-bit grid resolution code -> subdivisions per beat.
#: Codes follow the order given in Tabel 3.7: quarter, eighth, sixteenth,
#: twenty-fourth.
GRID_SUBDIVISIONS = {
    0: 1,  # 1/4 note
    1: 2,  # 1/8 note
    2: 4,  # 1/16 note  <- default, the resolution Bab III designs around
    3: 6,  # 1/24 note (triplet sixteenths)
}
DEFAULT_GRID_CODE = 2

# ---------------------------------------------------------------------------
# Quantised note (Tabel 3.6)
# ---------------------------------------------------------------------------

MIN_PITCH = 0
MAX_PITCH = 127
MIN_DURATION_UNITS = 1
MAX_DURATION_UNITS = 64  # durations beyond this are clamped, per Subbab 3.3.4

# ---------------------------------------------------------------------------
# Header layout, 32 bits total (Tabel 3.7)
# ---------------------------------------------------------------------------

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

#: Tempo is stored as (BPM - 40), giving the 40..295 BPM range of Tabel 3.7.
TEMPO_OFFSET = 40
MIN_TEMPO = TEMPO_OFFSET
MAX_TEMPO = TEMPO_OFFSET + (1 << HEADER_TEMPO_BITS) - 1

MAX_TOKEN_COUNT = (1 << HEADER_TOKEN_COUNT_BITS) - 1

# ---------------------------------------------------------------------------
# Note token, 22 bits total (Tabel 3.8)
# ---------------------------------------------------------------------------

TOKEN_TYPE_BITS = 1
TOKEN_TYPE_NOTE = 0
TOKEN_TYPE_REFERENCE = 1

NOTE_PITCH_BITS = 7  # 0..127
NOTE_DELTA_BITS = 8  # 0..255 grid units since the previous note
NOTE_DURATION_BITS = 6  # stored as (duration - 1), giving 1..64 units
NOTE_TOKEN_BITS = (
    TOKEN_TYPE_BITS + NOTE_PITCH_BITS + NOTE_DELTA_BITS + NOTE_DURATION_BITS
)

MAX_DELTA_UNITS = (1 << NOTE_DELTA_BITS) - 1
NOTE_DURATION_OFFSET = 1

# ---------------------------------------------------------------------------
# Reference token, 17 bits total (Tabel 3.9)
# ---------------------------------------------------------------------------

REF_DISTANCE_BITS = 10  # stored as (distance - 1), giving 1..1024 tokens back
REF_LENGTH_BITS = 6  # stored as (length - 2), giving 2..65 tokens copied
REFERENCE_TOKEN_BITS = TOKEN_TYPE_BITS + REF_DISTANCE_BITS + REF_LENGTH_BITS

REF_DISTANCE_OFFSET = 1
REF_LENGTH_OFFSET = 2

# ---------------------------------------------------------------------------
# LZ77 repeat detection (Subbab 3.3.4)
# ---------------------------------------------------------------------------

LZ77_WINDOW = (1 << REF_DISTANCE_BITS)  # 1024 tokens
LZ77_MIN_MATCH = REF_LENGTH_OFFSET  # 2 tokens
LZ77_MAX_MATCH = REF_LENGTH_OFFSET + (1 << REF_LENGTH_BITS) - 1  # 65 tokens

# ---------------------------------------------------------------------------
# Reed-Solomon outer code (Subbab 2.4.3, Subbab 3.3.4)
# ---------------------------------------------------------------------------

RS_N = 255  # codeword length in symbols, the maximum for GF(2^8)
RS_K = 223  # data symbols per codeword
RS_NSYM = RS_N - RS_K  # 32 parity symbols -> corrects 16 symbol errors

#: OPEN QUESTION, to settle with corpus measurements in Fase 5.
#:
#: Subbab 3.3.4 zero-pads the final codeword, and that padding is fragmented and
#: synthesised along with everything else. So any payload costs at least one
#: whole codeword: 255 coded bytes -> 9 oligos -> 1818 bases, whether the token
#: stream is 23 bytes or 223. One byte past 223 doubles the base count.
#:
#: The waste falls hardest on short, highly repetitive samples, which is exactly
#: the corner of Tabel 3.4 where the token scheme should look best, so it could
#: confound the duration dimension of the efficiency results.
#:
#: MEASURED 2026-08-07 on a real 132 s, 192 kbps MP3, and the effect is large:
#: payloads of 909 and 1114 bytes both produced exactly 8888 bases, so a 23%
#: difference in payload vanished entirely, while going from 1114 to 1165 bytes
#: (+4.6%) raised the base count by 20%. Across a nine-sample corpus,
#: differences between samples can therefore be created or erased by where the
#: codeword boundary happens to fall rather than by the music.
#:
#: Decision taken 2026-08-07: leave the design as written and report this as an
#: open limitation. Bab IV is not imminent and the near-term deliverable is a
#: conference paper. The standard fix, if it is taken up later, is a shortened
#: RS code -- pad for encoding, transmit only the real data and parity -- which
#: needs the payload length stored somewhere, cheapest as a header in the first
#: oligo, and revisions to Tabel 3.10 and Subbab 3.3.4.
#:
#: Exactly 223/255 = 0.87451. Subbab 2.4.3 and Subbab 3.3.4 both quote 0.875,
#: which is that value rounded to three decimals rather than the code rate
#: itself. Parity overhead is 32/255 = 12.55% of synthesised symbols, not 12.5%.
#: Small, but it feeds the base counts of Bab IV, so the exact ratio is used
#: here and the rounded figure in the report should be marked as approximate.
RS_RATE = RS_K / RS_N

# ---------------------------------------------------------------------------
# Oligo layout (Tabel 3.10)
# ---------------------------------------------------------------------------

OLIGO_PAYLOAD_BYTES = 32
OLIGO_INDEX_BYTES = 2  # position of this oligo within the file
OLIGO_SEED_COUNTER_BYTES = 1  # incremented on each GC screening rejection
OLIGO_DATA_BYTES = (
    OLIGO_PAYLOAD_BYTES - OLIGO_INDEX_BYTES - OLIGO_SEED_COUNTER_BYTES
)  # 29

OLIGO_PAYLOAD_NT = 162
PRIMER_NT = 20
OLIGO_TOTAL_NT = PRIMER_NT + OLIGO_PAYLOAD_NT + PRIMER_NT  # 202

#: OPEN LIMITATION, left as designed by decision of 2026-08-07.
#:
#: The 2-byte index caps how many oligos one file can span, and therefore how
#: much RS-coded data the format addresses: 65536 * 29 bytes, about 1.81 MiB,
#: or roughly 1.59 MiB of payload. At 192 kbps that is 69 seconds of MP3.
#:
#: This is not merely a ceiling: Tabel 3.1 requirement 11 has the system encode
#: raw MP3 through the same codec as a comparison path, and Tabel 3.4 asks for
#: two-minute samples. A 132 s test file needed 125443 oligos, nearly twice
#: what the index can address, so requirement 11 cannot be met for the longer
#: samples as the design stands.
#:
#: Reported base counts are unaffected: comparison path B1 exists to count
#: bases, never to decode, and :func:`src.baselines.count_bases` computes that
#: count exactly from Persamaan 3.2 without building any oligo. Widening the
#: index to 3 bytes would fix it, at 28 data bytes per oligo instead of 29, a
#: 3.4% capacity cost.
MAX_OLIGO_COUNT = 1 << (OLIGO_INDEX_BYTES * 8)
MAX_CODED_BYTES = MAX_OLIGO_COUNT * OLIGO_DATA_BYTES

# ---------------------------------------------------------------------------
# Scrambling (Subbab 2.3.5, Subbab 3.3.4)
# ---------------------------------------------------------------------------

#: Only the data bytes are scrambled. The index and seed-counter bytes stay in
#: the clear, because the decoder has to read them to rebuild the seed before it
#: can undo the XOR. Bab III says the seed is reconstructed "dari isi header
#: oligo" but does not spell out that this excludes those bytes from the XOR;
#: scrambling them as well would make the payload unrecoverable.
SCRAMBLE_OFFSET = OLIGO_INDEX_BYTES + OLIGO_SEED_COUNTER_BYTES  # 3
SCRAMBLE_LENGTH = OLIGO_DATA_BYTES  # 29

#: Domain separator mixed into the keystream so the PRNG stream is tied to this
#: schema. Changing it changes every output, so treat it as frozen.
SCRAMBLE_DOMAIN = b"mp3-to-dna/scramble/v1"

#: The keystream is derived with SHA-256 rather than Python's `random`, whose
#: output stream carries no cross-version guarantee. The non-functional
#: repeatability requirement (Tabel 3.2) demands identical output for identical
#: input, which needs a generator specified by algorithm, not by library.

# ---------------------------------------------------------------------------
# Bit-to-trit conversion (Subbab 2.3.3, Subbab 3.3.4)
# ---------------------------------------------------------------------------

BLOCK_BITS = 128
BLOCK_TRITS = 81  # 3**81 > 2**128, efficiency 128/81 = 1.5802 bit/trit (99.7%)
BLOCKS_PER_OLIGO = 2  # 32 bytes = 256 bits = 2 blocks -> 162 trits -> 162 nt

# ---------------------------------------------------------------------------
# Rotating code (Tabel 2.3, Tabel 3.11)
# ---------------------------------------------------------------------------

BASES = ("A", "C", "G", "T")

#: previous base -> (base for trit 0, base for trit 1, base for trit 2).
#: The chosen base always differs from the previous one, so the payload can
#: never contain a homopolymer longer than 1.
ROTATION = {
    "A": ("C", "G", "T"),
    "C": ("G", "T", "A"),
    "G": ("T", "A", "C"),
    "T": ("A", "C", "G"),
}

#: (previous base, current base) -> trit. Inverse of ROTATION, built once here
#: so decoding never has to search a row.
DEROTATION = {
    (prev, base): trit
    for prev, row in ROTATION.items()
    for trit, base in enumerate(row)
}

# ---------------------------------------------------------------------------
# Biological constraints (Subbab 2.2, Tabel 3.2)
# ---------------------------------------------------------------------------

GC_MIN = 0.40
GC_MAX = 0.60
HOMOPOLYMER_MAX = 3  # the requirement the output is checked against

#: Highest seed-counter value tried before giving up on GC screening. The
#: counter is one byte, so it cannot exceed 255 anyway. Scrambling already
#: centres GC near 50%, so rejections should be rare; the observed rejection
#: rate is reported in Bab IV.
MAX_SCRAMBLE_ATTEMPTS = 1 << (OLIGO_SEED_COUNTER_BYTES * 8)

# ---------------------------------------------------------------------------
# Primers (Tabel 3.10)
# ---------------------------------------------------------------------------

#: Fixed 20 nt flanks. Both are GC-balanced at exactly 50% and contain no two
#: identical adjacent bases, so they add no homopolymer of their own and stay
#: under the 25 nt limit of Subbab 2.1.4.
#:
#: Because neither primer nor payload ever repeats a base, no restriction site
#: containing a doubled base (EcoRI GAATTC, BamHI GGATCC, HindIII AAGCTT,
#: NotI GCGGCCGC, ...) can occur anywhere in an oligo. The common 6-cutters that
#: have no doubled base (XhoI CTCGAG, SalI GTCGAC, XbaI TCTAGA, SacI GAGCTC)
#: were checked against both primers and are absent.
PRIMER_FORWARD = "ACGTAGCTAGCATGCATCGA"
PRIMER_REVERSE = "TGCATCGATCGTACGATGCA"

#: The first payload base is rotated against the last base of the forward
#: primer, so the primer/payload junction is homopolymer-free by construction
#: (Subbab 3.3.4).
ROTATION_SEED_BASE = PRIMER_FORWARD[-1]

#: KNOWN LIMIT, needs a report correction.
#:
#: Subbab 3.3.4 claims the maximum homopolymer length in the output is
#: guaranteed to be 1. That holds inside the payload and at the forward
#: junction, but not at the payload -> reverse-primer junction: the last payload
#: base is data-dependent, and when it happens to equal the first base of the
#: reverse primer ('T') the sequence carries a run of 2. The reverse primer is
#: fixed, so it cannot be rotated away.
#:
#: The <= 3 requirement of Tabel 3.2 still holds with room to spare, and the
#: measured maximum is reported in Bab IV. Subbab 3.3.4 should say the payload
#: is homopolymer-free and the whole oligo stays within 2.
EXPECTED_MAX_HOMOPOLYMER = 2

# ---------------------------------------------------------------------------
# FASTA output (Subbab 2.10.3)
# ---------------------------------------------------------------------------

FASTA_LINE_WIDTH = 60
FASTA_ID_PREFIX = "oligo"

# ---------------------------------------------------------------------------
# Evaluation (Subbab 2.9.3, Subbab 3.3.5)
# ---------------------------------------------------------------------------

#: mir_eval defaults, stated explicitly because loose tolerances inflate the
#: reported metrics (Subbab 2.9.3).
ONSET_TOLERANCE_S = 0.050
PITCH_TOLERANCE_CENTS = 50.0
OFFSET_RATIO = 0.20
OFFSET_MIN_TOLERANCE_S = 0.050

#: Theoretical reference path B3 (Tabel 3.12): naive 2 bits per base, with no
#: biological constraint and no error correction.
THEORETICAL_BITS_PER_BASE = 2.0


# ---------------------------------------------------------------------------
# Derived helpers
# ---------------------------------------------------------------------------


def grid_unit_seconds(tempo_bpm: float, grid_code: int = DEFAULT_GRID_CODE) -> float:
    """Length of one grid unit in seconds (Persamaan 3.1).

    At the 1/16 resolution this is 60 / (4 * tempo), matching the equation as
    written in the report; the subdivision count generalises it to the other
    resolutions of Tabel 3.7.
    """
    return 60.0 / (GRID_SUBDIVISIONS[grid_code] * tempo_bpm)


def assert_min_note_length_fits(
    tempo_bpm: float, grid_code: int = DEFAULT_GRID_CODE
) -> None:
    """Fail loudly if basic-pitch would discard notes one grid unit long.

    Guards the conflict documented on MINIMUM_NOTE_LENGTH_MS: transcription must
    not silently drop the shortest notes the grid can represent.
    """
    unit_ms = grid_unit_seconds(tempo_bpm, grid_code) * 1000.0
    if MINIMUM_NOTE_LENGTH_MS >= unit_ms:
        raise ValueError(
            f"minimum_note_length ({MINIMUM_NOTE_LENGTH_MS:.1f} ms) is not shorter "
            f"than one grid unit at {tempo_bpm:g} BPM "
            f"(1/{4 * GRID_SUBDIVISIONS[grid_code]} note = {unit_ms:.1f} ms). "
            "basic-pitch would discard the shortest representable notes."
        )


def oligo_count_for(coded_bytes: int) -> int:
    """Number of oligos needed for `coded_bytes` bytes of RS-coded data."""
    return -(-coded_bytes // OLIGO_DATA_BYTES)  # ceil division


def total_bases_for(coded_bytes: int) -> int:
    """Total synthesised bases, i.e. Persamaan 3.2.

    `coded_bytes` is the byte count *after* Reed-Solomon expansion. Persamaan
    3.2 writes this as B without saying which side of the RS stage it is
    measured on; counting before expansion would understate the base count by
    the 12.5% parity overhead.
    """
    return oligo_count_for(coded_bytes) * OLIGO_TOTAL_NT


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------


def _gc_fraction(seq: str) -> float:
    return (seq.count("G") + seq.count("C")) / len(seq)


def _max_homopolymer(seq: str) -> int:
    longest = run = 1
    for prev, cur in zip(seq, seq[1:]):
        run = run + 1 if cur == prev else 1
        longest = max(longest, run)
    return longest


def _validate() -> None:
    """Check that the constants above are mutually consistent.

    Runs on import so a typo in a field width fails immediately rather than
    surfacing as a corrupted round-trip much later.
    """
    assert HEADER_BITS == 32, f"header must be 32 bits, got {HEADER_BITS}"
    assert NOTE_TOKEN_BITS == 22, f"note token must be 22 bits, got {NOTE_TOKEN_BITS}"
    assert REFERENCE_TOKEN_BITS == 17, (
        f"reference token must be 17 bits, got {REFERENCE_TOKEN_BITS}"
    )

    # A reference token must never cost more than the notes it replaces,
    # otherwise repeat detection could inflate the output (Subbab 3.3.3).
    assert REFERENCE_TOKEN_BITS < LZ77_MIN_MATCH * NOTE_TOKEN_BITS

    assert MAX_PITCH == (1 << NOTE_PITCH_BITS) - 1
    assert MAX_DURATION_UNITS == (1 << NOTE_DURATION_BITS)
    assert MAX_TEMPO == 295, f"tempo range must top out at 295, got {MAX_TEMPO}"
    assert LZ77_WINDOW == 1024 and LZ77_MAX_MATCH == 65

    assert RS_N <= 255 and RS_NSYM == 32
    assert round(RS_RATE, 3) == 0.875, "RS rate no longer rounds to the reported 0.875"

    # Oligo arithmetic (Tabel 3.10).
    assert (
        OLIGO_INDEX_BYTES + OLIGO_SEED_COUNTER_BYTES + OLIGO_DATA_BYTES
        == OLIGO_PAYLOAD_BYTES
    )
    assert OLIGO_DATA_BYTES == 29
    assert OLIGO_PAYLOAD_BYTES * 8 == BLOCK_BITS * BLOCKS_PER_OLIGO
    assert BLOCK_TRITS * BLOCKS_PER_OLIGO == OLIGO_PAYLOAD_NT
    assert OLIGO_TOTAL_NT == 202
    assert SCRAMBLE_OFFSET + SCRAMBLE_LENGTH == OLIGO_PAYLOAD_BYTES

    # The conversion is only lossless if the trit block can hold the bit block.
    assert 3**BLOCK_TRITS >= 2**BLOCK_BITS, "trit block too small for bit block"
    assert 3 ** (BLOCK_TRITS - 1) < 2**BLOCK_BITS, "trit block larger than needed"

    # Rotating code: each row is the three bases other than the previous one.
    for prev, row in ROTATION.items():
        assert len(row) == 3 and len(set(row)) == 3
        assert prev not in row, f"rotation row {prev} may not map back to {prev}"
        assert set(row) == set(BASES) - {prev}
    assert len(DEROTATION) == 12

    # Primers (Tabel 3.10).
    for name, primer in (("forward", PRIMER_FORWARD), ("reverse", PRIMER_REVERSE)):
        assert len(primer) == PRIMER_NT, f"{name} primer must be {PRIMER_NT} nt"
        assert set(primer) <= set(BASES), f"{name} primer has a non-ACGT base"
        assert GC_MIN <= _gc_fraction(primer) <= GC_MAX, (
            f"{name} primer GC {_gc_fraction(primer):.2%} is outside the window"
        )
        assert _max_homopolymer(primer) == 1, (
            f"{name} primer must have no repeated adjacent base"
        )
    assert PRIMER_FORWARD != PRIMER_REVERSE
    assert ROTATION_SEED_BASE in BASES

    assert GC_MIN < GC_MAX and EXPECTED_MAX_HOMOPOLYMER <= HOMOPOLYMER_MAX
    assert SCHEMA_VERSION < (1 << HEADER_VERSION_BITS)


_validate()
