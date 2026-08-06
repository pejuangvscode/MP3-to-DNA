"""MP3-to-DNA: an in-silico pipeline from MP3 recordings to constraint-compliant
DNA sequences, and back to MIDI.

Implements the system designed in Bab III of the thesis. Modules mirror the
eight modules of Tabel 3.5, one file each, with the input/output contract of
that table so every module can be tested in isolation.

Planned layout (modules land here through Fase 1-3):

    config.py       design constants, the single source of truth for Bab III
    bitio.py        bit-level reader/writer for token packing
    preprocess.py   MP3 -> mono PCM at 22050 Hz
    transcribe.py   PCM -> note list, via basic-pitch
    quantize.py     note list -> grid-quantised notes
    tokenizer.py    quantised notes -> tokens -> packed bytes (LZ77 included)
    notation.py     note lists -> MusicXML, an artefact outside the data path
    dna_codec.py    bytes <-> FASTA (RS, scramble, trit, rotating code, GC)
    reconstruct.py  tokens -> MIDI
    baselines.py    comparison paths B1 / B2 / B3 of Tabel 3.12
    evaluate.py     base counts, constraint compliance, mir_eval metrics
    encode.py       CLI: MP3 -> FASTA
    decode.py       CLI: FASTA -> MIDI

`tokenizer.py` rather than `tokenize.py` as the README proposes: a module named
`tokenize.py` shadows the standard library module of that name, which several
stdlib modules import indirectly. The clash only bites when a script is run from
inside the package directory, which is exactly what happens while debugging.
"""

from __future__ import annotations

__version__ = "0.1.0"
