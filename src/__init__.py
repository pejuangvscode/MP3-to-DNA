"""MP3 recordings -> constraint-compliant DNA sequences, and back to MIDI.

    config.py       design constants, the single source of truth
    bitio.py        bit-level reader/writer
    preprocess.py   MP3 -> mono PCM at 22050 Hz
    transcribe.py   PCM -> note list, via basic-pitch
    quantize.py     note list -> grid-quantised notes
    tokenizer.py    quantised notes -> tokens -> packed bytes, LZ77 included
    notation.py     note lists -> MusicXML, outside the data path
    dna_codec.py    bytes <-> FASTA
    reconstruct.py  tokens -> MIDI
    baselines.py    comparison paths B1 / B2 / B3
    evaluate.py     base counts, constraint compliance, mir_eval metrics
    corpus.py       corpus validation
    encode.py       CLI: MP3 -> FASTA
    decode.py       CLI: FASTA -> MIDI
    experiment.py   CLI: run the corpus, write the result tables

tokenizer.py rather than tokenize.py: the latter shadows a stdlib module that
several other stdlib modules import indirectly, which bites when a script is run
from inside the package directory.
"""

from __future__ import annotations

__version__ = "0.1.0"
