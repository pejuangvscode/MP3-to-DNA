# Penjelasan Kode

Dokumen ini menjelaskan isi seluruh kode dan alur kerjanya, ditulis untuk dibaca dari nol. Setiap berkas dijelaskan perannya, lalu ditunjukkan bagaimana data berubah bentuk dari MP3 sampai FASTA dan kembali lagi, memakai satu contoh nyata yang dijalankan sungguhan.

Total: 4.020 baris kode di `src/` dan 2.154 baris pengujian di `tests/`, terbagi menjadi 16 modul dan 13 berkas uji.

---

## 1. Prinsip penyusunan

Tiga aturan dipakai konsisten di seluruh kode, dan mengetahuinya membuat sisanya mudah diikuti.

**Satu sumber kebenaran.** Seluruh konstanta rancangan Bab III berada di `config.py` dan tidak pernah ditulis ulang di modul lain. Lebar medan token, struktur oligo, parameter RS, rentang GC, tabel rotasi — semuanya dari sana. Kalau ada angka yang perlu diubah, cukup satu tempat.

**Setiap modul punya kontrak masukan dan keluaran yang jelas**, mengikuti Tabel 3.5. Akibatnya tiap modul bisa diuji sendirian tanpa menjalankan yang lain, dan itulah sebabnya ada 211 kasus uji.

**Modul yang murni aritmetika dipisahkan dari modul yang menyentuh model.** Tokenisasi dan codec DNA tidak mengimpor TensorFlow sama sekali, sehingga jalan dalam hitungan milidetik dan hasilnya bisa dijamin identik setiap kali. Hanya `transcribe.py` yang memuat model.

---

## 2. Peta berkas

### Lapisan dasar

| Berkas | Baris | Isi |
|---|---|---|
| `config.py` | 496 | Seluruh konstanta Bab III, plus pemeriksaan mandiri yang jalan saat diimpor |
| `bitio.py` | 104 | Penulis dan pembaca bit, untuk medan yang lebarnya bukan kelipatan delapan |

`config.py` adalah berkas terpenting untuk dibaca lebih dulu. Selain konstanta, di dalamnya tersimpan seluruh catatan keputusan rancangan dan temuan yang belum diselesaikan, ditandai `DEVIATION`, `OPEN QUESTION`, `OPEN LIMITATION`, dan `KNOWN LIMIT`. Kalau Anda ingin tahu apa saja yang menyimpang dari laporan dan mengapa, cukup baca berkas itu.

Bagian bawah `config.py` berisi fungsi `_validate()` yang dijalankan otomatis setiap kali modul diimpor. Fungsi ini memeriksa bahwa konstanta-konstantanya saling konsisten: lebar header benar-benar 32 bit, muatan oligo benar-benar terbagi habis, 3⁸¹ memang lebih besar dari 2¹²⁸, primer memenuhi batasan GC, dan seterusnya. Kalau ada salah ketik pada salah satu angka, program gagal seketika saat impor, bukan berjam-jam kemudian sebagai round-trip yang rusak.

### Jalur encoding

| Berkas | Baris | Masukan → keluaran |
|---|---|---|
| `preprocess.py` | 122 | Berkas MP3 → sampel PCM mono 22.050 Hz |
| `transcribe.py` | 213 | Berkas audio → daftar not (pitch, waktu awal, waktu akhir) |
| `quantize.py` | 200 | Daftar not + tempo → not terkuantisasi (pitch, posisi kisi, durasi kisi) |
| `tokenizer.py` | 390 | Not terkuantisasi → barisan token → aliran bita |
| `dna_codec.py` | 435 | Aliran bita ↔ daftar oligo ↔ berkas FASTA |

### Jalur decoding dan keluaran

| Berkas | Baris | Masukan → keluaran |
|---|---|---|
| `reconstruct.py` | 107 | Not terkuantisasi → berkas MIDI, dan sebaliknya |
| `notation.py` | 206 | Daftar not → berkas MusicXML |

### Pengukuran

| Berkas | Baris | Isi |
|---|---|---|
| `baselines.py` | 157 | Jalur pembanding B1, B2, B3 dari Tabel 3.12 |
| `evaluate.py` | 457 | Efisiensi, kepatuhan, akurasi, dekomposisi galat |

### Antarmuka perintah

| Berkas | Baris | Perintah |
|---|---|---|
| `encode.py` | 244 | `python -m src.encode` — MP3 jadi FASTA |
| `decode.py` | 113 | `python -m src.decode` — FASTA jadi MIDI |
| `corpus.py` | 306 | `python -m src.corpus` — validasi korpus |
| `experiment.py` | 438 | `python -m src.experiment` — jalankan seluruh korpus, hasilkan semua tabel |

---

## 3. Alur encoding, dengan contoh nyata

Contoh berikut dijalankan sungguhan melalui kode. Frasa empat not C–E–G–C diulang dua kali pada tempo 120 BPM, resolusi kisi 1/16.

### Tahap 1 — `preprocess.py`

MP3 dibaca melalui `soundfile`, kanal kiri dan kanan **dirata-ratakan** menjadi satu kanal, lalu di-*resample* ke 22.050 Hz karena itulah yang dibutuhkan model.

Kanal dirata-ratakan, bukan diambil salah satunya, supaya not yang di-*pan* keras ke satu sisi tidak hilang sama sekali. Modul ini juga mengukur *silence* di awal berkas, yang berguna untuk mendeteksi pergeseran onset akibat delay encoder MP3.

### Tahap 2 — `transcribe.py`

Model basic-pitch dijalankan, menghasilkan daftar not berisi pitch, waktu awal, dan waktu akhir dalam satuan detik.

Dua hal penting di modul ini. Pertama, hasilnya **di-cache** ke berkas JSON dengan kunci berupa ringkasan isi berkas audio digabung parameter inferensi. Inferensi model adalah satu-satunya tahap yang tidak dijamin identik antarjalan, jadi meng-cache-nya membuat seluruh tahap sesudahnya bisa dijalankan ulang atas masukan yang benar-benar sama. Mengubah audionya atau salah satu parameternya otomatis memaksa transkripsi ulang.

Kedua, modul ini juga menuliskan berkas MIDI keluaran model. Berkas itu dipakai sebagai jalur pembanding B2 dan sebagai acuan tengah pada dekomposisi galat Tabel 3.13.

### Tahap 3 — `quantize.py`

Not diselaraskan ke kisi ritmis mengikuti empat langkah Subbab 3.3.4: hitung panjang satu satuan kisi dari tempo, bulatkan pitch dan waktu, urutkan menurut posisi lalu pitch, dan gabungkan not yang pitch serta posisinya sama dengan mengambil durasi terpanjang.

```
not terkuantisasi:
  (pitch 60, posisi  0, durasi 4)    (pitch 60, posisi 16, durasi 4)
  (pitch 64, posisi  4, durasi 4)    (pitch 64, posisi 20, durasi 4)
  (pitch 67, posisi  8, durasi 4)    (pitch 67, posisi 24, durasi 4)
  (pitch 72, posisi 12, durasi 4)    (pitch 72, posisi 28, durasi 4)
```

Modul ini juga menyediakan `estimate_offset()`, yang mengukur pergeseran waktu awal yang dialami seluruh not secara bersamaan. Fungsinya hanya mengukur, tidak mengoreksi, karena Subbab 3.3.4 mendefinisikan kuantisasi sebagai pembulatan murni tanpa suku offset. Kompensasi tersedia sebagai pilihan eksplisit yang harus dinyatakan bila dipakai.

### Tahap 4 — `tokenizer.py`

Ini inti kontribusi penelitian, dan berlangsung dalam tiga langkah.

**4a. Delta encoding.** Posisi mutlak diganti selisih terhadap not sebelumnya.

```
token not (pitch, delta, durasi):
  (60, 0, 4)  (64, 4, 4)  (67, 4, 4)  (72, 4, 4)
  (60, 4, 4)  (64, 4, 4)  (67, 4, 4)  (72, 4, 4)
```

Perhatikan bahwa tujuh token terakhir semuanya berdelta 4, sementara token pertama berdelta 0. Delta token pertama membawa posisi mutlak awal komposisi. Inilah yang membuat frasa identik menghasilkan barisan token identik di mana pun ia muncul, dan tanpa sifat itu deteksi pengulangan tidak akan pernah menemukan apa pun.

**4b. Deteksi pengulangan LZ77.** Sistem menelusuri barisan token, mencari barisan terpanjang yang sama persis di dalam jendela 1.024 token ke belakang.

```
setelah LZ77:
  NoteToken (60, 0, 4)
  NoteToken (64, 4, 4)
  NoteToken (67, 4, 4)
  NoteToken (72, 4, 4)
  NoteToken (60, 4, 4)
  ReferenceToken (jarak 4, panjang 3)
```

Delapan token menjadi enam. Token rujukan terakhir menggantikan tiga token: "salin tiga token mulai dari empat token ke belakang".

Ada satu detail instruktif di sini. Not pertama frasa kedua, yaitu `(60, 4, 4)`, **tidak ikut tercocokkan** karena tidak sama dengan not pertama frasa pertama `(60, 0, 4)` — deltanya berbeda, sebab yang pertama membawa posisi awal komposisi. Biayanya satu token per komposisi dan dapat diabaikan, tetapi menjelaskan mengapa penghematan tidak pernah mencapai 100% meski frasanya berulang sempurna.

**4c. Pemadatan bit.** Token dirangkai menjadi aliran bit lalu dipotong per bita. Token not memakai 22 bit, token rujukan 17 bit, dan header 32 bit di awal.

```
176 bit tanpa LZ77  →  127 bit dengan LZ77  (hemat 28%)
hasil akhir 20 bita: 150800183c000d0010343040d201033c040e0182
```

### Tahap 5 — `dna_codec.py`

Aliran bita diubah menjadi oligo melalui enam tahap berurutan.

1. **Reed–Solomon.** Data diisi nol hingga kelipatan 223 bita, lalu tiap blok dikodekan menjadi 255 bita. Ini kode luar yang melindungi data lintas oligo.
2. **Fragmentasi.** Aliran dipecah menjadi potongan 29 bita.
3. **Pengacakan.** Tiap potongan di-XOR dengan aliran pseudo-acak yang diturunkan dari SHA-256. Tujuannya meratakan distribusi bit supaya kandungan GC memusat di 50%. Hanya 29 bita datanya yang diacak; 2 bita indeks dan 1 bita penghitung seed dibiarkan terbaca, sebab decoder harus membacanya lebih dulu untuk bisa membalik pengacakan.
4. **Bit ke trit.** Tiap blok 128 bit diubah menjadi 81 digit basis tiga.
5. **Rotating code.** Tiap trit dipetakan ke basa yang selalu berbeda dari basa sebelumnya, sehingga muatan mustahil memuat homopolymer.
6. **Penapisan GC.** Bila kandungan GC oligo di luar 40–60%, penghitung seed dinaikkan dan oligo diacak ulang.

Terakhir primer ditempelkan di kedua ujung dan hasilnya ditulis sebagai FASTA.

```
20 bita  →  1 kata sandi RS (255 bita)  →  9 oligo  →  1.818 basa

oligo pertama, 60 basa awal:
ACGTAGCTAGCATGCATCGA CGTACGTACGTACGTCGAGATGATCGTATGTACTACTCTG
└──── primer maju ──┘ └──────────── awal muatan ─────────────┘
```

Dua puluh bita menjadi 1.818 basa terlihat sangat boros, dan memang begitu: satu kata sandi RS berukuran tetap 255 bita, sehingga muatan sekecil apa pun tetap membayar satu kata sandi penuh. Persoalan ini terdokumentasi di `config.py` sebagai `OPEN QUESTION` dan dibahas di Seksi V-E paper.

`dna_codec.py` juga menulis **manifes muatan** di sebelah berkas FASTA, berisi panjang dan ringkasan SHA-256 dari bita token. Manifes ini yang memungkinkan `evaluate.py` benar-benar memverifikasi sifat lossless, bukan sekadar mengasumsikannya.

---

## 4. Alur decoding

Kebalikan persis dari encoding, dijalankan oleh `decode.py`.

Primer dipangkas, basa dipetakan balik menjadi trit lewat tabel rotasi terbalik, trit diubah kembali menjadi bit, indeks dan penghitung seed dibaca dari bagian yang tidak diacak, lalu pengacakan dibalik. Oligo disusun ulang menurut indeksnya — bukan menurut urutan kemunculannya di berkas, sebab pada penyimpanan sungguhan oligo mengambang di dalam larutan tanpa urutan fisik. Setelah itu Reed–Solomon di-decode, token dibaca dari aliran bita, token rujukan diekspansi, dan not disusun kembali menjadi berkas MIDI.

Ekspansi token rujukan dilakukan satu token demi satu token dari barisan keluaran yang sedang tumbuh. Cara ini penting: ia memungkinkan sebuah rujukan yang jarak baliknya lebih kecil daripada panjang salinnya tetap terekspansi dengan benar, sehingga pola berulang beruntun bisa diringkas oleh satu token rujukan saja.

Decoding tidak memerlukan apa pun selain berkas FASTA. Tempo dan resolusi kisi ikut tersimpan di header token, sehingga sekuens yang ditemukan terpisah pun tetap dapat direkonstruksi.

---

## 5. Alur pengukuran

`baselines.py` menyediakan tiga jalur pembanding Tabel 3.12. B1 mengambil bita MP3 mentah, B2 mengambil bita MIDI hasil transkripsi, dan keduanya melewati codec DNA yang sama persis dengan pipeline sehingga perbandingannya hanya mengukur ukuran muatan. B3 adalah acuan teoretis dua bit per basa.

Satu catatan pada B1: berkas MP3 yang panjang membutuhkan lebih banyak oligo daripada yang dapat dialamati indeks dua bita. Karena B1 hanya dipakai untuk mencacah basa dan tidak pernah di-decode, jumlahnya dihitung langsung lewat Persamaan 3.2 tanpa membangun oligonya. Perhitungannya eksak.

`evaluate.py` menghitung tiga kelompok metrik. Efisiensi memakai Persamaan 3.3 sampai 3.6, dan identitas Persamaan 3.6 diperiksa otomatis — kalau ketiga angka basa tidak konsisten, program melempar error alih-alih melaporkan angka yang salah. Kepatuhan menghitung kandungan GC dan panjang homopolymer atas seluruh oligo. Akurasi memakai `mir_eval` dalam dua varian, dengan dan tanpa memperhitungkan waktu akhir.

Dekomposisi galat Tabel 3.13 dihitung dengan memperlakukan keluaran tiap tahap sebagai acuan bagi tahap berikutnya. Baris codec DNA hanya diisi bila manifes muatan tersedia dan cocok; bila tidak, baris itu berbunyi `not verified` dan bukan 1,0000. Ini disengaja: melaporkan nilai sempurna tanpa memeriksa berarti mengasumsikan justru hal yang paling penting untuk dibuktikan.

---

## 6. Cara menjalankan

Alur normal untuk korpus lengkap ada tiga perintah, dijelaskan lengkap di [RUNNING.md](RUNNING.md).

```bash
python -m pytest tests/ -q
```

```bash
python -m src.corpus --data-dir data
```

```bash
python -m src.experiment --data-dir data --output results
```

`experiment.py` mengerjakan seluruh korpus sekali jalan: untuk tiap sampel ia meng-encode, memverifikasi round-trip, memeriksa determinisme, men-decode, mengukur kepatuhan, mencacah basa terhadap ketiga pembanding, dan menilai akurasi terhadap acuan. Keluarannya `results/per_sample.csv` berisi seluruh kolom, dan `results/summary.md` berisi enam tabel siap tempel.

Untuk satu berkas saja, tiga perintah `src.encode`, `src.decode`, dan `src.evaluate` bekerja mandiri tanpa manifes.

---

## 7. Bagaimana pengujian disusun

Ke-211 kasus uji mengikuti kelompok pengujian Tabel 3.14, satu berkas per modul.

Urutannya disengaja. `test_tokenizer.py` dan `test_dna_codec.py` menguji sifat lossless lebih dulu, sebab Subbab 3.2.3 menyebutnya kriteria paling menentukan: kegagalan di situ berarti cacat implementasi, bukan keterbatasan metode, dan membatalkan penafsiran metrik lainnya.

`test_constraints.py` menguji kepatuhan atas enam masukan ekstrem, termasuk seluruh bita nol dan seluruh bita 0xFF — dua kasus yang justru merusak pemetaan naif. `test_determinism.py` memuat dua nilai *golden*: ringkasan aliran pengacakan dan ringkasan keluaran pipeline. Kalau salah satu berubah, tesnya gagal. Tujuannya agar perubahan pada skema pengacakan harus merupakan keputusan sadar, bukan efek samping pemutakhiran pustaka.

Lima tes ditandai `slow` karena menjalankan model. Untuk iterasi cepat, jalankan `python -m pytest tests/ -q -m "not slow"`.

---

## 8. Di mana keputusan dan temuan terdokumentasi

Kalau Anda perlu menjelaskan suatu pilihan rancangan saat sidang, uraian lengkapnya ada di dokumen, sementara kodenya hanya memuat ringkasan satu-dua baris di tempat konstanta itu didefinisikan.

**Seluruh temuan dan keterbatasan terurai lengkap di [PAPER-IEEE.md](PAPER-IEEE.md) Seksi V dan VI**: granularitas RS beserta angka pengukurannya, batas pengalamatan oligo, klaim homopolymer yang ternyata probabilistik, asal-usul ambang onset lengkap dengan tabel penelusurannya, dan alasan durasi not minimum diturunkan.

Di kode, empat pekerjaan yang belum selesai ditandai `TODO` sehingga bisa dicari dengan `grep -rn TODO src/`: ambang onset yang perlu dikalibrasi ulang atas korpus penuh, dan pengisian nol Reed–Solomon yang menciptakan lantai jumlah basa.

Docstring tiap modul menjelaskan alasan modul itu ada dan mengutip subbab laporan yang melandasinya. Komentar di dalam kode menjelaskan mengapa sesuatu dilakukan, bukan apa yang dilakukan — yang terakhir sudah terbaca dari kodenya sendiri.

Dokumen pendamping: [RUNNING.md](RUNNING.md) untuk menjalankan, [CORPUS.md](CORPUS.md) untuk menyusun korpus, [SETUP.md](SETUP.md) untuk pemasangan, dan [PAPER-IEEE.md](PAPER-IEEE.md) untuk hasilnya.
