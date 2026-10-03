# Cara Setup dan Menjalankan Program

Panduan langkah demi langkah, mandiri, sesuai keadaan kode saat ini. Seluruh perintah dijalankan dari direktori `source_code/`.

---

## Langkah 0 — Prasyarat

**Python 3.11.** Versi yang dipakai dan terverifikasi adalah 3.11.3. Jangan pakai 3.12 ke atas: TensorFlow 2.15 tidak menyediakan wheel untuknya.

Periksa versinya:

```bash
python --version
```

Tidak perlu ffmpeg. Berkas MP3 dibaca langsung oleh libsndfile yang sudah menyatu dengan pustaka `soundfile`.

GPU juga tidak perlu. Transkripsi di CPU berjalan sekitar 91 kali waktu nyata — audio 120 detik selesai dalam 1,3 detik.

---

## Langkah 1 — Pasang dependensi

```bash
python -m pip install -r requirements.txt
```

Versi yang terpasang dan terverifikasi:

| Pustaka | Versi | Fungsi |
|---|---|---|
| basic-pitch | 0.4.0 | transkripsi musik otomatis |
| tensorflow | 2.15.0 | runtime model, CPU |
| reedsolo | 1.7.0 | koreksi galat Reed–Solomon |
| biopython | 1.87 | penulisan FASTA |
| music21 | 10.5.0 | ekspor MusicXML |
| mir_eval | 0.8.2 | metrik akurasi transkripsi |
| pretty_midi | 0.2.11 | pemrosesan MIDI |
| soundfile | 0.14.0 | dekode audio termasuk MP3 |
| librosa | 0.11.0 | resampling |
| numpy | 1.26.4 | numerik |
| pytest | 9.1.1 | pengujian |

---

## Langkah 2 — Verifikasi instalasi

Periksa konstanta rancangan bisa dimuat:

```bash
python -c "from src import config; print('OK', config.OLIGO_TOTAL_NT, 'nt per oligo')"
```

Harusnya mencetak `OK 202 nt per oligo`.

Jalankan seluruh pengujian:

```bash
python -m pytest tests/ -q
```

Harusnya **173 lolos, 1 di-skip**, sekitar satu menit. Yang di-skip adalah pengujian yang perlu membuat berkas MP3 sendiri — libsndfile bisa membaca MP3 tapi tidak bisa menulisnya.

Untuk iterasi cepat, lewati lima pengujian yang menjalankan model:

```bash
python -m pytest tests/ -q -m "not slow"
```

---

## Langkah 3 — Siapkan data uji

Susun komposisi di Digital Audio Workstation, lalu ekspor **dua berkas dari proyek yang sama**: MIDI sebagai notasi acuan, dan MP3 sebagai masukan pipeline.

Tata letaknya:

```
data/
  audio/<nama>.mp3           rekaman
  ground_truth/<nama>.mid    notasi acuan
  corpus.csv                 manifes
```

Isi `data/corpus.csv`, satu baris per sampel:

```csv
sample,tempo,durasi,kerapatan,pengulangan
a1,130,pendek,sedang,sedang
```

Kolom `sample` harus sama dengan nama berkas tanpa ekstensi. Kolom `tempo` diambil dari metadata proyek DAW, bukan diestimasi — nilai yang salah akan menggeser seluruh not. Tiga kolom terakhir hanya label untuk pengelompokan hasil: `durasi` diisi pendek/sedang/panjang, sedangkan `kerapatan` dan `pengulangan` diisi rendah/sedang/tinggi.

### Aturan yang harus dipenuhi setiap sampel

| Aturan | Alasan |
|---|---|
| Birama 4/4, tempo tetap | Header token hanya menyimpan satu tempo |
| Tempo 40–249 BPM | Di bawah 40 tidak tersimpan; pada 250 ke atas not 1/16 lebih pendek daripada ambang model |
| Tanpa triol | Kisi 1/16 tidak bisa menyatakannya |
| Maksimal dua instrumen | Sesuai batasan penelitian |
| Jeda antar not tidak lebih dari 15 birama | Medan selisih posisi hanya 8 bit |
| Durasi not tidak lebih dari 4 birama | Durasi dibatasi 64 satuan kisi |

**Aktifkan humanisasi sebelum me-render MP3.** Not yang ditulis di piano roll jatuh persis di kisi, sehingga tanpa humanisasi modul kuantisasi tidak mengerjakan apa pun dan akurasinya tampak sempurna secara semu.

**Pengulangan harus persis.** Frasa yang kembali dengan transposisi atau setelah jeda berbeda akan menghasilkan barisan token berbeda dan tidak tercocokkan. Salin-tempel frasa, jangan mainkan ulang.

---

## Langkah 4 — Validasi korpus

```bash
python -m src.corpus --data-dir data
```

Keluarannya seperti ini:

```
ok   a1               130 BPM  pendek/sedang/sedang
       69 notes, 21.69 s, 3.18 notes/s, repetition saving 50.0 %

--- coverage (Tabel 3.4) ---
  durasi       missing sedang, panjang
  kerapatan    missing rendah, tinggi
  pengulangan  missing rendah, tinggi

1 of 1 samples usable
```

Perintah ini memeriksa tiap sampel terhadap batas yang bisa direpresentasikan skema token, lalu melaporkan jumlah not, kerapatan, dan **derajat pengulangan yang benar-benar dicapai**. Angka terakhir itu berguna untuk mengkalibrasi label rendah/sedang/tinggi pada sampel berikutnya.

Perbaiki semua yang dilaporkan sebelum lanjut. Masalah korpus yang baru ketahuan setelah eksperimen berarti mengulang semuanya.

Dua temuan yang paling sering muncul dan artinya:

**`reference notes sit N ms off a M ms grid`** — tempo di manifes tidak cocok dengan proyek, atau komposisinya memuat triol.

**`audio ends at X s but the reference MIDI runs to Y s`** — render audionya kehilangan sebagian musik, biasanya karena kedua ekspor diambil dari keadaan proyek yang berbeda.

---

## Langkah 5 — Jalankan eksperimen

```bash
python -m src.experiment --data-dir data --output results
```

Untuk tiap sampel: encode, verifikasi round-trip, cek determinisme, decode, ukur kepatuhan batasan biologis, cacah basa terhadap tiga jalur pembanding, dan nilai akurasi terhadap acuan.

Opsi yang berguna:

| Opsi | Efek |
|---|---|
| `--only a1 a4` | jalankan sampel tertentu saja |
| `--output results/run2` | tulis ke tempat lain, hasil lama tetap utuh |
| `--grid 1` | pakai kisi 1/8 alih-alih 1/16 |

Transkripsi di-cache berdasarkan isi berkas audio digabung parameter inferensi, jadi menjalankan ulang murah dan membandingkan hal yang sama. Mengubah audio atau salah satu parameter otomatis memaksa transkripsi baru.

---

## Langkah 6 — Baca hasil

```
results/
  summary.md                    enam tabel siap tempel
  per_sample.csv                satu baris per sampel, seluruh kolom
  fasta/<nama>.fasta            sekuens hasil encoding
  fasta/<nama>.fasta.payload.json  panjang dan ringkasan muatan
  reconstructed/<nama>.mid      notasi hasil rekonstruksi
  reconstructed/<nama>.musicxml notasi untuk dilihat
  work/<nama>.transcribed.mid   keluaran model, jalur pembanding B2
  work/<nama>.prepared.wav      audio mono 22.050 Hz yang dilihat model
  work/cache/                   cache transkripsi
```

Enam tabel di `summary.md`:

| Tabel | Menjawab |
|---|---|
| Efisiensi | berapa basa dihemat, dan berapa dari transkripsi versus skema token |
| Kepatuhan | apakah tiap oligo memenuhi batasan GC dan homopolymer |
| Sumbangan deteksi pengulangan | apa yang disumbang LZ77, pada tataran token dan basa |
| Akurasi rekonstruksi | precision, recall, F-measure terhadap acuan |
| Dekomposisi error | modul mana kehilangan apa |
| Keterulangan dan waktu | determinisme dan waktu proses per sampel |

### Satu tabel yang perlu hati-hati dibaca

Pada tabel sumbangan deteksi pengulangan, **penghematan token dan penghematan basa adalah dua angka berbeda**, dan selisihnya bukan efek musikal. Reed–Solomon membulatkan tiap muatan ke kelipatan kata sandi 255 bita, sehingga membuang token bisa mendorong sampel melewati batas kata sandi dan menurunkan jumlah basa jauh lebih besar daripada penurunan tokennya — atau tidak menurunkannya sama sekali.

Untuk menyatakan apa yang dilakukan mekanismenya sendiri, kutip **angka token**. Angka basa mencampur mekanisme dengan pembulatan kata sandi.

---

## Menjalankan satu berkas saja

Ketiga perintah ini bekerja mandiri tanpa manifes.

**Encode.** Tempo wajib dan diambil sebagai diketahui.

```bash
python -m src.encode --input data/audio/a1.mp3 --tempo 130 --output a1.fasta
```

Keluarannya:

```
audio        23.5363 s, 2 ch @ 44100 Hz, leading silence 0.0314 s
transcribed  73 notes
offset       +34.18 ms measured (concentration 0.784), +0.00 ms applied
quantised    73 -> 73 notes, grid 115.4 ms, rms error 35.38 ms
tokens       51 (46 note + 5 reference), 142 bytes
dna          9 oligos, 1818 bases, 0 rescrambles, 0.6249 bit/base
written      a1.fasta
```

**Decode.** Tidak butuh apa pun selain berkas FASTA — tempo dan resolusi kisi ikut tersimpan di header token.

```bash
python -m src.decode --input a1.fasta --output a1.mid
```

**Evaluate.** Tiga argumen pertama cukup untuk kepatuhan dan akurasi; dua terakhir menambahkan dekomposisi efisiensi B1/B2/B3.

```bash
python -m src.evaluate --reference data/ground_truth/a1.mid --reconstructed a1.mid --fasta a1.fasta --mp3 data/audio/a1.mp3 --transcribed-midi work/a1.transcribed.mid
```

### Opsi encode yang perlu diketahui

| Opsi | Efek |
|---|---|
| `--no-repeat-detection` | matikan LZ77, untuk mengukur sumbangannya |
| `--offset auto` | terapkan pergeseran onset yang terukur |
| `--offset 25` | terapkan pergeseran tetap dalam milidetik |
| `--grid 0..3` | 1/4, 1/8, 1/16 (bawaan), 1/24 |
| `--no-musicxml` | lewati ekspor notasi, artefak paling lambat |
| `--work-dir DIR` | tentukan lokasi berkas antara |

Nilai bawaan `--offset` adalah `none`, yaitu kuantisasi berupa pembulatan murni. Pergeseran yang terukur tetap dilaporkan, sehingga mengompensasinya selalu menjadi pilihan yang disadari.

---

## Menjalankan ulang dari nol

Hasilnya dapat direproduksi: aliran pengacakan diturunkan dari SHA-256, bukan dari pembangkit acak bawaan bahasa, sehingga masukan yang sama menghasilkan sekuens yang identik bita demi bita. Transkripsi adalah satu-satunya tahap yang tidak demikian, dan justru karena itu di-cache.

Untuk memaksa semuanya dihitung ulang termasuk transkripsi:

```bash
rm -rf results
```

```bash
python -m src.experiment --data-dir data --output results
```

Pada sampel 23 detik, satu putaran penuh memakan sekitar 13 detik. Sembilan sampel berdurasi sampai dua menit selesai dalam beberapa menit.

---

## Catatan penting

**Program ini tidak punya penanganan kesalahan.** Sesuai keputusan tahap proof of concept, seluruh pemeriksaan masukan sudah dihapus. Konsekuensinya:

Masukan yang salah tidak menghasilkan pesan yang menjelaskan, melainkan traceback Python dari lapisan mana pun yang kebetulan pecah lebih dulu. Berkas yang tidak ada, misalnya, memunculkan `LibsndfileError`, bukan "berkas tidak ditemukan".

Dua kasus bahkan tidak menghasilkan galat sama sekali. Jeda yang melampaui 255 satuan kisi akan terpotong diam-diam, begitu pula tempo di luar rentang 40–295 BPM. Keduanya menghasilkan data yang salah tanpa peringatan.

Karena itu **Langkah 4 menjadi penting**: validator korpus adalah satu-satunya lapisan yang tersisa untuk menangkap masalah data sebelum masuk pipeline. Jangan dilewati.
