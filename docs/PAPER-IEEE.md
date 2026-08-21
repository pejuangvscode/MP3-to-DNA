# Pengembangan Codec Konversi File Musik Digital ke Susunan Rantai DNA Berbasis Transkripsi dan Tokenisasi Notasi Otomatis

**Teofilus Satria Rada Insani**
Faculty of Artificial Intelligence and Data Science
Universitas Pelita Harapan
Tangerang, Indonesia
01082230015@student.uph.edu

> **Catatan penyuntingan (hapus sebelum submit).** Blok penulis pada draf sebelumnya tertulis dua kali; di sini ditulis sekali. Nama pembimbing sebagai penulis kedua perlu ditambahkan sesuai ketentuan konferensi. Seluruh angka pada Seksi V dihasilkan oleh perangkat lunak yang menyertai makalah ini dan dapat direproduksi. **Hasil berasal dari satu sampel uji**, sehingga disajikan sebagai hasil awal atas prototipe yang berfungsi, bukan sebagai evaluasi.

---

## Abstrak

Biaya penyimpanan data berbasis DNA berbanding lurus dengan jumlah basa nitrogen yang harus disintesis, sehingga setiap basa yang dihemat berdampak langsung pada kelayakan ekonominya. Pendekatan konvensional menyimpan rekaman musik sebagaimana berkas biner lain, yaitu dengan memetakan deretan bita berkas audio secara langsung menjadi nukleotida. Cara ini tidak efisien untuk musik: berkas MP3 telah berada dekat dengan entropinya sendiri karena tahap akhir pengodeannya berupa Huffman coding, sehingga tidak dapat dimampatkan lebih lanjut, sementara struktur musikal berupa nada, durasi, dan pengulangan motif justru hilang ketika musik disimpan sebagai deretan amplitudo. Makalah ini mengusulkan dan mengimplementasikan pipeline yang mengubah representasi musik sebelum pengodean: rekaman ditranskripsi menjadi notasi melalui transkripsi musik otomatis, dikuantisasi terhadap kisi ritmis, diringkas menjadi token fitur dengan deteksi pengulangan berbasis LZ77 pada tataran token, lalu dipetakan menjadi sekuens FASTA yang memenuhi batasan biologis melalui rotating code dan diperkuat kode Reed–Solomon. Prototipe berhasil dibangun dan diuji atas satu sampel berdurasi 23,5 detik. Pembacaan balik terbukti lossless secara identik-bita, seluruh oligo memenuhi batasan kandungan GC 40–60% dan panjang homopolymer tanpa satu pun penolakan pada tahap penapisan, dan skema token menghemat 66,67% basa dibandingkan pengodean berkas MIDI hasil transkripsi yang sama. Akurasi rekonstruksi pada tataran not mencapai F-measure 0,9296. Dekomposisi galat menunjukkan kehilangan informasi terlokalisasi pada tahap transkripsi, sementara tahap penyimpanan DNA tidak menyumbang galat sama sekali. Ditemukan pula bahwa granularitas kata sandi Reed–Solomon dapat menutupi sumbangan peringkasan pengulangan pada sampel berdurasi pendek.

**Kata kunci** — penyimpanan data DNA, transkripsi musik otomatis, constrained coding, Reed–Solomon, preservasi digital, kompresi simbolik

---

## I. PENDAHULUAN

Saat ini, data digital mengalami pertumbuhan secara eksponensial tetapi tidak diimbangi oleh kapasitas dan ketahanan media penyimpanan yang memadai. Hard disk dan pita magnetik memiliki masa pakai yang relatif pendek sehingga data harus disalin ulang secara berkala agar tetap dapat diakses, dan proses ini membutuhkan energi, waktu, serta pemeliharaan yang terus-menerus [1]. Kondisi ini menjadi penting bagi arsip yang berhubungan dengan kekayaan kultural, termasuk rekaman musik yang nilainya justru bertambah seiring waktu, namun karena degradasi material dan fungsi keberadaannya kini terancam.

Rekaman musik lawas menghadapi ancaman pada dua sisi. Media fisik tempat rekaman tersimpan mengalami degradasi material, sementara format berkas dan perangkat pembacanya menjadi usang dan ditinggalkan. Akibatnya, sebagian kekayaan musik dunia semakin sulit dicari dan dapat hilang sebelum sempat dialihmediakan. Oleh karena itu dibutuhkan medium penyimpanan yang padat, awet selama berabad-abad pada suhu ruang, dan tidak bergantung pada keusangan teknologi pembacanya.

DNA merupakan salah satu kandidat yang memenuhi kebutuhan tersebut. Sebagai pembawa informasi genetik alami, DNA memiliki densitas penyimpanan yang jauh melampaui media elektronik dan dapat bertahan ribuan tahun bila disimpan dengan benar [1], [2]. Dalam konteks musik, kelayakan DNA untuk arsip audio bukan sekadar asumsi. Pada perhelatan Montreux Jazz Festival, lagu *Smoke on the Water* dan *Tutu* berhasil di-encode ke dalam DNA dan dibaca kembali dengan akurasi penuh melalui proyek Twist Bioscience bersama Microsoft dan University of Washington, dan kedua rekaman tersebut menjadi bagian dari program UNESCO Memory of the World [3]. Secara teknis, musik juga berhasil disimpan langsung ke dalam DNA, seperti pada tema utama gim Nintendo *Super Mario Bros.* (1985) melalui sintesis enzimatik [4]. Singkatnya, preservasi musik berbasis DNA telah terbukti dapat dilakukan.

Meskipun demikian, sebagian besar pendekatan memperlakukan berkas musik sebagaimana berkas biner lain: deretan bita MP3 langsung dikonversi menjadi urutan nukleotida. Karena biaya sintesis DNA dihitung per nukleotida dan tergolong mahal [5], strategi semacam ini menghasilkan muatan yang besar dan kurang efisien secara ekonomi. Persoalannya diperberat oleh sifat berkas MP3 itu sendiri: tahap akhir pengodean MP3 berupa Huffman coding, yang menghasilkan kode dengan redundansi minimum, sehingga bita penyusunnya sudah berada dekat dengan entropinya sendiri dan praktis tidak dapat dimampatkan lebih lanjut oleh algoritma kompresi umum. Penghematan karenanya tidak dapat diperoleh dengan memampatkan berkas audio, melainkan hanya dengan mengganti representasinya.

Padahal musik memiliki struktur internal berupa nada, durasi, dan pengulangan motif, yang membuka peluang representasi jauh lebih ringkas daripada gelombang audio mentahnya [6]. Redundansi pengulangan ini hanya dapat dimanfaatkan pada representasi simbolik: pada representasi audio, dua kemunculan frasa yang sama secara musikal hampir tidak pernah menghasilkan deretan amplitudo yang identik.

Makalah ini mengusulkan dan mengimplementasikan pemetaan token fitur MP3 sebagai alternatif. Alih-alih menyimpan sinyal audio, rekaman dilewatkan pada pipeline *from sound to sequence*: (1) sinyal ditranskripsi menjadi daftar not simbolik melalui transkripsi musik otomatis; (2) not dikuantisasi terhadap kisi ritmis berdasarkan tempo yang diketahui; (3) not terkuantisasi dikodekan menjadi barisan token berukuran tetap, dengan frasa berulang diringkas menjadi token rujukan; dan (4) barisan token dipetakan menjadi sekuens ATGC berformat FASTA yang mematuhi batasan biologis dan diperkuat kode koreksi galat.

Kontribusi makalah ini ada tiga. Pertama, kerangka pemetaan token yang menjembatani transkripsi musik otomatis dengan penyimpanan DNA sadar-constraint, suatu tautan yang belum tersedia pada literatur. Kedua, implementasi berfungsi beserta pengukuran awal atas efisiensi muatan basa, kepatuhan batasan biologis, dan akurasi rekonstruksi, dengan galat diuraikan menurut modul penyebabnya. Ketiga, temuan bahwa granularitas kata sandi kode koreksi galat dapat menutupi sumbangan mekanisme peringkasan pada sampel berdurasi pendek, yang berimplikasi pada cara efisiensi semacam ini seharusnya dilaporkan.

---

## II. KAJIAN LITERATUR

### A. Medium dan Landasan Teori Penyimpanan DNA

Tinjauan komprehensif oleh Dong dkk. [1] merangkum lanskap penyimpanan DNA, mulai dari sejarah perkembangannya, keunggulan densitas dan daya tahan, hingga tantangan teknis yang masih dihadapi, dan menegaskan bahwa profil galat serta kendala biokimia merupakan persoalan inti setiap skema pengodean. Dari sisi teori, Shomorony dan Heckel [2] memformalkan batas-batas informasi kanal penyimpanan DNA dengan memodelkan tiga karakteristik khasnya, yakni data tersebar pada banyak untai pendek yang tidak terurut, untai terkena derau, serta pembacaan dilakukan melalui pengambilan sampel acak. Landasan ini memberikan tolok ukur untuk menilai seberapa efisien suatu representasi dapat dirancang sebelum mencapai batas kapasitas kanal.

Konsekuensi praktis dari keandalan sintesis yang menurun secara eksponensial terhadap panjang untai adalah bahwa data harus dipecah menjadi banyak oligonukleotida pendek [5]. Pemecahan ini menuntut setiap oligo membawa indeks yang menyatakan posisinya serta sepasang primer sebagai tempat penempelan PCR, dan keduanya menempati ruang yang tidak membawa muatan data [7]. Benang merah dari karya-karya ini adalah bahwa efisiensi muatan dan keandalan pemulihan merupakan dua tujuan yang selalu harus diseimbangkan.

### B. Pengodean Berbasis Constraint dan Koreksi Galat

Urutan DNA yang stabil harus memenuhi sejumlah kendala biokimia, terutama kandungan GC yang dijaga pada kisaran 40–60% serta pembatasan panjang homopolymer, guna menekan galat selama sintesis dan pembacaan [8]. Press dkk. [9] memperkenalkan kode HEDGES yang memperbaiki galat insersi dan delesi sekaligus mengakomodasi kendala urutan, sehingga kepatuhan constraint dan koreksi galat dapat ditangani secara terpadu.

Sejumlah skema mutakhir menjadikan kepatuhan constraint sebagai bagian inheren proses pengodean, bukan sekadar penyaringan di akhir. Löchel dkk. [10] memanfaatkan representasi *chaos game* untuk membangun *code word* yang secara konstruktif memenuhi kendala kandungan GC, homopolymer, dan motif terlarang. Ping dkk. [11] mengusulkan *Yin–Yang codec* yang memetakan dua bit biner menjadi satu nukleotida melalui pasangan aturan komplementer. Cao dkk. [12] menempuh arah adaptif dengan menyesuaikan ambang constraint terhadap karakteristik muatan. Welzel dkk. [8] mengembangkan DNA-Aeon, skema *arithmetic coding* yang menghasilkan urutan sesuai definisi pengguna sambil mengoreksi seluruh tipe galat yang lazim.

Pendekatan yang lebih awal namun secara struktural relevan bagi penelitian ini adalah *rotating code* yang diperkenalkan Goldman dkk. [13]. Setiap simbol basis tiga dipetakan ke salah satu dari tiga nukleotida yang berbeda dari nukleotida sebelumnya, sehingga homopolymer tidak akan terbentuk sama sekali. Kerapatannya sebesar log₂3 ≈ 1,585 bit per basa berada di bawah kapasitas kanal untuk batasan homopolymer maksimum tiga basa yang bernilai sekitar 1,982 bit per basa, namun selisih tersebut merupakan harga yang dibayar bagi kesederhanaan dan jaminan kepatuhan secara konstruksi.

Aspek pemulihan sama pentingnya dengan pengodean. Preuss dkk. [14] merancang sistem penyimpanan berbasis pengodean kombinatorial *shortmer* lengkap dengan kode Reed–Solomon dua dimensi, sementara Schwarz dan Freisleben [15] mengembangkan metode pemulihan berbasis *fountain code* yang disesuaikan terhadap kanal DNA. Pelajaran kolektifnya adalah bahwa constraint sebaiknya dibangun langsung ke dalam pengodean dan dipadukan dengan koreksi galat, dan prinsip inilah yang diadopsi pada tahap pemetaan ATGC di sini.

### C. Dari Audio Menuju Representasi Simbolik dan Musik-ke-DNA

Agar token yang ringkas dapat diperoleh, rekaman audio harus lebih dahulu diubah menjadi notasi melalui transkripsi musik otomatis. Benetos dkk. [6] memberikan tinjauan menyeluruh atas bidang ini, mencakup estimasi multipitch, deteksi onset dan offset, hingga penataan partitur, sekaligus menggarisbawahi tantangan transkripsi musik polifonik. Sebagai realisasi praktis, Bittner dkk. [16] memperkenalkan basic-pitch, model yang ringan dan agnostik terhadap instrumen, mampu menghasilkan transkripsi polifonik tanpa menuntut sumber daya komputasi besar. Model semacam inilah yang memungkinkan tahap transkripsi berjalan praktis di luar lingkungan komputasi besar.

Perlu ditegaskan bahwa keluaran transkripsi otomatis bersifat tidak sempurna. Terdapat tiga bentuk galat: not yang seharusnya ada tidak terdeteksi, not yang sebenarnya tidak ada justru terdeteksi karena harmonik nada lain keliru dianggap sebagai nada tersendiri, serta not terdeteksi dengan tinggi nada yang benar namun waktu awal atau durasinya bergeser [6]. Ketiganya menjadikan setiap pipeline yang berangkat dari transkripsi otomatis bersifat lossy, tanpa memandang seberapa sempurna tahap-tahap sesudahnya.

Pada sisi pemetaan musik ke DNA, Antkowiak dkk. [17] melakukan encoding berkas notasi MusicXML sebuah komposisi ke dalam untai DNA alih-alih menyimpan rekaman audionya. Lee dkk. [4] mendemonstrasikan penyimpanan melodi dengan menyandikan tiap nada beserta nomor nada, oktaf, urutan, dan durasinya. Pendekatan serupa diperdalam Kiryanova dkk. [18], yang mengusulkan metode pengodean melodi dengan memperhitungkan durasi dan tonalitas serta mencakup rentang tujuh oktaf, dan menunjukkan efisiensi lebih tinggi dibandingkan pendekatan berbasis algoritme Huffman. Ketiga karya ini menegaskan bahwa representasi simbolik musik dapat dipetakan ke nukleotida secara terstruktur, tetapi seluruhnya bertolak dari notasi yang dimasukkan secara simbolik, bukan dari rekaman audio.

### D. Redundansi Pengulangan dan Celah Penelitian

Musik pada umumnya bersifat repetitif: sebuah komposisi tersusun dari motif yang diulang dan dikembangkan, sehingga struktur seperti bait dan refrein pada dasarnya merupakan pengulangan. Algoritma LZ77 [19] memanfaatkan redundansi semacam ini dengan menggantikan barisan berulang oleh rujukan balik berupa pasangan jarak dan panjang salinan. Penerapan konvensionalnya bekerja pada sekuens bita, namun prinsip yang sama berlaku pada barisan simbol apa pun, termasuk barisan token yang merepresentasikan not.

Dari ketiga sudut di atas tampak adanya kesenjangan. Karya yang menyimpan musik dalam bentuk simbolik masih bertolak dari notasi yang dimasukkan secara manual [4], [17], [18], sedangkan perkembangan pengodean DNA mutakhir berfokus pada efisiensi dan keandalan untuk data generik [8], [11], [14], [15]. Kemajuan transkripsi musik otomatis [6], [16] dan pengodean patuh-constraint [8], [10], [11] belum dipadukan menjadi satu alur utuh untuk musik nyata, dan belum ada yang mengukur secara kuantitatif keseimbangan antara penghematan basa yang diperoleh dan kesetiaan rekonstruksi yang dikorbankan. Penelitian ini menempati celah tersebut.

---

## III. PERANCANGAN SISTEM

### A. Arsitektur

Sistem dirancang sebagai pipeline modular dua arah. Alur encoding mengubah rekaman MP3 menjadi sekuens FASTA, sedangkan alur decoding merekonstruksi notasi MIDI dari sekuens tersebut. Tahap sintesis, penyimpanan, dan sequencing disimulasikan secara komputasional tanpa penyuntikan galat. Koreksi galat tetap disertakan karena redundansinya menyumbang pada jumlah basa yang menjadi objek pengukuran efisiensi.

Arsitektur bersifat berlapis, mencerminkan pembagian kode luar dan kode dalam yang lazim pada penyimpanan DNA: kode luar berupa Reed–Solomon bekerja pada tataran bita dan melindungi data lintas oligo, sedangkan kode dalam berupa constrained coding bekerja pada tataran basa dan menjamin kepatuhan batasan biologis di dalam satu oligo.

### B. Skema Token Fitur

Setiap not terkuantisasi direpresentasikan sebagai tiga besaran diskret, yaitu tinggi nada berupa nomor not MIDI, posisi kisi, dan durasi dalam satuan kisi. Barisan not kemudian dikodekan menjadi barisan token berukuran tetap. Sistem mengenali dua jenis token yang dibedakan oleh satu bit penanda: token not selebar 22 bit yang menyatakan sebuah not tunggal, dan token rujukan selebar 17 bit yang menyatakan pengulangan atas sekelompok token sebelumnya. Sebuah header selebar 32 bit dituliskan sekali di awal untuk menyimpan versi skema, tempo, resolusi kisi, dan jumlah token.

Waktu awal not tidak disimpan sebagai posisi mutlak melainkan sebagai selisih terhadap not sebelumnya. Pilihan ini bukan semata untuk memperkecil nilai yang disimpan, melainkan terutama untuk memastikan bahwa dua frasa musikal yang identik menghasilkan barisan token yang identik pula, tanpa memandang posisi kemunculannya. Sifat tersebut merupakan prasyarat mutlak bagi bekerjanya mekanisme deteksi pengulangan.

Pengulangan dideteksi melalui pencarian rujukan balik yang mengadaptasi prinsip LZ77 [19], namun bekerja pada barisan token alih-alih pada sekuens bita sehingga pencocokan berlangsung pada tataran musikal. Algoritma bersifat greedy dengan mengambil kecocokan terpanjang di dalam jendela geser sepanjang 1.024 token. Karena satu token rujukan selebar 17 bit sekurang-kurangnya menggantikan dua token not yang berukuran total 44 bit, setiap kecocokan yang ditemukan selalu menghasilkan penghematan.

### C. Pengodean DNA

Aliran bita hasil pemadatan token di-encode melalui enam tahap. Pertama, penyisipan redundansi Reed–Solomon [20] dengan konfigurasi RS(255, 223) atas GF(2⁸), yang mengoreksi hingga enam belas galat simbol per kata sandi. Kedua, fragmentasi menjadi oligo berukuran tetap. Ketiga, pengacakan isi oligo melalui operasi XOR terhadap aliran pseudo-acak, yang menghasilkan distribusi bit mendekati seragam sehingga kandungan GC memusat di sekitar 50%. Keempat, konversi setiap blok 128 bit menjadi 81 trit, dengan efisiensi 1,5802 bit per trit atau 99,7% terhadap kapasitas trit. Kelima, pemetaan trit menjadi basa melalui tabel rotasi *rotating code*, yang menjamin muatan bebas homopolymer secara konstruksi. Keenam, penapisan kandungan GC, di mana oligo yang berada di luar rentang diacak ulang dengan seed berbeda.

Struktur setiap oligo terdiri atas primer maju sepanjang 20 nt, muatan sepanjang 162 nt yang membawa 2 bita indeks, 1 bita penghitung seed, dan 29 bita data, serta primer mundur sepanjang 20 nt, sehingga total 202 nt. Panjang ini berada dalam rentang yang dapat disintesis secara andal. Basa pertama muatan dirotasikan terhadap basa terakhir primer maju agar sambungan keduanya juga bebas homopolymer.

---

## IV. IMPLEMENTASI

### A. Lingkungan dan Pustaka

Seluruh pipeline diimplementasikan dengan Python 3.11.3 dan dijalankan sepenuhnya secara lokal tanpa ketergantungan pada arsitektur cloud. Pustaka utama yang digunakan disajikan pada Tabel I.

**TABEL I. PUSTAKA YANG DIGUNAKAN**

| Komponen | Pustaka | Versi |
|---|---|---|
| Transkripsi musik otomatis | basic-pitch | 0.4.0 |
| Runtime model | TensorFlow (CPU) | 2.15.0 |
| Koreksi galat Reed–Solomon | reedsolo | 1.7.0 |
| Penulisan FASTA | biopython | 1.87 |
| Notasi MusicXML | music21 | 10.5.0 |
| Metrik transkripsi | mir_eval | 0.8.2 |
| Pemrosesan MIDI | pretty_midi | 0.2.11 |
| Dekode audio | soundfile | 0.14.0 |

Inferensi model dijalankan pada CPU. Pengukuran atas audio berdurasi 120 detik menghasilkan waktu inferensi 1,3 detik, yakni sekitar 91 kali waktu nyata, dengan pemuatan model sekali sebesar 15 detik. Hasil ini mengonfirmasi secara empiris klaim Bittner dkk. [16] bahwa basic-pitch bersifat ringan, sehingga akselerasi GPU tidak diperlukan pada skala penelitian ini.

Sistem tersusun atas sembilan modul dengan kontrak masukan dan keluaran yang terdefinisi sehingga dapat diuji secara terpisah. Verifikasi implementasi dilakukan melalui 211 kasus uji otomatis yang mencakup kebutuhan fungsional, keterulangan, round-trip token, dan kepatuhan batasan biologis.

Perlu dicatat satu keputusan penempatan. MusicXML merupakan format notasi tertulis sehingga setiap durasi harus dapat dinyatakan sebagai nilai not. Keluaran transkripsi yang bersifat kontinu terhadap waktu karenanya tidak dapat dinotasikan sebagaimana adanya, dan notasi hanya dimungkinkan pada atau sesudah tahap kuantisasi. MusicXML ditempatkan di luar jalur data utama sebagai artefak keluaran, sehingga tidak menambah tahap lossy pada pipeline, sedangkan jalur token dibangun langsung dari daftar not terkuantisasi.

### B. Parameter Sistem

**TABEL II. PARAMETER SISTEM**

| Parameter | Nilai |
|---|---|
| Ambang onset | 0,6 |
| Ambang bingkai | 0,3 |
| Durasi not minimum | 60 ms |
| Resolusi kisi | 1/16 nada |
| Kode luar | RS(255, 223) atas GF(2⁸) |
| Struktur oligo | 20 + 162 + 20 = 202 nt |
| Muatan per oligo | 2 B indeks + 1 B seed + 29 B data |
| Konversi basis | 128 bit → 81 trit |
| Rentang kandungan GC | 40%–60% |

Durasi not minimum diturunkan dari nilai bawaan pustaka sebesar 127,70 ms. Nilai bawaan tersebut melampaui panjang satu not seperenam belas pada tempo 120 BPM yang bernilai 125 ms, sehingga apabila dipertahankan, model akan membuang seluruh not terpendek yang dapat direpresentasikan kisi. Ambang onset dinaikkan dari nilai bawaan 0,5; prosedur kalibrasinya diuraikan pada Subseksi V-G beserta keterbatasannya.

### C. Data Uji

Sampel uji disusun penulis menggunakan Digital Audio Workstation sehingga notasi acuan bersifat eksak secara konstruksi: notasi yang ditulis pada piano roll persis sama dengan yang terdengar pada audio hasil render, tanpa memerlukan penyelarasan waktu maupun anotasi manual yang keduanya berpotensi menimbulkan galat pada acuan itu sendiri. Karakteristiknya disajikan pada Tabel III.

**TABEL III. KARAKTERISTIK SAMPEL UJI**

| Atribut | Nilai |
|---|---|
| Berkas audio | MP3, 564.929 bita, 44,1 kHz, stereo, 23,54 s |
| Notasi acuan | MIDI, 618 bita, 69 not |
| Tempo | 130 BPM, birama 4/4, tetap |
| Rentang nada | 36–69 (nomor not MIDI) |
| Kerapatan not | 3,18 not per detik |

---

## V. HASIL DAN PEMBAHASAN

### A. Verifikasi Round-Trip dan Keterulangan

Kebenaran pembacaan balik diverifikasi terlebih dahulu, mendahului seluruh pengujian lain, sebab kegagalan pada tahap ini menandakan cacat implementasi dan membatalkan penafsiran metrik lainnya. Barisan token sebelum pengodean dibandingkan terhadap barisan token hasil pembacaan balik melalui pencocokan ringkasan SHA-256 atas muatan token. Keduanya terbukti identik bita demi bita.

Keterulangan diuji melalui eksekusi ganda atas masukan yang sama, dan sekuens yang dihasilkan terbukti identik. Sifat ini diperoleh dengan menurunkan aliran pengacakan dari SHA-256 alih-alih dari pembangkit bilangan acak semu bawaan bahasa, yang keluarannya tidak dijamin stabil antarversi.

Hasil ini menegaskan bahwa modul penyimpanan DNA tidak menyumbang kehilangan informasi sama sekali, sehingga seluruh galat rekonstruksi yang terukur pada Subseksi V-D bersumber pada tahap sebelumnya.

### B. Kepatuhan Batasan Biologis

**TABEL IV. KEPATUHAN BATASAN BIOLOGIS**

| Besaran | Nilai | Batasan |
|---|---|---|
| Jumlah oligo | 9 | — |
| Kandungan GC rerata | 0,5017 | — |
| Kandungan GC minimum | 0,4802 | ≥ 0,40 |
| Kandungan GC maksimum | 0,5297 | ≤ 0,60 |
| Oligo dalam rentang | 100% | 100% |
| Panjang homopolymer maksimum | 2 | ≤ 3 |
| Tingkat penolakan penapisan | 0,00% | — |

Seluruh oligo memenuhi batasan. Kandungan GC memusat rapat di sekitar 50% dengan simpangan kurang dari tiga poin persen, dan tidak satu pun oligo memerlukan pengacakan ulang. Hasil ini menunjukkan bahwa tahap pengacakan sudah cukup untuk menyeragamkan distribusi basa, sehingga penapisan berperan sebagai jaring pengaman dan bukan sebagai mekanisme utama.

Panjang homopolymer maksimum bernilai dua, bukan satu. Rotating code menjamin muatan bebas homopolymer, dan sambungan primer maju ke muatan juga bebas karena dirotasikan. Namun basa terakhir muatan bergantung pada data, sehingga ketika nilainya kebetulan sama dengan basa pertama primer mundur yang bersifat tetap, terbentuk deret sepanjang dua basa. Sifat ini probabilistik: pada muatan berbeda dari sampel yang sama, nilai maksimum terukur bernilai satu. Batasan tidak lebih dari tiga basa tetap terpenuhi dengan margin lebar.

### C. Efisiensi Muatan Basa

Jumlah basa dibandingkan terhadap tiga jalur pembanding yang seluruhnya melewati skema pengodean DNA yang sama, sehingga perbandingan mengisolasi ukuran muatan dan bukan perbedaan skema.

**TABEL V. PERBANDINGAN JUMLAH BASA NITROGEN**

| Jalur | Muatan masukan | Jumlah basa |
|---|---|---|
| Pipeline yang diusulkan | 142 bita token | **1.818** |
| B1 — pembanding langsung (bita MP3) | 564.929 bita | 4.500.964 |
| B2 — pembanding simbolik (MIDI transkripsi) | 531 bita | 5.454 |
| B3 — referensi teoretis (2 bit/basa) | 564.929 bita | 2.259.716 |

**TABEL VI. DEKOMPOSISI PENGHEMATAN BASA**

| Besaran | Nilai |
|---|---|
| Penghematan total terhadap B1 | 99,96% |
| Sumbangan transkripsi | 99,88% |
| **Sumbangan skema token** | **66,67%** |
| Kerapatan efektif sistem | 0,6249 bit/basa |

Kedua sumbangan bersifat multiplikatif dan tidak dapat dijumlahkan. Perlu ditegaskan bahwa angka 99,96% terhadap B1 tidak boleh dibaca sebagai kontribusi penelitian ini: sebagian besarnya hanya menyatakan bahwa representasi simbolik jauh lebih kecil daripada berkas audio, yang sudah dapat disimpulkan sejak awal. Kontribusi yang sesungguhnya adalah penghematan 66,67% terhadap B2, yaitu terhadap berkas MIDI hasil transkripsi yang sama tanpa kuantisasi dan tanpa tokenisasi. Jalur pembanding B2 karenanya bersifat esensial; tanpanya, penghematan yang terukur tidak dapat dipisahkan dari fakta trivial tersebut.

Kerapatan efektif sistem terukur 0,6249 bit per basa, berada di bawah plafon rancangan sebesar 1,0044 bit per basa yang diturunkan sebagai hasil kali kerapatan skema 1,5802 bit/basa dengan rasio muatan terhadap panjang oligo (162/202), rasio bita data terhadap muatan (29/32), dan laju kode RS (0,8745). Selisih terhadap plafon disebabkan pengisian nol Reed–Solomon, sebagaimana dibahas pada Subseksi V-E.

### D. Akurasi Rekonstruksi dan Dekomposisi Galat

Akurasi diukur pada tataran not menggunakan mir_eval [21] dengan toleransi bawaan, yaitu 50 ms pada waktu awal dan 50 cent pada tinggi nada. Varian kedua turut memperhitungkan waktu akhir dengan toleransi sebesar nilai terbesar antara 20% durasi not acuan dan 50 ms.

**TABEL VII. AKURASI REKONSTRUKSI**

| Varian | Precision | Recall | F-measure |
|---|---|---|---|
| Waktu awal dan tinggi nada | 0,9041 | 0,9565 | **0,9296** |
| Turut memperhitungkan waktu akhir | 0,4247 | 0,4493 | 0,4366 |

Dari 69 not acuan, 66 berhasil dipasangkan dengan pencocokan satu lawan satu. Rekonstruksi menghasilkan 73 not, sehingga terdapat kelebihan empat not.

**TABEL VIII. DEKOMPOSISI GALAT REKONSTRUKSI**

| Modul penyebab | F-measure |
|---|---|
| Transkripsi musik otomatis | 0,9014 |
| Kuantisasi | 0,9726 |
| Pengodean dan pembacaan balik DNA | lossless (terverifikasi) |
| Keseluruhan sistem | 0,9296 |

Dekomposisi ini memperlihatkan dua hal. Pertama, kehilangan informasi terlokalisasi pada tahap transkripsi, bukan pada tahap penyimpanan DNA. Modul pengodean dan pembacaan balik terbukti lossless secara eksak, sehingga sifat lossy sistem sepenuhnya berasal dari ketidaksempurnaan transkripsi otomatis dan, pada derajat jauh lebih kecil, dari pembulatan kuantisasi.

Kedua, dan ini di luar dugaan, F-measure keseluruhan sistem sebesar 0,9296 lebih tinggi daripada F-measure tahap transkripsi sebesar 0,9014. Kuantisasi tidak hanya tidak merusak, melainkan sedikit memperbaiki akurasi tataran not. Penjelasannya adalah bahwa penyelarasan ke kisi menarik kembali waktu awal yang meleset sedikit sehingga masuk ke dalam toleransi 50 ms; dengan kata lain, kuantisasi berperan sebagai penapis galat waktu berskala kecil.

Penurunan tajam pada varian yang memperhitungkan waktu akhir tidak disebabkan oleh bias sistematis, sebab selisih durasi antara not acuan dan not rekonstruksi yang berpasangan bernilai median nol. Galatnya bersifat bimodal: sebagian besar durasi tepat sementara sebagian kecil meleset jauh. Pada histogram durasi rekonstruksi terdapat 14 not berdurasi tepat satu satuan kisi, padahal notasi acuan hanya memuat dua nilai durasi. Not pendek tersebut merupakan penggalan hasil transkripsi, dan temuan ini sejalan dengan karakteristik AMT yang telah dikenal bahwa deteksi waktu akhir jauh lebih sulit daripada deteksi waktu awal [6].

Pengukuran tambahan menunjukkan pergeseran waktu awal yang bersifat sistematis sebesar +34,18 ms dengan konsentrasi fase 0,784, terhadap satuan kisi sebesar 115,38 ms. Mengompensasi pergeseran tersebut menurunkan galat penyelarasan kisi dari 35,38 ms menjadi 14,64 ms, namun hanya menaikkan F-measure sebesar 0,6 poin persen, sebab toleransi 50 ms telah menampung pergeseran tersebut.

### E. Sumbangan Deteksi Pengulangan

Sumbangan mekanisme deteksi pengulangan diukur dengan menjalankan sistem dua kali atas sampel yang sama, dengan dan tanpa mengaktifkan mekanisme tersebut.

**TABEL IX. SUMBANGAN DETEKSI PENGULANGAN**

| Besaran | Tanpa LZ77 | Dengan LZ77 | Penghematan |
|---|---|---|---|
| Jumlah token | 73 | 51 | **30,14%** |
| Ukuran muatan | 205 bita | 142 bita | 30,73% |
| Jumlah basa | 1.818 | 1.818 | **0,00%** |

Terdapat ketimpangan yang mencolok: peringkasan pengulangan memangkas 30,14% token dan 30,73% muatan, tetapi tidak menghemat satu basa pun. Penyebabnya adalah granularitas kode Reed–Solomon. Kata sandi RS(255, 223) berpanjang tetap, dan muatan yang lebih pendek daripada 223 bita tetap diisi nol hingga memenuhi satu kata sandi utuh sebelum difragmentasi. Muatan sebesar 142 bita maupun 205 bita sama-sama menempati satu kata sandi, sehingga keduanya menghasilkan sembilan oligo dan 1.818 basa yang sama.

Konsekuensi lanjutannya bersifat paradoksal. Ketika ambang onset dinaikkan sehingga muatan mengecil dari 159 menjadi 142 bita, kerapatan efektif yang terukur justru turun dari 0,6997 menjadi 0,6249 bit per basa, sebab penyebutnya tertahan pada nilai yang sama. Selama lantai granularitas ini berlaku, kompresi yang lebih baik menurunkan kerapatan efektif yang terukur, yakni berlawanan arah dengan besaran yang hendak diukur.

Temuan ini berimplikasi pada cara pelaporan. Sumbangan deteksi pengulangan sebaiknya dilaporkan pada tataran token, yang mencerminkan mekanismenya sendiri, dan bukan pada tataran basa, yang mencampurkannya dengan pembulatan kata sandi. Perbaikan yang lazim adalah penggunaan kode Reed–Solomon terpendek, yaitu mengisi nol hanya pada tahap pengodean tanpa ikut mensintesisnya, dan dicatat sebagai pekerjaan lanjutan.

### F. Waktu Proses

Waktu proses untuk audio berdurasi 23,54 detik adalah 12,91 detik pada jalur encoding dan 0,19 detik pada jalur decoding. Sebagian besar waktu encoding dihabiskan pada pemuatan model transkripsi yang bersifat sekali per proses. Ketimpangan antara kedua jalur mencerminkan bahwa seluruh beban komputasi berat berada pada tahap transkripsi, sedangkan pembacaan balik hanyalah aritmetika bilangan bulat.

### G. Kalibrasi Ambang Onset

Pada nilai bawaan pustaka sebesar 0,5, sistem menghasilkan precision 0,8442 berhadapan dengan recall 0,9420, ketimpangan yang menandakan ambang deteksi terlalu rendah.

**TABEL X. PENELUSURAN AMBANG ONSET**

| Ambang | Jumlah not | Precision | Recall | F-measure |
|---|---|---|---|---|
| 0,30 | 122 | 0,5246 | 0,9275 | 0,6702 |
| 0,50 | 77 | 0,8442 | 0,9420 | 0,8904 |
| **0,60** | 73 | 0,9041 | 0,9565 | **0,9296** |
| 0,70 | 71 | 0,9155 | 0,9420 | 0,9286 |
| 0,80 | 63 | 0,9048 | 0,8261 | 0,8636 |

Pada ambang 0,6, precision dan recall meningkat bersamaan. Peningkatan recall yang menyertai kenaikan ambang tampak berlawanan dengan pertukaran yang lazim, namun dapat dijelaskan oleh sifat pencocokan mir_eval yang bersifat satu lawan satu: sebuah not palsu dapat merebut pasangan yang seharusnya diperoleh not yang benar, sehingga membuang not palsu memperbaiki kedua metrik sekaligus.

Perlu ditegaskan bahwa penelusuran ini dilakukan pada sampel yang sama dengan yang digunakan untuk melaporkan hasil, sehingga berisiko overfitting. Konsekuensinya diuraikan pada Seksi VI.

---

## VI. KETERBATASAN

**Jumlah sampel.** Seluruh angka berasal dari satu sampel uji. Hasil ini membuktikan bahwa pipeline berfungsi dan memenuhi batasan biologis secara terverifikasi, tetapi belum memungkinkan generalisasi. Korpus yang bervariasi pada durasi, kerapatan not, dan derajat pengulangan sedang disusun.

**Kalibrasi parameter.** Ambang onset ditetapkan melalui penelusuran pada sampel yang sama dengan yang digunakan untuk melaporkan hasil. Prosedur ini tidak dapat dipertahankan sebagai penetapan parameter yang independen, dan kalibrasi ulang atas korpus penuh diperlukan.

**Tanpa penyuntikan galat.** Tahap sintesis, penyimpanan, dan sequencing disimulasikan tanpa menyuntikkan galat biologis. Kemampuan koreksi Reed–Solomon diverifikasi secara terpisah melalui pengujian unit yang membuktikan koreksi hingga enam belas galat simbol per kata sandi, namun ketahanan terhadap profil galat sesungguhnya belum diukur.

**Audio hasil sintesis perangkat lunak.** Audio yang dihasilkan DAW jauh lebih bersih daripada rekaman akustik, sehingga akurasi transkripsi yang dilaporkan merupakan batas atas.

**Batas pengalamatan oligo.** Medan indeks oligo selebar dua bita mengalamati 65.536 oligo, setara sekitar 1,59 MiB muatan atau 69 detik audio pada laju bit 192 kbps. Untuk sampel lebih panjang, jalur pembanding B1 tidak dapat dibangun sebagai oligo sehingga jumlah basanya dihitung secara analitis. Perhitungan tersebut eksak dan jalur pembanding memang tidak pernah didekode, tetapi keterbatasannya perlu dinyatakan.

**Informasi yang tidak dipulihkan.** Skema token tidak menyimpan velocity maupun kanal instrumen, sehingga dinamika permainan hilang dan seluruh instrumen tergabung menjadi satu jalur pada notasi hasil rekonstruksi. Hal ini tidak memengaruhi metrik tataran not yang mencocokkan berdasarkan tinggi nada dan waktu saja.

**Batasan cakupan.** Penelitian dibatasi pada audio dengan maksimal dua instrumen guna mengisolasi evaluasi pemetaan token, sehingga pemisahan sumber tidak dibahas. Tempo diperlakukan sebagai diketahui dari metadata proyek dan estimasi tempo otomatis berada di luar lingkup.

---

## VII. KESIMPULAN

Makalah ini mengusulkan dan mengimplementasikan pipeline yang menjembatani transkripsi musik otomatis dengan penyimpanan data berbasis DNA melalui pemetaan token fitur. Alih-alih memetakan bita berkas audio secara langsung, rekaman diubah representasinya lebih dahulu menjadi barisan token simbolik yang ringkas, kemudian dipetakan menjadi sekuens FASTA yang memenuhi batasan biologis secara konstruksi dan diperkuat kode Reed–Solomon.

Pengujian awal atas satu sampel menunjukkan bahwa pipeline berfungsi sebagaimana dirancang. Pembacaan balik terbukti lossless secara identik-bita, seluruh oligo memenuhi batasan kandungan GC dan panjang homopolymer tanpa satu pun penolakan pada tahap penapisan, dan skema token menghemat 66,67% basa dibandingkan pengodean berkas MIDI hasil transkripsi yang sama. Akurasi rekonstruksi pada tataran not mencapai F-measure 0,9296.

Dekomposisi galat menurut modul penyebabnya memberikan temuan yang paling bermakna: kehilangan informasi terlokalisasi sepenuhnya pada tahap transkripsi, sementara tahap penyimpanan DNA tidak menyumbang galat sama sekali. Ditemukan pula bahwa kuantisasi justru sedikit memperbaiki akurasi tataran not dengan menarik kembali waktu awal yang meleset ke dalam toleransi, serta bahwa granularitas kata sandi Reed–Solomon dapat sepenuhnya menutupi sumbangan peringkasan pengulangan pada sampel berdurasi pendek, sehingga sumbangan tersebut sebaiknya dilaporkan pada tataran token.

Pekerjaan lanjutan mencakup evaluasi atas korpus penuh yang bervariasi pada durasi, kerapatan not, dan derajat pengulangan; penggunaan kode Reed–Solomon terpendek untuk menghilangkan lantai granularitas; serta penyuntikan galat guna mengukur ketahanan sistem terhadap profil galat sintesis dan sequencing yang sesungguhnya.

---

## REFERENSI

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
