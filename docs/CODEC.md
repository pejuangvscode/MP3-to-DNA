# Codec DNA

Dokumen ini menjelaskan cara kerja codec yang mengubah aliran bita menjadi sekuens DNA dan sebaliknya. Seluruh angka di sini dihasilkan dengan menjalankan kode yang sesungguhnya, bukan ditulis tangan, sehingga bisa Anda verifikasi ulang.

Codec ini berdiri sendiri dan tidak tahu apa-apa soal musik. Masukannya bita, keluarannya berkas FASTA. Lapisan token yang menghasilkan bita itu dijelaskan terpisah.

---

## 1. Contoh kecil yang bisa dicek tangan

Sebelum menelusuri jejak lengkap, dua mekanisme intinya cukup kecil untuk diperiksa manual.

### Rotating code

Tabel rotasinya 4 baris kali 3 kolom. Baris dipilih berdasarkan basa sebelumnya, kolom berdasarkan nilai trit.

| Basa sebelumnya | Trit 0 | Trit 1 | Trit 2 |
|---|---|---|---|
| A | C | G | T |
| C | G | T | A |
| G | T | A | C |
| T | A | C | G |

Petakan trit `[0, 1, 2]` dengan basa awal `A`:

```
A + trit 0 → C        baris A, kolom 0
C + trit 1 → T        baris C, kolom 1
T + trit 2 → G        baris T, kolom 2
```

Hasilnya `CTG`. Perhatikan tidak ada basa yang berulang, dan itu berlaku otomatis: setiap baris tabel tidak pernah memuat basa penunjuk barisnya sendiri.

Membaliknya sama mudahnya. Dengan mengetahui basa sebelumnya dan basa sekarang, nilai trit adalah posisi kolomnya:

```
A → C  posisi 0
C → T  posisi 1
T → G  posisi 2        hasilnya [0, 1, 2]
```

### Konversi ke basis tiga

Sama seperti mengubah bilangan ke basis apa pun, yaitu bagi berulang dan ambil sisanya. Contoh dengan bilangan 100:

```
100 ÷ 3 = 33 sisa 1
 33 ÷ 3 = 11 sisa 0
 11 ÷ 3 =  3 sisa 2
  3 ÷ 3 =  1 sisa 0
  1 ÷ 3 =  0 sisa 1

dibaca terbalik → 10201
```

Periksa: 1×81 + 0×27 + 2×9 + 0×3 + 1×1 = 81 + 18 + 1 = 100. ✓

Codec melakukan hal yang persis sama, hanya bilangannya jauh lebih besar: satu blok 128 bit diperlakukan sebagai satu bilangan bulat, lalu dinyatakan sebagai 81 digit basis tiga.

---

## 2. Jejak lengkap encoding

Masukan yang dipakai sepanjang bagian ini adalah 20 bita berisi angka 0 sampai 19.

```
000102030405060708090a0b0c0d0e0f10111213
```

### Tahap 1 — Reed–Solomon

```
20 bita → 255 bita
```

Data diisi nol sampai mencapai 223 bita, lalu blok itu dikodekan menjadi 255 bita.

```
awal   000102030405060708090a0b0c0d0e0f10111213   data asli, utuh
       0000000000000000000000000000000000000000   pengisian nol
       ...
akhir  5099e8faf9b411410621961ae1dac5f94386387b   32 bita paritas
       4bdfafad380d31544d4f3c14
```

Perhatikan data aslinya muncul apa adanya di awal. RS(255, 223) bersifat *systematic*: data tidak diubah, paritas hanya ditempelkan di belakang. Ke-32 bita paritas itu yang memungkinkan koreksi hingga 16 galat simbol per kata sandi.

### Tahap 2 — Fragmentasi

255 bita dipecah menjadi potongan 29 bita, menghasilkan 9 potongan.

```
potongan 0: 000102030405060708090a0b0c0d0e0f10111213000000000000000000
```

Kenapa 29 dan bukan 32 akan jelas pada tahap berikutnya.

### Tahap 3 — Pengacakan

Potongan di-XOR dengan aliran pseudo-acak yang dibangkitkan SHA-256 dari indeks oligo dan penghitung seed.

```
data      000102030405060708090a0b0c0d0e0f10111213000000000000000000
keystream 8d62d26d5705f1b824e31bc191a0d1f40c24dfd18ac63cc23d0babaad5
          ────────────────────── XOR ──────────────────────
hasil     8d63d06e5300f7bf2cea11ca9daddffb1c35cdc28ac63cc23d0babaad5
```

Lihat sembilan bita terakhir. Datanya bernilai nol semua, sehingga hasil XOR-nya persis sama dengan keystream-nya. Itu memperlihatkan apa yang sebenarnya dikerjakan tahap ini: **daerah data yang seragam diganti oleh sesuatu yang tampak acak.** Tanpa itu, deretan nol akan dipetakan menjadi pola basa yang berulang dan kandungan GC-nya menyimpang jauh dari 50%.

XOR bersifat involutif, sehingga fungsi yang sama dipakai untuk mengacak dan menyahacak.

### Tahap 4 — Perakitan muatan

```
indeks    0000                                          2 bita
seed      00                                            1 bita
data      8d63d06e5300f7bf2cea11ca9daddffb1c35cdc28a…  29 bita
                                                      ──────────
                                                       32 bita
```

Inilah alasan potongannya 29 bita: 3 bita tersita untuk indeks dan penghitung seed, menyisakan 29 bita untuk data dalam muatan 32 bita.

**Indeks dan penghitung seed sengaja tidak diacak.** Decoder harus membacanya lebih dulu untuk bisa menyusun ulang seed, dan tanpa itu XOR tidak bisa dibalik. Kalau ikut diacak, muatannya hilang selamanya.

### Tahap 5 — Bit ke trit

Muatan 32 bita dipandang sebagai dua blok 16 bita. Setiap blok jadi satu bilangan bulat besar, lalu dinyatakan dalam basis tiga.

```
blok 0    0000008d63d06e5300f7bf2cea11ca9d
sebagai bilangan  11202061908045527213659529530013

81 trit   000000000000000100210020212122211200102000121212000121211002020101122012011210222
```

Lima belas trit pertama bernilai nol karena tiga bita pertama muatan memang nol — indeks 0 dan penghitung seed 0 untuk oligo pertama.

Konversi ini sah karena 3⁸¹ lebih besar daripada 2¹²⁸, sementara 3⁸⁰ masih lebih kecil. Delapan puluh satu adalah jumlah trit minimum yang cukup.

### Tahap 6 — Rotating code

Setiap trit jadi satu basa, dimulai dari basa terakhir primer maju, yaitu `A`.

```
A + 0 → C    C + 0 → G    G + 0 → T    T + 0 → A
A + 0 → C    C + 0 → G    G + 0 → T    T + 0 → A
```

Delapan trit pertama semuanya nol, sehingga rotasinya berputar melalui siklus `C G T A` berulang:

```
CGTACGTACGTACGTCGTGACGCGCTGATGCTCACGACAC ...
```

Pola berulang di awal itu wajar, bukan cacat. Ia hanya mencerminkan bita header yang memang bernilai nol, dan kebetulan siklus `CGTA` sendiri sudah berkandungan GC 50% sehingga tidak merugikan.

Panjang homopolymer maksimum pada 162 basa muatan ini: **1**. Dijamin, bukan kebetulan.

### Tahap 7 — Penapisan GC dan primer

```
GC muatan  0,4938
GC oligo   0,4950     rentang yang disyaratkan 0,40–0,60  ✓
```

Karena sudah di dalam rentang, tidak perlu pengacakan ulang. Primer lalu ditempelkan di kedua ujung.

Perhatikan sambungannya: primer maju berakhir dengan `A`, muatan dimulai dengan `C`. Berbeda, jadi sambungan itu pun bebas homopolymer — memang itu tujuannya memilih basa terakhir primer sebagai basa awal rotasi.

---

## 3. Anatomi oligo

```
ACGTAGCTAGCATGCATCGA CGTACGTACGTACGTCGTGACG…CAC TGCATCGATCGTACGATGCA
└────── 20 nt ──────┘ └──────── 162 nt ────────┘ └────── 20 nt ──────┘
    primer maju              muatan                  primer mundur

                      ┌──────── muatan membawa ────────┐
                       2 bita indeks
                       1 bita penghitung seed
                      29 bita data
                      ──────────────────────
                      32 bita = 256 bit = 2 blok × 81 trit = 162 basa

total 202 nt
```

Untuk 20 bita masukan tadi, hasil akhirnya **9 oligo, 1.818 basa**.

---

## 4. Decoding

Kebalikan persis, dan tidak memerlukan apa pun selain berkas FASTA.

| Langkah | Operasi |
|---|---|
| 1 | Baca rekaman FASTA |
| 2 | Pangkas 20 basa di kedua ujung, sisakan 162 nt |
| 3 | Petakan basa jadi trit lewat tabel rotasi terbalik |
| 4 | Baca 81 trit sebagai bilangan basis tiga, kembalikan jadi 16 bita |
| 5 | Baca indeks dan penghitung seed dari tiga bita pertama yang tidak teracak |
| 6 | Susun ulang seed, balik XOR |
| 7 | Urutkan oligo menurut indeksnya sendiri, bukan urutan di berkas |
| 8 | Decode Reed–Solomon, buang paritas |

Hasilnya:

```
pulih   000102030405060708090a0b0c0d0e0f10111213
masukan 000102030405060708090a0b0c0d0e0f10111213
identik ✓
```

Langkah 7 penting dan mudah terlewat. Pada penyimpanan DNA yang sesungguhnya, oligo mengambang di dalam larutan **tanpa urutan fisik**. Itu sebabnya setiap oligo harus membawa alamatnya sendiri, dan itu pula sebabnya 2 bita muatan dikorbankan untuk indeks.

Panjang aliran ter-RS dipulihkan sebagai kelipatan 255 terbesar yang tidak melampaui hasil penyusunan. Ini sahih karena oligo terakhir diisi nol, sehingga hasil penyusunan melampaui panjang sebenarnya kurang dari 29 bita, dan hanya satu kelipatan 255 yang bisa berada dalam rentang sesempit itu.

---

## 5. Sifat yang dijamin

**Homopolymer.** Dijamin oleh konstruksi rotating code, bukan oleh penapisan. Tidak ada satu pun basa yang boleh sama dengan pendahulunya, sehingga muatan mustahil memuat pengulangan. Nilai maksimum untuk oligo utuh adalah 2, dan itu hanya bisa terjadi di satu tempat: sambungan muatan ke primer mundur, karena basa terakhir muatan bergantung data sementara primer mundur bersifat tetap. Batasan yang disyaratkan adalah tidak lebih dari 3, jadi masih longgar.

**Kandungan GC.** Dipenuhi oleh pengacakan, dengan penapisan hanya sebagai jaring pengaman. Pada pengujian atas enam masukan ekstrem — termasuk seluruh bita nol dan seluruh bita 0xFF — **tidak satu pun oligo memerlukan pengacakan ulang**.

**Keterulangan.** Masukan yang sama menghasilkan sekuens yang identik bita demi bita, karena aliran pengacakan diturunkan dari SHA-256 dan bukan dari pembangkit acak bawaan bahasa yang alirannya tidak dijamin stabil antarversi.

**Lossless.** Bita yang masuk sama persis dengan bita yang keluar. Sifat ini diverifikasi melalui pencocokan ringkasan SHA-256, bukan diasumsikan: `encode` menuliskan manifes berisi panjang dan ringkasan muatan di sebelah berkas FASTA, dan `verify_lossless` men-decode ulang lalu membandingkannya.

---

## 6. Kenapa algoritmanya dipilih

### Kenapa harus dipecah jadi oligo pendek

Ini bukan pilihan, melainkan paksaan kimia. Sintesis DNA menambahkan basa satu per satu, dan efisiensi penggabungan per tahap tidak pernah mencapai seratus persen — pada kimia fosforamidit berkisar 95% sampai 99,5%. Perolehan untaian utuh sepanjang L basa karenanya menurun secara eksponensial, mengikuti η^(L−1):

| Efisiensi per basa | 100 nt | 200 nt | 300 nt | 1.000 nt |
|---|---|---|---|---|
| 99,0% | 37,0% | 13,5% | 5,0% | ~0% |
| 99,5% | 60,9% | 36,9% | 22,3% | 0,7% |
| 99,9% | 90,6% | 82,0% | 74,1% | 36,8% |

Pada 1.000 basa, bahkan efisiensi 99,5% hanya menyisakan 0,7% untaian utuh. Menyimpan satu berkas sebagai satu untai panjang praktis mustahil. Karena itu data harus dipecah, dan pemecahan itulah yang memunculkan kebutuhan akan indeks dan primer.

### Kenapa Reed–Solomon, bukan fountain code

Keduanya lazim dipakai pada penyimpanan DNA dan keduanya sah. Perbedaannya pada apa yang ditangani.

Reed–Solomon adalah **kode blok**: jumlah kata sandinya tetap, dan ia kuat menangani substitusi simbol. Fountain code dapat membangkitkan untaian berkode dalam jumlah tak terbatas, sehingga unggul ketika sebagian untaian hilang sama sekali dan Anda hanya bisa mengumpulkan subset acaknya.

Penelitian ini memilih Reed–Solomon karena tiga alasan. Pertama, penelitian ini **tidak menyuntikkan galat**, sehingga keunggulan fountain code dalam menghadapi kehilangan untaian tidak akan terukur sama sekali. Kedua, redundansinya tetap dan dapat dihitung persis, sehingga jumlah basa dapat diprediksi dari ukuran muatan — sifat yang penting karena jumlah basa justru objek pengukuran penelitian ini. Ketiga, RS jauh lebih sederhana dan sudah tersedia sebagai pustaka matang.

### Kenapa rotating code, bukan skema yang lebih rapat

Inilah keputusan yang paling menentukan bentuk seluruh codec, dan konsekuensinya paling mahal.

Rotating code menjamin kepatuhan homopolymer **secara konstruksi**: karena basa berikutnya selalu dipilih berbeda dari basa sebelumnya, pengulangan mustahil terbentuk. Tidak ada kasus tepi, tidak ada penapisan, tidak ada kemungkinan gagal.

Harganya adalah kerapatan. Bandingkan kapasitas kanal untuk berbagai batas panjang homopolymer:

| Batas homopolymer | Kapasitas |
|---|---|
| 1 (yang diberlakukan rotating code) | 1,5850 bit/basa |
| 2 | 1,9227 bit/basa |
| **3 (yang sesungguhnya disyaratkan)** | **1,9824 bit/basa** |
| tanpa batas | 2,0000 bit/basa |

Batasan biologis hanya menuntut homopolymer maksimum tiga basa, yang kapasitasnya 1,98 bit per basa. Rotating code memberlakukan batas satu basa, yang kapasitasnya 1,58. Selisih **sekitar 0,40 bit per basa itu tidak dimanfaatkan** — dan tabel di atas juga menunjukkan bahwa rotating code sebenarnya sudah optimal terhadap batasan yang diberlakukannya sendiri, sebab 1,5850 persis sama dengan kapasitas untuk L=1.

Skema mutakhir seperti Yin–Yang codec, HEDGES, dan DNA-Aeon mencapai kerapatan jauh lebih dekat ke kapasitas. Yin–Yang bahkan memetakan dua bit biner langsung ke satu nukleotida tanpa konversi basis sama sekali, sehingga tidak memerlukan trit.

Rotating code tetap dipilih karena pertanyaan penelitian ini adalah **penghematan dari penggantian representasi**, bukan dari kerapatan codec. Karena codec yang sama diterapkan pada seluruh jalur pembanding, selisih 0,40 bit itu saling meniadakan dan tidak membiaskan pengukuran efisiensi. Yang ditukar adalah kesederhanaan dan sifat jaminannya: rotating code cukup satu tabel 4×3 dan kepatuhannya dapat dibuktikan dalam satu kalimat.

### Kenapa harus ke trit

Konsekuensi langsung dari rotating code. Karena satu basa terlarang pada setiap posisi, hanya tersisa tiga pilihan, dan alfabet tiga simbol adalah basis tiga. Data biner karenanya harus dikonversi.

Trit bukan tujuan, melainkan akibat aritmetis dari memilih rotating code. Skema yang memetakan bit langsung ke basa tidak memerlukannya.

### Kenapa perlu diacak

Kandungan GC hasil pemetaan mengikuti distribusi nilai trit, dan distribusi itu mengikuti distribusi bit pada data. Data terstruktur seperti barisan token jauh dari seragam: banyak medan bernilai kecil, banyak nol, banyak pola berulang.

Tanpa pengacakan, keteraturan itu diteruskan ke sekuens basa dan kandungan GC bisa menyimpang jauh dari 50%. Contoh paling ekstrem ada pada pemetaan naif: deretan bita bernilai nol menghasilkan `AAAA…`, dan deretan 0xFF menghasilkan `TTTT…` dengan kandungan GC 0%.

XOR terhadap aliran pseudo-acak membuat distribusi bit mendekati seragam tanpa memandang struktur data aslinya, sehingga kandungan GC memusat di sekitar 50% dengan sendirinya.

### Kenapa SHA-256, bukan pembangkit acak bawaan

Karena syarat keterulangan. Masukan yang sama harus menghasilkan sekuens yang identik, dan itu menuntut generator yang **ditetapkan oleh algoritma, bukan oleh pustaka**. Aliran keluaran `random` pada Python tidak dijamin stabil antarversi, sehingga pemutakhiran interpreter dapat mengubah seluruh sekuens yang dilaporkan penelitian ini tanpa satu baris kode pun berubah.

SHA-256 dalam mode pencacah bersifat baku, terdefinisi persis, dan menghasilkan aliran yang sama di mesin mana pun selamanya.

### Kenapa penapisan pakai rejection sampling

Karena pengacakan bersifat probabilistik, bukan jaminan. Kandungan GC memusat di sekitar 50%, tetapi tidak ada yang mencegah satu oligo kebetulan jatuh di luar rentang.

Rejection sampling menanganinya dengan cara paling sederhana: kalau gagal, ganti seed dan coba lagi. Penghitung seed disimpan di dalam muatan sehingga decoder tahu seed mana yang akhirnya dipakai. Pada praktiknya tingkat penolakannya nol, sehingga tahap ini berperan sebagai jaring pengaman dan bukan mekanisme utama.

---

## 7. Kenapa angkanya begitu

| Nilai | Alasan |
|---|---|
| RS(255, 223) | 255 adalah kata sandi terpanjang untuk GF(2⁸), karena satu simbol tepat satu bita dan medannya beranggotakan 256 elemen. Sisa 32 bita paritas memberi koreksi 16 galat simbol, dengan overhead 12,55% |
| Blok 128 bit | Efisiensi konversi ke trit 99,7%. Blok lebih kecil boros: per bita hanya 84,1%, per 32 bit 96,1% |
| 81 trit | Minimum yang memenuhi 3⁸¹ ≥ 2¹²⁸. Delapan puluh trit tidak cukup, karena 3⁸⁰ < 2¹²⁸ |
| Muatan 32 bita | Tepat dua blok 128 bit, sehingga tidak ada bit tersisa yang perlu ditangani khusus |
| Muatan 162 nt | 2 × 81 trit, satu basa per trit |
| Indeks 2 bita | Mengalamati 65.536 oligo, setara sekitar 1,59 MiB muatan |
| Penghitung seed 1 bita | Cukup untuk 256 percobaan pengacakan ulang, jauh melampaui kebutuhan |
| Data 29 bita | Sisa dari 32 setelah indeks dan penghitung seed |
| Primer 20 nt | Kompromi: lebih panjang membuat suhu leleh PCR terlalu tinggi dan makin banyak basa terbuang, lebih pendek mengurangi spesifisitas dan keragaman alamat. Konvensi membatasi di bawah 25 nt |
| Total 202 nt | Panjang yang dapat disintesis andal lazimnya terbatas 200 nt, sedangkan produk komersial mencapai sekitar 300 nt. Jadi 202 nt tepat di atas ambang keandalan namun jauh di bawah batas atas |
| GC 40–60% | Pasangan G–C terikat tiga ikatan hidrogen, A–T hanya dua. Untaian terlalu kaya GC sulit dipisahkan saat denaturasi, terlalu miskin GC rentan hilang terbaca |

### Plafon kerapatan efektif

Seluruh angka di atas berkumpul menjadi satu batas yang tidak bisa dilampaui sistem ini:

```
1,5802  kerapatan skema, bit per basa
  × 162/202   porsi muatan terhadap panjang oligo, primer tidak membawa data
  ×  29/32    porsi data terhadap muatan, indeks dan seed tidak membawa data
  ×  0,87451  laju kode Reed–Solomon
  ─────────
= 1,0044 bit per basa
```

Bandingkan dengan kapasitas kanal 1,982 bit per basa. Separuh kapasitas hilang, dan tabel di atas menunjukkan persis ke mana perginya: sekitar 0,40 bit ke rotating code, 20% ke primer, 9% ke indeks dan seed, serta 12,5% ke paritas.

### Satu keterbatasan yang timbul dari angka-angka ini

Karena kata sandi RS berpanjang tetap 255 bita, **muatan sekecil apa pun tetap membayar satu kata sandi penuh**. Contoh di dokumen ini hanya 20 bita masukan, tetapi tetap menghasilkan 9 oligo dan 1.818 basa — sama persis dengan yang dihasilkan muatan 223 bita.

Efeknya paling terasa pada berkas pendek, dan pada sampel uji penelitian ini bahkan sempat menutupi sepenuhnya sumbangan mekanisme peringkasan pengulangan: token berkurang 30,14% sementara jumlah basa tidak berkurang sama sekali. Perbaikan yang lazim adalah kode Reed–Solomon terpendek, yaitu mengisi nol hanya pada tahap pengodean tanpa ikut mensintesisnya.
