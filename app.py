import streamlit as st
import sqlite3
import hashlib
import secrets
import json
import io
import math
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import streamlit.components.v1 as components

# =========================================================
# KOMPONEN KEAMANAN MISKONSEPTION
# =========================================================

_folder_safety = (
    Path(__file__).parent
    / "safety_component"
    / "build"
)

safety_monitor = components.declare_component(
    "miskonseption_safety",
    path=str(_folder_safety)
)


def jalankan_pemantauan_ujian(session_id, user_id):

    status_sesi = ambil_status_ujian(session_id)

    if not status_sesi:
        st.error("Sesi ujian tidak ditemukan.")
        return False

    jumlah_pelanggaran = int(
        status_sesi.get("violation_count", 0)
    )

    status = status_sesi.get("status")

    if status != "BERLANGSUNG":
        return False

    if "pelanggaran_terakhir_diproses" not in st.session_state:
        st.session_state.pelanggaran_terakhir_diproses = {}

    event = safety_monitor(
        active=True,
        violation_count=jumlah_pelanggaran,
        last_processed_event_id=(
            st.session_state.pelanggaran_terakhir_diproses.get(
                session_id
            )
        ),
        key=f"monitor_{session_id}"
    )

    # Tidak ada kejadian baru
    if not isinstance(event, dict):
        return True

    event_id = event.get("event_id")

    if not event_id:
        return True

    # Catat kejadian ke database
    catat_pelanggaran(
        session_id=session_id,
        user_id=user_id,
        violation_type=event.get(
            "violation_type",
            "AKTIVITAS_TIDAK_WAJAR"
        ),
        description=event.get(
            "description",
            "Aktivitas meninggalkan halaman ujian."
        ),
        event_id=event_id
    )

    # Tandai agar kejadian yang sama tidak diproses berulang
    st.session_state.pelanggaran_terakhir_diproses[
        session_id
    ] = event_id

    # Periksa kembali status setelah pencatatan
    status_baru = ambil_status_ujian(session_id)

    if status_baru:
        jumlah_baru = int(
            status_baru.get("violation_count", 0)
        )

        if jumlah_baru >= BATAS_PELANGGARAN:
            st.session_state.ujian_dihentikan = True

    st.rerun()

    return True
# =========================================================
# PEMANTAUAN AKTIF SELAMA UJIAN
# =========================================================

if not jalankan_pemantauan_ujian(
    sesi_id,
    pengguna["id"]
):
    st.error(
        "Ujian tidak dapat dilanjutkan karena sesi "
        "sudah tidak aktif."
    )
    return

status_sesi = ambil_status_ujian(sesi_id)

if not status_sesi:
    st.error("Sesi ujian tidak ditemukan.")
    return

if status_sesi.get("status") == "DIHENTIKAN":
    st.error("Ujian dihentikan karena mencapai tiga pelanggaran.")
    st.warning(
        "Guru perlu memeriksa catatan pelanggaran sebelum "
        "siswa dapat mengikuti ujian kembali."
    )
    return

from datetime import datetime

# =========================================================
# 1. KONFIGURASI
# =========================================================

st.set_page_config(
    page_title="MISCONCEPTION",
    page_icon="🧠",
    layout="wide"
)

DATABASE = "Misconception"

C = 299792458          # Kecepatan cahaya (m/s)
H = 6.62607015e-34    # Konstanta Planck (J.s)


# =========================================================
# 2. DATABASE
# =========================================================

def koneksi_database():
    conn = sqlite3.connect(DATABASE)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def inisialisasi_database():

    conn = koneksi_database()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            jenis_tes TEXT NOT NULL,
            nilai REAL NOT NULL,
            hasil_json TEXT NOT NULL,
            tanggal TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# 3. PASSWORD
# =========================================================

def buat_hash_password(password, salt=None):

    if salt is None:
        salt = secrets.token_hex(16)

    hasil = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000
    ).hex()

    return salt, hasil


def verifikasi_password(password, salt, hash_asli):

    _, hash_baru = buat_hash_password(password, salt)

    return secrets.compare_digest(
        hash_baru,
        hash_asli
    )


# =========================================================
# 4. REGISTRASI
# =========================================================

def daftar_siswa(nama, username, password):

    conn = koneksi_database()
    cursor = conn.cursor()

    salt, password_hash = buat_hash_password(password)

    try:

        cursor.execute("""
            INSERT INTO users
            (nama, username, salt, password_hash, role)
            VALUES (?, ?, ?, ?, ?)
        """, (
            nama,
            username,
            salt,
            password_hash,
            "Siswa"
        ))

        conn.commit()

        berhasil = True
        pesan = "Pendaftaran berhasil."

    except sqlite3.IntegrityError:

        berhasil = False
        pesan = "Username telah digunakan."

    conn.close()

    return berhasil, pesan


# =========================================================
# 5. LOGIN
# =========================================================

def login_pengguna(username, password):

    conn = koneksi_database()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nama, username, salt, password_hash, role
        FROM users
        WHERE username = ?
    """, (username,))

    data = cursor.fetchone()
    conn.close()

    if data is None:
        return None

    if verifikasi_password(
        password,
        data[3],
        data[4]
    ):

        return {
            "id": data[0],
            "nama": data[1],
            "username": data[2],
            "role": data[5]
        }

    return None


# =========================================================
# 6. MENYIMPAN HASIL
# =========================================================

def simpan_hasil(user_id, jenis_tes, nilai, hasil):

    conn = koneksi_database()

    conn.execute("""
        INSERT INTO results
        (user_id, jenis_tes, nilai, hasil_json, tanggal)
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        jenis_tes,
        nilai,
        json.dumps(hasil, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def ambil_riwayat_siswa(user_id):

    conn = koneksi_database()

    df = pd.read_sql_query("""
        SELECT id, jenis_tes, nilai, tanggal, hasil_json
        FROM results
        WHERE user_id = ?
        ORDER BY id DESC
    """, conn, params=(user_id,))

    conn.close()

    return df


def ambil_semua_hasil():

    conn = koneksi_database()

    df = pd.read_sql_query("""
        SELECT
            users.id AS user_id,
            users.nama,
            users.username,
            results.id AS test_id,
            results.jenis_tes,
            results.nilai,
            results.tanggal,
            results.hasil_json
        FROM results
        JOIN users ON users.id = results.user_id
        ORDER BY results.id DESC
    """, conn)

    conn.close()

    return df


def ambil_semua_siswa():

    conn = koneksi_database()

    df = pd.read_sql_query("""
        SELECT id, nama, username
        FROM users
        WHERE role = 'Siswa'
        ORDER BY nama
    """, conn)

    conn.close()

    return df


inisialisasi_database()

# =========================================================
# 7. BANK SOAL FOUR-TIER
# =========================================================

SOAL = [
    {
        "topik": "Konsep dasar gelombang elektromagnetik",
        "pertanyaan": "Gelombang elektromagnetik dapat merambat tanpa medium karena ...",
        "jawaban": [
            "Memerlukan partikel udara",
            "Medan listrik dan medan magnet yang berubah saling berkaitan",
            "Merupakan gelombang bunyi",
            "Tidak membawa energi"
        ],
        "benar": 1,
        "alasan": [
            "Semua gelombang memerlukan udara",
            "Medan listrik dan medan magnet yang berubah saling berkaitan",
            "Gelombang elektromagnetik adalah gelombang mekanik",
            "Gelombang elektromagnetik tidak membawa energi"
        ],
        "alasan_benar": 1,
        "penjelasan": "Gelombang elektromagnetik dapat merambat di ruang hampa. Gelombang ini tersusun dari medan listrik dan medan magnet yang berubah serta saling berkaitan."
    },

    {
        "topik": "Sifat gelombang elektromagnetik",
        "pertanyaan": "Gelombang elektromagnetik bersifat transversal karena ...",
        "jawaban": [
            "Getarnya sejajar arah rambat",
            "Medan listrik dan medan magnet tegak lurus arah rambat",
            "Tidak mempunyai arah rambat",
            "Hanya merambat dalam zat padat"
        ],
        "benar": 1,
        "alasan": [
            "Semua gelombang memiliki getaran sejajar arah rambat",
            "Medan listrik dan medan magnet tegak lurus terhadap arah rambat",
            "Gelombang elektromagnetik tidak memiliki arah",
            "Gelombang elektromagnetik adalah gelombang longitudinal"
        ],
        "alasan_benar": 1,
        "penjelasan": "Gelombang elektromagnetik merupakan gelombang transversal. Medan listrik, medan magnet, dan arah rambat saling tegak lurus."
    },

    {
        "topik": "Kecepatan gelombang elektromagnetik",
        "pertanyaan": "Cepat rambat cahaya di ruang hampa mendekati ...",
        "jawaban": [
            "340 m/s",
            "3 × 10⁶ m/s",
            "3 × 10⁸ m/s",
            "3 × 10¹⁰ m/s"
        ],
        "benar": 2,
        "alasan": [
            "Sama dengan kecepatan bunyi",
            "Merupakan nilai pendekatan cepat rambat cahaya di ruang hampa",
            "Semua gelombang memiliki kecepatan bunyi",
            "Cahaya tidak mempunyai kecepatan"
        ],
        "alasan_benar": 1,
        "penjelasan": "Cepat rambat cahaya di ruang hampa adalah 299.792.458 m/s, atau sekitar 3 × 10⁸ m/s."
    },

    {
        "topik": "Frekuensi dan panjang gelombang",
        "pertanyaan": "Jika cepat rambat tetap dan frekuensi meningkat, panjang gelombang akan ...",
        "jawaban": [
            "Bertambah",
            "Berkurang",
            "Tetap",
            "Menjadi nol"
        ],
        "benar": 1,
        "alasan": [
            "Frekuensi dan panjang gelombang berbanding lurus",
            "v = fλ, sehingga jika v tetap, f meningkat maka λ berkurang",
            "Frekuensi tidak berhubungan dengan panjang gelombang",
            "Cepat rambat menjadi nol"
        ],
        "alasan_benar": 1,
        "penjelasan": "Hubungan v = fλ menunjukkan bahwa ketika cepat rambat tetap, frekuensi dan panjang gelombang berbanding terbalik."
    },

    {
        "topik": "Spektrum elektromagnetik",
        "pertanyaan": "Urutan spektrum dari frekuensi rendah menuju tinggi adalah ...",
        "jawaban": [
            "Gamma, X, ultraviolet, tampak, inframerah, mikro, radio",
            "Radio, mikro, inframerah, tampak, ultraviolet, X, gamma",
            "Tampak, radio, gamma, mikro, ultraviolet, inframerah, X",
            "Inframerah, radio, tampak, mikro, gamma, X, ultraviolet"
        ],
        "benar": 1,
        "alasan": [
            "Radio memiliki frekuensi paling tinggi",
            "Frekuensi meningkat dari radio menuju gamma",
            "Gamma memiliki panjang gelombang terbesar",
            "Urutan spektrum tidak berkaitan dengan frekuensi"
        ],
        "alasan_benar": 1,
        "penjelasan": "Urutannya adalah radio, mikro, inframerah, cahaya tampak, ultraviolet, sinar-X, dan sinar gamma."
    },

    {
        "topik": "Gelombang radio",
        "pertanyaan": "Gelombang radio dimanfaatkan untuk ...",
        "jawaban": [
            "Komunikasi dan penyiaran",
            "Pemeriksaan tulang",
            "Menghasilkan suara secara langsung",
            "Melihat benda dengan mata"
        ],
        "benar": 0,
        "alasan": [
            "Gelombang radio dapat membawa informasi melalui modulasi",
            "Gelombang radio memiliki energi foton tertinggi",
            "Gelombang radio merupakan gelombang bunyi",
            "Mata manusia dapat melihat gelombang radio"
        ],
        "alasan_benar": 0,
        "penjelasan": "Gelombang radio digunakan untuk komunikasi, penyiaran, dan pengiriman informasi secara nirkabel."
    },

    {
        "topik": "Gelombang mikro",
        "pertanyaan": "Oven microwave memanfaatkan gelombang mikro untuk ...",
        "jawaban": [
            "Menghasilkan bunyi",
            "Berinteraksi dengan bahan makanan dan menghasilkan pemanasan",
            "Mengubah makanan menjadi cahaya",
            "Menghilangkan massa makanan"
        ],
        "benar": 1,
        "alasan": [
            "Gelombang mikro dapat berinteraksi dengan komponen makanan dan mengubah energi menjadi energi termal",
            "Gelombang mikro merupakan gelombang mekanik",
            "Semua gelombang menghasilkan pemanasan yang sama",
            "Makanan hanya dapat dipanaskan oleh udara"
        ],
        "alasan_benar": 0,
        "penjelasan": "Gelombang mikro berinteraksi dengan bahan makanan. Energi elektromagnetik kemudian berubah menjadi energi termal melalui berbagai mekanisme interaksi."
    },

    {
        "topik": "Inframerah",
        "pertanyaan": "Radiasi inframerah berkaitan erat dengan ...",
        "jawaban": [
            "Radiasi termal",
            "Gelombang bunyi",
            "Arus listrik",
            "Gelombang air"
        ],
        "benar": 0,
        "alasan": [
            "Benda dapat memancarkan radiasi inframerah sesuai suhu dan karakteristik permukaannya",
            "Inframerah merupakan gelombang mekanik",
            "Inframerah tidak membawa energi",
            "Inframerah hanya dihasilkan oleh benda beku"
        ],
        "alasan_benar": 0,
        "penjelasan": "Banyak benda memancarkan radiasi inframerah sebagai bagian dari radiasi termal. Kamera termal dapat mendeteksi radiasi tersebut."
    },

    {
        "topik": "Cahaya tampak",
        "pertanyaan": "Cahaya tampak adalah gelombang elektromagnetik yang ...",
        "jawaban": [
            "Dapat dideteksi mata manusia",
            "Tidak membawa energi",
            "Memiliki frekuensi paling rendah",
            "Hanya merambat dalam air"
        ],
        "benar": 0,
        "alasan": [
            "Retina manusia peka terhadap rentang frekuensi tertentu",
            "Semua gelombang elektromagnetik dapat dilihat",
            "Cahaya tampak tidak memiliki panjang gelombang",
            "Cahaya tampak merupakan gelombang bunyi"
        ],
        "alasan_benar": 0,
        "penjelasan": "Mata manusia dapat mendeteksi rentang cahaya tampak. Gelombang elektromagnetik lainnya tidak dapat dilihat langsung oleh mata."
    },

    {
        "topik": "Ultraviolet",
        "pertanyaan": "Frekuensi ultraviolet dibandingkan cahaya tampak adalah ...",
        "jawaban": [
            "Lebih rendah",
            "Lebih tinggi",
            "Selalu sama",
            "Nol"
        ],
        "benar": 1,
        "alasan": [
            "Ultraviolet berada di bawah inframerah",
            "Ultraviolet memiliki frekuensi lebih tinggi daripada cahaya tampak",
            "Ultraviolet merupakan gelombang mekanik",
            "Frekuensi tidak berkaitan dengan spektrum"
        ],
        "alasan_benar": 1,
        "penjelasan": "Ultraviolet memiliki frekuensi lebih tinggi dan panjang gelombang lebih pendek daripada cahaya tampak."
    },

    {
        "topik": "Sinar-X",
        "pertanyaan": "Sinar-X dalam bidang medis digunakan untuk ...",
        "jawaban": [
            "Pencitraan bagian dalam tubuh",
            "Mendengar detak jantung",
            "Mengukur kelembapan udara",
            "Menghasilkan gelombang suara"
        ],
        "benar": 0,
        "alasan": [
            "Sinar-X diserap jaringan tubuh dengan tingkat berbeda",
            "Sinar-X adalah gelombang suara",
            "Sinar-X hanya dipantulkan kulit",
            "Sinar-X tidak berinteraksi dengan materi"
        ],
        "alasan_benar": 0,
        "penjelasan": "Sinar-X dapat menembus jaringan tubuh. Perbedaan penyerapan oleh jaringan dan tulang menghasilkan citra."
    },

    {
        "topik": "Sinar gamma",
        "pertanyaan": "Radiasi dengan frekuensi paling tinggi di antara pilihan berikut adalah ...",
        "jawaban": [
            "Radio",
            "Inframerah",
            "Cahaya tampak",
            "Gamma"
        ],
        "benar": 3,
        "alasan": [
            "Radio memiliki energi foton paling besar",
            "Gamma berada pada bagian frekuensi sangat tinggi",
            "Cahaya tampak memiliki frekuensi tidak terbatas",
            "Inframerah memiliki panjang gelombang terpendek"
        ],
        "alasan_benar": 1,
        "penjelasan": "Sinar gamma memiliki frekuensi sangat tinggi dan energi foton tinggi. Namun batas antara sinar-X dan gamma dapat ditentukan berdasarkan asal radiasi juga."
    },

    {
        "topik": "Energi foton",
        "pertanyaan": "Energi foton berbanding lurus dengan ...",
        "jawaban": [
            "Panjang gelombang",
            "Frekuensi",
            "Massa medium",
            "Periode kuadrat"
        ],
        "benar": 1,
        "alasan": [
            "Energi foton mengikuti E = hf",
            "Energi selalu berbanding terbalik dengan frekuensi",
            "Energi tidak dipengaruhi frekuensi",
            "Energi sama dengan massa medium"
        ],
        "alasan_benar": 0,
        "penjelasan": "Energi foton dihitung dengan E = hf. Semakin tinggi frekuensi, semakin besar energi foton."
    },

    {
        "topik": "Pemantulan gelombang",
        "pertanyaan": "Pada pemantulan cahaya berlaku ...",
        "jawaban": [
            "Sudut datang sama dengan sudut pantul",
            "Sudut datang dua kali sudut pantul",
            "Frekuensi menjadi nol",
            "Energi selalu hilang seluruhnya"
        ],
        "benar": 0,
        "alasan": [
            "Hukum pemantulan menyatakan sudut datang sama dengan sudut pantul",
            "Pemantulan tidak mempunyai aturan",
            "Gelombang selalu diserap seluruhnya",
            "Arah rambat tidak dapat berubah"
        ],
        "alasan_benar": 0,
        "penjelasan": "Sudut datang dan sudut pantul diukur terhadap garis normal, bukan terhadap permukaan."
    },

    {
        "topik": "Pembiasan gelombang",
        "pertanyaan": "Ketika cahaya masuk ke medium berbeda, frekuensinya pada umumnya ...",
        "jawaban": [
            "Berubah",
            "Tetap",
            "Menjadi dua kali",
            "Menjadi nol"
        ],
        "benar": 1,
        "alasan": [
            "Frekuensi ditentukan oleh sumber dan tetap saat memasuki medium lain",
            "Frekuensi selalu ditentukan kecepatan medium",
            "Panjang gelombang tidak pernah berubah",
            "Pembiasan menghentikan gelombang"
        ],
        "alasan_benar": 0,
        "penjelasan": "Frekuensi tetap. Cepat rambat dan panjang gelombang dapat berubah ketika cahaya memasuki medium berbeda."
    },

    {
        "topik": "Polarisasi",
        "pertanyaan": "Polarisasi menunjukkan bahwa cahaya bersifat ...",
        "jawaban": [
            "Longitudinal",
            "Transversal",
            "Mekanik",
            "Tidak memiliki arah getar"
        ],
        "benar": 1,
        "alasan": [
            "Polarisasi berkaitan dengan pembatasan arah getar gelombang transversal",
            "Gelombang longitudinal dapat dipolarisasi dengan cara yang sama",
            "Cahaya memerlukan medium",
            "Cahaya tidak memiliki medan listrik"
        ],
        "alasan_benar": 0,
        "penjelasan": "Polarisasi merupakan bukti bahwa cahaya bersifat transversal karena arah getarnya dapat dibatasi."
    },

    {
        "topik": "Energi gelombang elektromagnetik",
        "pertanyaan": "Gelombang elektromagnetik membawa energi karena ...",
        "jawaban": [
            "Memiliki medan listrik dan medan magnet",
            "Selalu membawa udara",
            "Tidak memiliki frekuensi",
            "Harus merambat dalam air"
        ],
        "benar": 0,
        "alasan": [
            "Medan elektromagnetik dapat membawa dan mentransfer energi",
            "Energi hanya dimiliki gelombang mekanik",
            "Gelombang tidak berinteraksi dengan benda",
            "Energi sama dengan massa udara"
        ],
        "alasan_benar": 0,
        "penjelasan": "Gelombang elektromagnetik membawa energi yang dapat ditransfer ke materi ketika terjadi interaksi."
    },

    {
        "topik": "Kecepatan dalam medium",
        "pertanyaan": "Jika indeks bias medium lebih besar daripada satu, kecepatan cahaya dalam medium dibandingkan di ruang hampa adalah ...",
        "jawaban": [
            "Lebih besar",
            "Lebih kecil",
            "Selalu sama",
            "Nol"
        ],
        "benar": 1,
        "alasan": [
            "v = c/n, sehingga n lebih besar menghasilkan v lebih kecil",
            "Medium selalu mempercepat cahaya",
            "Indeks bias tidak berhubungan dengan kecepatan",
            "Cahaya berhenti dalam medium"
        ],
        "alasan_benar": 0,
        "penjelasan": "Dalam medium dengan indeks bias n, kecepatan fase cahaya adalah v = c/n."
    },

    {
        "topik": "Panjang gelombang",
        "pertanyaan": "Jika frekuensi tetap dan cepat rambat berkurang, panjang gelombang akan ...",
        "jawaban": [
            "Bertambah",
            "Berkurang",
            "Tetap",
            "Menjadi tak terhingga"
        ],
        "benar": 1,
        "alasan": [
            "λ = v/f, sehingga v berkurang dan f tetap menyebabkan λ berkurang",
            "Panjang gelombang tidak dipengaruhi kecepatan",
            "Frekuensi ikut menjadi nol",
            "Medium menghilangkan gelombang"
        ],
        "alasan_benar": 0,
        "penjelasan": "Berdasarkan λ = v/f, panjang gelombang berkurang jika kecepatan berkurang sedangkan frekuensi tetap."
    },

    {
        "topik": "Aplikasi gelombang elektromagnetik",
        "pertanyaan": "Komunikasi satelit umumnya memanfaatkan gelombang ...",
        "jawaban": [
            "Mikro",
            "Bunyi",
            "Air",
            "Gelombang tali"
        ],
        "benar": 0,
        "alasan": [
            "Gelombang mikro digunakan pada berbagai sistem komunikasi satelit",
            "Bunyi dapat merambat melalui ruang hampa",
            "Gelombang air dapat merambat di ruang angkasa",
            "Gelombang tali digunakan untuk komunikasi satelit"
        ],
        "alasan_benar": 0,
        "penjelasan": "Komunikasi satelit menggunakan frekuensi radio, termasuk pita gelombang mikro, untuk mengirim dan menerima sinyal."
    }
]

# =========================================================
# 8. ANALISIS FOUR-TIER
# =========================================================

def analisis_jawaban(jawaban_siswa):

    hasil = []

    for nomor, jawaban in enumerate(jawaban_siswa):

        soal = SOAL[nomor]

        benar_jawaban = (
            jawaban["jawaban"] == soal["jawaban"][soal["benar"]]
        )

        benar_alasan = (
            jawaban["alasan"] == soal["alasan"][soal["alasan_benar"]]
        )

        yakin_jawaban = jawaban["yakin_jawaban"] == "Yakin"
        yakin_alasan = jawaban["yakin_alasan"] == "Yakin"

        if benar_jawaban and benar_alasan:

            if yakin_jawaban and yakin_alasan:
                kategori = "Paham Konsep"

            else:
                kategori = "Paham Konsep, Belum Yakin"

        elif not benar_jawaban and not benar_alasan:

            if yakin_jawaban and yakin_alasan:
                kategori = "Indikasi Miskonsepsi"

            else:
                kategori = "Belum Memahami Konsep"

        elif benar_jawaban and not benar_alasan:

            kategori = "Jawaban Benar, Alasan Keliru"

        else:

            kategori = "Jawaban Salah, Alasan Benar"

        hasil.append({

            "nomor": nomor + 1,

            "topik": soal["topik"],

            "pertanyaan": soal["pertanyaan"],

            "jawaban_siswa": jawaban["jawaban"],

            "alasan_siswa": jawaban["alasan"],

            "keyakinan_jawaban": jawaban["yakin_jawaban"],

            "keyakinan_alasan": jawaban["yakin_alasan"],

            "jawaban_benar": benar_jawaban,

            "alasan_benar": benar_alasan,

            "kategori": kategori,

            "jawaban_seharusnya":
                soal["jawaban"][soal["benar"]],

            "alasan_seharusnya":
                soal["alasan"][soal["alasan_benar"]],

            "penjelasan": soal["penjelasan"]

        })

    return hasil

# =========================================================
# 9. PERHITUNGAN NILAI
# =========================================================

def hitung_nilai(hasil):

    if not hasil:
        return 0

    skor_jawaban = sum(
        item["jawaban_benar"] for item in hasil
    )

    skor_alasan = sum(
        item["alasan_benar"] for item in hasil
    )

    total = len(hasil) * 2

    nilai = (
        (skor_jawaban + skor_alasan)
        / total
    ) * 100

    return round(nilai, 2)

def hitung_persentase(hasil):

    if not hasil:
        return 0

    jumlah = sum(
        item["kategori"] == "Indikasi Miskonsepsi"
        for item in hasil
    )

    return round(jumlah / len(hasil) * 100, 2)

# =========================================================
# 10. MATERI REMEDIAL
# =========================================================

MATERI = {

    "Konsep dasar gelombang elektromagnetik": {
        "konsep": """
Gelombang elektromagnetik merupakan gelombang yang tersusun
dari medan listrik dan medan magnet yang berubah.

Gelombang elektromagnetik dapat merambat tanpa medium material.
Contohnya, cahaya Matahari dapat mencapai Bumi melalui ruang hampa.
""",

        "rumus": [
            ("c = 1/√(μ₀ε₀)", "Hubungan konstanta elektromagnetik dengan cepat rambat cahaya")
        ],

        "contoh": "Cahaya Matahari merambat melalui ruang antara Matahari dan Bumi tanpa memerlukan udara."
    },

    "Sifat gelombang elektromagnetik": {
        "konsep": """
Gelombang elektromagnetik bersifat transversal.

Medan listrik (E), medan magnet (B), dan arah rambat
gelombang saling tegak lurus.
""",

        "rumus": [
            ("E ⟂ B", "Medan listrik tegak lurus medan magnet"),
            ("E ⟂ arah rambat", "Medan listrik tegak lurus arah rambat"),
            ("B ⟂ arah rambat", "Medan magnet tegak lurus arah rambat")
        ],

        "contoh": "Polarisasi cahaya menggunakan filter untuk membatasi arah getar medan listrik."
    },

    "Kecepatan gelombang elektromagnetik": {
        "konsep": """
Di ruang hampa, gelombang elektromagnetik merambat
dengan kecepatan cahaya.
""",

        "rumus": [
            ("c ≈ 3 × 10⁸ m/s", "Kecepatan cahaya di ruang hampa")
        ],

        "contoh": "Cahaya menempuh jarak sekitar 300.000 km dalam satu detik di ruang hampa."
    },

    "Frekuensi dan panjang gelombang": {
        "konsep": """
Frekuensi adalah jumlah gelombang yang melewati titik
dalam satu detik.

Panjang gelombang adalah jarak antara dua titik sefase
yang berurutan.
""",

        "rumus": [
            ("v = fλ", "Hubungan cepat rambat, frekuensi, dan panjang gelombang"),
            ("λ = v/f", "Menghitung panjang gelombang"),
            ("f = v/λ", "Menghitung frekuensi")
        ],

        "contoh": """
Jika v = 3 × 10⁸ m/s dan f = 6 × 10⁸ Hz:

λ = v/f
λ = (3 × 10⁸)/(6 × 10⁸)
λ = 0,5 m
"""
    },

    "Spektrum elektromagnetik": {
        "konsep": """
Urutan frekuensi rendah ke tinggi:

Radio → Mikro → Inframerah → Tampak →
Ultraviolet → Sinar-X → Gamma.

Semakin tinggi frekuensi, semakin pendek panjang gelombang
dan semakin besar energi fotonnya.
""",

        "rumus": [
            ("c = fλ", "Hubungan frekuensi dan panjang gelombang"),
            ("E = hf", "Energi foton")
        ],

        "contoh": "Sinar gamma memiliki frekuensi lebih tinggi daripada cahaya tampak."
    },

    "Gelombang radio": {
        "konsep": """
Gelombang radio digunakan untuk komunikasi, penyiaran,
dan transmisi informasi.
""",

        "rumus": [
            ("c = fλ", "Hubungan cepat rambat, frekuensi, dan panjang gelombang")
        ],

        "contoh": "Siaran radio FM menggunakan gelombang elektromagnetik untuk membawa informasi suara."
    },

    "Gelombang mikro": {
        "konsep": """
Gelombang mikro digunakan pada radar, komunikasi satelit,
dan oven microwave.
""",

        "rumus": [
            ("E = hf", "Energi foton"),
            ("v = fλ", "Hubungan gelombang")
        ],

        "contoh": "Oven microwave memanfaatkan interaksi gelombang mikro dengan bahan makanan."
    },

    "Inframerah": {
        "konsep": """
Inframerah merupakan radiasi elektromagnetik yang
berkaitan dengan radiasi termal.
""",

        "rumus": [
            ("E = hf", "Energi foton")
        ],

        "contoh": "Kamera termal mendeteksi radiasi inframerah dari objek."
    },

    "Cahaya tampak": {
        "konsep": """
Cahaya tampak merupakan rentang elektromagnetik
yang dapat dideteksi oleh mata manusia.
""",

        "rumus": [
            ("c = fλ", "Hubungan frekuensi dan panjang gelombang")
        ],

        "contoh": "Cahaya putih dapat diuraikan menjadi berbagai warna."
    },

    "Ultraviolet": {
        "konsep": """
Ultraviolet memiliki frekuensi lebih tinggi daripada
cahaya tampak.
""",

        "rumus": [
            ("E = hf", "Energi foton berbanding lurus dengan frekuensi")
        ],

        "contoh": "Radiasi ultraviolet dari Matahari dapat menyebabkan perubahan pada kulit."
    },

    "Sinar-X": {
        "konsep": """
Sinar-X dapat menembus materi dan mengalami penyerapan
berbeda oleh berbagai jaringan.
""",

        "rumus": [
            ("E = hf", "Energi foton")
        ],

        "contoh": "Sinar-X digunakan untuk menghasilkan citra tulang."
    },

    "Sinar gamma": {
        "konsep": """
Sinar gamma memiliki frekuensi sangat tinggi
dan energi foton tinggi.
""",

        "rumus": [
            ("E = hf", "Energi foton")
        ],

        "contoh": "Sinar gamma dapat berasal dari proses nuklir dan digunakan dalam bidang tertentu."
    },

    "Energi foton": {
        "konsep": """
Energi foton berbanding lurus dengan frekuensinya.
Semakin tinggi frekuensi, semakin besar energi foton.
""",

        "rumus": [
            ("E = hf", "Energi berdasarkan frekuensi"),
            ("E = hc/λ", "Energi berdasarkan panjang gelombang")
        ],

        "contoh": """
f = 5 × 10¹⁴ Hz
h = 6,626 × 10⁻³⁴ J.s

E = hf
E = 6,626 × 10⁻³⁴ × 5 × 10¹⁴
E = 3,313 × 10⁻¹⁹ J
"""
    },

    "Pemantulan gelombang": {
        "konsep": """
Pada pemantulan cahaya, sudut datang sama dengan
sudut pantul.
""",

        "rumus": [
            ("θᵢ = θᵣ", "Sudut datang sama dengan sudut pantul")
        ],

        "contoh": "Cahaya yang mengenai cermin datar dipantulkan dengan sudut yang sama terhadap garis normal."
    },

    "Pembiasan gelombang": {
        "konsep": """
Ketika cahaya memasuki medium berbeda,
frekuensinya tetap.

Cepat rambat dan panjang gelombangnya dapat berubah.
""",

        "rumus": [
            ("n₁ sin θ₁ = n₂ sin θ₂", "Hukum Snellius"),
            ("v = c/n", "Kecepatan cahaya dalam medium")
        ],

        "contoh": "Pensil dalam air tampak bengkok karena cahaya mengalami pembiasan."
    },

    "Polarisasi": {
        "konsep": """
Polarisasi adalah pembatasan arah getar gelombang transversal.
""",

        "rumus": [
            ("I = I₀ cos²θ", "Hukum Malus untuk cahaya terpolarisasi")
        ],

        "contoh": "Kacamata polarisasi mengurangi cahaya pantulan tertentu."
    },

    "Energi gelombang elektromagnetik": {
        "konsep": """
Gelombang elektromagnetik membawa energi yang dapat
ditransfer kepada benda ketika terjadi interaksi.
""",

        "rumus": [
            ("E = hf", "Energi foton"),
            ("P = E/t", "Daya merupakan energi per waktu")
        ],

        "contoh": "Panel surya mengubah energi radiasi elektromagnetik menjadi energi listrik."
    },

    "Kecepatan dalam medium": {
        "konsep": """
Indeks bias menunjukkan hubungan antara kecepatan
cahaya di ruang hampa dan dalam medium.
""",

        "rumus": [
            ("n = c/v", "Indeks bias"),
            ("v = c/n", "Kecepatan dalam medium")
        ],

        "contoh": "Cahaya merambat lebih lambat dalam kaca daripada di ruang hampa."
    },

    "Panjang gelombang": {
        "konsep": """
Panjang gelombang dipengaruhi oleh cepat rambat
dan frekuensi.
""",

        "rumus": [
            ("λ = v/f", "Panjang gelombang"),
            ("λ = c/f", "Panjang gelombang di ruang hampa")
        ],

        "contoh": "Jika frekuensi tetap dan cahaya memasuki medium dengan kecepatan lebih rendah, panjang gelombangnya berkurang."
    },

    "Aplikasi gelombang elektromagnetik": {
        "konsep": """
Gelombang elektromagnetik digunakan dalam komunikasi,
kesehatan, penginderaan, dan teknologi.
""",

        "rumus": [
            ("c = fλ", "Hubungan frekuensi dan panjang gelombang"),
            ("E = hf", "Energi foton")
        ],

        "contoh": "Radio digunakan untuk penyiaran, microwave untuk komunikasi, dan sinar-X untuk pencitraan medis."
    }
}

# =========================================================
# 11. SESSION STATE
# =========================================================

DEFAULT_STATE = {
    "pengguna": None,
    "halaman": "Beranda",
    "hasil_terakhir": [],
    "nilai_terakhir": 0,
    "jawaban_terakhir": []
}

for key, value in DEFAULT_STATE.items():

    if key not in st.session_state:
        st.session_state[key] = value

def ke_halaman(nama):

    st.session_state.halaman = nama

def keluar():

    st.session_state.pengguna = None
    st.session_state.halaman = "Beranda"
    st.session_state.hasil_terakhir = []
    st.session_state.nilai_terakhir = 0
    st.session_state.jawaban_terakhir = []

# =========================================================
# 12. STYLE
# =========================================================

def style_aplikasi():

    st.markdown("""
    <style>

    .hero {
        background: linear-gradient(120deg,#17345e,#087f8c);
        color: white;
        padding: 28px;
        border-radius: 16px;
        text-align: center;
        margin-bottom: 25px;
    }

    .hero h1 {
        font-size: 38px;
        font-weight: 800;
    }

    .small-note {
        color: #777;
        font-size: 14px;
    }

    </style>
    """, unsafe_allow_html=True)

def header():

    st.markdown("""
    <div class="hero">
        <h1>🧠 MISCONCEPT AI</h1>
        <p>Website Deteksi Miskonsepsi Fisika SMA</p>
        <p>Materi Gelombang Elektromagnetik</p>
    </div>
    """, unsafe_allow_html=True)

style_aplikasi()

# =========================================================
# 13. BERANDA
# =========================================================

def halaman_beranda():

    header()

    st.title("Selamat Datang di MISCONCEPT AI")

    st.write("""
    MISCONCEPT AI merupakan media pembelajaran fisika
    yang dirancang untuk membantu siswa memahami konsep
    gelombang elektromagnetik dan mengidentifikasi
    kemungkinan miskonsepsi melalui tes diagnostik Four-Tier.
    """)

    a, b, c = st.columns(3)

    a.metric("Jumlah Soal", "20")
    b.metric("Metode", "Four-Tier")
    c.metric("Materi", "Gelombang Elektromagnetik")

    st.subheader("Fitur Pembelajaran")

    fitur = [
        "Tes diagnostik Four-Tier",
        "Analisis jawaban dan alasan",
        "Penjelasan konsep otomatis",
        "Peta miskonsepsi",
        "Pembelajaran remedial",
        "Laboratorium virtual",
        "Riwayat tes",
        "Laporan guru"
    ]

    col1, col2 = st.columns(2)

    for i, fitur_item in enumerate(fitur):

        if i % 2 == 0:
            col1.write("✓ " + fitur_item)
        else:
            col2.write("✓ " + fitur_item)

    st.divider()

    col1, col2 = st.columns(2)

    with col1:

        if st.button("Login", use_container_width=True):

            ke_halaman("Login")
            st.rerun()

    with col2:

        if st.button("Daftar Siswa", use_container_width=True):

            ke_halaman("Daftar")
            st.rerun()

# =========================================================
# 14. LOGIN
# =========================================================

def halaman_login():

    header()

    st.title("Login")

    with st.form("login_form"):

        username = st.text_input("Username")

        password = st.text_input(
            "Password",
            type="password"
        )

        kirim = st.form_submit_button(
            "Login",
            use_container_width=True
        )

    if kirim:

        pengguna = login_pengguna(
            username.strip(),
            password
        )

        if pengguna:

            st.session_state.pengguna = pengguna
            st.session_state.halaman = "Dashboard"

            st.success("Login berhasil.")
            st.rerun()

        else:

            st.error("Username atau password salah.")

    if st.button("Kembali"):

        ke_halaman("Beranda")
        st.rerun()

# =========================================================
# 15. PENDAFTARAN
# =========================================================

def halaman_daftar():

    header()

    st.title("Pendaftaran Siswa")

    with st.form("daftar_form"):

        nama = st.text_input("Nama lengkap")

        username = st.text_input("Username")

        password = st.text_input(
            "Password",
            type="password"
        )

        konfirmasi = st.text_input(
            "Konfirmasi password",
            type="password"
        )

        kirim = st.form_submit_button("Daftar")

    if kirim:

        if not nama.strip() or not username.strip() or not password:

            st.warning("Semua kolom harus diisi.")

        elif len(password) < 8:

            st.warning("Password minimal 8 karakter.")

        elif password != konfirmasi:

            st.error("Konfirmasi password tidak sesuai.")

        else:

            berhasil, pesan = daftar_siswa(
                nama.strip(),
                username.strip(),
                password
            )

            if berhasil:
                st.success(pesan)
            else:
                st.error(pesan)

    if st.button("Kembali"):

        ke_halaman("Beranda")
        st.rerun()

# =========================================================
# 16. DASHBOARD SISWA
# =========================================================

def halaman_dashboard():

    header()

    pengguna = st.session_state.pengguna

    riwayat = ambil_riwayat_siswa(
        pengguna["id"]
    )

    st.title("Dashboard Siswa")

    st.write(
        f"Selamat datang, **{pengguna['nama']}**!"
    )

    a, b, c = st.columns(3)

    a.metric("Jumlah Tes", len(riwayat))

    b.metric("Jumlah Soal", 20)

    c.metric("Materi", "Gelombang EM")

    st.subheader("Aktivitas Pembelajaran")

    if not riwayat.empty:

        nilai_terakhir = riwayat.iloc[0]["nilai"]

        st.metric(
            "Nilai Tes Terakhir",
            f"{nilai_terakhir:.2f}/100"
        )

        if len(riwayat) > 1:

            nilai_sebelumnya = riwayat.iloc[1]["nilai"]

            perubahan = nilai_terakhir - nilai_sebelumnya

            st.metric(
                "Perubahan dari Tes Sebelumnya",
                f"{perubahan:+.2f}"
            )

    else:

        st.info(
            "Kamu belum mengerjakan tes diagnostik. "
            "Mulailah tes untuk mengetahui pemahaman konsep."
        )

    st.divider()

    if st.button(
        "📝 Mulai Tes Four-Tier",
        use_container_width=True
    ):

        ke_halaman("Tes Four-Tier")
        st.rerun()

    st.subheader("Menu Pembelajaran")

    col1, col2, col3 = st.columns(3)

    with col1:

        if st.button("📊 Hasil Diagnosis", use_container_width=True):

            ke_halaman("Hasil Diagnosis")
            st.rerun()

    with col2:

        if st.button("🗺️ Peta Miskonsepsi", use_container_width=True):

            ke_halaman("Peta Miskonsepsi")
            st.rerun()

    with col3:

        if st.button("📚 Remedial", use_container_width=True):

            ke_halaman("Pembelajaran Remedial")
            st.rerun()

# =========================================================
# 17. TES FOUR-TIER
# =========================================================

def halaman_tes():

    header()

    st.title("Tes Diagnostik Four-Tier")

    st.info("""
    Petunjuk:
    1. Pilih jawaban yang menurutmu benar.
    2. Tentukan tingkat keyakinan terhadap jawaban.
    3. Pilih alasan yang paling sesuai.
    4. Tentukan tingkat keyakinan terhadap alasan.
    """)

    jawaban_siswa = []

    with st.form("tes_form"):

        for i, soal in enumerate(SOAL):

            st.divider()

            st.markdown(f"### Soal {i + 1}")

            st.caption(soal["topik"])

            st.write(soal["pertanyaan"])

            jawaban = st.radio(
                "Tingkat 1 — Jawaban",
                soal["jawaban"],
                index=None,
                key=f"jawaban_{i}"
            )

            yakin_jawaban = st.radio(
                "Tingkat 2 — Keyakinan jawaban",
                ["Yakin", "Tidak yakin"],
                index=None,
                horizontal=True,
                key=f"yakin_jawaban_{i}"
            )

            alasan = st.radio(
                "Tingkat 3 — Alasan",
                soal["alasan"],
                index=None,
                key=f"alasan_{i}"
            )

            yakin_alasan = st.radio(
                "Tingkat 4 — Keyakinan alasan",
                ["Yakin", "Tidak yakin"],
                index=None,
                horizontal=True,
                key=f"yakin_alasan_{i}"
            )

            jawaban_siswa.append({
                "jawaban": jawaban,
                "yakin_jawaban": yakin_jawaban,
                "alasan": alasan,
                "yakin_alasan": yakin_alasan
            })

        konfirmasi = st.checkbox(
            "Saya sudah memeriksa seluruh jawaban."
        )

        kirim = st.form_submit_button(
            "Kirim Jawaban dan Analisis",
            use_container_width=True
        )

    if kirim:

        lengkap = all(
            item["jawaban"] is not None
            and item["yakin_jawaban"] is not None
            and item["alasan"] is not None
            and item["yakin_alasan"] is not None
            for item in jawaban_siswa
        )

        if not lengkap:

            st.warning(
                "Masih ada soal yang belum dijawab. "
                "Lengkapi seluruh tingkat pada setiap soal."
            )

        elif not konfirmasi:

            st.warning(
                "Centang konfirmasi sebelum mengirim."
            )

        else:

            hasil = analisis_jawaban(jawaban_siswa)

            nilai = hitung_nilai(hasil)

            st.session_state.hasil_terakhir = hasil

            st.session_state.nilai_terakhir = nilai

            st.session_state.jawaban_terakhir = jawaban_siswa

            simpan_hasil(
                st.session_state.pengguna["id"],
                "Diagnostik Four-Tier",
                nilai,
                hasil
            )

            st.session_state.halaman = "Hasil Diagnosis"

            st.success("Tes berhasil dianalisis.")

            st.rerun()

# =========================================================
# 18. HASIL DIAGNOSIS
# =========================================================

def halaman_hasil():

    header()

    st.title("Hasil Diagnosis")

    hasil = st.session_state.hasil_terakhir

    if not hasil:

        st.warning(
            "Belum ada hasil tes. Silakan mengerjakan tes terlebih dahulu."
        )

        return

    nilai = st.session_state.nilai_terakhir

    jumlah_soal = len(hasil)

    benar_jawaban = sum(
        item["jawaban_benar"] for item in hasil
    )

    benar_alasan = sum(
        item["alasan_benar"] for item in hasil
    )

    miskonsepsi = sum(
        item["kategori"] == "Indikasi Miskonsepsi"
        for item in hasil
    )

    a, b, c, d = st.columns(4)

    a.metric("Nilai", f"{nilai:.2f}/100")

    b.metric(
        "Jawaban Benar",
        f"{benar_jawaban}/{jumlah_soal}"
    )

    c.metric(
        "Alasan Benar",
        f"{benar_alasan}/{jumlah_soal}"
    )

    d.metric(
        "Indikasi Miskonsepsi",
        miskonsepsi
    )

    st.subheader("Ringkasan Kategori")

    kategori = pd.Series(
        [item["kategori"] for item in hasil]
    ).value_counts()

    tabel = kategori.rename_axis(
        "Kategori"
    ).reset_index(
        name="Jumlah Soal"
    )

    st.dataframe(
        tabel,
        use_container_width=True,
        hide_index=True
    )

    st.subheader("Interpretasi Hasil")

    if nilai >= 85:

        st.success(
            "Pemahaman konsep secara umum sudah baik. "
            "Tetap perhatikan materi yang masih menunjukkan "
            "ketidakkonsistenan antara jawaban dan alasan."
        )

    elif nilai >= 70:

        st.info(
            "Pemahaman konsep cukup baik, tetapi beberapa "
            "konsep perlu diperdalam."
        )

    elif nilai >= 50:

        st.warning(
            "Sebagian konsep sudah dipahami, tetapi masih "
            "terdapat beberapa bagian yang perlu dipelajari kembali."
        )

    else:

        st.warning(
            "Hasil menunjukkan bahwa beberapa konsep dasar "
            "perlu dipelajari kembali melalui pembelajaran remedial."
        )

    st.caption("""
    Nilai merupakan skor jawaban dan alasan. 
    Kategori diagnosis memperhatikan pola jawaban serta keyakinan.
    Indikasi miskonsepsi bukan diagnosis permanen terhadap siswa.
    """)

    st.divider()

    st.subheader("Pembahasan Setiap Soal")

    for item in hasil:

        with st.expander(
            f"Soal {item['nomor']} — {item['kategori']}"
        ):

            st.write("**Materi:**", item["topik"])

            st.write("**Pertanyaan:**", item["pertanyaan"])

            st.write(
                "**Jawaban siswa:**",
                item["jawaban_siswa"]
            )

            st.write(
                "**Keyakinan jawaban:**",
                item["keyakinan_jawaban"]
            )

            st.write(
                "**Alasan siswa:**",
                item["alasan_siswa"]
            )

            st.write(
                "**Keyakinan alasan:**",
                item["keyakinan_alasan"]
            )

            st.write(
                "**Kategori diagnosis:**",
                item["kategori"]
            )

            st.success(
                "Jawaban yang benar: "
                + item["jawaban_seharusnya"]
            )

            st.success(
                "Alasan yang benar: "
                + item["alasan_seharusnya"]
            )

            st.info(
                item["penjelasan"]
            )

            if item["kategori"] != "Paham Konsep":

                st.markdown("**Rekomendasi:**")

                st.write(
                    "Pelajari kembali materi "
                    + item["topik"]
                    + " melalui menu Pembelajaran Remedial."
                )

    st.divider()

    if st.button(
        "📚 Buka Pembelajaran Remedial",
        use_container_width=True
    ):

        ke_halaman("Pembelajaran Remedial")
        st.rerun()

# =========================================================
# 19. PETA MISKONSEPSI
# =========================================================

def halaman_peta():

    header()

    st.title("Peta Miskonsepsi")

    hasil = st.session_state.hasil_terakhir

    if not hasil:

        st.warning(
            "Selesaikan tes diagnostik terlebih dahulu."
        )

        return

    df = pd.DataFrame(hasil)

    st.subheader("Distribusi Kategori Diagnosis")

    distribusi = df["kategori"].value_counts()

    fig, ax = plt.subplots(figsize=(10, 5))

    distribusi.plot(
        kind="barh",
        ax=ax
    )

    ax.set_xlabel("Jumlah Soal")
    ax.set_ylabel("Kategori")
    ax.set_title("Distribusi Kategori Diagnosis")

    ax.grid(
        axis="x",
        linestyle="--",
        alpha=0.4
    )

    ax.invert_yaxis()

    plt.tight_layout()

    st.pyplot(fig)

    plt.close(fig)

    st.divider()

    st.subheader("Distribusi Diagnosis per Materi")

    tabel = pd.crosstab(
        df["topik"],
        df["kategori"]
    )

    st.dataframe(
        tabel,
        use_container_width=True
    )

    st.divider()

    st.subheader("Materi dengan Indikasi Miskonsepsi")

    data_miskonsepsi = df[
        df["kategori"] == "Indikasi Miskonsepsi"
    ]

    if data_miskonsepsi.empty:

        st.success(
            "Tidak terdapat indikasi miskonsepsi "
            "berdasarkan klasifikasi tes ini."
        )

    else:

        jumlah = data_miskonsepsi[
            "topik"
        ].value_counts()

        fig, ax = plt.subplots(figsize=(10, 5))

        jumlah.sort_values().plot(
            kind="barh",
            ax=ax
        )

        ax.set_xlabel("Jumlah Soal")
        ax.set_ylabel("Materi")
        ax.set_title("Materi dengan Indikasi Miskonsepsi")

        ax.grid(
            axis="x",
            linestyle="--",
            alpha=0.4
        )

        plt.tight_layout()

        st.pyplot(fig)

        plt.close(fig)

        st.metric(
            "Jumlah Indikasi Miskonsepsi",
            len(data_miskonsepsi)
        )

        st.subheader("Materi Prioritas")

        for topik in jumlah.index:

            st.write(
                "🔴 **" + topik + "**"
            )

            st.write(
                "Jumlah soal dengan indikasi miskonsepsi:",
                int(jumlah[topik])
            )

    st.caption("""
    Peta miskonsepsi menunjukkan pola jawaban pada tes.
    Hasil ini tidak dapat digunakan untuk menyimpulkan
    miskonsepsi permanen tanpa pemeriksaan lanjutan.
    """)

# =========================================================
# 20. PEMBELAJARAN REMEDIAL
# =========================================================

def halaman_remedial():

    header()

    st.title("Pembelajaran Remedial")

    hasil = st.session_state.hasil_terakhir

    if not hasil:

        st.info(
            "Kerjakan tes diagnostik terlebih dahulu "
            "agar rekomendasi materi dapat disesuaikan."
        )

        topik = st.selectbox(
            "Pilih materi yang ingin dipelajari",
            list(MATERI.keys())
        )

    else:

        perlu_dipelajari = list(dict.fromkeys(
            item["topik"]
            for item in hasil
            if item["kategori"] != "Paham Konsep"
        ))

        if perlu_dipelajari:

            st.info(
                "Materi berikut direkomendasikan berdasarkan hasil tes."
            )

            topik = st.selectbox(
                "Pilih materi remedial",
                perlu_dipelajari
            )

        else:

            st.success(
                "Semua soal berada dalam kategori Paham Konsep."
            )

            topik = st.selectbox(
                "Pilih materi untuk pengayaan",
                list(MATERI.keys())
            )

    materi = MATERI[topik]

    st.divider()

    st.subheader("1. Penjelasan Konsep")

    st.write(materi["konsep"])

    st.subheader("2. Rumus Penting")

    for rumus, keterangan in materi["rumus"]:

        st.markdown(f"### `{rumus}`")

        st.write(keterangan)

    st.subheader("3. Contoh Penerapan")

    st.write(materi["contoh"])

    st.divider()

    st.subheader("4. Latihan Mandiri")

    latihan = {

        "Frekuensi dan panjang gelombang":
            "Gelombang memiliki cepat rambat 3 × 10⁸ m/s dan frekuensi 6 × 10⁸ Hz. Berapakah panjang gelombangnya?",

        "Energi foton":
            "Foton memiliki frekuensi 5 × 10¹⁴ Hz. Hitung energi foton menggunakan h = 6,626 × 10⁻³⁴ J.s.",

        "Kecepatan dalam medium":
            "Jika indeks bias medium 1,5, hitung kecepatan cahaya di medium tersebut.",

        "Panjang gelombang":
            "Jika frekuensi cahaya 5 × 10¹⁴ Hz dan cepat rambatnya 2 × 10⁸ m/s, hitung panjang gelombangnya.",

        "Pembiasan gelombang":
            "Mengapa frekuensi cahaya tetap ketika memasuki medium berbeda?",

        "Pemantulan gelombang":
            "Jika sudut datang cahaya 35° terhadap garis normal, berapakah sudut pantulnya?",

        "Polarisasi":
            "Mengapa polarisasi dapat digunakan sebagai bukti bahwa cahaya merupakan gelombang transversal?"
    }

    pertanyaan_latihan = latihan.get(
        topik,
        "Jelaskan konsep " + topik + " dan berikan contoh penerapannya dalam kehidupan sehari-hari."
    )

    st.write(pertanyaan_latihan)

    jawaban_latihan = st.text_area(
        "Tuliskan jawabanmu",
        key=f"latihan_{topik}"
    )

    if st.button("Periksa Jawaban Latihan"):

        if not jawaban_latihan.strip():

            st.warning("Tuliskan jawaban terlebih dahulu.")

        else:

            st.info("""
            Bandingkan jawabanmu dengan penjelasan konsep
            dan rumus yang tersedia di atas.

            Pastikan kamu menuliskan:
            - Konsep yang digunakan
            - Rumus yang sesuai
            - Substitusi nilai
            - Satuan
            - Kesimpulan
            """)

    st.divider()

    if st.button(
        "Kembali ke Hasil Diagnosis",
        use_container_width=True
    ):

        ke_halaman("Hasil Diagnosis")
        st.rerun()

# =========================================================
# 21. LABORATORIUM VIRTUAL
# =========================================================

def halaman_laboratorium():

    header()

    st.title("Laboratorium Virtual Gelombang Elektromagnetik")

    st.write("""
    Laboratorium ini digunakan untuk mengamati hubungan
    frekuensi, panjang gelombang, cepat rambat, indeks bias,
    dan energi foton secara matematis.
    """)

    st.divider()

    st.subheader("A. Pengaturan Simulasi")

    col1, col2 = st.columns(2)

    with col1:

        pangkat_f = st.slider(
            "Pangkat frekuensi",
            6,
            20,
            14
        )

        frekuensi = 10.0 ** pangkat_f

        st.write(
            f"Frekuensi: **{frekuensi:.3e} Hz**"
        )

    with col2:

        indeks_bias = st.slider(
            "Indeks bias medium",
            min_value=1.0,
            max_value=2.5,
            value=1.5,
            step=0.1
        )

    st.caption("""
    Frekuensi ditampilkan dalam bentuk 10ⁿ Hz.
    Indeks bias 1,0 digunakan sebagai pendekatan ruang hampa.
    """)

    # Perhitungan

    lambda_vakum = C / frekuensi

    kecepatan_medium = C / indeks_bias

    lambda_medium = kecepatan_medium / frekuensi

    periode = 1 / frekuensi

    energi = H * frekuensi

    energi_ev = energi / 1.602176634e-19

    # =====================================================
    # METRIK
    # =====================================================

    st.subheader("B. Hasil Perhitungan")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Panjang Gelombang Vakum",
        f"{lambda_vakum:.3e} m"
    )

    col2.metric(
        "Kecepatan dalam Medium",
        f"{kecepatan_medium:.3e} m/s"
    )

    col3.metric(
        "Panjang Gelombang Medium",
        f"{lambda_medium:.3e} m"
    )

    col4, col5, col6 = st.columns(3)

    col4.metric(
        "Periode",
        f"{periode:.3e} s"
    )

    col5.metric(
        "Energi Foton",
        f"{energi:.3e} J"
    )

    col6.metric(
        "Energi Foton",
        f"{energi_ev:.3e} eV"
    )

    # =====================================================
    # RUMUS
    # =====================================================

    st.subheader("C. Rumus yang Digunakan")

    st.latex(r"c = f\lambda_0")

    st.latex(r"\lambda_0 = \frac{c}{f}")

    st.latex(r"n = \frac{c}{v}")

    st.latex(r"v = \frac{c}{n}")

    st.latex(r"\lambda_m = \frac{v}{f}")

    st.latex(r"E = hf")

    st.latex(r"T = \frac{1}{f}")

    st.write("**Keterangan:**")

    st.write("""
    - c = cepat rambat cahaya di ruang hampa (m/s)
    - v = cepat rambat dalam medium (m/s)
    - f = frekuensi (Hz)
    - λ₀ = panjang gelombang di ruang hampa (m)
    - λm = panjang gelombang dalam medium (m)
    - n = indeks bias
    - E = energi foton (J)
    - h = konstanta Planck (J.s)
    - T = periode (s)
    """)

    st.divider()

    # =====================================================
    # CONTOH PERHITUNGAN
    # =====================================================

    st.subheader("D. Langkah Perhitungan")

    st.write("**1. Panjang gelombang di ruang hampa**")

    st.latex(
        rf"\lambda_0 = \frac{{{C:.0f}}}{{{frekuensi:.3e}}}"
    )

    st.latex(
        rf"\lambda_0 = {lambda_vakum:.3e}\ \mathrm{{m}}"
    )

    st.write("**2. Kecepatan dalam medium**")

    st.latex(
        rf"v = \frac{{{C:.0f}}}{{{indeks_bias}}}"
    )

    st.latex(
        rf"v = {kecepatan_medium:.3e}\ \mathrm{{m/s}}"
    )

    st.write("**3. Panjang gelombang dalam medium**")

    st.latex(
        rf"\lambda_m = \frac{{{kecepatan_medium:.3e}}}{{{frekuensi:.3e}}}"
    )

    st.latex(
        rf"\lambda_m = {lambda_medium:.3e}\ \mathrm{{m}}"
    )

    st.write("**4. Energi foton**")

    st.latex(
        rf"E = ({H:.3e})({frekuensi:.3e})"
    )

    st.latex(
        rf"E = {energi:.3e}\ \mathrm{{J}}"
    )

    st.divider()

    # =====================================================
    # GRAFIK GELOMBANG
    # =====================================================

    st.subheader("E. Grafik Gelombang")

    jumlah_gelombang = st.slider(
        "Jumlah gelombang yang ditampilkan",
        1,
        5,
        2
    )

    x = np.linspace(
        0,
        jumlah_gelombang * lambda_medium,
        1000
    )

    fase = 2 * np.pi * x / lambda_medium

    medan_listrik = np.sin(fase)

    medan_magnet = np.sin(fase)

    fig, ax = plt.subplots(figsize=(11, 5))

    ax.plot(
        x,
        medan_listrik,
        label="Medan listrik (relatif)"
    )

    ax.plot(
        x,
        medan_magnet,
        linestyle="--",
        label="Medan magnet (relatif)"
    )

    ax.set_title(
        "Representasi Gelombang Elektromagnetik"
    )

    ax.set_xlabel(
        "Posisi (m)"
    )

    ax.set_ylabel(
        "Amplitudo relatif"
    )

    ax.grid(True)

    ax.legend()

    plt.tight_layout()

    st.pyplot(fig)

    plt.close(fig)

    st.info("""
    Grafik ini merupakan representasi matematis dua medan
    sebagai fungsi posisi. Medan listrik dan medan magnet
    pada gelombang elektromagnetik ideal sefase, tetapi
    arahnya saling tegak lurus.

    Grafik ini bukan visualisasi vektor tiga dimensi.
    Amplitudo yang digunakan bersifat relatif dan bukan
    hasil pengukuran medan listrik atau medan magnet.
    """)

    st.divider()

    # =====================================================
    # SPEKTRUM ELEKTROMAGNETIK
    # =====================================================

    st.subheader("F. Posisi pada Spektrum Elektromagnetik")

    fig, ax = plt.subplots(figsize=(12, 3.5))

    batas = [
        1e3,
        3e8,
        3e11,
        4.3e14,
        7.5e14,
        3e16,
        3e19,
        1e22
    ]

    nama = [
        "Radio",
        "Mikro",
        "Inframerah",
        "Tampak",
        "Ultraviolet",
        "Sinar-X",
        "Gamma"
    ]

    for i in range(len(nama)):

        ax.axvspan(
            batas[i],
            batas[i + 1],
            alpha=0.2
        )

        titik_tengah = math.sqrt(
            batas[i] * batas[i + 1]
        )

        ax.text(
            titik_tengah,
            0.65,
            nama[i],
            ha="center",
            va="center",
            fontsize=9
        )

    ax.axvline(
        frekuensi,
        linestyle="--",
        linewidth=2,
        label=f"Frekuensi simulasi: {frekuensi:.2e} Hz"
    )

    ax.set_xscale("log")

    ax.set_xlim(
        batas[0],
        batas[-1]
    )

    ax.set_ylim(
        0,
        1
    )

    ax.set_yticks([])

    ax.set_xlabel("Frekuensi (Hz)")

    ax.set_title(
        "Spektrum Elektromagnetik"
    )

    ax.legend(
        loc="upper center"
    )

    ax.grid(
        axis="x",
        which="both",
        linestyle=":"
    )

    plt.tight_layout()

    st.pyplot(fig)

    plt.close(fig)

    st.caption("""
    Batas rentang spektrum merupakan pendekatan.
    Klasifikasi radio, mikro, inframerah, dan lainnya
    dapat memiliki batas yang berbeda pada berbagai referensi.
    """)

    # =====================================================
    # INTERPRETASI
    # =====================================================

    st.subheader("G. Interpretasi Hasil")

    st.write(
        f"""
        Frekuensi yang dipilih adalah **{frekuensi:.3e} Hz**.

        Panjang gelombang di ruang hampa adalah
        **{lambda_vakum:.3e} m**.

        Ketika gelombang memasuki medium dengan indeks bias
        **{indeks_bias}**, cepat rambatnya menjadi
        **{kecepatan_medium:.3e} m/s**.

        Panjang gelombang dalam medium menjadi
        **{lambda_medium:.3e} m**.

        Frekuensi tetap karena ditentukan oleh sumber.
        """

    )

    if indeks_bias > 1:

        st.info("""
        Ketika indeks bias meningkat, kecepatan cahaya
        dalam medium berkurang. Jika frekuensi tetap,
        panjang gelombang juga berkurang.
        """)

    else:

        st.success("""
        Indeks bias 1,0 digunakan sebagai pendekatan
        ruang hampa. Kecepatan gelombang sama dengan c.
        """)

# =========================================================
# 22. RIWAYAT TES
# =========================================================

def halaman_riwayat():

    header()

    st.title("Riwayat Tes")

    pengguna = st.session_state.pengguna

    df = ambil_riwayat_siswa(
        pengguna["id"]
    )

    if df.empty:

        st.info("Belum ada riwayat tes.")

        return

    st.subheader("Daftar Riwayat")

    tampil = df.drop(
        columns=["hasil_json", "id"]
    )

    st.dataframe(
        tampil,
        use_container_width=True,
        hide_index=True
    )

    pilihan = st.selectbox(
        "Pilih tes",
        options=list(range(len(df))),

        format_func=lambda i: (
            f"{df.iloc[i]['tanggal']} | "
            f"{df.iloc[i]['nilai']:.2f} | "
            f"{df.iloc[i]['jenis_tes']}"
        )
    )

    if st.button(
        "Buka Hasil Tes",
        use_container_width=True
    ):

        hasil_lama = json.loads(
            df.iloc[pilihan]["hasil_json"]
        )

        st.session_state.hasil_terakhir = hasil_lama

        st.session_state.nilai_terakhir = float(
            df.iloc[pilihan]["nilai"]
        )

        st.session_state.halaman = "Hasil Diagnosis"

        st.rerun()

    st.divider()

    st.subheader("Grafik Perkembangan Nilai")

    grafik = df.copy()

    grafik["tanggal"] = pd.to_datetime(
        grafik["tanggal"]
    )

    grafik = grafik.sort_values(
        "tanggal"
    )

    fig, ax = plt.subplots(figsize=(10, 4))

    ax.plot(
        grafik["tanggal"],
        grafik["nilai"],
        marker="o"
    )

    ax.set_xlabel("Tanggal Tes")

    ax.set_ylabel("Nilai")

    ax.set_ylim(0, 100)

    ax.set_title("Perkembangan Nilai Tes")

    ax.grid(True)

    plt.xticks(rotation=30)

    plt.tight_layout()

    st.pyplot(fig)

    plt.close(fig)

# =========================================================
# 23. DASHBOARD GURU
# =========================================================

def halaman_guru():

    header()

    st.title("Dashboard Guru")

    siswa = ambil_semua_siswa()

    hasil = ambil_semua_hasil()

    a, b, c, d = st.columns(4)

    a.metric(
        "Jumlah Siswa",
        len(siswa)
    )

    b.metric(
        "Jumlah Tes",
        len(hasil)
    )

    rata_rata = (
        round(hasil["nilai"].mean(), 2)
        if not hasil.empty
        else 0
    )

    c.metric(
        "Rata-rata Nilai",
        rata_rata
    )

    d.metric(
        "Nilai Tertinggi",
        round(hasil["nilai"].max(), 2)
        if not hasil.empty
        else 0
    )

    st.divider()

    st.subheader("Data Siswa")

    st.dataframe(
        siswa,
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    st.subheader("Laporan Hasil Tes")

    if hasil.empty:

        st.info("Belum ada hasil tes siswa.")

        return

    laporan = hasil.drop(
        columns=["hasil_json", "user_id", "test_id"]
    )

    st.dataframe(
        laporan,
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # =====================================================
    # GRAFIK NILAI SISWA
    # =====================================================

    st.subheader("Grafik Nilai Siswa")

    grafik_nilai = hasil.copy()

    grafik_nilai["label"] = (
        grafik_nilai["nama"]
        + " | "
        + grafik_nilai["tanggal"].astype(str)
    )

    fig, ax = plt.subplots(figsize=(11, 5))

    ax.bar(
        grafik_nilai["label"],
        grafik_nilai["nilai"]
    )

    ax.set_ylabel("Nilai")

    ax.set_ylim(0, 100)

    ax.set_title("Nilai Tes Siswa")

    ax.grid(
        axis="y",
        linestyle="--",
        alpha=0.4
    )

    plt.xticks(
        rotation=45,
        ha="right"
    )

    plt.tight_layout()

    st.pyplot(fig)

    plt.close(fig)

    st.divider()

    # =====================================================
    # ANALISIS DIAGNOSIS SISWA
    # =====================================================

    st.subheader("Analisis Kategori Diagnosis")

    rincian = []

    for _, baris in hasil.iterrows():

        try:

            daftar_hasil = json.loads(
                baris["hasil_json"]
            )

        except Exception:

            daftar_hasil = []

        for item in daftar_hasil:

            rincian.append({

                "Nama": baris["nama"],

                "Username": baris["username"],

                "Tanggal": baris["tanggal"],

                "Nomor Soal": item.get("nomor"),

                "Materi": item.get("topik"),

                "Kategori": item.get("kategori"),

                "Jawaban": item.get("jawaban_siswa"),

                "Alasan": item.get("alasan_siswa")

            })

    df_rincian = pd.DataFrame(rincian)

    if not df_rincian.empty:

        st.subheader("Distribusi Kategori")

        distribusi = df_rincian[
            "Kategori"
        ].value_counts()

        fig, ax = plt.subplots(figsize=(10, 5))

        distribusi.sort_values().plot(
            kind="barh",
            ax=ax
        )

        ax.set_xlabel("Jumlah")

        ax.set_ylabel("Kategori")

        ax.set_title(
            "Distribusi Diagnosis Seluruh Siswa"
        )

        ax.grid(
            axis="x",
            linestyle="--",
            alpha=0.4
        )

        plt.tight_layout()

        st.pyplot(fig)

        plt.close(fig)

        st.subheader("Materi yang Memerlukan Perhatian")

        tabel_materi = pd.crosstab(
            df_rincian["Materi"],
            df_rincian["Kategori"]
        )

        st.dataframe(
            tabel_materi,
            use_container_width=True
        )

        st.subheader("Rincian Diagnosis")

        st.dataframe(
            df_rincian,
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    # =====================================================
    # EKSPOR EXCEL
    # =====================================================

    st.subheader("Ekspor Laporan")

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        laporan.to_excel(
            writer,
            index=False,
            sheet_name="Ringkasan Tes"
        )

        siswa.to_excel(
            writer,
            index=False,
            sheet_name="Data Siswa"
        )

        if not df_rincian.empty:

            df_rincian.to_excel(
                writer,
                index=False,
                sheet_name="Rincian Diagnosis"
            )

            tabel_materi.to_excel(
                writer,
                sheet_name="Analisis Materi"
            )

    st.download_button(
        label="📥 Download Laporan Excel",
        data=output.getvalue(),
        file_name="laporan_misconcept_ai.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# =========================================================
# 24. SIDEBAR DAN NAVIGASI
# =========================================================

def tampilkan_sidebar():

    pengguna = st.session_state.pengguna

    st.sidebar.title("🧠 MISCONCEPT AI")

    if pengguna is None:

        st.sidebar.caption("Menu Pengunjung")

        daftar_menu = [
            ("🏠 Beranda", "Beranda"),
            ("🔐 Login", "Login"),
            ("📝 Daftar Siswa", "Daftar")
        ]

    elif pengguna["role"] == "Siswa":

        st.sidebar.caption(
            f"Siswa: {pengguna['nama']}"
        )

        daftar_menu = [
            ("🏠 Dashboard", "Dashboard"),
            ("📝 Tes Four-Tier", "Tes Four-Tier"),
            ("📊 Hasil Diagnosis", "Hasil Diagnosis"),
            ("🗺️ Peta Miskonsepsi", "Peta Miskonsepsi"),
            ("📚 Pembelajaran Remedial", "Pembelajaran Remedial"),
            ("🌐 Laboratorium Virtual", "Laboratorium Virtual"),
            ("📋 Riwayat Tes", "Riwayat Tes")
        ]

    elif pengguna["role"] == "Guru":

        st.sidebar.caption(
            f"Guru: {pengguna['nama']}"
        )

        daftar_menu = [
            ("📊 Dashboard Guru", "Dashboard Guru")
        ]

    else:

        daftar_menu = [
            ("🏠 Beranda", "Beranda")
        ]

    for label, halaman in daftar_menu:

        if st.sidebar.button(
            label,
            key=f"nav_{halaman}",
            use_container_width=True
        ):

            ke_halaman(halaman)
            st.rerun()

    if pengguna is not None:

        st.sidebar.divider()

        st.sidebar.write(
            f"**{pengguna['nama']}**"
        )

        st.sidebar.write(
            f"Peran: {pengguna['role']}"
        )

        if st.sidebar.button(
            "🚪 Logout",
            use_container_width=True
        ):

            keluar()
            st.rerun()

# =========================================================
# 25. ROUTING HALAMAN
# =========================================================

def jalankan_aplikasi():

    tampilkan_sidebar()

    halaman = st.session_state.halaman

    pengguna = st.session_state.pengguna

    # -----------------------------------------
    # PENGUNJUNG
    # -----------------------------------------

    if pengguna is None:

        halaman_pengunjung = {
            "Beranda": halaman_beranda,
            "Login": halaman_login,
            "Daftar": halaman_daftar
        }

        fungsi = halaman_pengunjung.get(
            halaman,
            halaman_beranda
        )

        fungsi()

    # -----------------------------------------
    # SISWA
    # -----------------------------------------

    elif pengguna["role"] == "Siswa":

        halaman_siswa = {

            "Dashboard": halaman_dashboard,

            "Tes Four-Tier": halaman_tes,

            "Hasil Diagnosis": halaman_hasil,

            "Peta Miskonsepsi": halaman_peta,

            "Pembelajaran Remedial": halaman_remedial,

            "Laboratorium Virtual": halaman_laboratorium,

            "Riwayat Tes": halaman_riwayat

        }

        fungsi = halaman_siswa.get(
            halaman,
            halaman_dashboard
        )

        fungsi()

    # -----------------------------------------
    # GURU
    # -----------------------------------------

    elif pengguna["role"] == "Guru":

        halaman_guru()

    else:

        keluar()

        halaman_beranda()

# =========================================================
# 26. JALANKAN
# =========================================================

jalankan_aplikasi()
import streamlit as st
import sqlite3
import hashlib
import secrets
import json
import io
import math
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from datetime import datetime

# =========================================================
# 1. KONFIGURASI
# =========================================================

st.set_page_config(
    page_title="MISKONSEPTION",
    page_icon="🧠",
    layout="wide"
)

# Nama database tidak diubah agar data lama tetap digunakan.
DATABASE = "misconcept_ai.db"

C = 299792458          # Kecepatan cahaya (m/s)
H = 6.62607015e-34    # Konstanta Planck (J.s)


# =========================================================
# 2. DATABASE
# =========================================================

def koneksi_database():
    conn = sqlite3.connect(DATABASE)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def inisialisasi_database():

    conn = koneksi_database()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            jenis_tes TEXT NOT NULL,
            nilai REAL NOT NULL,
            hasil_json TEXT NOT NULL,
            tanggal TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# 3. PASSWORD
# =========================================================

def buat_hash_password(password, salt=None):

    if salt is None:
        salt = secrets.token_hex(16)

    hasil = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000
    ).hex()

    return salt, hasil


def verifikasi_password(password, salt, hash_asli):

    _, hash_baru = buat_hash_password(password, salt)

    return secrets.compare_digest(
        hash_baru,
        hash_asli
    )


# =========================================================
# 4. REGISTRASI
# =========================================================

def daftar_siswa(nama, username, password):

    conn = koneksi_database()
    cursor = conn.cursor()

    salt, password_hash = buat_hash_password(password)

    try:

        cursor.execute("""
            INSERT INTO users
            (nama, username, salt, password_hash, role)
            VALUES (?, ?, ?, ?, ?)
        """, (
            nama,
            username,
            salt,
            password_hash,
            "Siswa"
        ))

        conn.commit()

        berhasil = True
        pesan = "Pendaftaran berhasil."

    except sqlite3.IntegrityError:

        berhasil = False
        pesan = "Username telah digunakan."

    conn.close()

    return berhasil, pesan


# =========================================================
# 5. LOGIN
# =========================================================

def login_pengguna(username, password):

    conn = koneksi_database()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nama, username, salt, password_hash, role
        FROM users
        WHERE username = ?
    """, (username,))

    data = cursor.fetchone()
    conn.close()

    if data is None:
        return None

    if verifikasi_password(
        password,
        data[3],
        data[4]
    ):

        return {
            "id": data[0],
            "nama": data[1],
            "username": data[2],
            "role": data[5]
        }

    return None


# =========================================================
# 6. MENYIMPAN HASIL
# =========================================================

def simpan_hasil(user_id, jenis_tes, nilai, hasil):

    conn = koneksi_database()

    conn.execute("""
        INSERT INTO results
        (user_id, jenis_tes, nilai, hasil_json, tanggal)
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        jenis_tes,
        nilai,
        json.dumps(hasil, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


def ambil_riwayat_siswa(user_id):

    conn = koneksi_database()

    df = pd.read_sql_query("""
        SELECT id, jenis_tes, nilai, tanggal, hasil_json
        FROM results
        WHERE user_id = ?
        ORDER BY id DESC
    """, conn, params=(user_id,))

    conn.close()

    return df


def ambil_semua_hasil():

    conn = koneksi_database()

    df = pd.read_sql_query("""
        SELECT
            users.id AS user_id,
            users.nama,
            users.username,
            results.id AS test_id,
            results.jenis_tes,
            results.nilai,
            results.tanggal,
            results.hasil_json
        FROM results
        JOIN users ON users.id = results.user_id
        ORDER BY results.id DESC
    """, conn)

    conn.close()

    return df


def ambil_semua_siswa():

    conn = koneksi_database()

    df = pd.read_sql_query("""
        SELECT id, nama, username
        FROM users
        WHERE role = 'Siswa'
        ORDER BY nama
    """, conn)

    conn.close()

    return df


inisialisasi_database()


# =========================================================
# 7. BANK SOAL FOUR-TIER
# =========================================================

SOAL = [
    {
        "topik": "Konsep dasar gelombang elektromagnetik",
        "pertanyaan": "Gelombang elektromagnetik dapat merambat tanpa medium karena ...",
        "jawaban": [
            "Memerlukan partikel udara",
            "Medan listrik dan medan magnet yang berubah saling berkaitan",
            "Merupakan gelombang bunyi",
            "Tidak membawa energi"
        ],
        "benar": 1,
        "alasan": [
            "Semua gelombang memerlukan udara",
            "Medan listrik dan medan magnet yang berubah saling berkaitan",
            "Gelombang elektromagnetik adalah gelombang mekanik",
            "Gelombang elektromagnetik tidak membawa energi"
        ],
        "alasan_benar": 1,
        "penjelasan": "Gelombang elektromagnetik dapat merambat di ruang hampa. Gelombang ini tersusun dari medan listrik dan medan magnet yang berubah serta saling berkaitan."
    },
    {
        "topik": "Sifat gelombang elektromagnetik",
        "pertanyaan": "Gelombang elektromagnetik bersifat transversal karena ...",
        "jawaban": [
            "Getarnya sejajar arah rambat",
            "Medan listrik dan medan magnet tegak lurus arah rambat",
            "Tidak mempunyai arah rambat",
            "Hanya merambat dalam zat padat"
        ],
        "benar": 1,
        "alasan": [
            "Semua gelombang memiliki getaran sejajar arah rambat",
            "Medan listrik dan medan magnet tegak lurus terhadap arah rambat",
            "Gelombang elektromagnetik tidak memiliki arah",
            "Gelombang elektromagnetik adalah gelombang longitudinal"
        ],
        "alasan_benar": 1,
        "penjelasan": "Gelombang elektromagnetik merupakan gelombang transversal. Medan listrik, medan magnet, dan arah rambat saling tegak lurus."
    },
    {
        "topik": "Kecepatan gelombang elektromagnetik",
        "pertanyaan": "Cepat rambat cahaya di ruang hampa mendekati ...",
        "jawaban": [
            "340 m/s",
            "3 × 10⁶ m/s",
            "3 × 10⁸ m/s",
            "3 × 10¹⁰ m/s"
        ],
        "benar": 2,
        "alasan": [
            "Sama dengan kecepatan bunyi",
            "Merupakan nilai pendekatan cepat rambat cahaya di ruang hampa",
            "Semua gelombang memiliki kecepatan bunyi",
            "Cahaya tidak mempunyai kecepatan"
        ],
        "alasan_benar": 1,
        "penjelasan": "Cepat rambat cahaya di ruang hampa adalah 299.792.458 m/s, atau sekitar 3 × 10⁸ m/s."
    },
    {
        "topik": "Frekuensi dan panjang gelombang",
        "pertanyaan": "Jika cepat rambat tetap dan frekuensi meningkat, panjang gelombang akan ...",
        "jawaban": [
            "Bertambah",
            "Berkurang",
            "Tetap",
            "Menjadi nol"
        ],
        "benar": 1,
        "alasan": [
            "Frekuensi dan panjang gelombang berbanding lurus",
            "v = fλ, sehingga jika v tetap, f meningkat maka λ berkurang",
            "Frekuensi tidak berhubungan dengan panjang gelombang",
            "Cepat rambat menjadi nol"
        ],
        "alasan_benar": 1,
        "penjelasan": "Hubungan v = fλ menunjukkan bahwa ketika cepat rambat tetap, frekuensi dan panjang gelombang berbanding terbalik."
    },
    {
        "topik": "Spektrum elektromagnetik",
        "pertanyaan": "Urutan spektrum dari frekuensi rendah menuju tinggi adalah ...",
        "jawaban": [
            "Gamma, X, ultraviolet, tampak, inframerah, mikro, radio",
            "Radio, mikro, inframerah, tampak, ultraviolet, X, gamma",
            "Tampak, radio, gamma, mikro, ultraviolet, inframerah, X",
            "Inframerah, radio, tampak, mikro, gamma, X, ultraviolet"
        ],
        "benar": 1,
        "alasan": [
            "Radio memiliki frekuensi paling tinggi",
            "Frekuensi meningkat dari radio menuju gamma",
            "Gamma memiliki panjang gelombang terbesar",
            "Urutan spektrum tidak berkaitan dengan frekuensi"
        ],
        "alasan_benar": 1,
        "penjelasan": "Urutannya adalah radio, mikro, inframerah, cahaya tampak, ultraviolet, sinar-X, dan sinar gamma."
    },
    {
        "topik": "Gelombang radio",
        "pertanyaan": "Gelombang radio dimanfaatkan untuk ...",
        "jawaban": [
            "Komunikasi dan penyiaran",
            "Pemeriksaan tulang",
            "Menghasilkan suara secara langsung",
            "Melihat benda dengan mata"
        ],
        "benar": 0,
        "alasan": [
            "Gelombang radio dapat membawa informasi melalui modulasi",
            "Gelombang radio memiliki energi foton tertinggi",
            "Gelombang radio merupakan gelombang bunyi",
            "Mata manusia dapat melihat gelombang radio"
        ],
        "alasan_benar": 0,
        "penjelasan": "Gelombang radio digunakan untuk komunikasi, penyiaran, dan pengiriman informasi secara nirkabel."
    },
    {
        "topik": "Gelombang mikro",
        "pertanyaan": "Oven microwave memanfaatkan gelombang mikro untuk ...",
        "jawaban": [
            "Menghasilkan bunyi",
            "Berinteraksi dengan bahan makanan dan menghasilkan pemanasan",
            "Mengubah makanan menjadi cahaya",
            "Menghilangkan massa makanan"
        ],
        "benar": 1,
        "alasan": [
            "Gelombang mikro dapat berinteraksi dengan komponen makanan dan mengubah energi menjadi energi termal",
            "Gelombang mikro merupakan gelombang mekanik",
            "Semua gelombang menghasilkan pemanasan yang sama",
            "Makanan hanya dapat dipanaskan oleh udara"
        ],
        "alasan_benar": 0,
        "penjelasan": "Gelombang mikro berinteraksi dengan bahan makanan. Energi elektromagnetik kemudian berubah menjadi energi termal melalui berbagai mekanisme interaksi."
    },
    {
        "topik": "Inframerah",
        "pertanyaan": "Radiasi inframerah berkaitan erat dengan ...",
        "jawaban": [
            "Radiasi termal",
            "Gelombang bunyi",
            "Arus listrik",
            "Gelombang air"
        ],
        "benar": 0,
        "alasan": [
            "Benda dapat memancarkan radiasi inframerah sesuai suhu dan karakteristik permukaannya",
            "Inframerah merupakan gelombang mekanik",
            "Inframerah tidak membawa energi",
            "Inframerah hanya dihasilkan oleh benda beku"
        ],
        "alasan_benar": 0,
        "penjelasan": "Banyak benda memancarkan radiasi inframerah sebagai bagian dari radiasi termal. Kamera termal dapat mendeteksi radiasi tersebut."
    },
    {
        "topik": "Cahaya tampak",
        "pertanyaan": "Cahaya tampak adalah gelombang elektromagnetik yang ...",
        "jawaban": [
            "Dapat dideteksi mata manusia",
            "Tidak membawa energi",
            "Memiliki frekuensi paling rendah",
            "Hanya merambat dalam air"
        ],
        "benar": 0,
        "alasan": [
            "Retina manusia peka terhadap rentang frekuensi tertentu",
            "Semua gelombang elektromagnetik dapat dilihat",
            "Cahaya tampak tidak memiliki panjang gelombang",
            "Cahaya tampak merupakan gelombang bunyi"
        ],
        "alasan_benar": 0,
        "penjelasan": "Mata manusia dapat mendeteksi rentang cahaya tampak. Gelombang elektromagnetik lainnya tidak dapat dilihat langsung oleh mata."
    },
    {
        "topik": "Ultraviolet",
        "pertanyaan": "Frekuensi ultraviolet dibandingkan cahaya tampak adalah ...",
        "jawaban": [
            "Lebih rendah",
            "Lebih tinggi",
            "Selalu sama",
            "Nol"
        ],
        "benar": 1,
        "alasan": [
            "Ultraviolet berada di bawah inframerah",
            "Ultraviolet memiliki frekuensi lebih tinggi daripada cahaya tampak",
            "Ultraviolet merupakan gelombang mekanik",
            "Frekuensi tidak berkaitan dengan spektrum"
        ],
        "alasan_benar": 1,
        "penjelasan": "Ultraviolet memiliki frekuensi lebih tinggi dan panjang gelombang lebih pendek daripada cahaya tampak."
    },

    {
        "topik": "Sinar-X",
        "pertanyaan": "Sinar-X dalam bidang medis digunakan untuk ...",
        "jawaban": [
            "Pencitraan bagian dalam tubuh",
            "Mendengar detak jantung",
            "Mengukur kelembapan udara",
            "Menghasilkan gelombang suara"
        ],
        "benar": 0,
        "alasan": [
            "Sinar-X diserap jaringan tubuh dengan tingkat berbeda",
            "Sinar-X adalah gelombang suara",
            "Sinar-X hanya dipantulkan kulit",
            "Sinar-X tidak berinteraksi dengan materi"
        ],
        "alasan_benar": 0,
        "penjelasan": "Sinar-X dapat menembus jaringan tubuh. Perbedaan penyerapan oleh jaringan dan tulang menghasilkan citra."
    },

    {
        "topik": "Sinar gamma",
        "pertanyaan": "Radiasi dengan frekuensi paling tinggi di antara pilihan berikut adalah ...",
        "jawaban": [
            "Radio",
            "Inframerah",
            "Cahaya tampak",
            "Gamma"
        ],
        "benar": 3,
        "alasan": [
            "Radio memiliki energi foton paling besar",
            "Gamma berada pada bagian frekuensi sangat tinggi",
            "Cahaya tampak memiliki frekuensi tidak terbatas",
            "Inframerah memiliki panjang gelombang terpendek"
        ],
        "alasan_benar": 1,
        "penjelasan": "Sinar gamma memiliki frekuensi sangat tinggi dan energi foton tinggi. Namun batas antara sinar-X dan gamma dapat ditentukan berdasarkan asal radiasi juga."
    },

    {
        "topik": "Energi foton",
        "pertanyaan": "Energi foton berbanding lurus dengan ...",
        "jawaban": [
            "Panjang gelombang",
            "Frekuensi",
            "Massa medium",
            "Periode kuadrat"
        ],
        "benar": 1,
        "alasan": [
            "Energi foton mengikuti E = hf",
            "Energi selalu berbanding terbalik dengan frekuensi",
            "Energi tidak dipengaruhi frekuensi",
            "Energi sama dengan massa medium"
        ],
        "alasan_benar": 0,
        "penjelasan": "Energi foton dihitung dengan E = hf. Semakin tinggi frekuensi, semakin besar energi foton."
    },

    {
        "topik": "Pemantulan gelombang",
        "pertanyaan": "Pada pemantulan cahaya berlaku ...",
        "jawaban": [
            "Sudut datang sama dengan sudut pantul",
            "Sudut datang dua kali sudut pantul",
            "Frekuensi menjadi nol",
            "Energi selalu hilang seluruhnya"
        ],
        "benar": 0,
        "alasan": [
            "Hukum pemantulan menyatakan sudut datang sama dengan sudut pantul",
            "Pemantulan tidak mempunyai aturan",
            "Gelombang selalu diserap seluruhnya",
            "Arah rambat tidak dapat berubah"
        ],
        "alasan_benar": 0,
        "penjelasan": "Sudut datang dan sudut pantul diukur terhadap garis normal, bukan terhadap permukaan."
    },

    {
        "topik": "Pembiasan gelombang",
        "pertanyaan": "Ketika cahaya masuk ke medium berbeda, frekuensinya pada umumnya ...",
        "jawaban": [
            "Berubah",
            "Tetap",
            "Menjadi dua kali",
            "Menjadi nol"
        ],
        "benar": 1,
        "alasan": [
            "Frekuensi ditentukan oleh sumber dan tetap saat memasuki medium lain",
            "Frekuensi selalu ditentukan kecepatan medium",
            "Panjang gelombang tidak pernah berubah",
            "Pembiasan menghentikan gelombang"
        ],
        "alasan_benar": 0,
        "penjelasan": "Frekuensi tetap. Cepat rambat dan panjang gelombang dapat berubah ketika cahaya memasuki medium berbeda."
    },

    {
        "topik": "Polarisasi",
        "pertanyaan": "Polarisasi menunjukkan bahwa cahaya bersifat ...",
        "jawaban": [
            "Longitudinal",
            "Transversal",
            "Mekanik",
            "Tidak memiliki arah getar"
        ],
        "benar": 1,
        "alasan": [
            "Polarisasi berkaitan dengan pembatasan arah getar gelombang transversal",
            "Gelombang longitudinal dapat dipolarisasi dengan cara yang sama",
            "Cahaya memerlukan medium",
            "Cahaya tidak memiliki medan listrik"
        ],
        "alasan_benar": 0,
        "penjelasan": "Polarisasi merupakan bukti bahwa cahaya bersifat transversal karena arah getarnya dapat dibatasi."
    },

    {
        "topik": "Energi gelombang elektromagnetik",
        "pertanyaan": "Gelombang elektromagnetik membawa energi karena ...",
        "jawaban": [
            "Memiliki medan listrik dan medan magnet",
            "Selalu membawa udara",
            "Tidak memiliki frekuensi",
            "Harus merambat dalam air"
        ],
        "benar": 0,
        "alasan": [
            "Medan elektromagnetik dapat membawa dan mentransfer energi",
            "Energi hanya dimiliki gelombang mekanik",
            "Gelombang tidak berinteraksi dengan benda",
            "Energi sama dengan massa udara"
        ],
        "alasan_benar": 0,
        "penjelasan": "Gelombang elektromagnetik membawa energi yang dapat ditransfer ke materi ketika terjadi interaksi."
    },

    {
        "topik": "Kecepatan dalam medium",
        "pertanyaan": "Jika indeks bias medium lebih besar daripada satu, kecepatan cahaya dalam medium dibandingkan di ruang hampa adalah ...",
        "jawaban": [
            "Lebih besar",
            "Lebih kecil",
            "Selalu sama",
            "Nol"
        ],
        "benar": 1,
        "alasan": [
            "v = c/n, sehingga n lebih besar menghasilkan v lebih kecil",
            "Medium selalu mempercepat cahaya",
            "Indeks bias tidak berhubungan dengan kecepatan",
            "Cahaya berhenti dalam medium"
        ],
        "alasan_benar": 0,
        "penjelasan": "Dalam medium dengan indeks bias n, kecepatan fase cahaya adalah v = c/n."
    },

    {
        "topik": "Panjang gelombang",
        "pertanyaan": "Jika frekuensi tetap dan cepat rambat berkurang, panjang gelombang akan ...",
        "jawaban": [
            "Bertambah",
            "Berkurang",
            "Tetap",
            "Menjadi tak terhingga"
        ],
        "benar": 1,
        "alasan": [
            "λ = v/f, sehingga v berkurang dan f tetap menyebabkan λ berkurang",
            "Panjang gelombang tidak dipengaruhi kecepatan",
            "Frekuensi ikut menjadi nol",
            "Medium menghilangkan gelombang"
        ],
        "alasan_benar": 0,
        "penjelasan": "Berdasarkan λ = v/f, panjang gelombang berkurang jika kecepatan berkurang sedangkan frekuensi tetap."
    },

    {
        "topik": "Aplikasi gelombang elektromagnetik",
        "pertanyaan": "Komunikasi satelit umumnya memanfaatkan gelombang ...",
        "jawaban": [
            "Mikro",
            "Bunyi",
            "Air",
            "Gelombang tali"
        ],
        "benar": 0,
        "alasan": [
            "Gelombang mikro digunakan pada berbagai sistem komunikasi satelit",
            "Bunyi dapat merambat melalui ruang hampa",
            "Gelombang air dapat merambat di ruang angkasa",
            "Gelombang tali digunakan untuk komunikasi satelit"
        ],
        "alasan_benar": 0,
        "penjelasan": "Komunikasi satelit menggunakan frekuensi radio, termasuk pita gelombang mikro, untuk mengirim dan menerima sinyal."
    }
]

# =========================================================
# PEMBATASAN JUMLAH SOAL MENJADI 10
# =========================================================

SOAL = SOAL[:10]

# =========================================================
# 8. ANALISIS FOUR-TIER
# =========================================================

def analisis_jawaban(jawaban_siswa):

    hasil = []

    for nomor, jawaban in enumerate(jawaban_siswa):

        soal = SOAL[nomor]

        benar_jawaban = (
            jawaban["jawaban"] == soal["jawaban"][soal["benar"]]
        )

        benar_alasan = (
            jawaban["alasan"] == soal["alasan"][soal["alasan_benar"]]
        )

        yakin_jawaban = jawaban["yakin_jawaban"] == "Yakin"
        yakin_alasan = jawaban["yakin_alasan"] == "Yakin"

        if benar_jawaban and benar_alasan:

            if yakin_jawaban and yakin_alasan:
                kategori = "Paham Konsep"

            else:
                kategori = "Paham Konsep, Belum Yakin"

        elif not benar_jawaban and not benar_alasan:

            if yakin_jawaban and yakin_alasan:
                kategori = "Indikasi Miskonsepsi"

            else:
                kategori = "Belum Memahami Konsep"

        elif benar_jawaban and not benar_alasan:
            kategori = "Jawaban Benar, Alasan Keliru"

        else:
            kategori = "Jawaban Salah, Alasan Benar"

        hasil.append({

            "nomor": nomor + 1,
            "topik": soal["topik"],
            "pertanyaan": soal["pertanyaan"],
            "jawaban_siswa": jawaban["jawaban"],
            "alasan_siswa": jawaban["alasan"],
            "keyakinan_jawaban": jawaban["yakin_jawaban"],
            "keyakinan_alasan": jawaban["yakin_alasan"],
            "jawaban_benar": benar_jawaban,
            "alasan_benar": benar_alasan,
            "kategori": kategori,
            "jawaban_seharusnya": soal["jawaban"][soal["benar"]],
            "alasan_seharusnya": soal["alasan"][soal["alasan_benar"]],
            "penjelasan": soal["penjelasan"]

        })

    return hasil

# =========================================================
# 9. PERHITUNGAN NILAI
# =========================================================

def hitung_nilai(hasil):

    if not hasil:
        return 0

    skor_jawaban = sum(
        item["jawaban_benar"] for item in hasil
    )

    skor_alasan = sum(
        item["alasan_benar"] for item in hasil
    )

    total = len(hasil) * 2

    nilai = (
        (skor_jawaban + skor_alasan)
        / total
    ) * 100

    return round(nilai, 2)

def hitung_persentase(hasil):

    if not hasil:
        return 0

    jumlah = sum(
        item["kategori"] == "Indikasi Miskonsepsi"
        for item in hasil
    )

    return round(jumlah / len(hasil) * 100, 2)
