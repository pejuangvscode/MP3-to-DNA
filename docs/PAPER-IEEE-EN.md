# Development of a Codec for Converting Digital Music Files into DNA Sequences Based on Automatic Notation Transcription and Tokenization

**Teofilus Satria Rada Insani**
Faculty of Artificial Intelligence and Data Science
Universitas Pelita Harapan
Tangerang, Indonesia
01082230015@student.uph.edu

> **Editorial note (delete before submission).** The author block appeared twice in the earlier draft; it is written once here. A supervising co-author should be added per the conference's requirements. Every figure in Section V was produced by the software accompanying this paper and is reproducible. **Results come from a single test sample**, so they are presented as preliminary findings from a working prototype rather than as an evaluation. Decimal separators follow English convention throughout; the Indonesian version uses commas.

---

## Abstract

The cost of DNA data storage is directly proportional to the number of nucleotide bases that must be synthesised, so every base saved translates directly into economic feasibility. Conventional approaches treat music recordings like any other binary file, mapping the byte stream of an audio file straight into nucleotides. This is inefficient for music: the final stage of MP3 encoding is Huffman coding, which leaves the byte stream close to its own entropy and therefore practically incompressible, while the musical structure of pitch, duration, and motif repetition is lost entirely once music is stored as a sequence of amplitudes. This paper proposes and implements a pipeline that changes the representation before encoding: a recording is transcribed into symbolic notation through automatic music transcription, quantised against a rhythmic grid, condensed into feature tokens with LZ77-style repeat detection operating at the token level, and then mapped into a FASTA sequence that satisfies biological constraints through a rotating code and is protected by a Reed–Solomon outer code. A working prototype was built and tested on a single 23.5-second sample. Read-back proved lossless at byte-level identity, every oligonucleotide satisfied the 40–60% GC content and homopolymer length constraints with no rejections at the screening stage, and the token scheme saved 66.67% of bases compared with encoding the MIDI file produced by the same transcription. Note-level reconstruction accuracy reached an F-measure of 0.9296. Error decomposition shows that information loss is localised to the transcription stage, while the DNA storage stage contributes no error at all. A further finding is that Reed–Solomon codeword granularity can entirely mask the contribution of repeat detection on short samples.

**Index Terms** — DNA data storage, automatic music transcription, constrained coding, Reed–Solomon, digital preservation, symbolic compression

---

## I. INTRODUCTION

Digital data is growing exponentially, and the capacity and durability of storage media have not kept pace. Hard disks and magnetic tape have relatively short service lives, so data must be periodically copied forward to remain accessible, and that process demands continuous energy, time, and maintenance [1]. This matters most for archives tied to cultural heritage, including music recordings whose value increases with time, yet whose survival is now threatened by material and functional degradation.

Older music recordings face threats from two directions. The physical media holding them degrade materially, while the file formats and the devices that read them fall into obsolescence and are abandoned. As a result, part of the world's musical heritage becomes progressively harder to locate and may be lost before it can be migrated. What is needed is a storage medium that is dense, durable for centuries at room temperature, and independent of the obsolescence of its reading technology.

DNA is one candidate that meets these requirements. As nature's own information carrier, DNA offers storage density far beyond electronic media and can survive for thousands of years when stored properly [1], [2]. In the musical domain, the feasibility of DNA for audio archives is more than an assumption. At the Montreux Jazz Festival, *Smoke on the Water* and *Tutu* were encoded into DNA and read back with full accuracy in a project by Twist Bioscience together with Microsoft and the University of Washington, and both recordings became part of the UNESCO Memory of the World programme [3]. Technically, music has also been stored directly in DNA, as with the main theme of the Nintendo game *Super Mario Bros.* (1985) via enzymatic synthesis [4]. DNA-based music preservation is therefore demonstrably achievable.

Even so, most approaches treat a music file like any other binary file: the MP3 byte stream is converted directly into a nucleotide sequence. Because DNA synthesis is priced per nucleotide and remains expensive [5], this strategy produces a large payload and is economically inefficient. The problem is compounded by the nature of MP3 itself: the final stage of MP3 encoding is Huffman coding, which produces a minimum-redundancy code, so the resulting bytes already sit close to their own entropy and cannot meaningfully be compressed further by general-purpose algorithms. Savings therefore cannot be obtained by compressing the audio file; they can only be obtained by changing its representation.

Music, however, has internal structure in the form of pitch, duration, and motif repetition, which opens the way to a representation far more compact than the raw waveform [6]. This repetition redundancy can only be exploited on a symbolic representation: in the audio domain, two musically identical occurrences of a phrase almost never produce identical sequences of amplitudes.

This paper proposes and implements feature token mapping of MP3 recordings as an alternative. Rather than storing the audio signal, a recording passes through a *from sound to sequence* pipeline: (1) the signal is transcribed into a symbolic note list via automatic music transcription; (2) the notes are quantised against a rhythmic grid using a known tempo; (3) the quantised notes are encoded as a stream of fixed-width tokens, with repeated phrases condensed into reference tokens; and (4) the token stream is mapped into an ATGC sequence in FASTA format that complies with biological constraints and carries error-correction redundancy.

The paper makes three contributions. First, a token mapping framework that bridges automatic music transcription and constraint-aware DNA storage, a link not yet present in the literature. Second, a working implementation together with preliminary measurements of base payload efficiency, biological constraint compliance, and reconstruction accuracy, with error attributed to the module that caused it. Third, the finding that error-correction codeword granularity can mask the contribution of a condensing mechanism on short samples, which has implications for how efficiency of this kind should be reported.

---

## II. RELATED WORK

### A. Medium and Theoretical Foundations of DNA Storage

The comprehensive review by Dong et al. [1] surveys the DNA storage landscape, from its development history through its density and durability advantages to the technical challenges that remain, and establishes that error profiles and biochemical constraints are the central concern of any encoding scheme. On the theoretical side, Shomorony and Heckel [2] formalise the information limits of the DNA storage channel by modelling its three distinctive characteristics: data spread across many short unordered strands, strands subject to noise, and reading performed through random sampling. This foundation provides a benchmark for judging how efficiently a representation can be designed before reaching channel capacity.

A practical consequence of synthesis reliability decaying exponentially with strand length is that data must be split into many short oligonucleotides [5]. This fragmentation requires every oligo to carry an index stating its position along with a primer pair as PCR binding sites, and both occupy space that carries no data payload [7]. The common thread across these works is that payload efficiency and recovery reliability are two goals that must always be balanced.

### B. Constraint-Based Coding and Error Correction

A stable DNA sequence must satisfy several biochemical constraints, chiefly GC content held in the 40–60% range and a bound on homopolymer length, in order to suppress errors during synthesis and reading [8]. Press et al. [9] introduced the HEDGES code, which corrects insertion and deletion errors while simultaneously accommodating sequence constraints, so that constraint adherence and error correction are handled together.

A number of recent schemes make constraint adherence an inherent part of the encoding process rather than a filter applied at the end. Löchel et al. [10] use a *chaos game* representation to construct code words that satisfy GC content, homopolymer, and forbidden motif constraints by construction. Ping et al. [11] propose the *Yin–Yang codec*, which maps two binary bits to a single nucleotide through a pair of complementary transcoding rules. Cao et al. [12] take an adaptive route, tuning constraint thresholds to the characteristics of the payload. Welzel et al. [8] developed DNA-Aeon, an *arithmetic coding* scheme producing sequences that meet user-defined constraints while correcting all the usual error types.

An earlier but structurally relevant approach for this work is the *rotating code* introduced by Goldman et al. [13]. Each base-three symbol maps to one of the three nucleotides that differ from the preceding nucleotide, so homopolymers cannot form at all. Its density of log₂3 ≈ 1.585 bits per base falls below the channel capacity for a maximum homopolymer length of three bases, which is approximately 1.982 bits per base, but that difference is the price paid for simplicity and for constraint compliance guaranteed by construction.

Recovery matters as much as encoding. Preuss et al. [14] designed a storage system based on *shortmer* combinatorial encoding with a two-dimensional Reed–Solomon code, while Schwarz and Freisleben [15] developed *fountain code* recovery methods tailored to the DNA channel. The collective lesson is that constraints are best built directly into the encoding and combined with error correction, and this is the principle adopted for the ATGC mapping stage here.

### C. From Audio to Symbolic Representation and Music-to-DNA

Before compact tokens can be obtained, an audio recording must first be converted into notation through automatic music transcription. Benetos et al. [6] provide a thorough review of the field covering multipitch estimation, onset and offset detection, and score typesetting, while highlighting the difficulty of polyphonic transcription. As a practical realisation, Bittner et al. [16] introduced basic-pitch, a lightweight instrument-agnostic model capable of polyphonic transcription without demanding large computational resources. It is precisely such a model that makes the transcription stage practical outside a large computing environment.

It must be emphasised that automatic transcription output is imperfect. Three error modes occur: a note that should be present goes undetected; a note that does not exist is detected, for instance when the harmonic of another pitch is mistaken for a pitch in its own right; and a note is detected at the correct pitch but with a shifted onset or duration [6]. All three render any pipeline that begins with automatic transcription lossy, regardless of how exact the subsequent stages are.

On the music-to-DNA side, Antkowiak et al. [17] encoded the MusicXML notation file of a composition into DNA strands rather than storing its audio recording. Lee et al. [4] demonstrated melody storage by encoding each note along with its note number, octave, ordering, and duration. Kiryanova et al. [18] deepened this approach, proposing a melody encoding method that accounts for duration and tonality across a seven-octave range and demonstrating higher efficiency than Huffman-based approaches. All three works establish that symbolic music representations can be mapped to nucleotides in a structured way, but each begins from notation entered symbolically rather than from an audio recording.

### D. Repetition Redundancy and the Research Gap

Music is generally repetitive: a composition is built from motifs that are repeated and developed, so structures such as verse and refrain are fundamentally repetition. The LZ77 algorithm [19] exploits this kind of redundancy by replacing a repeated sequence with a back-reference consisting of a distance and a copy length. Its conventional application operates on byte sequences, but the same principle holds for any sequence of symbols, including a token stream representing notes.

Taken together, these three perspectives reveal a gap. Work that stores music symbolically still begins from manually entered notation [4], [17], [18], while recent DNA coding advances focus on efficiency and reliability for generic data [8], [11], [14], [15]. Progress in automatic music transcription [6], [16] and in constraint-compliant coding [8], [10], [11] has not been combined into a single end-to-end path for real music, and no work has quantitatively measured the balance between the bases saved and the reconstruction fidelity sacrificed to save them. This research occupies that gap.

---

## III. SYSTEM DESIGN

### A. Architecture

The system is designed as a bidirectional modular pipeline. The encoding path converts an MP3 recording into a FASTA sequence, while the decoding path reconstructs MIDI notation from that sequence. The synthesis, storage, and sequencing stages are simulated computationally without error injection. Error correction is nevertheless included, because its redundancy contributes to the base count that efficiency measurement depends on.

The architecture is layered, reflecting the outer-code and inner-code division customary in DNA storage: the outer code, a Reed–Solomon code, works at byte level and protects data across oligos, while the inner code, a constrained coding scheme, works at base level and guarantees biological constraint compliance within a single oligo.

### B. Feature Token Scheme

Each quantised note is represented by three discrete quantities: pitch as a MIDI note number, grid position, and duration in grid units. The note sequence is then encoded as a stream of fixed-width tokens. The system recognises two token types distinguished by a leading type bit: a 22-bit note token representing a single note, and a 17-bit reference token representing a repetition of a group of preceding tokens. A 32-bit header is written once at the start to carry the schema version, tempo, grid resolution, and token count.

Note onsets are stored not as absolute positions but as deltas relative to the preceding note. This choice is not merely a way to shrink the stored values; its primary purpose is to ensure that two musically identical phrases produce identical token sequences regardless of where they occur. That property is an absolute prerequisite for repeat detection to work at all.

Repetition is detected through back-reference search adapting the LZ77 principle [19], but operating on the token stream rather than on bytes so that matching happens at the musical level. The algorithm is greedy, taking the longest match within a sliding window of 1,024 tokens. Because a 17-bit reference token replaces at least two note tokens totalling 44 bits, every match found always yields a saving.

### C. DNA Encoding

The byte stream produced by token packing is encoded through six stages. First, Reed–Solomon redundancy [20] is inserted with an RS(255, 223) configuration over GF(2⁸), correcting up to sixteen symbol errors per codeword. Second, the stream is fragmented into fixed-size oligos. Third, each oligo's contents are scrambled by XOR against a pseudo-random stream, producing a near-uniform bit distribution so that GC content centres near 50%. Fourth, each 128-bit block is converted into 81 trits, at an efficiency of 1.5802 bits per trit, or 99.7% of trit capacity. Fifth, trits are mapped to bases through the *rotating code* rotation table, guaranteeing a homopolymer-free payload by construction. Sixth, GC content is screened, and any oligo falling outside the range is re-scrambled with a different seed.

Each oligo consists of a 20 nt forward primer, a 162 nt payload carrying 2 bytes of index, 1 byte of seed counter, and 29 bytes of data, and a 20 nt reverse primer, totalling 202 nt. This length lies within the range that can be synthesised reliably. The first payload base is rotated against the last base of the forward primer so that their junction is also homopolymer-free.

---

## IV. IMPLEMENTATION

### A. Environment and Libraries

The entire pipeline is implemented in Python 3.11.3 and runs fully locally with no dependence on cloud architecture. The main libraries used are listed in Table I.

**TABLE I. LIBRARIES USED**

| Component | Library | Version |
|---|---|---|
| Automatic music transcription | basic-pitch | 0.4.0 |
| Model runtime | TensorFlow (CPU) | 2.15.0 |
| Reed–Solomon error correction | reedsolo | 1.7.0 |
| FASTA writing | biopython | 1.87 |
| MusicXML notation | music21 | 10.5.0 |
| Transcription metrics | mir_eval | 0.8.2 |
| MIDI processing | pretty_midi | 0.2.11 |
| Audio decoding | soundfile | 0.14.0 |

Model inference runs on CPU. Measurement on 120 seconds of audio yielded an inference time of 1.3 seconds, roughly 91 times real time, with a one-off model load of 15 seconds. This empirically confirms the claim of Bittner et al. [16] that basic-pitch is lightweight, so GPU acceleration is unnecessary at the scale of this research.

The system comprises nine modules with defined input and output contracts, allowing each to be tested in isolation. Implementation was verified through 211 automated test cases covering functional requirements, repeatability, token round-trip, and biological constraint compliance.

One placement decision deserves note. MusicXML is a written-notation format, so every duration must be expressible as a note value. Transcription output, being continuous in time, therefore cannot be notated as it stands, and notation is only possible at or after the quantisation stage. MusicXML is placed outside the main data path as an output artefact, so it adds no lossy stage to the pipeline, while the token path is built directly from the quantised note list.

### B. System Parameters

**TABLE II. SYSTEM PARAMETERS**

| Parameter | Value |
|---|---|
| Onset threshold | 0.6 |
| Frame threshold | 0.3 |
| Minimum note length | 60 ms |
| Grid resolution | 1/16 note |
| Outer code | RS(255, 223) over GF(2⁸) |
| Oligo structure | 20 + 162 + 20 = 202 nt |
| Payload per oligo | 2 B index + 1 B seed + 29 B data |
| Base conversion | 128 bits → 81 trits |
| GC content range | 40%–60% |

The minimum note length was lowered from the library default of 127.70 ms. That default exceeds the length of a sixteenth note at 120 BPM, which is 125 ms, so retaining it would cause the model to discard every shortest note the grid can represent. The onset threshold was raised from the default of 0.5; its calibration procedure is described in Subsection V-G along with its limitations.

### C. Test Data

The test sample was composed by the author using a Digital Audio Workstation so that the reference notation is exact by construction: what is written on the piano roll is exactly what sounds in the rendered audio, with no time-alignment or manual annotation step, either of which could introduce error into the reference itself. Its characteristics are given in Table III.

**TABLE III. TEST SAMPLE CHARACTERISTICS**

| Attribute | Value |
|---|---|
| Audio file | MP3, 564,929 bytes, 44.1 kHz, stereo, 23.54 s |
| Reference notation | MIDI, 618 bytes, 69 notes |
| Tempo | 130 BPM, 4/4 time, constant |
| Pitch range | 36–69 (MIDI note numbers) |
| Note density | 3.18 notes per second |

---

## V. RESULTS AND DISCUSSION

### A. Round-Trip and Repeatability Verification

Read-back correctness was verified first, ahead of every other test, because a failure here indicates an implementation defect and invalidates the interpretation of all other metrics. The token stream before encoding was compared against the token stream recovered after decoding by matching SHA-256 digests of the token payload. The two proved identical byte for byte.

Repeatability was tested by executing twice on the same input, and the sequences produced proved identical. This property is obtained by deriving the scrambling stream from SHA-256 rather than from the language's built-in pseudo-random generator, whose output is not guaranteed stable across versions.

These results establish that the DNA storage module contributes no information loss whatsoever, so all reconstruction error measured in Subsection V-D originates in earlier stages.

### B. Biological Constraint Compliance

**TABLE IV. BIOLOGICAL CONSTRAINT COMPLIANCE**

| Quantity | Value | Constraint |
|---|---|---|
| Oligo count | 9 | — |
| Mean GC content | 0.5017 | — |
| Minimum GC content | 0.4802 | ≥ 0.40 |
| Maximum GC content | 0.5297 | ≤ 0.60 |
| Oligos within range | 100% | 100% |
| Maximum homopolymer length | 2 | ≤ 3 |
| Screening rejection rate | 0.00% | — |

Every oligo satisfies the constraints. GC content clusters tightly around 50% with a spread of under three percentage points, and not a single oligo required re-scrambling. This shows that the scrambling stage alone suffices to make the base distribution uniform, so screening acts as a safety net rather than as the primary mechanism.

The maximum homopolymer length is two, not one. The rotating code guarantees a homopolymer-free payload, and the forward-primer-to-payload junction is likewise free because it is rotated. The last payload base, however, depends on the data, so when it happens to equal the first base of the fixed reverse primer, a run of two bases forms. This behaviour is probabilistic: on a different payload from the same sample, the measured maximum was one. The constraint of no more than three bases is still satisfied with a wide margin.

### C. Base Payload Efficiency

Base counts are compared against three comparison paths, all of which pass through the same DNA encoding scheme so that the comparison isolates payload size rather than differences between schemes.

**TABLE V. NUCLEOTIDE BASE COUNT COMPARISON**

| Path | Input payload | Base count |
|---|---|---|
| Proposed pipeline | 142 token bytes | **1,818** |
| B1 — direct baseline (MP3 bytes) | 564,929 bytes | 4,500,964 |
| B2 — symbolic baseline (transcribed MIDI) | 531 bytes | 5,454 |
| B3 — theoretical reference (2 bits/base) | 564,929 bytes | 2,259,716 |

**TABLE VI. DECOMPOSITION OF BASE SAVINGS**

| Quantity | Value |
|---|---|
| Total saving against B1 | 99.96% |
| Contribution of transcription | 99.88% |
| **Contribution of the token scheme** | **66.67%** |
| System effective density | 0.6249 bits/base |

The two contributions are multiplicative and cannot be summed. It must be stressed that the 99.96% figure against B1 should not be read as this research's contribution: most of it merely states that a symbolic representation is far smaller than an audio file, which was never in doubt. The actual contribution is the 66.67% saving against B2, that is, against the MIDI file produced by the same transcription without quantisation and without tokenisation. Comparison path B2 is therefore essential; without it, the measured saving cannot be separated from that trivial fact.

The system's effective density measures 0.6249 bits per base, below the design ceiling of 1.0044 bits per base derived as the product of the scheme density of 1.5802 bits/base with the ratio of payload to oligo length (162/202), the ratio of data bytes to payload (29/32), and the RS code rate (0.8745). The shortfall against the ceiling is caused by Reed–Solomon zero padding, as discussed in Subsection V-E.

### D. Reconstruction Accuracy and Error Decomposition

Accuracy is measured at the note level using mir_eval [21] with default tolerances: 50 ms on onset and 50 cents on pitch. The second variant additionally accounts for offset, with a tolerance equal to the larger of 20% of the reference note duration and 50 ms.

**TABLE VII. RECONSTRUCTION ACCURACY**

| Variant | Precision | Recall | F-measure |
|---|---|---|---|
| Onset and pitch | 0.9041 | 0.9565 | **0.9296** |
| Including offset | 0.4247 | 0.4493 | 0.4366 |

Of 69 reference notes, 66 were matched under one-to-one pairing. The reconstruction produced 73 notes, four more than the reference.

**TABLE VIII. RECONSTRUCTION ERROR DECOMPOSITION**

| Responsible module | F-measure |
|---|---|
| Automatic music transcription | 0.9014 |
| Quantisation | 0.9726 |
| DNA encoding and read-back | lossless (verified) |
| Whole system | 0.9296 |

This decomposition shows two things. First, information loss is localised to the transcription stage rather than to DNA storage. The encoding and read-back module is exactly lossless, so the system's lossy character stems entirely from the imperfection of automatic transcription and, to a far smaller degree, from quantisation rounding.

Second, and unexpectedly, the whole-system F-measure of 0.9296 exceeds the transcription-stage F-measure of 0.9014. Quantisation does not merely avoid damage; it slightly improves note-level accuracy. The explanation is that grid alignment pulls slightly displaced onsets back inside the 50 ms tolerance; in other words, quantisation acts as a filter on small-scale timing error.

The sharp drop in the offset-aware variant is not caused by systematic bias, since the duration difference between paired reference and reconstructed notes has a median of zero. The error is bimodal: most durations are exact while a minority are far off. The reconstruction duration histogram contains 14 notes lasting exactly one grid unit, whereas the reference notation contains only two duration values. Those short notes are fragments produced by transcription, and this finding is consistent with the well-known characteristic of AMT that offset detection is considerably harder than onset detection [6].

A supplementary measurement reveals a systematic onset shift of +34.18 ms with a phase concentration of 0.784, against a grid unit of 115.38 ms. Compensating for that shift reduces grid alignment error from 35.38 ms to 14.64 ms, yet raises the F-measure by only 0.6 percentage points, because the 50 ms tolerance already absorbs the shift.

### E. Contribution of Repeat Detection

The contribution of the repeat detection mechanism was measured by running the system twice on the same sample, with and without the mechanism enabled.

**TABLE IX. CONTRIBUTION OF REPEAT DETECTION**

| Quantity | Without LZ77 | With LZ77 | Saving |
|---|---|---|---|
| Token count | 73 | 51 | **30.14%** |
| Payload size | 205 bytes | 142 bytes | 30.73% |
| Base count | 1,818 | 1,818 | **0.00%** |

There is a striking discrepancy: repeat condensation removes 30.14% of tokens and 30.73% of the payload, yet saves not a single base. The cause is Reed–Solomon codeword granularity. An RS(255, 223) codeword has a fixed length, and a payload shorter than 223 bytes is still zero-padded to fill one whole codeword before fragmentation. A payload of 142 bytes and one of 205 bytes both occupy a single codeword, so both produce the same nine oligos and the same 1,818 bases.

The knock-on consequence is paradoxical. When the onset threshold was raised so that the payload shrank from 159 to 142 bytes, the measured effective density *fell* from 0.6997 to 0.6249 bits per base, because the denominator stayed fixed. As long as this granularity floor applies, better compression lowers the measured effective density, moving in the opposite direction to the quantity it is meant to capture.

This finding has reporting implications. The contribution of repeat detection is better reported at the token level, which reflects the mechanism itself, than at the base level, which conflates it with codeword rounding. The customary remedy is a shortened Reed–Solomon code, padding with zeros only for encoding without synthesising the padding, and this is recorded as future work.

### F. Processing Time

Processing 23.54 seconds of audio took 12.91 seconds on the encoding path and 0.19 seconds on the decoding path. Most of the encoding time is spent loading the transcription model, which happens once per process. The disparity between the two paths reflects that all heavy computation sits in the transcription stage, whereas read-back is nothing but integer arithmetic.

### G. Onset Threshold Calibration

At the library default of 0.5, the system produced a precision of 0.8442 against a recall of 0.9420, an imbalance indicating a detection threshold set too low.

**TABLE X. ONSET THRESHOLD SWEEP**

| Threshold | Note count | Precision | Recall | F-measure |
|---|---|---|---|---|
| 0.30 | 122 | 0.5246 | 0.9275 | 0.6702 |
| 0.50 | 77 | 0.8442 | 0.9420 | 0.8904 |
| **0.60** | 73 | 0.9041 | 0.9565 | **0.9296** |
| 0.70 | 71 | 0.9155 | 0.9420 | 0.9286 |
| 0.80 | 63 | 0.9048 | 0.8261 | 0.8636 |

At a threshold of 0.6, precision and recall rise together. Recall increasing alongside a higher threshold appears to contradict the usual trade-off, but follows from mir_eval's one-to-one matching: a spurious note can take the pairing a correct note would otherwise have received, so removing spurious notes improves both metrics at once.

It must be stated plainly that this sweep was carried out on the same sample used to report the results, and therefore risks overfitting. Its consequences are set out in Section VI.

---

## VI. LIMITATIONS

**Sample count.** All figures come from a single test sample. They establish that the pipeline functions and satisfies biological constraints verifiably, but they do not support generalisation. A corpus varying in duration, note density, and degree of repetition is being assembled.

**Parameter calibration.** The onset threshold was set through a sweep on the same sample used to report results. This procedure cannot be defended as an independent parameter choice, and recalibration across the full corpus is required.

**No error injection.** The synthesis, storage, and sequencing stages are simulated without injecting biological errors. Reed–Solomon correction capability was verified separately through unit tests demonstrating correction of up to sixteen symbol errors per codeword, but robustness against real error profiles has not been measured.

**Software-synthesised audio.** Audio rendered by a DAW is far cleaner than an acoustic recording, so the transcription accuracy reported here is an upper bound.

**Oligo addressing limit.** A two-byte oligo index addresses 65,536 oligos, equivalent to roughly 1.59 MiB of payload, or 69 seconds of audio at 192 kbps. For longer samples, comparison path B1 cannot be materialised as oligos, so its base count is computed analytically. That computation is exact and the comparison path is never decoded, but the limitation must be stated.

**Information not recovered.** The token scheme stores neither velocity nor instrument channel, so performance dynamics are lost and all instruments merge into a single track in the reconstructed notation. This does not affect note-level metrics, which match on pitch and timing alone.

**Scope constraints.** The research is limited to audio with at most two instruments in order to isolate evaluation of the token mapping, so source separation is not addressed. Tempo is treated as known from project metadata, and automatic tempo estimation lies outside the scope.

---

## VII. CONCLUSION

This paper proposes and implements a pipeline bridging automatic music transcription and DNA-based data storage through feature token mapping. Rather than mapping audio file bytes directly, a recording is first re-represented as a compact symbolic token stream, then mapped into a FASTA sequence that satisfies biological constraints by construction and is protected by a Reed–Solomon code.

Preliminary testing on a single sample shows that the pipeline works as designed. Read-back proved lossless at byte-level identity, every oligo satisfied the GC content and homopolymer length constraints with no rejections at the screening stage, and the token scheme saved 66.67% of bases compared with encoding the MIDI file produced by the same transcription. Note-level reconstruction accuracy reached an F-measure of 0.9296.

Decomposing error by responsible module yields the most meaningful finding: information loss is localised entirely to the transcription stage, while DNA storage contributes no error at all. It was also found that quantisation slightly improves note-level accuracy by pulling displaced onsets back within tolerance, and that Reed–Solomon codeword granularity can completely mask the contribution of repeat condensation on short samples, so that contribution is better reported at the token level.

Future work includes evaluation over a full corpus varying in duration, note density, and degree of repetition; adoption of a shortened Reed–Solomon code to remove the granularity floor; and error injection to measure system robustness against realistic synthesis and sequencing error profiles.

---

## REFERENCES

[1] Y. Dong, F. Sun, Z. Ping, Q. Ouyang, and L. Qian, "DNA storage: Research landscape and future prospects," *National Science Review*, Jun. 2020, doi: 10.1093/nsr/nwaa007.

[2] I. Shomorony and R. Heckel, "Information-Theoretic Foundations of DNA Data Storage," *Foundations and Trends in Communications and Information Theory*, vol. 19, no. 1, pp. 1–106, Feb. 2022, doi: 10.1561/0100000117.

[3] A. Dufaux and T. Amsallem, "The Montreux Jazz Digital Project: From Preserving Heritage to a Platform for Innovation," *Journal of Digital Media Management*, vol. 7, no. 4, p. 315, 2019, doi: 10.69554/HKXL1171.

[4] H. Lee et al., "Photon-Directed Multiplexed Enzymatic DNA Synthesis for Molecular Digital Data Storage," *Nature Communications*, vol. 11, no. 1, p. 5246, 2020, doi: 10.1038/s41467-020-18681-5.

[5] M. Yu et al., "High-Throughput DNA Synthesis for Data Storage," *Chemical Society Reviews*, vol. 53, no. 9, pp. 4463–4489, 2024, doi: 10.1039/D3CS00469D.

[6] E. Benetos, S. Dixon, Z. Duan, and S. Ewert, "Automatic Music Transcription: An Overview," *IEEE Signal Processing Magazine*, vol. 36, no. 1, pp. 20–30, 2019, doi: 10.1109/MSP.2018.2869928.

[7] C. Xu, C. Zhao, B. Ma, and H. Liu, "Uncertainties in Synthetic DNA-Based Data Storage," *Nucleic Acids Research*, vol. 49, no. 10, pp. 5451–5469, 2021, doi: 10.1093/nar/gkab230.

[8] M. Welzel et al., "DNA-Aeon Provides Flexible Arithmetic Coding for Constraint Adherence and Error Correction in DNA Storage," *Nature Communications*, vol. 14, no. 1, p. 628, 2023, doi: 10.1038/s41467-023-36297-3.

[9] W. H. Press, J. A. Hawkins, S. K. Jones Jr., J. M. Schaub, and I. J. Finkelstein, "HEDGES Error-Correcting Code for DNA Storage Corrects Indels and Allows Sequence Constraints," *Proceedings of the National Academy of Sciences*, vol. 117, no. 31, pp. 18489–18496, 2020, doi: 10.1073/pnas.2004821117.

[10] H. F. Löchel, M. Welzel, G. Hattab, A.-C. Hauschild, and D. Heider, "Fractal Construction of Constrained Code Words for DNA Storage Systems," *Nucleic Acids Research*, vol. 50, no. 5, p. e30, 2022, doi: 10.1093/nar/gkab1209.

[11] Z. Ping et al., "Towards Practical and Robust DNA-Based Data Archiving Using the Yin–Yang Codec System," *Nature Computational Science*, vol. 2, no. 4, pp. 234–242, 2022, doi: 10.1038/s43588-022-00231-2.

[12] B. Cao, X. Zhang, S. Cui, and Q. Zhang, "Adaptive Coding for DNA Storage with High Storage Density and Low Coverage," *npj Systems Biology and Applications*, vol. 8, no. 1, p. 23, 2022, doi: 10.1038/s41540-022-00233-w.

[13] N. Goldman et al., "Towards Practical, High-Capacity, Low-Maintenance Information Storage in Synthesized DNA," *Nature*, vol. 494, no. 7435, pp. 77–80, 2013, doi: 10.1038/nature11875.

[14] I. Preuss, M. Rosenberg, Z. Yakhini, and L. Anavy, "Efficient DNA-Based Data Storage Using Shortmer Combinatorial Encoding," *Scientific Reports*, vol. 14, no. 1, p. 7731, 2024, doi: 10.1038/s41598-024-58386-z.

[15] P. M. Schwarz and B. Freisleben, "Data Recovery Methods for DNA Storage Based on Fountain Codes," *Computational and Structural Biotechnology Journal*, vol. 23, pp. 1808–1823, 2024, doi: 10.1016/j.csbj.2024.04.048.

[16] R. M. Bittner, J. J. Bosch, D. Rubinstein, G. Meseguer-Brocal, and S. Ewert, "A Lightweight Instrument-Agnostic Model for Polyphonic Note Transcription and Multipitch Estimation," in *Proc. IEEE ICASSP*, 2022, pp. 781–785, doi: 10.1109/ICASSP43922.2022.9746549.

[17] P. L. Antkowiak et al., "Low Cost DNA Data Storage Using Photolithographic Synthesis and Advanced Information Reconstruction and Error Correction," *Nature Communications*, vol. 11, no. 1, p. 5345, 2020, doi: 10.1038/s41467-020-19148-3.

[18] O. Yu. Kiryanova, R. R. Garafutdinov, I. M. Gubaydullin, and A. V. Chemeris, "A Novel Approach to Encode Melodies in DNA," *BioSystems*, vol. 237, p. 105136, 2024, doi: 10.1016/j.biosystems.2024.105136.

[19] J. Ziv and A. Lempel, "A Universal Algorithm for Sequential Data Compression," *IEEE Transactions on Information Theory*, vol. 23, no. 3, pp. 337–343, 1977, doi: 10.1109/TIT.1977.1055714.

[20] I. S. Reed and G. Solomon, "Polynomial Codes Over Certain Finite Fields," *Journal of the Society for Industrial and Applied Mathematics*, vol. 8, no. 2, pp. 300–304, 1960, doi: 10.1137/0108018.

[21] C. Raffel et al., "mir_eval: A Transparent Implementation of Common MIR Metrics," in *Proc. ISMIR*, 2014.
