"""Test suite for the MP3-to-DNA pipeline.

Organised around the test groups of Tabel 3.14:

    test_config.py      design constants are mutually consistent
    test_bitio.py       bit packing round-trips
    test_tokenizer.py   token round-trip and LZ77 correctness
    test_dna_codec.py   byte -> FASTA -> byte round-trip, lossless
    test_constraints.py GC content and homopolymer length over every oligo
    test_determinism.py identical input yields identical output
    test_quantize.py    grid alignment
    test_pipeline.py    end-to-end, on the corpus

The token round-trip test comes first: Subbab 3.2.3 names losslessness at the
token level the decisive requirement, and a failure there means an
implementation defect rather than a limitation of the method.
"""
