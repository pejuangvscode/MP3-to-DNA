# Hasil Eksperimen — draf untuk conference paper

Draf seksi Implementasi, Hasil, dan Keterbatasan dalam bahasa Indonesia, siap
disunting ke templat IEEE. Seluruh angka dihasilkan oleh `python -m src.experiment`
dan dapat direproduksi dengan perintah yang sama.

> **Status data: satu sampel.** Korpus penuh sembilan sampel (Tabel 3.4) belum
> tersusun. Seluruh angka di bawah berasal dari satu sampel uji, sehingga harus
> disajikan sebagai **hasil awal atas prototipe yang berfungsi**, bukan sebagai
> evaluasi. Setiap klaim generalisasi harus ditunda sampai korpus lengkap.

---

## IV. IMPLEMENTASI

### A. Lingkungan dan Pustaka

Seluruh pipeline diimplementasikan dengan Python 3.11.3 pada Windows 11 dan
dijalankan sepenuhnya secara lokal tanpa ketergantungan pada arsitektur cloud.
Pustaka yang digunakan disajikan pada Tabel I.

**Tabel I. Pustaka yang digunakan**

| Komponen | Pustaka | Versi |
|---|---|---|
| Transkripsi musik otomatis | basic-pitch | 0.4.0 |
| Runtime model | TensorFlow (CPU) | 2.15.0 |
| Koreksi galat Reed–Solomon | reedsolo | 1.7.0 |
| Penulisan FASTA | biopython | 1.87 |
| Notasi MusicXML | music21 | 10.5.0 |
| Metrik transkripsi | mir_eval | 0.8.2 |
| Pemrosesan MIDI | pretty_midi | 0.2.11 |
| Dekode audio | soundfile (libsndfile 1.2.2) | 0.14.0 |
| Pemrosesan sinyal | librosa | 0.11.0 |

Inferensi model dijalankan pada CPU. Pengukuran terpisah atas audio berdurasi
120 detik menghasilkan waktu inferensi 1,3 detik, yakni sekitar **91 kali waktu
nyata**, dengan pemuatan model sekali sebesar 15 detik. Hasil ini merupakan
konfirmasi empiris atas klaim Bittner dkk. bahwa basic-pitch bersifat ringan dan
tidak menuntut sumber daya komputasi besar, sehingga akselerasi GPU tidak
diperlukan pada skala korpus penelitian ini.

Sistem tersusun atas sembilan modul dengan kontrak masukan dan keluaran yang
terdefinisi, sehingga setiap modul dapat diuji secara terpisah. Verifikasi
implementasi dilakukan melalui 211 kasus uji otomatis yang mencakup seluruh
kebutuhan fungsional, keterulangan, round-trip token, dan kepatuhan batasan
biologis.

### B. Parameter Sistem

**Tabel II. Parameter sistem**

| Parameter | Nilai |
|---|---|
| Ambang onset | 0,6 |
| Ambang bingkai | 0,3 |
| Durasi not minimum | 60 ms |
| Resolusi kisi | 1/16 nada |
| Kode luar | RS(255, 223) atas GF(2⁸) |
| Struktur oligo | 20 nt primer + 162 nt muatan + 20 nt primer = 202 nt |
| Muatan per oligo | 2 B indeks + 1 B penghitung seed + 29 B data |
| Konversi basis | 128 bit → 81 trit (1,5802 bit/trit) |
| Rentang kandungan GC | 40%–60% |

Ambang onset dinaikkan dari nilai bawaan pustaka sebesar 0,5. Prosedur dan
justifikasi kalibrasinya diuraikan pada Subbab V-G, beserta keterbatasan yang
melekat padanya.

### C. Data Uji

Sampel uji disusun penulis menggunakan Digital Audio Workstation, sehingga
notasi acuan bersifat eksak secara konstruksi: notasi yang ditulis pada piano
roll persis sama dengan yang terdengar pada audio hasil render, tanpa
memerlukan penyelarasan waktu maupun anotasi manual yang keduanya berpotensi
menimbulkan galat pada acuan itu sendiri. Karakteristik sampel disajikan pada
Tabel III.

**Tabel III. Karakteristik sampel uji**

| Atribut | Nilai |
|---|---|
| Berkas audio | MP3, 564.929 bita, 44,1 kHz, stereo, 23,54 s |
| Notasi acuan | MIDI, 618 bita, 69 not, satu instrumen |
| Tempo | 130 BPM, birama 4/4, tetap |
| Rentang nada | 36–69 (nomor not MIDI) |
| Durasi notasi | 21,69 s |
| Kerapatan not | 3,18 not per detik |

---

## V. HASIL DAN PEMBAHASAN

### A. Verifikasi Round-Trip dan Keterulangan

Kebenaran pembacaan balik diverifikasi terlebih dahulu, mendahului seluruh
pengujian lain. Barisan token sebelum pengodean dibandingkan terhadap barisan
token hasil pembacaan balik melalui pencocokan ringkasan SHA-256 atas muatan
token. Keduanya terbukti **identik bita demi bita**.

Keterulangan diuji melalui eksekusi ganda atas masukan yang sama. Sekuens yang
dihasilkan terbukti identik. Sifat ini diperoleh dengan menurunkan aliran
pengacakan dari SHA-256 alih-alih dari pembangkit bilangan acak semu bawaan
bahasa, yang keluarannya tidak dijamin stabil antarversi.

Hasil ini menegaskan bahwa modul penyimpanan DNA tidak menyumbang kehilangan
informasi sama sekali. Konsekuensinya, seluruh galat rekonstruksi yang terukur
pada Subbab V-D bersumber pada tahap sebelumnya.

### B. Kepatuhan Batasan Biologis

Kepatuhan diverifikasi atas seluruh oligo yang dihasilkan. Hasilnya disajikan
pada Tabel IV.

**Tabel IV. Kepatuhan batasan biologis**

| Besaran | Nilai | Batasan |
|---|---|---|
| Jumlah oligo | 9 | — |
| Kandungan GC rerata | 0,5017 | — |
| Kandungan GC minimum | 0,4802 | ≥ 0,40 |
| Kandungan GC maksimum | 0,5297 | ≤ 0,60 |
| Oligo dalam rentang | 100% | 100% |
| Panjang homopolymer maksimum | 2 | ≤ 3 |
| Tingkat penolakan penapisan GC | 0,00% | — |

Seluruh oligo memenuhi batasan. Kandungan GC memusat rapat di sekitar 50%
dengan simpangan kurang dari 3 poin persen, dan **tidak satu pun oligo
memerlukan pengacakan ulang**. Hasil ini menunjukkan bahwa tahap pengacakan
sudah cukup untuk menyeragamkan distribusi basa, sehingga penapisan berperan
sebagai jaring pengaman dan bukan sebagai mekanisme utama.

Perlu dicatat bahwa panjang homopolymer maksimum bernilai dua, bukan satu.
Rotating code menjamin muatan bebas homopolymer, dan basa pertama muatan
dirotasikan terhadap basa terakhir primer maju sehingga sambungan tersebut juga
bebas. Namun basa terakhir muatan bergantung pada data, sehingga ketika nilainya
kebetulan sama dengan basa pertama primer mundur yang bersifat tetap, terbentuk
deret sepanjang dua basa. Sifat ini probabilistik: pada muatan yang berbeda dari
sampel yang sama, nilai maksimum terukur bernilai satu. Batasan tidak lebih dari
tiga basa tetap terpenuhi dengan margin yang lebar.

### C. Efisiensi Muatan Basa

Jumlah basa nitrogen dibandingkan terhadap tiga jalur pembanding yang seluruhnya
melewati skema pengodean DNA yang sama. Hasilnya disajikan pada Tabel V.

**Tabel V. Perbandingan jumlah basa nitrogen**

| Jalur | Muatan masukan | Jumlah basa |
|---|---|---|
| Pipeline yang diusulkan | 142 bita token | **1.818** |
| B1 — pembanding langsung (bita MP3) | 564.929 bita | 4.500.964 |
| B2 — pembanding simbolik (MIDI transkripsi) | 531 bita | 5.454 |
| B3 — referensi teoretis (2 bit/basa) | 564.929 bita | 2.259.716 |

Dekomposisi penghematan disajikan pada Tabel VI.

**Tabel VI. Dekomposisi penghematan basa**

| Besaran | Nilai |
|---|---|
| Penghematan total terhadap B1 | 99,96% |
| Sumbangan transkripsi | 99,88% |
| **Sumbangan skema token** | **66,67%** |
| Kerapatan efektif sistem | 0,6249 bit/basa |

Kedua sumbangan bersifat multiplikatif dan tidak dapat dijumlahkan. Hubungannya
diverifikasi secara otomatis oleh perangkat evaluasi.

**Angka 99,96% terhadap B1 tidak boleh dibaca sebagai kontribusi penelitian
ini.** Sebagian besar penghematan tersebut hanya menyatakan bahwa representasi
simbolik jauh lebih kecil daripada berkas audio, yang sudah dapat disimpulkan
sejak awal. Kontribusi yang sesungguhnya adalah **penghematan 66,67% terhadap
B2**, yaitu terhadap berkas MIDI hasil transkripsi yang sama, tanpa kuantisasi
dan tanpa tokenisasi. Angka inilah yang mengukur sumbangan skema token beserta
mekanisme peringkasan pengulangan yang diusulkan.

Kerapatan efektif sistem terukur 0,6249 bit per basa. Nilai ini berada di bawah
plafon rancangan sebesar 1,0044 bit per basa, yang diturunkan sebagai

    1,5802 (kerapatan skema) × 162/202 (primer) × 29/32 (indeks dan seed)
        × 0,8745 (laju RS) = 1,0044 bit/basa

Selisih terhadap plafon disebabkan pengisian nol Reed–Solomon, sebagaimana
dibahas pada Subbab V-E.

### D. Akurasi Rekonstruksi dan Dekomposisi Galat

Akurasi diukur pada tataran not menggunakan mir_eval dengan toleransi bawaan,
yaitu 50 ms pada waktu awal dan 50 cent pada tinggi nada. Varian kedua turut
memperhitungkan waktu akhir dengan toleransi sebesar nilai terbesar antara 20%
durasi not acuan dan 50 ms. Hasilnya disajikan pada Tabel VII.

**Tabel VII. Akurasi rekonstruksi**

| Varian | Precision | Recall | F-measure |
|---|---|---|---|
| Waktu awal dan tinggi nada | 0,9041 | 0,9565 | **0,9296** |
| Turut memperhitungkan waktu akhir | 0,4247 | 0,4493 | 0,4366 |

Dari 69 not acuan, 66 berhasil dipasangkan berdasarkan waktu awal dan tinggi
nada, dengan pencocokan bersifat satu lawan satu. Rekonstruksi menghasilkan 73
not, sehingga terdapat kelebihan empat not terhadap acuan.

Galat diuraikan menurut modul penyebabnya pada Tabel VIII, dengan memperlakukan
keluaran setiap tahap sebagai acuan bagi tahap sesudahnya.

**Tabel VIII. Dekomposisi galat rekonstruksi**

| Modul penyebab | F-measure |
|---|---|
| Transkripsi musik otomatis | 0,9014 |
| Kuantisasi | 0,9726 |
| Pengodean dan pembacaan balik DNA | lossless (terverifikasi) |
| Keseluruhan sistem | 0,9296 |

Dekomposisi ini memperlihatkan dua hal.

Pertama, **kehilangan informasi terlokalisasi pada tahap transkripsi**, bukan
pada tahap penyimpanan DNA. Modul pengodean dan pembacaan balik terbukti
lossless secara eksak, sehingga sifat lossy sistem sepenuhnya berasal dari
ketidaksempurnaan transkripsi otomatis dan, pada derajat yang jauh lebih kecil,
dari pembulatan kuantisasi.

Kedua, dan ini di luar dugaan, **F-measure keseluruhan sistem (0,9296) lebih
tinggi daripada F-measure tahap transkripsi (0,9014)**. Kuantisasi tidak hanya
tidak merusak, melainkan sedikit memperbaiki akurasi tataran not. Penjelasannya
adalah bahwa penyelarasan ke kisi menarik kembali waktu awal yang meleset sedikit
sehingga masuk ke dalam toleransi 50 ms. Dengan kata lain, kuantisasi berperan
sebagai penapis galat waktu berskala kecil.

Penurunan tajam pada varian yang memperhitungkan waktu akhir, dari 0,9296 menjadi
0,4366, tidak disebabkan oleh bias sistematis: selisih durasi antara not acuan
dan not rekonstruksi yang berpasangan bernilai median 0 ms. Galatnya bersifat
bimodal, yakni sebagian besar durasi tepat sementara sebagian kecil meleset jauh.
Pada histogram durasi rekonstruksi terdapat 14 not berdurasi tepat satu satuan
kisi, padahal notasi acuan hanya memuat dua nilai durasi, yaitu empat satuan
kisi sebanyak 48 not dan delapan satuan kisi sebanyak 21 not. Not-not pendek
tersebut merupakan penggalan hasil transkripsi. Temuan ini
sejalan dengan karakteristik AMT yang telah dikenal, yaitu bahwa deteksi waktu
akhir jauh lebih sulit daripada deteksi waktu awal.

Pengukuran tambahan menunjukkan adanya pergeseran waktu awal yang bersifat
sistematis sebesar +34,18 ms dengan konsentrasi fase 0,784, terhadap satuan kisi
sebesar 115,38 ms. Mengompensasi pergeseran tersebut menurunkan galat penyelarasan
kisi dari 35,38 ms menjadi 14,64 ms, namun hanya menaikkan F-measure sebesar 0,6
poin persen, sebab toleransi 50 ms pada mir_eval telah menampung pergeseran
tersebut. Kuantisasi karenanya dijalankan tanpa kompensasi, sesuai definisi
algoritmanya.

### E. Sumbangan Deteksi Pengulangan

Sumbangan mekanisme deteksi pengulangan diukur dengan menjalankan sistem dua kali
atas sampel yang sama, dengan dan tanpa mengaktifkan mekanisme tersebut. Hasilnya
disajikan pada Tabel IX.

**Tabel IX. Sumbangan deteksi pengulangan**

| Besaran | Tanpa LZ77 | Dengan LZ77 | Penghematan |
|---|---|---|---|
| Jumlah token | 73 | 51 | **30,14%** |
| Ukuran muatan | 205 bita | 142 bita | 30,73% |
| Jumlah basa | 1.818 | 1.818 | **0,00%** |

Terdapat ketimpangan yang mencolok. Peringkasan pengulangan memangkas 30,14%
token dan 30,73% muatan, tetapi **tidak menghemat satu basa pun**.

Penyebabnya adalah granularitas kode Reed–Solomon. Kata sandi RS(255, 223)
memiliki panjang tetap, dan muatan yang lebih pendek daripada 223 bita tetap
diisi nol hingga memenuhi satu kata sandi utuh sebelum difragmentasi menjadi
oligo. Muatan sebesar 142 bita maupun 205 bita sama-sama menempati satu kata
sandi, sehingga keduanya menghasilkan sembilan oligo dan 1.818 basa yang sama.

Konsekuensi lanjutannya bersifat paradoksal. Ketika ambang onset dinaikkan
sehingga muatan mengecil dari 159 menjadi 142 bita, kerapatan efektif yang
terukur justru **turun** dari 0,6997 menjadi 0,6249 bit per basa, sebab
penyebutnya tertahan pada nilai yang sama. Selama lantai granularitas ini
berlaku, kompresi yang lebih baik menurunkan kerapatan efektif yang terukur,
yakni berlawanan arah dengan besaran yang hendak diukur.

Temuan ini merupakan keterbatasan rancangan yang penting: pada sampel berdurasi
pendek, sumbangan mekanisme inti yang diusulkan penelitian ini menjadi tidak
terlihat sama sekali pada metrik jumlah basa. Karena itu, sumbangan deteksi
pengulangan dilaporkan pada **tataran token**, yang mencerminkan mekanismenya
sendiri, dan bukan pada tataran basa, yang mencampurkannya dengan pembulatan
kata sandi. Perbaikan yang lazim untuk persoalan ini adalah penggunaan kode
Reed–Solomon terpendek, yaitu mengisi nol hanya pada tahap pengodean tanpa ikut
mensintesisnya, dan dicatat sebagai pekerjaan lanjutan.

### F. Waktu Proses

Waktu proses untuk audio berdurasi 23,54 detik adalah 12,91 detik pada jalur
encoding dan 0,19 detik pada jalur decoding, atau 13,16 detik secara keseluruhan.
Sebagian besar waktu encoding dihabiskan pada pemuatan model transkripsi, yang
bersifat sekali per proses. Ketimpangan antara kedua jalur mencerminkan bahwa
seluruh beban komputasi berat berada pada tahap transkripsi, sedangkan pembacaan
balik hanyalah aritmetika bilangan bulat.

### G. Kalibrasi Ambang Onset

Pada nilai bawaan pustaka sebesar 0,5, sistem menghasilkan precision 0,8442
berhadapan dengan recall 0,9420, yakni ketimpangan yang menandakan ambang
deteksi terlalu rendah. Penelusuran ambang disajikan pada Tabel X.

**Tabel X. Penelusuran ambang onset**

| Ambang onset | Jumlah not | Precision | Recall | F-measure |
|---|---|---|---|---|
| 0,30 | 122 | 0,5246 | 0,9275 | 0,6702 |
| 0,50 | 77 | 0,8442 | 0,9420 | 0,8904 |
| **0,60** | 73 | 0,9041 | 0,9565 | **0,9296** |
| 0,70 | 71 | 0,9155 | 0,9420 | 0,9286 |
| 0,80 | 63 | 0,9048 | 0,8261 | 0,8636 |

Pada ambang 0,6, precision dan recall meningkat bersamaan. Peningkatan recall
yang menyertai kenaikan ambang tampak berlawanan dengan pertukaran yang lazim,
namun dapat dijelaskan oleh sifat pencocokan mir_eval yang bersifat satu lawan
satu: sebuah not palsu dapat merebut pasangan yang seharusnya diperoleh not yang
benar, sehingga membuang not palsu memperbaiki kedua metrik sekaligus.

Penelusuran serupa atas parameter durasi not minimum menunjukkan bahwa nilai 60
ms sudah optimal; menaikkannya menurunkan F-measure pada seluruh ambang.

---

## VI. KETERBATASAN

1. **Jumlah sampel.** Seluruh angka berasal dari satu sampel uji. Hasil ini
   membuktikan bahwa pipeline berfungsi dan memenuhi batasan biologis secara
   terverifikasi, tetapi belum memungkinkan generalisasi. Korpus penuh yang
   bervariasi pada durasi, kerapatan not, dan derajat pengulangan sedang
   disusun.

2. **Kalibrasi parameter.** Ambang onset sebesar 0,6 ditetapkan melalui
   penelusuran pada sampel yang sama dengan yang digunakan untuk melaporkan
   hasil. Prosedur ini berisiko overfitting dan tidak dapat dipertahankan
   sebagai penetapan parameter yang independen. Kalibrasi ulang atas korpus
   penuh diperlukan, dan penelusurannya harus dilaporkan sebagai bagian dari
   hasil.

3. **Tanpa penyuntikan galat.** Tahap sintesis, penyimpanan, dan sequencing
   disimulasikan tanpa menyuntikkan galat biologis. Kemampuan koreksi
   Reed–Solomon diverifikasi secara terpisah melalui pengujian unit yang
   membuktikan koreksi hingga 16 galat simbol per kata sandi, namun ketahanan
   sistem terhadap profil galat yang sesungguhnya belum diukur.

4. **Audio hasil sintesis perangkat lunak.** Audio yang dihasilkan DAW jauh
   lebih bersih daripada rekaman akustik, sehingga akurasi transkripsi yang
   dilaporkan merupakan batas atas.

5. **Batas pengalamatan oligo.** Medan indeks oligo selebar dua bita dapat
   mengalamati 65.536 oligo, setara sekitar 1,59 MiB muatan atau 69 detik audio
   pada laju bit 192 kbps. Untuk sampel yang lebih panjang, jalur pembanding B1
   tidak dapat dibangun sebagai oligo, sehingga jumlah basanya dihitung secara
   analitis. Perhitungan tersebut eksak, dan jalur pembanding memang tidak
   pernah didekode, tetapi keterbatasan ini perlu dinyatakan.

6. **Informasi yang tidak dipulihkan.** Skema token tidak menyimpan velocity
   maupun kanal instrumen, sehingga dinamika permainan hilang dan seluruh
   instrumen tergabung menjadi satu jalur pada notasi hasil rekonstruksi. Hal
   ini tidak memengaruhi metrik tataran not, yang mencocokkan berdasarkan tinggi
   nada dan waktu saja.

7. **Penempatan MusicXML.** MusicXML merupakan format notasi tertulis sehingga
   setiap durasi harus dapat dinyatakan sebagai nilai not. Keluaran transkripsi
   yang bersifat kontinu terhadap waktu karenanya tidak dapat dinotasikan
   sebagaimana adanya, dan notasi hanya dimungkinkan pada atau sesudah tahap
   kuantisasi. MusicXML ditempatkan di luar jalur data utama sebagai artefak
   keluaran, sehingga tidak menambah tahap lossy pada pipeline.
