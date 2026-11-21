import streamlit as st
import streamlit.components.v1 as components
import sqlite3
import hashlib
import secrets
import json
import io
import math
import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from datetime import datetime


# =========================================================
# 1. KONFIGURASI APLIKASI
# =========================================================

st.set_page_config(
    page_title="MISKONSEPTION",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

NAMA_APLIKASI = "MISKONSEPTION"

# Tetap menggunakan database lama
DATABASE = "misconception"

# Jumlah soal ujian
JUMLAH_SOAL = 10

# Batas maksimal pelanggaran
BATAS_PELANGGARAN = 3

# Pilihan keamanan ujian
MODE_KEAMANAN = [
    "Website Monitoring",
    "Safe Exam Browser (SEB)",
    "Gabungan"
]


# =========================================================
# 2. FUNGSI KONEKSI DATABASE
# =========================================================

def koneksi_database():
    """
    Membuka koneksi ke database SQLite.
    Database tetap menggunakan nama misconception.
    """
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# =========================================================
# 3. MEMBUAT TABEL PELANGGARAN UJIAN
# =========================================================

def buat_tabel_keamanan():
    """
    Membuat tabel untuk menyimpan pelanggaran selama ujian.
    Tabel lama users dan results tidak dihapus.
    """

    conn = koneksi_database()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exam_violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            session_id TEXT NOT NULL,
            violation_type TEXT NOT NULL,
            violation_count INTEGER NOT NULL,
            violation_time TEXT NOT NULL,
            exam_mode TEXT,
            description TEXT
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# 4. FUNGSI MENCATAT PELANGGARAN
# =========================================================

def catat_pelanggaran(
    username,
    session_id,
    violation_type,
    violation_count,
    exam_mode,
    description=""
):
    """
    Menyimpan pelanggaran ujian ke database.
    """

    conn = koneksi_database()
    cursor = conn.cursor()

    waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO exam_violations (
            username,
            session_id,
            violation_type,
            violation_count,
            violation_time,
            exam_mode,
            description
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        username,
        session_id,
        violation_type,
        violation_count,
        waktu,
        exam_mode,
        description
    ))

    conn.commit()
    conn.close()


# =========================================================
# 5. MENGAMBIL DATA PELANGGARAN
# =========================================================

def ambil_semua_pelanggaran():
    """
    Mengambil seluruh catatan pelanggaran untuk dashboard guru.
    """

    conn = koneksi_database()

    try:
        data = pd.read_sql_query("""
            SELECT
                username AS 'Nama Siswa',
                session_id AS 'ID Sesi Ujian',
                violation_type AS 'Jenis Pelanggaran',
                violation_count AS 'Jumlah Pelanggaran',
                violation_time AS 'Waktu',
                exam_mode AS 'Mode Keamanan',
                description AS 'Keterangan'
            FROM exam_violations
            ORDER BY id DESC
        """, conn)

    except Exception:
        data = pd.DataFrame()

    conn.close()
    return data


# =========================================================
# 6. MENGAMBIL PELANGGARAN BERDASARKAN SISWA
# =========================================================

def ambil_pelanggaran_siswa(username):
    """
    Mengambil catatan pelanggaran milik satu siswa.
    """

    conn = koneksi_database()

    try:
        data = pd.read_sql_query("""
            SELECT
                violation_type,
                violation_count,
                violation_time,
                exam_mode,
                description
            FROM exam_violations
            WHERE username = ?
            ORDER BY id DESC
        """, conn, params=(username,))

    except Exception:
        data = pd.DataFrame()

    conn.close()
    return data


# =========================================================
# 7. MEMBUAT ID SESI UJIAN
# =========================================================

def buat_id_sesi():
    """
    Membuat ID unik untuk setiap sesi ujian.
    """

    return secrets.token_hex(8)


# =========================================================
# 8. FUNGSI HASH PASSWORD
# =========================================================

def hash_password(password, salt=None):
    """
    Mengubah password menjadi hash agar tidak disimpan
    dalam bentuk teks biasa.
    """

    if salt is None:
        salt = secrets.token_hex(16)

    hasil_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000
    ).hex()

    return salt + ":" + hasil_hash


def verifikasi_password(password, password_tersimpan):
    """
    Memeriksa password yang dimasukkan pengguna.
    """

    try:
        salt, hash_lama = password_tersimpan.split(":")

        hash_baru = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100000
        ).hex()

        return secrets.compare_digest(hash_baru, hash_lama)

    except Exception:
        return False


# =========================================================
# 9. INISIALISASI SESSION STATE
# =========================================================

def inisialisasi_session():

    nilai_awal = {
        "login": False,
        "username": None,
        "role": None,

        "halaman": "Beranda",

        "ujian_aktif": False,
        "ujian_dihentikan": False,
        "ujian_selesai": False,

        "mode_ujian": "Website Monitoring",

        "pelanggaran_sesi": 0,
        "id_sesi_ujian": None,

        "nomor_soal": 0,
        "jawaban_siswa": {},

        "hasil_ujian": None,
        "waktu_mulai_ujian": None
    }

    for key, value in nilai_awal.items():
        if key not in st.session_state:
            st.session_state[key] = value


# =========================================================
# 10. MENJALANKAN INISIALISASI
# =========================================================

buat_tabel_keamanan()
inisialisasi_session()


# =========================================================
# 11. MEMBUAT TABEL PENGGUNA
# =========================================================

def buat_tabel_pengguna():

    conn = koneksi_database()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'Siswa',
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# 12. MEMBUAT TABEL HASIL TES
# =========================================================

def buat_tabel_hasil():

    conn = koneksi_database()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            tanggal TEXT NOT NULL,
            skor REAL,
            total_soal INTEGER,
            jumlah_miskonsepsi INTEGER,
            jumlah_paham REAL,
            detail_jawaban TEXT
        )
    """)

    conn.commit()
    conn.close()


# Membuat tabel pengguna dan hasil tes
buat_tabel_pengguna()
buat_tabel_hasil()


# =========================================================
# 13. FUNGSI REGISTRASI
# =========================================================

def registrasi_pengguna(username, password):

    username = username.strip()

    if not username or not password:
        return False, "Username dan password harus diisi."

    if len(username) < 3:
        return False, "Username minimal terdiri dari 3 karakter."

    if len(password) < 6:
        return False, "Password minimal terdiri dari 6 karakter."

    conn = koneksi_database()
    cursor = conn.cursor()

    try:
        password_hash = hash_password(password)

        cursor.execute("""
            INSERT INTO users (
                username,
                password,
                role,
                created_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            username,
            password_hash,
            "Siswa",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        return True, "Registrasi berhasil. Silakan login."

    except sqlite3.IntegrityError:
        return False, "Username sudah digunakan."

    except Exception as e:
        return False, f"Registrasi gagal: {e}"

    finally:
        conn.close()


# =========================================================
# 14. FUNGSI LOGIN
# =========================================================

def login_pengguna(username, password):

    conn = koneksi_database()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT username, password, role
        FROM users
        WHERE username = ?
    """, (username.strip(),))

    pengguna = cursor.fetchone()
    conn.close()

    if pengguna is None:
        return False, "Username tidak ditemukan."

    if not verifikasi_password(password, pengguna["password"]):
        return False, "Password yang dimasukkan salah."

    st.session_state.login = True
    st.session_state.username = pengguna["username"]
    st.session_state.role = pengguna["role"]

    st.session_state.halaman = (
        "Dashboard Guru"
        if pengguna["role"] == "Guru"
        else "Dashboard Siswa"
    )

    return True, "Login berhasil."


# =========================================================
# 15. FUNGSI LOGOUT
# =========================================================

def logout_pengguna():

    st.session_state.login = False
    st.session_state.username = None
    st.session_state.role = None

    st.session_state.ujian_aktif = False
    st.session_state.ujian_dihentikan = False
    st.session_state.ujian_selesai = False

    st.session_state.pelanggaran_sesi = 0
    st.session_state.id_sesi_ujian = None

    st.session_state.nomor_soal = 0
    st.session_state.jawaban_siswa = {}

    st.session_state.halaman = "Beranda"

    st.rerun()


# =========================================================
# 16. HALAMAN LOGIN
# =========================================================

def halaman_login():

    st.title("🔐 Login MISKONSEPTION")

    st.write(
        "Silakan masuk menggunakan akun yang telah terdaftar."
    )

    with st.form("form_login"):

        username = st.text_input(
            "Username",
            placeholder="Masukkan username"
        )

        password = st.text_input(
            "Password",
            type="password",
            placeholder="Masukkan password"
        )

        tombol_login = st.form_submit_button(
            "Login",
            use_container_width=True
        )

    if tombol_login:

        berhasil, pesan = login_pengguna(
            username,
            password
        )

        if berhasil:
            st.success(pesan)
            st.rerun()
        else:
            st.error(pesan)


# =========================================================
# 17. HALAMAN REGISTRASI
# =========================================================

def halaman_registrasi():

    st.title("📝 Registrasi Akun")

    st.write(
        "Buat akun terlebih dahulu untuk menggunakan aplikasi."
    )

    with st.form("form_registrasi"):

        username = st.text_input(
            "Buat Username"
        )

        password = st.text_input(
            "Buat Password",
            type="password"
        )

        konfirmasi = st.text_input(
            "Konfirmasi Password",
            type="password"
        )

        tombol_daftar = st.form_submit_button(
            "Daftar",
            use_container_width=True
        )

    if tombol_daftar:

        if password != konfirmasi:
            st.error("Konfirmasi password tidak sama.")

        else:
            berhasil, pesan = registrasi_pengguna(
                username,
                password
            )

            if berhasil:
                st.success(pesan)
            else:
                st.error(pesan)


# =========================================================
# 18. FUNGSI MEMERIKSA HAK AKSES
# =========================================================

def hanya_guru():

    return (
        st.session_state.login
        and st.session_state.role == "Guru"
    )


def hanya_siswa():

    return (
        st.session_state.login
        and st.session_state.role == "Siswa"
    )

# =========================================================
# 19. BANK SOAL FOUR-TIER
# =========================================================

SOAL = [{'id': 1,
  'materi': 'Pengertian Gelombang Elektromagnetik',
  'pertanyaan': 'Gelombang elektromagnetik adalah gelombang yang ....',
  'pilihan': ['A. Memerlukan medium untuk merambat',
              'B. Tidak memerlukan medium untuk merambat',
              'C. Hanya dapat merambat dalam zat cair',
              'D. Hanya dapat merambat dalam zat padat',
              'E. Hanya dapat merambat jika terdapat udara'],
  'kunci': 'B',
  'alasan': ['A. Karena gelombang elektromagnetik membutuhkan partikel medium',
             'B. Karena gelombang elektromagnetik dapat merambat di ruang hampa',
             'C. Karena gelombang elektromagnetik hanya merambat melalui udara',
             'D. Karena gelombang elektromagnetik tidak membawa energi',
             'E. Karena gelombang elektromagnetik merupakan gelombang bunyi'],
  'kunci_alasan': 'B',
  'pembahasan': 'Gelombang elektromagnetik tidak membutuhkan medium untuk merambat. '
                'Gelombang ini dapat bergerak di ruang hampa, contohnya cahaya Matahari '
                'yang sampai ke Bumi.\n'
                '\n'
                'Gelombang elektromagnetik tidak sama dengan gelombang bunyi. Bunyi '
                'memerlukan medium seperti udara, air, atau benda padat, sedangkan '
                'gelombang elektromagnetik dapat merambat di ruang hampa.'},
 {'id': 2,
  'materi': 'Sifat Gelombang Elektromagnetik',
  'pertanyaan': 'Gelombang elektromagnetik memiliki medan listrik dan medan magnet yang '
                '....',
  'pilihan': ['A. Sejajar satu sama lain',
              'B. Saling tegak lurus dan tegak lurus terhadap arah rambat',
              'C. Berlawanan arah dan tidak berubah',
              'D. Selalu berada pada satu garis lurus',
              'E. Sejajar dengan arah rambat gelombang'],
  'kunci': 'B',
  'alasan': ['A. Karena medan listrik dan magnet merambat secara terpisah',
             'B. Karena gelombang elektromagnetik merupakan gelombang transversal',
             'C. Karena gelombang elektromagnetik merupakan gelombang longitudinal',
             'D. Karena medan listrik tidak berhubungan dengan medan magnet',
             'E. Karena arah medan listrik selalu sama dengan arah rambat'],
  'kunci_alasan': 'B',
  'pembahasan': 'Gelombang elektromagnetik merupakan gelombang transversal. Medan listrik '
                'dan medan magnet saling tegak lurus serta keduanya tegak lurus terhadap '
                'arah rambat gelombang.\n'
                '\n'
                'Arah medan listrik, medan magnet, dan arah rambat saling tegak lurus. '
                'Hubungan ini merupakan ciri gelombang elektromagnetik sebagai gelombang '
                'transversal.'},
 {'id': 3,
  'materi': 'Kecepatan Gelombang Elektromagnetik',
  'pertanyaan': 'Kecepatan gelombang elektromagnetik di ruang hampa adalah ....',
  'pilihan': ['A. 3 × 10⁶ m/s',
              'B. 3 × 10⁷ m/s',
              'C. 3 × 10⁸ m/s',
              'D. 3 × 10⁹ m/s',
              'E. 3 × 10¹⁰ m/s'],
  'kunci': 'C',
  'alasan': ['A. Karena kecepatan cahaya di ruang hampa sekitar 300.000 km/s',
             'B. Karena semua gelombang bergerak dengan kecepatan yang sama di udara',
             'C. Karena gelombang elektromagnetik tidak memiliki kecepatan tetap',
             'D. Karena kecepatan gelombang elektromagnetik bergantung pada massanya',
             'E. Karena nilai kecepatan cahaya di ruang hampa ditentukan oleh frekuensi sumber'],
  'kunci_alasan': 'A',
  'pembahasan': 'Kecepatan gelombang elektromagnetik di ruang hampa adalah sekitar 3 × 10⁸ '
                'm/s. Nilai ini merupakan kecepatan cahaya di ruang hampa.\n'
                '\n'
                'Nilai kecepatan cahaya di ruang hampa mendekati 3 × 10⁸ m/s. Nilai ini '
                'merupakan konstanta fisika dan bukan ditentukan oleh massa gelombang.'},
 {'id': 4,
  'materi': 'Hubungan Frekuensi dan Panjang Gelombang',
  'pertanyaan': 'Jika frekuensi gelombang elektromagnetik semakin besar, maka panjang '
                'gelombangnya akan ....',
  'pilihan': ['A. Semakin besar',
              'B. Semakin kecil',
              'C. Tetap sama',
              'D. Menjadi nol',
              'E. Berubah secara tidak beraturan'],
  'kunci': 'B',
  'alasan': ['A. Karena frekuensi dan panjang gelombang berbanding lurus',
             'B. Karena frekuensi dan panjang gelombang berbanding terbalik pada kecepatan '
             'rambat tetap',
             'C. Karena frekuensi tidak berhubungan dengan panjang gelombang',
             'D. Karena panjang gelombang selalu bertambah ketika frekuensi bertambah',
             'E. Karena cepat rambat selalu menjadi nol ketika frekuensi naik'],
  'kunci_alasan': 'B',
  'pembahasan': 'Hubungan frekuensi dan panjang gelombang dinyatakan dengan rumus c = λf. '
                'Pada kecepatan rambat tetap, frekuensi yang semakin besar menyebabkan '
                'panjang gelombang semakin kecil.\n'
                '\n'
                'Persamaan c = λf menunjukkan bahwa pada cepat rambat tetap, frekuensi dan '
                'panjang gelombang berbanding terbalik. Keduanya bukan berubah secara '
                'acak.'},
 {'id': 5,
  'materi': 'Spektrum Elektromagnetik',
  'pertanyaan': 'Urutan gelombang elektromagnetik dari frekuensi paling rendah ke paling '
                'tinggi adalah ....',
  'pilihan': ['A. Radio, mikro, inframerah, cahaya tampak, ultraviolet, sinar-X, gamma',
              'B. Gamma, sinar-X, ultraviolet, cahaya tampak, inframerah, mikro, radio',
              'C. Radio, inframerah, mikro, ultraviolet, cahaya tampak, gamma, sinar-X',
              'D. Cahaya tampak, radio, mikro, gamma, ultraviolet, inframerah, sinar-X',
              'E. Mikro, radio, cahaya tampak, inframerah, sinar-X, ultraviolet, gamma'],
  'kunci': 'A',
  'alasan': ['A. Karena gelombang radio memiliki frekuensi paling rendah dan gamma paling '
             'tinggi',
             'B. Karena sinar gamma memiliki panjang gelombang paling besar',
             'C. Karena semua jenis gelombang memiliki frekuensi yang sama',
             'D. Karena gelombang radio memiliki energi paling tinggi',
             'E. Karena urutan spektrum ditentukan berdasarkan warna saja'],
  'kunci_alasan': 'A',
  'pembahasan': 'Urutan spektrum elektromagnetik dari frekuensi terendah ke tertinggi '
                'adalah radio, mikro, inframerah, cahaya tampak, ultraviolet, sinar-X, dan '
                'sinar gamma.\n'
                '\n'
                'Urutan spektrum ditentukan oleh frekuensi atau panjang gelombang, bukan '
                'berdasarkan warna saja. Cahaya tampak hanyalah bagian kecil dari seluruh '
                'spektrum elektromagnetik.'},
 {'id': 6,
  'materi': 'Energi Gelombang Elektromagnetik',
  'pertanyaan': 'Energi foton gelombang elektromagnetik akan semakin besar jika ....',
  'pilihan': ['A. Frekuensinya semakin kecil',
              'B. Panjang gelombangnya semakin besar',
              'C. Frekuensinya semakin besar',
              'D. Kecepatannya menjadi nol',
              'E. Amplitudonya selalu menjadi nol'],
  'kunci': 'C',
  'alasan': ['A. Karena energi foton berbanding lurus dengan frekuensi',
             'B. Karena energi foton tidak dipengaruhi frekuensi',
             'C. Karena energi foton selalu tetap untuk semua gelombang',
             'D. Karena energi foton berbanding lurus dengan panjang gelombang',
             'E. Karena energi foton hanya ditentukan oleh medium'],
  'kunci_alasan': 'A',
  'pembahasan': 'Energi foton dirumuskan dengan E = hf. Artinya, semakin besar frekuensi '
                'gelombang elektromagnetik, semakin besar pula energi fotonnya.\n'
                '\n'
                'Energi foton ditentukan oleh frekuensinya melalui E = hf. Amplitudo '
                'gelombang bukan besaran yang digunakan dalam persamaan energi satu foton '
                'tersebut.'},
 {'id': 7,
  'materi': 'Gelombang Radio',
  'pertanyaan': 'Gelombang radio banyak dimanfaatkan dalam kehidupan sehari-hari untuk '
                '....',
  'pilihan': ['A. Pemeriksaan tulang menggunakan sinar-X',
              'B. Komunikasi dan penyiaran',
              'C. Sterilisasi alat medis dengan sinar gamma',
              'D. Menghasilkan panas pada makanan menggunakan inframerah',
              'E. Mengukur massa suatu benda secara langsung'],
  'kunci': 'B',
  'alasan': ['A. Karena gelombang radio dapat membawa informasi melalui gelombang '
             'elektromagnetik',
             'B. Karena gelombang radio hanya dapat digunakan untuk menghasilkan panas',
             'C. Karena gelombang radio memiliki energi paling besar',
             'D. Karena gelombang radio tidak dapat merambat di udara',
             'E. Karena gelombang radio merupakan gelombang mekanik'],
  'kunci_alasan': 'A',
  'pembahasan': 'Gelombang radio digunakan untuk komunikasi, seperti siaran radio, '
                'televisi, dan sistem komunikasi nirkabel.\n'
                '\n'
                'Gelombang radio merupakan gelombang elektromagnetik, bukan gelombang '
                'mekanik. Gelombang radio dapat membawa informasi melalui proses modulasi '
                'dan diterima oleh antena.'},
 {'id': 8,
  'materi': 'Sinar Ultraviolet',
  'pertanyaan': 'Paparan sinar ultraviolet Matahari secara berlebihan dapat menyebabkan '
                '....',
  'pilihan': ['A. Kerusakan kulit',
              'B. Bertambahnya massa tubuh secara langsung',
              'C. Hilangnya gaya gravitasi',
              'D. Bertambahnya kecepatan suara',
              'E. Berubahnya arah medan magnet Bumi secara langsung'],
  'kunci': 'A',
  'alasan': ['A. Karena sinar ultraviolet memiliki energi yang dapat merusak sel kulit',
             'B. Karena sinar ultraviolet tidak memiliki energi',
             'C. Karena sinar ultraviolet hanya dapat merambat dalam air',
             'D. Karena sinar ultraviolet merupakan gelombang mekanik',
             'E. Karena sinar ultraviolet memiliki frekuensi lebih rendah daripada radio'],
  'kunci_alasan': 'A',
  'pembahasan': 'Paparan ultraviolet yang berlebihan dapat merusak sel kulit dan '
                'meningkatkan risiko gangguan kulit. Karena itu, perlindungan dari sinar '
                'Matahari diperlukan.\n'
                '\n'
                'Ultraviolet memiliki frekuensi lebih tinggi daripada cahaya tampak dan '
                'radio. Paparan UV berlebihan dapat merusak jaringan kulit dan mata.'},
 {'id': 9,
  'materi': 'Sinar-X',
  'pertanyaan': 'Sinar-X dimanfaatkan dalam bidang kesehatan terutama untuk ....',
  'pilihan': ['A. Mengukur suhu tubuh',
              'B. Melihat struktur bagian dalam tubuh',
              'C. Mengukur tekanan darah',
              'D. Mengukur denyut jantung secara langsung',
              'E. Menentukan golongan darah tanpa pemeriksaan'],
  'kunci': 'B',
  'alasan': ['A. Karena sinar-X dapat menembus jaringan lunak dan diserap berbeda oleh '
             'tulang',
             'B. Karena sinar-X tidak dapat menembus tubuh manusia',
             'C. Karena sinar-X hanya digunakan untuk menghasilkan cahaya',
             'D. Karena sinar-X merupakan gelombang suara',
             'E. Karena sinar-X dapat mengukur kerja jantung secara langsung'],
  'kunci_alasan': 'A',
  'pembahasan': 'Sinar-X dapat menembus jaringan tubuh dengan tingkat penyerapan berbeda. '
                'Tulang menyerap lebih banyak sinar-X daripada jaringan lunak sehingga '
                'dapat digunakan untuk menghasilkan citra bagian dalam tubuh.\n'
                '\n'
                'Sinar-X digunakan untuk membentuk citra bagian dalam tubuh karena '
                'jaringan menyerap sinar-X secara berbeda. Pengukuran denyut jantung dan '
                'golongan darah memerlukan metode pemeriksaan lain.'},
 {'id': 10,
  'materi': 'Sinar Gamma',
  'pertanyaan': 'Sinar gamma memiliki energi yang sangat tinggi dibandingkan gelombang '
                'elektromagnetik lainnya karena ....',
  'pilihan': ['A. Frekuensinya sangat rendah',
              'B. Panjang gelombangnya sangat besar',
              'C. Frekuensinya sangat tinggi',
              'D. Tidak memiliki energi',
              'E. Merambat paling lambat di ruang hampa'],
  'kunci': 'C',
  'alasan': ['A. Karena energi foton sebanding dengan frekuensinya',
             'B. Karena energi foton berbanding terbalik dengan frekuensi',
             'C. Karena sinar gamma tidak membawa energi',
             'D. Karena semua gelombang elektromagnetik memiliki energi yang sama',
             'E. Karena energi foton hanya dipengaruhi oleh panjang medium'],
  'kunci_alasan': 'A',
  'pembahasan': 'Sinar gamma memiliki frekuensi sangat tinggi dan panjang gelombang sangat '
                'pendek. Berdasarkan persamaan E = hf, frekuensi yang tinggi menghasilkan '
                'energi foton yang tinggi.\n'
                '\n'
                'Sinar gamma memiliki frekuensi sangat tinggi. Karena E = hf, energi '
                'fotonnya juga sangat tinggi; bukan karena gelombang ini merambat paling '
                'lambat.'}]


# =========================================================
# 20. MEMBATASI JUMLAH SOAL MENJADI 10
# =========================================================

SOAL = SOAL[:JUMLAH_SOAL]


# =========================================================
# 21. MATERI REMEDIAL
# =========================================================

MATERI = {'Pengertian Gelombang Elektromagnetik': {'judul': 'Pengertian Gelombang Elektromagnetik',
                                          'isi': '\n'
                                                 'Gelombang elektromagnetik merupakan '
                                                 'gelombang yang terbentuk\n'
                                                 'dari perubahan medan listrik dan medan '
                                                 'magnet.\n'
                                                 '\n'
                                                 'Gelombang ini dapat merambat tanpa '
                                                 'memerlukan medium sehingga\n'
                                                 'bisa bergerak melalui ruang hampa.\n'
                                                 '\n'
                                                 'Contohnya adalah cahaya Matahari yang '
                                                 'dapat sampai ke Bumi\n'
                                                 'meskipun melewati ruang angkasa.\n'
                                                 '\n'
                                                 '**Penjelasan lebih lanjut:** Gelombang '
                                                 'elektromagnetik terbentuk ketika medan '
                                                 'listrik dan medan magnet berubah '
                                                 'terhadap waktu. Perubahan kedua medan '
                                                 'saling berkaitan sehingga gelombang '
                                                 'dapat merambat membawa energi. Contoh '
                                                 'yang mudah diamati adalah cahaya '
                                                 'Matahari, sinyal radio, dan cahaya dari '
                                                 'lampu. Karena tidak membutuhkan medium, '
                                                 'gelombang elektromagnetik tetap dapat '
                                                 'merambat meskipun tidak ada udara.',
                                          'rumus': 'c = λf'},
 'Sifat Gelombang Elektromagnetik': {'judul': 'Sifat Gelombang Elektromagnetik',
                                     'isi': '\n'
                                            'Gelombang elektromagnetik termasuk gelombang '
                                            'transversal.\n'
                                            '\n'
                                            'Medan listrik dan medan magnet saling tegak '
                                            'lurus.\n'
                                            'Keduanya juga tegak lurus terhadap arah '
                                            'rambat gelombang.\n'
                                            '\n'
                                            'Gelombang elektromagnetik dapat mengalami '
                                            'pemantulan,\n'
                                            'pembiasan, interferensi, difraksi, dan '
                                            'polarisasi.\n'
                                            '\n'
                                            '**Penjelasan lebih lanjut:** Sebagai '
                                            'gelombang transversal, arah medan listrik dan '
                                            'medan magnet tidak searah dengan arah rambat. '
                                            'Keduanya saling tegak lurus. Gelombang '
                                            'elektromagnetik juga dapat mengalami '
                                            'pemantulan ketika mengenai permukaan, '
                                            'pembiasan ketika memasuki medium berbeda, '
                                            'interferensi ketika bertemu gelombang lain, '
                                            'difraksi ketika melewati celah, dan '
                                            'polarisasi karena arah getarnya dapat '
                                            'diseleksi.',
                                     'rumus': 'E ⟂ B ⟂ arah rambat'},
 'Kecepatan Gelombang Elektromagnetik': {'judul': 'Kecepatan Gelombang Elektromagnetik',
                                         'isi': '\n'
                                                'Di ruang hampa, gelombang elektromagnetik '
                                                'merambat dengan\n'
                                                'kecepatan sekitar 3 × 10⁸ m/s.\n'
                                                '\n'
                                                'Kecepatan tersebut merupakan kecepatan '
                                                'cahaya di ruang hampa.\n'
                                                'Ketika merambat melalui medium, '
                                                'kecepatannya dapat berubah.\n'
                                                '\n'
                                                '**Penjelasan lebih lanjut:** Simbol c '
                                                'digunakan untuk menyatakan kecepatan '
                                                'cahaya di ruang hampa, yaitu sekitar '
                                                '299.792.458 m/s atau dibulatkan menjadi 3 '
                                                '× 10⁸ m/s. Di dalam medium, kecepatan '
                                                'cahaya dipengaruhi sifat optik medium. '
                                                'Hubungan kecepatan, frekuensi, dan '
                                                'panjang gelombang perlu dipahami bersama '
                                                'agar tidak menganggap kecepatan di semua '
                                                'bahan selalu sama.',
                                         'rumus': 'c = 3 × 10⁸ m/s'},
 'Hubungan Frekuensi dan Panjang Gelombang': {'judul': 'Hubungan Frekuensi dan Panjang '
                                                       'Gelombang',
                                              'isi': '\n'
                                                     'Frekuensi menunjukkan banyaknya '
                                                     'gelombang yang melewati\n'
                                                     'suatu titik setiap detik.\n'
                                                     '\n'
                                                     'Panjang gelombang adalah jarak '
                                                     'antara dua titik yang\n'
                                                     'memiliki fase sama dan berurutan.\n'
                                                     '\n'
                                                     'Pada kecepatan rambat tetap, '
                                                     'frekuensi dan panjang\n'
                                                     'gelombang berbanding terbalik.\n'
                                                     '\n'
                                                     '**Penjelasan lebih lanjut:** '
                                                     'Frekuensi dilambangkan f dan '
                                                     'memiliki satuan hertz (Hz), '
                                                     'sedangkan panjang gelombang '
                                                     'dilambangkan λ dan memiliki satuan '
                                                     'meter (m). Satu hertz berarti satu '
                                                     'siklus setiap sekon. Pada ruang '
                                                     'hampa berlaku c = λf. Contohnya, '
                                                     'jika f = 6 × 10⁶ Hz, maka λ = (3 × '
                                                     '10⁸)/(6 × 10⁶) = 50 m. Periksa '
                                                     'satuan dan pangkat sepuluh saat '
                                                     'melakukan perhitungan.',
                                              'rumus': 'c = λf'},
 'Spektrum Elektromagnetik': {'judul': 'Spektrum Elektromagnetik',
                              'isi': '\n'
                                     'Spektrum elektromagnetik merupakan susunan berbagai\n'
                                     'jenis gelombang elektromagnetik berdasarkan '
                                     'frekuensi\n'
                                     'atau panjang gelombangnya.\n'
                                     '\n'
                                     'Urutan dari frekuensi rendah ke tinggi:\n'
                                     '\n'
                                     '1. Gelombang radio\n'
                                     '2. Gelombang mikro\n'
                                     '3. Inframerah\n'
                                     '4. Cahaya tampak\n'
                                     '5. Ultraviolet\n'
                                     '6. Sinar-X\n'
                                     '7. Sinar gamma\n'
                                     '\n'
                                     '**Penjelasan lebih lanjut:** Urutan dari frekuensi '
                                     'rendah menuju tinggi adalah radio, mikro, '
                                     'inframerah, cahaya tampak, ultraviolet, sinar-X, dan '
                                     'gamma. Ketika bergerak dari radio menuju gamma, '
                                     'frekuensi meningkat, panjang gelombang mengecil, dan '
                                     'energi foton meningkat. Batas antara setiap bagian '
                                     'spektrum tidak selalu berupa batas tajam karena '
                                     'rentang frekuensi dapat saling berdekatan.',
                              'rumus': 'c = λf'},
 'Energi Gelombang Elektromagnetik': {'judul': 'Energi Gelombang Elektromagnetik',
                                      'isi': '\n'
                                             'Energi gelombang elektromagnetik dibawa '
                                             'dalam bentuk\n'
                                             'paket energi yang disebut foton.\n'
                                             '\n'
                                             'Besarnya energi foton dipengaruhi oleh '
                                             'frekuensi.\n'
                                             'Semakin besar frekuensi, semakin besar '
                                             'energi foton.\n'
                                             '\n'
                                             '**Penjelasan lebih lanjut:** Energi satu '
                                             'foton dihitung menggunakan E = hf. Konstanta '
                                             'Planck h bernilai 6,626 × 10⁻³⁴ J s. Jika '
                                             'frekuensi naik dua kali, energi satu foton '
                                             'juga naik dua kali. Persamaan E = hf '
                                             'menjelaskan energi tiap foton, bukan secara '
                                             'langsung jumlah total energi dalam berkas '
                                             'cahaya yang juga dipengaruhi banyaknya '
                                             'foton.',
                                      'rumus': 'E = hf'},
 'Gelombang Radio': {'judul': 'Gelombang Radio',
                     'isi': '\n'
                            'Gelombang radio memiliki frekuensi relatif rendah\n'
                            'dan panjang gelombang relatif besar.\n'
                            '\n'
                            'Gelombang ini digunakan dalam komunikasi,\n'
                            'penyiaran radio, televisi, dan berbagai sistem komunikasi.\n'
                            '\n'
                            '**Penjelasan lebih lanjut:** Informasi suara atau gambar '
                            'terlebih dahulu diubah menjadi sinyal, kemudian digunakan '
                            'untuk memodulasi gelombang pembawa. Antena pemancar '
                            'mengirimkan gelombang radio dan antena penerima menangkapnya. '
                            'Perangkat penerima mengolah sinyal tersebut kembali menjadi '
                            'informasi. Gelombang radio adalah gelombang elektromagnetik, '
                            'sedangkan suara yang didengar manusia adalah gelombang '
                            'mekanik.'},
 'Sinar Ultraviolet': {'judul': 'Sinar Ultraviolet',
                       'isi': '\n'
                              'Sinar ultraviolet memiliki frekuensi lebih tinggi\n'
                              'daripada cahaya tampak.\n'
                              '\n'
                              'Sinar ultraviolet berasal dari Matahari dan beberapa\n'
                              'sumber buatan.\n'
                              '\n'
                              'Paparan berlebihan dapat menyebabkan kerusakan kulit\n'
                              'dan mata sehingga perlu perlindungan.\n'
                              '\n'
                              '**Penjelasan lebih lanjut:** Ultraviolet dibagi menjadi '
                              'beberapa rentang, yaitu UVA, UVB, dan UVC. Sinar UV dari '
                              'Matahari dapat memberi manfaat dalam pembentukan vitamin D, '
                              'tetapi paparan berlebihan dapat menyebabkan kulit terbakar '
                              'dan meningkatkan risiko kerusakan kulit serta mata. Dampak '
                              'paparan dipengaruhi intensitas, lama paparan, dan jenis UV. '
                              'Perlindungan dapat dilakukan dengan pakaian, kacamata '
                              'pelindung, berteduh, dan tabir surya.'},
 'Sinar-X': {'judul': 'Sinar-X',
             'isi': '\n'
                    'Sinar-X merupakan gelombang elektromagnetik dengan\n'
                    'frekuensi tinggi dan panjang gelombang pendek.\n'
                    '\n'
                    'Dalam bidang kesehatan, sinar-X digunakan untuk\n'
                    'membantu melihat struktur bagian dalam tubuh,\n'
                    'terutama tulang.\n'
                    '\n'
                    '**Penjelasan lebih lanjut:** Pada pemeriksaan radiografi, sinar-X '
                    'melewati tubuh dan diserap dengan tingkat berbeda oleh tulang serta '
                    'jaringan lunak. Perbedaan intensitas yang mencapai detektor membentuk '
                    'citra. Sinar-X termasuk radiasi pengion sehingga penggunaannya harus '
                    'berdasarkan kebutuhan medis dan mengikuti prinsip keselamatan '
                    'radiasi.'},
 'Sinar Gamma': {'judul': 'Sinar Gamma',
                 'isi': '\n'
                        'Sinar gamma memiliki frekuensi sangat tinggi\n'
                        'dan panjang gelombang sangat pendek.\n'
                        '\n'
                        'Sinar gamma memiliki energi foton yang tinggi.\n'
                        'Pemanfaatannya antara lain dalam radioterapi\n'
                        'dan sterilisasi alat medis dengan pengendalian khusus.\n'
                        '\n'
                        '**Penjelasan lebih lanjut:** Sinar gamma dapat berasal dari '
                        'proses nuklir atau peluruhan radioaktif tertentu. Energinya '
                        'tinggi sehingga mampu mengionisasi materi dan dapat merusak sel '
                        'hidup. Dalam pengawasan ketat, sinar gamma dimanfaatkan pada '
                        'radioterapi dan sterilisasi peralatan. Perlindungan radiasi, '
                        'pembatasan waktu paparan, jarak, dan pelindung yang sesuai sangat '
                        'penting.'}
}

# =========================================================
# 22. KONSTANTA FISIKA
# =========================================================

C = 299792458
H = 6.62607015e-34


# =========================================================
# 23. FUNGSI ANALISIS FOUR-TIER
# =========================================================

def analisis_jawaban(jawaban):

    hasil = []

    jumlah_paham = 0
    jumlah_miskonsepsi = 0
    jumlah_tidak_paham = 0
    jumlah_menebak = 0

    for nomor, soal in enumerate(SOAL):

        data = jawaban.get(str(nomor), {})

        jawaban_tingkat_1 = data.get("jawaban")
        keyakinan_tingkat_2 = data.get("keyakinan_jawaban")

        alasan_tingkat_3 = data.get("alasan")
        keyakinan_tingkat_4 = data.get("keyakinan_alasan")

        benar_jawaban = (
            jawaban_tingkat_1 == soal["kunci"]
        )

        benar_alasan = (
            alasan_tingkat_3 == soal["kunci_alasan"]
        )

        yakin_jawaban = (
            keyakinan_tingkat_2 == "Yakin"
        )

        yakin_alasan = (
            keyakinan_tingkat_4 == "Yakin"
        )

        # Klasifikasi Four-Tier

        if (
            benar_jawaban
            and benar_alasan
            and yakin_jawaban
            and yakin_alasan
        ):

            kategori = "Paham Konsep"
            jumlah_paham += 1

        elif (
            not benar_jawaban
            and not benar_alasan
            and yakin_jawaban
            and yakin_alasan
        ):

            kategori = "Miskonsepsi"
            jumlah_miskonsepsi += 1

        elif (
            benar_jawaban
            and benar_alasan
            and not yakin_jawaban
            and not yakin_alasan
        ):

            kategori = "Menebak"
            jumlah_menebak += 1

        else:

            kategori = "Tidak Paham Konsep"
            jumlah_tidak_paham += 1

        hasil.append({

            "Nomor": nomor + 1,

            "Materi": soal["materi"],

            "Jawaban Siswa": jawaban_tingkat_1,

            "Jawaban Benar": soal["kunci"],

            "Alasan Siswa": alasan_tingkat_3,

            "Alasan Benar": soal["kunci_alasan"],

            "Keyakinan Jawaban": keyakinan_tingkat_2,

            "Keyakinan Alasan": keyakinan_tingkat_4,

            "Kategori": kategori,

            "Pembahasan": soal["pembahasan"]

        })

    total = len(SOAL)

    skor = (
        jumlah_paham / total * 100
        if total > 0 else 0
    )

    return {

        "detail": hasil,

        "skor": skor,

        "jumlah_paham": jumlah_paham,

        "jumlah_miskonsepsi": jumlah_miskonsepsi,

        "jumlah_tidak_paham": jumlah_tidak_paham,

        "jumlah_menebak": jumlah_menebak,

        "total_soal": total

    }


# =========================================================
# 24. FUNGSI MENYIMPAN HASIL TES
# =========================================================

def simpan_hasil_tes(username, hasil):

    conn = koneksi_database()
    cursor = conn.cursor()

    tanggal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    detail_json = json.dumps(
        hasil["detail"],
        ensure_ascii=False
    )

    cursor.execute("""
        INSERT INTO results (
            username,
            tanggal,
            skor,
            total_soal,
            jumlah_miskonsepsi,
            jumlah_paham,
            detail_jawaban
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (

        username,

        tanggal,

        hasil["skor"],

        hasil["total_soal"],

        hasil["jumlah_miskonsepsi"],

        hasil["jumlah_paham"],

        detail_json

    ))

    conn.commit()
    conn.close()


# =========================================================
# 25. FUNGSI MENGAMBIL RIWAYAT HASIL TES SISWA
# =========================================================

def ambil_riwayat_siswa(username):

    conn = koneksi_database()

    try:

        data = pd.read_sql_query("""
            SELECT
                tanggal AS 'Tanggal',
                skor AS 'Skor',
                total_soal AS 'Total Soal',
                jumlah_miskonsepsi AS 'Jumlah Miskonsepsi',
                jumlah_paham AS 'Jumlah Paham'
            FROM results
            WHERE username = ?
            ORDER BY id DESC
        """, conn, params=(username,))

    except Exception:

        data = pd.DataFrame()

    conn.close()

    return data


# =========================================================
# 26. FUNGSI MENGAMBIL SELURUH HASIL TES
# =========================================================

def ambil_semua_hasil():

    conn = koneksi_database()

    try:

        data = pd.read_sql_query("""
            SELECT
                username AS 'Nama Siswa',
                tanggal AS 'Tanggal',
                skor AS 'Skor',
                total_soal AS 'Total Soal',
                jumlah_miskonsepsi AS 'Jumlah Miskonsepsi',
                jumlah_paham AS 'Jumlah Paham',
                detail_jawaban AS 'Detail Jawaban'
            FROM results
            ORDER BY id DESC
        """, conn)

    except Exception:

        data = pd.DataFrame()

    conn.close()

    return data


# =========================================================
# 27. CSS DAN TAMPILAN APLIKASI
# =========================================================

def pasang_css():

    st.markdown("""
    <style>

    .stApp {
        background-color: #f5f7fb;
    }

    .main-title {
        font-size: 36px;
        font-weight: 800;
        color: #17365d;
        text-align: center;
        margin-bottom: 5px;
    }

    .sub-title {
        text-align: center;
        color: #52657a;
        font-size: 16px;
        margin-bottom: 25px;
    }

    .info-card {
        background-color: white;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #e1e7ef;
        margin-bottom: 15px;
    }

    .info-card h3 {
        color: #17365d;
        margin-top: 0;
    }

    .small-text {
        color: #52657a;
        font-size: 14px;
    }

    </style>
    """, unsafe_allow_html=True)


pasang_css()


# =========================================================
# 28. HEADER APLIKASI
# =========================================================

def tampilkan_header():

    st.markdown(
        '<div class="main-title">🧠 MISKONSEPTION</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sub-title">'
        'Sistem Identifikasi dan Analisis Miskonsepsi Fisika'
        '</div>',
        unsafe_allow_html=True
    )

    st.divider()


# =========================================================
# 29. HALAMAN BERANDA
# =========================================================

def halaman_beranda():

    tampilkan_header()

    st.subheader("Selamat Datang di MISKONSEPTION")

    st.write("""
    MISKONSEPTION merupakan aplikasi pembelajaran yang
    dirancang untuk membantu mengidentifikasi pemahaman
    dan miskonsepsi siswa pada materi gelombang elektromagnetik.

    Aplikasi menggunakan metode Four-Tier Diagnostic Test
    yang terdiri dari empat tingkat pertanyaan, yaitu jawaban,
    keyakinan terhadap jawaban, alasan, dan keyakinan terhadap alasan.
    """)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Jumlah Soal",
            JUMLAH_SOAL
        )

    with col2:
        st.metric(
            "Tingkat Diagnosis",
            "4 Tier"
        )

    with col3:
        st.metric(
            "Materi",
            "Gelombang EM"
        )

    st.divider()

    st.subheader("Fitur Aplikasi")

    col1, col2 = st.columns(2)

    with col1:

        st.markdown("""
        <div class="info-card">
        <h3>📝 Tes Diagnostik</h3>
        <p>Mengerjakan soal Four-Tier untuk mengetahui
        tingkat pemahaman konsep siswa.</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="info-card">
        <h3>📊 Analisis Miskonsepsi</h3>
        <p>Menampilkan hasil identifikasi pemahaman,
        miskonsepsi, dan ketidakpahaman siswa.</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:

        st.markdown("""
        <div class="info-card">
        <h3>📚 Materi Remedial</h3>
        <p>Menyediakan materi pembelajaran sesuai
        dengan konsep yang belum dipahami.</p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div class="info-card">
        <h3>🔐 Keamanan Ujian</h3>
        <p>Menyediakan pemantauan aktivitas halaman
        selama ujian berlangsung.</p>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    if not st.session_state.login:

        col1, col2 = st.columns(2)

        with col1:
            if st.button(
                "Login",
                use_container_width=True
            ):
                st.session_state.halaman = "Login"
                st.rerun()

        with col2:
            if st.button(
                "Registrasi",
                use_container_width=True
            ):
                st.session_state.halaman = "Registrasi"
                st.rerun()

    else:

        st.success(
            f"Anda sudah login sebagai "
            f"{st.session_state.username}."
        )


# =========================================================
# 30. SIDEBAR NAVIGASI
# =========================================================

def halaman_sidebar():

    with st.sidebar:

        st.title("🧠 MISKONSEPTION")

        st.caption(
            "Sistem Analisis Miskonsepsi Fisika"
        )

        st.divider()

        if st.session_state.login:

            st.write(
                f"Pengguna: **{st.session_state.username}**"
            )

            st.write(
                f"Peran: **{st.session_state.role}**"
            )

            st.divider()

            if st.session_state.role == "Siswa":

                daftar_menu = [
                    "Dashboard Siswa",
                    "Tes Diagnostik",
                    "Hasil Diagnosis",
                    "Peta Miskonsepsi",
                    "Materi Remedial",
                    "Laboratorium Virtual",
                    "Riwayat Tes"
                ]

            else:

                daftar_menu = [
                    "Dashboard Guru"
                ]

            for menu in daftar_menu:

                if st.button(
                    menu,
                    use_container_width=True
                ):

                    if st.session_state.ujian_aktif:
                        st.warning(
                            "Selesaikan ujian sebelum berpindah halaman."
                        )
                    else:
                        st.session_state.halaman = menu
                        st.rerun()

            st.divider()

            if st.button(
                "Logout",
                use_container_width=True
            ):

                if st.session_state.ujian_aktif:
                    st.warning(
                        "Selesaikan ujian terlebih dahulu."
                    )
                else:
                    logout_pengguna()

        else:

            if st.button(
                "Beranda",
                use_container_width=True
            ):

                st.session_state.halaman = "Beranda"
                st.rerun()

            if st.button(
                "Login",
                use_container_width=True
            ):

                st.session_state.halaman = "Login"
                st.rerun()

            if st.button(
                "Registrasi",
                use_container_width=True
            ):

                st.session_state.halaman = "Registrasi"
                st.rerun()

# =========================================================
# 31. DASHBOARD SISWA
# =========================================================

def halaman_dashboard_siswa():

    tampilkan_header()

    st.title("📊 Dashboard Siswa")

    st.write(
        f"Selamat datang, {st.session_state.username}!"
    )

    riwayat = ambil_riwayat_siswa(
        st.session_state.username
    )

    if riwayat.empty:

        st.info(
            "Anda belum memiliki riwayat tes."
        )

        jumlah_tes = 0
        rata_rata = 0
        total_miskonsepsi = 0

    else:

        jumlah_tes = len(riwayat)

        rata_rata = riwayat["Skor"].mean()

        total_miskonsepsi = riwayat[
            "Jumlah Miskonsepsi"
        ].sum()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Jumlah Tes",
            jumlah_tes
        )

    with col2:
        st.metric(
            "Rata-rata Skor",
            f"{rata_rata:.1f}"
        )

    with col3:
        st.metric(
            "Total Miskonsepsi",
            int(total_miskonsepsi)
        )

    st.divider()

    st.subheader("Mulai Pembelajaran")

    st.write("""
    Kerjakan tes diagnostik untuk mengetahui
    tingkat pemahaman Anda terhadap materi
    gelombang elektromagnetik.
    """)

    if st.button(
        "Mulai Tes Diagnostik",
        use_container_width=True
    ):

        st.session_state.halaman = "Tes Diagnostik"
        st.rerun()

    st.divider()

    st.subheader("Riwayat Tes Terakhir")

    if not riwayat.empty:

        st.dataframe(
            riwayat.head(5),
            use_container_width=True,
            hide_index=True
        )


# =========================================================
# 32. MEMULAI SESI UJIAN
# =========================================================

def mulai_ujian(mode):

    st.session_state.mode_ujian = mode

    st.session_state.ujian_aktif = True
    st.session_state.ujian_dihentikan = False
    st.session_state.ujian_selesai = False

    st.session_state.pelanggaran_sesi = 0

    st.session_state.id_sesi_ujian = buat_id_sesi()

    st.session_state.nomor_soal = 0

    st.session_state.jawaban_siswa = {}

    st.session_state.hasil_ujian = None

    st.session_state.waktu_mulai_ujian = datetime.now()

    st.session_state.halaman = "Tes Diagnostik"

    st.rerun()


# =========================================================
# 33. MENCATAT PELANGGARAN UJIAN
# =========================================================

def proses_pelanggaran(jenis, keterangan=""):

    if not st.session_state.ujian_aktif:
        return

    if st.session_state.ujian_dihentikan:
        return

    st.session_state.pelanggaran_sesi += 1

    jumlah = st.session_state.pelanggaran_sesi

    catat_pelanggaran(
        username=st.session_state.username,
        session_id=st.session_state.id_sesi_ujian,
        violation_type=jenis,
        violation_count=jumlah,
        exam_mode=st.session_state.mode_ujian,
        description=keterangan
    )

    if jumlah == 1:

        st.warning(
            "Peringatan 1: Aktivitas di luar halaman ujian terdeteksi. "
            "Silakan kembali fokus pada ujian."
        )

    elif jumlah == 2:

        st.error(
            "Peringatan 2: Aktivitas mencurigakan kembali terdeteksi. "
            "Pelanggaran berikutnya akan menghentikan ujian."
        )

    elif jumlah >= BATAS_PELANGGARAN:

        st.session_state.ujian_aktif = False
        st.session_state.ujian_dihentikan = True

        st.session_state.halaman = "Tes Diagnostik"


# =========================================================
# 34. KOMPONEN PEMANTAUAN WEBSITE
# =========================================================

def tampilkan_monitor_website():

    if not st.session_state.ujian_aktif:
        return

    if st.session_state.mode_ujian not in [
        "Website Monitoring",
        "Gabungan"
    ]:
        return

    components.html(
        """
        <div id="monitor-status"
             style="font-family:Arial;
                    padding:8px;
                    border-radius:8px;
                    background:#e8f5e9;
                    color:#1b5e20;">
            🟢 Pemantauan halaman aktif
        </div>

        <script>

        const statusBox =
            document.getElementById("monitor-status");

        let pelanggaranTerkirim = false;

        function kirimPelanggaran(jenis) {

            if (pelanggaranTerkirim) {
                return;
            }

            pelanggaranTerkirim = true;

            statusBox.innerHTML =
                "⚠️ Aktivitas di luar halaman ujian terdeteksi.";

            statusBox.style.background = "#ffebee";
            statusBox.style.color = "#b71c1c";

            // Pesan peringatan visual.
            // Komunikasi ke server Streamlit belum tersedia
            // hanya dengan components.html biasa.

            console.log("Pelanggaran:", jenis);
        }

        document.addEventListener(
            "visibilitychange",
            function() {

                if (document.hidden) {
                    kirimPelanggaran("Berpindah tab atau halaman");
                }

            }
        );

        window.addEventListener(
            "blur",
            function() {

                kirimPelanggaran("Halaman kehilangan fokus");

            }
        );

        document.addEventListener(
            "fullscreenchange",
            function() {

                if (!document.fullscreenElement) {

                    kirimPelanggaran(
                        "Keluar dari mode layar penuh"
                    );

                }

            }
        );

        </script>
        """,
        height=65
    )


# =========================================================
# 35. FUNGSI PERINGATAN SUARA
# =========================================================

def tampilkan_peringatan_suara():

    components.html(
        """
        <script>

        try {

            const audioContext =
                new (window.AudioContext ||
                     window.webkitAudioContext)();

            const oscillator =
                audioContext.createOscillator();

            const gain =
                audioContext.createGain();

            oscillator.connect(gain);
            gain.connect(audioContext.destination);

            oscillator.frequency.value = 800;

            gain.gain.value = 0.15;

            oscillator.start();

            oscillator.stop(
                audioContext.currentTime + 0.3
            );

        } catch (error) {

            console.log("Audio tidak tersedia.");

        }

        </script>
        """,
        height=0
    )


# =========================================================
# 36. HALAMAN TES DIAGNOSTIK
# =========================================================

def halaman_tes():

    tampilkan_header()

    st.title("📝 Tes Diagnostik Four-Tier")

    # -----------------------------------------------------
    # Jika ujian dihentikan
    # -----------------------------------------------------

    if st.session_state.ujian_dihentikan:

        st.error("🚫 Ujian dihentikan.")

        st.write("""
        Ujian dihentikan karena telah terjadi tiga kali
        pelanggaran yang tercatat oleh sistem.

        Hasil ujian ditandai untuk pemeriksaan guru.
        """)

        st.warning(
            "Silakan hubungi guru untuk pemeriksaan lebih lanjut."
        )

        return

    # -----------------------------------------------------
    # Jika belum memulai ujian
    # -----------------------------------------------------

    if not st.session_state.ujian_aktif:

        st.subheader("Pengaturan Keamanan Ujian")

        st.write("""
        Pilih metode pemantauan sebelum memulai ujian.
        """)

        mode = st.selectbox(
            "Pilih Mode Keamanan",
            MODE_KEAMANAN
        )

        if mode == "Website Monitoring":

            st.info("""
            Sistem mencoba mendeteksi perpindahan tab,
            hilangnya fokus halaman, dan keluar dari
            mode layar penuh.
            """)

        elif mode == "Safe Exam Browser (SEB)":

            st.warning("""
            Mode SEB membutuhkan aplikasi Safe Exam Browser
            yang telah dipasang dan dikonfigurasi pada perangkat
            siswa. Aplikasi Streamlit ini belum dapat memastikan
            bahwa SEB benar-benar digunakan.
            """)

        else:

            st.info("""
            Mode Gabungan menggabungkan pemantauan website
            dengan penggunaan Safe Exam Browser yang
            dikonfigurasi secara terpisah.
            """)

        st.divider()

        st.subheader("Petunjuk Ujian")

        st.write("""
        1. Ujian terdiri dari 10 soal.
        2. Setiap soal memiliki empat tingkat pertanyaan, dengan lima pilihan jawaban (A–E) dan lima pilihan alasan (A–E).
        4. Jawablah sesuai pemahaman sendiri.
        5. Pilih tingkat keyakinan secara jujur.
        6. Jangan meninggalkan halaman ujian.
        """)

        persetujuan = st.checkbox(
            "Saya siap mengikuti ujian dan memahami petunjuk."
        )

        if st.button(
            "Mulai Ujian",
            disabled=not persetujuan,
            use_container_width=True
        ):

            mulai_ujian(mode)

        return

    # -----------------------------------------------------
    # Pemantauan ujian
    # -----------------------------------------------------

    st.info(
        f"Mode keamanan: {st.session_state.mode_ujian}"
    )

    st.write(
        f"Pelanggaran tercatat: "
        f"{st.session_state.pelanggaran_sesi}/"
        f"{BATAS_PELANGGARAN}"
    )

    tampilkan_monitor_website()

    st.divider()

    # -----------------------------------------------------
    # Menentukan nomor soal
    # -----------------------------------------------------

    nomor = st.session_state.nomor_soal

    soal = SOAL[nomor]

    st.subheader(
        f"Soal {nomor + 1} dari {JUMLAH_SOAL}"
    )

    st.progress(
        (nomor + 1) / JUMLAH_SOAL
    )

    st.write(
        f"**Materi: {soal['materi']}**"
    )

    st.write(
        soal["pertanyaan"]
    )

    # -----------------------------------------------------
    # Mengambil jawaban sebelumnya
    # -----------------------------------------------------

    data_lama = st.session_state.jawaban_siswa.get(
        str(nomor),
        {}
    )

    with st.form(
        key=f"form_soal_{nomor}"
    ):

        st.markdown("### Tingkat 1 — Jawaban")

        jawaban = st.radio(
            "Pilih jawaban yang paling tepat:",
            options=["A", "B", "C", "D", "E"],
            format_func=lambda x: next(
                item for item in soal["pilihan"]
                if item.startswith(x + ".")
            ),
            index=(
                ["A", "B", "C", "D", "E"].index(
                    data_lama["jawaban"]
                )
                if data_lama.get("jawaban") in
                ["A", "B", "C", "D", "E"]
                else None
            ),
            key=f"jawaban_{nomor}"
        )

        st.markdown("### Tingkat 2 — Keyakinan Jawaban")

        yakin_jawaban = st.radio(
            "Seberapa yakin Anda terhadap jawaban tersebut?",
            ["Yakin", "Tidak Yakin"],
            index=(
                ["Yakin", "Tidak Yakin"].index(
                    data_lama["keyakinan_jawaban"]
                )
                if data_lama.get("keyakinan_jawaban")
                in ["Yakin", "Tidak Yakin"]
                else None
            ),
            key=f"keyakinan_jawaban_{nomor}"
        )

        st.markdown("### Tingkat 3 — Alasan")

        alasan = st.radio(
            "Pilih alasan yang paling tepat:",
            options=["A", "B", "C", "D", "E"],
            format_func=lambda x: next(
                item for item in soal["alasan"]
                if item.startswith(x + ".")
            ),
            index=(
                ["A", "B", "C", "D", "E"].index(
                    data_lama["alasan"]
                )
                if data_lama.get("alasan") in
                ["A", "B", "C", "D", "E"]
                else None
            ),
            key=f"alasan_{nomor}"
        )

        st.markdown("### Tingkat 4 — Keyakinan Alasan")

        yakin_alasan = st.radio(
            "Seberapa yakin Anda terhadap alasan tersebut?",
            ["Yakin", "Tidak Yakin"],
            index=(
                ["Yakin", "Tidak Yakin"].index(
                    data_lama["keyakinan_alasan"]
                )
                if data_lama.get("keyakinan_alasan")
                in ["Yakin", "Tidak Yakin"]
                else None
            ),
            key=f"keyakinan_alasan_{nomor}"
        )

        st.divider()

        col1, col2 = st.columns(2)

        with col1:

            tombol_sebelumnya = st.form_submit_button(
                "Soal Sebelumnya",
                disabled=(nomor == 0),
                use_container_width=True
            )

        with col2:

            tombol_selanjutnya = st.form_submit_button(
                "Simpan dan Lanjutkan"
                if nomor < JUMLAH_SOAL - 1
                else "Selesaikan Ujian",
                use_container_width=True
            )

    # -----------------------------------------------------
    # Menyimpan jawaban dan berpindah soal
    # -----------------------------------------------------

    if tombol_sebelumnya or tombol_selanjutnya:

        if (
            jawaban is None
            or yakin_jawaban is None
            or alasan is None
            or yakin_alasan is None
        ):

            st.error(
                "Silakan lengkapi seluruh tingkat pertanyaan."
            )

            return

        st.session_state.jawaban_siswa[
            str(nomor)
        ] = {

            "jawaban": jawaban,

            "keyakinan_jawaban": yakin_jawaban,

            "alasan": alasan,

            "keyakinan_alasan": yakin_alasan

        }

        if tombol_sebelumnya:

            st.session_state.nomor_soal -= 1

            st.rerun()

        elif tombol_selanjutnya:

            if nomor < JUMLAH_SOAL - 1:

                st.session_state.nomor_soal += 1

                st.rerun()

            else:

                if len(st.session_state.jawaban_siswa) != JUMLAH_SOAL:

                    st.error(
                        "Masih ada soal yang belum dijawab."
                    )

                    return

                hasil = analisis_jawaban(
                    st.session_state.jawaban_siswa
                )

                simpan_hasil_tes(
                    st.session_state.username,
                    hasil
                )

                st.session_state.hasil_ujian = hasil

                st.session_state.ujian_aktif = False
                st.session_state.ujian_selesai = True

                st.session_state.halaman = "Hasil Diagnosis"

                st.rerun()

# =========================================================
# 37. HALAMAN HASIL DIAGNOSIS
# =========================================================

def halaman_hasil_diagnosis():

    tampilkan_header()

    st.title("📊 Hasil Diagnosis Miskonsepsi")

    if st.session_state.hasil_ujian is None:

        st.info(
            "Belum ada hasil diagnosis pada sesi ini. "
            "Silakan kerjakan tes diagnostik terlebih dahulu."
        )

        riwayat = ambil_riwayat_siswa(
            st.session_state.username
        )

        if not riwayat.empty:

            st.subheader("Riwayat Hasil Tes")

            st.dataframe(
                riwayat,
                use_container_width=True,
                hide_index=True
            )

        return

    hasil = st.session_state.hasil_ujian

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        st.metric(
            "Skor Pemahaman",
            f"{hasil['skor']:.1f}"
        )

    with col2:

        st.metric(
            "Paham Konsep",
            hasil["jumlah_paham"]
        )

    with col3:

        st.metric(
            "Miskonsepsi",
            hasil["jumlah_miskonsepsi"]
        )

    with col4:

        st.metric(
            "Tidak Paham",
            hasil["jumlah_tidak_paham"]
        )

    st.divider()

    st.subheader("Distribusi Hasil Diagnosis")

    data_grafik = pd.DataFrame({

        "Kategori": [
            "Paham Konsep",
            "Miskonsepsi",
            "Tidak Paham Konsep",
            "Menebak"
        ],

        "Jumlah": [
            hasil["jumlah_paham"],
            hasil["jumlah_miskonsepsi"],
            hasil["jumlah_tidak_paham"],
            hasil["jumlah_menebak"]
        ]

    })

    st.bar_chart(
        data_grafik.set_index("Kategori")
    )

    st.divider()

    st.subheader("Rincian Diagnosis Setiap Soal")

    detail = pd.DataFrame(
        hasil["detail"]
    )

    kolom_tampil = [
        "Nomor",
        "Materi",
        "Kategori",
        "Jawaban Siswa",
        "Jawaban Benar"
    ]

    st.dataframe(
        detail[kolom_tampil],
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    st.subheader("Pembahasan Jawaban")

    for item in hasil["detail"]:

        with st.expander(
            f"Soal {item['Nomor']} - {item['Materi']}"
        ):

            st.write(
                f"**Kategori:** {item['Kategori']}"
            )

            st.write(
                f"**Jawaban siswa:** {item['Jawaban Siswa']}"
            )

            st.write(
                f"**Jawaban benar:** {item['Jawaban Benar']}"
            )

            st.write(
                f"**Alasan siswa:** {item['Alasan Siswa']}"
            )

            st.write(
                f"**Alasan benar:** {item['Alasan Benar']}"
            )

            st.info(
                item["Pembahasan"]
            )

    st.divider()

    if hasil["jumlah_miskonsepsi"] > 0:

        st.warning(
            "Masih terdapat konsep yang mengalami miskonsepsi. "
            "Silakan pelajari kembali materi remedial."
        )

        if st.button(
            "Buka Materi Remedial",
            use_container_width=True
        ):

            st.session_state.halaman = "Materi Remedial"
            st.rerun()

    else:

        st.success(
            "Tidak ditemukan miskonsepsi berdasarkan "
            "aturan diagnosis yang digunakan."
        )


# =========================================================
# 38. HALAMAN PETA MISKONSEPSI
# =========================================================

def halaman_peta_miskonsepsi():

    tampilkan_header()

    st.title("🗺️ Peta Miskonsepsi")

    st.write("""
    Peta miskonsepsi menunjukkan materi yang paling banyak
    mengalami kesalahan pemahaman berdasarkan hasil tes siswa.
    """)

    hasil = st.session_state.hasil_ujian

    if hasil is None:

        st.info(
            "Peta miskonsepsi akan tersedia setelah "
            "siswa menyelesaikan tes."
        )

        return

    detail = pd.DataFrame(
        hasil["detail"]
    )

    ringkasan = detail.groupby(
        ["Materi", "Kategori"]
    ).size().unstack(fill_value=0)

    kategori = [
        "Paham Konsep",
        "Miskonsepsi",
        "Tidak Paham Konsep",
        "Menebak"
    ]

    for nama in kategori:

        if nama not in ringkasan.columns:

            ringkasan[nama] = 0

    ringkasan = ringkasan[kategori]

    st.subheader("Sebaran Diagnosis Berdasarkan Materi")

    st.dataframe(
        ringkasan,
        use_container_width=True
    )

    st.bar_chart(
        ringkasan
    )

    st.divider()

    st.subheader("Materi yang Perlu Diperbaiki")

    jumlah_miskonsepsi = (
        detail[
            detail["Kategori"] == "Miskonsepsi"
        ]
        .groupby("Materi")
        .size()
        .sort_values(ascending=False)
    )

    if jumlah_miskonsepsi.empty:

        st.success(
            "Tidak ditemukan kategori miskonsepsi."
        )

    else:

        for materi, jumlah in jumlah_miskonsepsi.items():

            st.warning(
                f"**{materi}**: {jumlah} soal mengalami miskonsepsi."
            )


# =========================================================
# 39. HALAMAN MATERI REMEDIAL
# =========================================================

def halaman_remedial():

    tampilkan_header()

    st.title("📚 Materi Remedial")

    st.write("""
    Materi remedial digunakan untuk membantu siswa
    memperbaiki pemahaman terhadap konsep yang belum dikuasai.
    """)

    hasil = st.session_state.hasil_ujian

    materi_rekomendasi = []

    if hasil is not None:

        for item in hasil["detail"]:

            if item["Kategori"] in [
                "Miskonsepsi",
                "Tidak Paham Konsep"
            ]:

                if item["Materi"] not in materi_rekomendasi:

                    materi_rekomendasi.append(
                        item["Materi"]
                    )

    if materi_rekomendasi:

        st.subheader("Rekomendasi Materi untuk Dipelajari")

        for materi in materi_rekomendasi:

            st.warning(
                f"Perlu mempelajari kembali: {materi}"
            )

    else:

        st.info(
            "Semua materi tersedia untuk dipelajari secara mandiri."
        )

    st.divider()

    pilihan_materi = st.selectbox(
        "Pilih materi pembelajaran",
        list(MATERI.keys())
    )

    materi = MATERI[pilihan_materi]

    st.subheader(
        materi["judul"]
    )

    st.markdown(
        materi["isi"]
    )

    if "rumus" in materi:

        st.divider()

        st.subheader("Rumus Penting")

        st.latex(
            materi["rumus"]
        )

    st.divider()

    st.subheader("Pemahaman Materi")

    st.write("""
    Setelah mempelajari materi, pastikan Anda dapat
    menjelaskan kembali konsep menggunakan bahasa sendiri.
    """)

    sudah_paham = st.checkbox(
        "Saya sudah mempelajari dan memahami materi ini."
    )

    if sudah_paham:

        st.success(
            "Bagus! Lanjutkan mempelajari materi lainnya."
        )


# =========================================================
# 40. HALAMAN LABORATORIUM VIRTUAL
# =========================================================

def halaman_laboratorium():

    tampilkan_header()

    st.title("🔬 Laboratorium Virtual")

    st.write("""
    Laboratorium virtual digunakan untuk mempelajari
    hubungan antara frekuensi, panjang gelombang,
    kecepatan rambat, dan energi gelombang elektromagnetik.
    """)

    st.divider()

    st.subheader("Simulasi Frekuensi dan Panjang Gelombang")

    frekuensi = st.slider(
        "Frekuensi gelombang (Hz)",
        min_value=1,
        max_value=100,
        value=10,
        step=1
    )

    # Kecepatan disederhanakan menjadi 300 m/s
    # agar hasil simulasi mudah diamati.

    kecepatan_simulasi = 300

    panjang_gelombang = (
        kecepatan_simulasi / frekuensi
    )

    col1, col2 = st.columns(2)

    with col1:

        st.metric(
            "Frekuensi",
            f"{frekuensi} Hz"
        )

    with col2:

        st.metric(
            "Panjang Gelombang",
            f"{panjang_gelombang:.2f} m"
        )

    st.info(
        "Simulasi menggunakan kecepatan rambat 300 m/s "
        "sebagai nilai ilustrasi, bukan kecepatan cahaya "
        "di ruang hampa."
    )

    st.latex(
        r"v = \lambda f"
    )

    st.latex(
        rf"\lambda = \frac{{{kecepatan_simulasi}}}{{{frekuensi}}}"
    )

    st.divider()

    st.subheader("Grafik Gelombang")

    x = np.linspace(
        0,
        2 * np.pi,
        500
    )

    y = np.sin(
        frekuensi / 10 * x
    )

    grafik, ax = plt.subplots()

    ax.plot(
        x,
        y
    )

    ax.set_title(
        "Simulasi Bentuk Gelombang"
    )

    ax.set_xlabel(
        "Posisi"
    )

    ax.set_ylabel(
        "Amplitudo"
    )

    ax.grid(True)

    st.pyplot(
        grafik
    )

    plt.close(grafik)

    st.divider()

    st.subheader("Simulasi Energi Foton")

    frekuensi_foton = st.number_input(
        "Frekuensi foton (Hz)",
        min_value=1.0,
        value=1e14,
        format="%.2e"
    )

    energi = H * frekuensi_foton

    st.metric(
        "Energi Foton",
        f"{energi:.4e} Joule"
    )

    st.latex(
        r"E = hf"
    )

    st.write(
        "Semakin besar frekuensi, semakin besar energi foton."
    )


# =========================================================
# 41. HALAMAN RIWAYAT TES
# =========================================================

def halaman_riwayat():

    tampilkan_header()

    st.title("📜 Riwayat Tes")

    riwayat = ambil_riwayat_siswa(
        st.session_state.username
    )

    if riwayat.empty:

        st.info(
            "Belum terdapat riwayat tes."
        )

        return

    st.subheader("Data Riwayat")

    st.dataframe(
        riwayat,
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    st.subheader("Grafik Perkembangan Skor")

    grafik_data = riwayat.copy()

    grafik_data["Tanggal"] = pd.to_datetime(
        grafik_data["Tanggal"]
    )

    grafik_data = grafik_data.sort_values(
        "Tanggal"
    )

    st.line_chart(
        grafik_data.set_index("Tanggal")["Skor"]
    )

    st.divider()

    st.subheader("Ringkasan Perkembangan")

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "Jumlah Tes",
            len(riwayat)
        )

    with col2:

        st.metric(
            "Skor Tertinggi",
            f"{riwayat['Skor'].max():.1f}"
        )

    with col3:

        st.metric(
            "Rata-rata Skor",
            f"{riwayat['Skor'].mean():.1f}"
        )

    csv = riwayat.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "Unduh Riwayat dalam CSV",
        data=csv,
        file_name="riwayat_tes.csv",
        mime="text/csv",
        use_container_width=True
    )

# =========================================================
# 42. DASHBOARD GURU
# =========================================================

def halaman_guru():

    tampilkan_header()

    st.title("👨‍🏫 Dashboard Guru")

    st.write("""
    Dashboard ini digunakan guru untuk memantau hasil
    tes diagnostik, menganalisis miskonsepsi siswa,
    dan memeriksa catatan pelanggaran ujian.
    """)

    # -----------------------------------------------------
    # Mengambil data
    # -----------------------------------------------------

    hasil = ambil_semua_hasil()

    pelanggaran = ambil_semua_pelanggaran()

    st.divider()

    # -----------------------------------------------------
    # Ringkasan pelanggaran
    # -----------------------------------------------------

    st.subheader("🔐 Pemantauan Keamanan Ujian")

    if pelanggaran.empty:

        st.success(
            "Belum terdapat catatan pelanggaran ujian."
        )

    else:

        col1, col2 = st.columns(2)

        with col1:

            st.metric(
                "Jumlah Catatan Pelanggaran",
                len(pelanggaran)
            )

        with col2:

            st.metric(
                "Jumlah Siswa Terpantau",
                pelanggaran["Nama Siswa"].nunique()
            )

        st.subheader("Daftar Pelanggaran")

        st.dataframe(
            pelanggaran,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Unduh Data Pelanggaran CSV",
            data=pelanggaran.to_csv(
                index=False
            ).encode("utf-8"),
            file_name="data_pelanggaran.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.divider()

    # -----------------------------------------------------
    # Jika belum ada hasil tes
    # -----------------------------------------------------

    if hasil.empty:

        st.info(
            "Belum ada hasil tes siswa yang tersimpan."
        )

        return

    # -----------------------------------------------------
    # Ringkasan hasil tes
    # -----------------------------------------------------

    st.subheader("📊 Ringkasan Hasil Tes Siswa")

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        st.metric(
            "Jumlah Tes",
            len(hasil)
        )

    with col2:

        st.metric(
            "Jumlah Siswa",
            hasil["Nama Siswa"].nunique()
        )

    with col3:

        st.metric(
            "Rata-rata Skor",
            f"{hasil['Skor'].mean():.1f}"
        )

    with col4:

        st.metric(
            "Total Miskonsepsi",
            int(
                hasil["Jumlah Miskonsepsi"].sum()
            )
        )

    st.divider()

    # -----------------------------------------------------
    # Data seluruh siswa
    # -----------------------------------------------------

    st.subheader("Data Hasil Tes")

    data_tampil = hasil.drop(
        columns=["Detail Jawaban"],
        errors="ignore"
    )

    st.dataframe(
        data_tampil,
        use_container_width=True,
        hide_index=True
    )

    # -----------------------------------------------------
    # Grafik nilai siswa
    # -----------------------------------------------------

    st.subheader("Grafik Skor Siswa")

    grafik_siswa = hasil.groupby(
        "Nama Siswa"
    )["Skor"].mean()

    st.bar_chart(
        grafik_siswa
    )

    st.divider()

    # -----------------------------------------------------
    # Analisis materi
    # -----------------------------------------------------

    st.subheader("Analisis Miskonsepsi Berdasarkan Materi")

    semua_detail = []

    for _, baris in hasil.iterrows():

        try:

            detail = json.loads(
                baris["Detail Jawaban"]
            )

            for item in detail:

                item["Nama Siswa"] = baris["Nama Siswa"]

                semua_detail.append(item)

        except Exception:

            continue

    if semua_detail:

        detail_df = pd.DataFrame(
            semua_detail
        )

        analisis_materi = detail_df.groupby(
            ["Materi", "Kategori"]
        ).size().unstack(fill_value=0)

        kategori = [
            "Paham Konsep",
            "Miskonsepsi",
            "Tidak Paham Konsep",
            "Menebak"
        ]

        for nama in kategori:

            if nama not in analisis_materi.columns:

                analisis_materi[nama] = 0

        analisis_materi = analisis_materi[
            kategori
        ]

        st.dataframe(
            analisis_materi,
            use_container_width=True
        )

        st.bar_chart(
            analisis_materi
        )

        st.divider()

        st.subheader("Rincian Diagnosis Siswa")

        nama_siswa = st.selectbox(
            "Pilih siswa",
            sorted(
                detail_df["Nama Siswa"].unique()
            )
        )

        rincian_siswa = detail_df[
            detail_df["Nama Siswa"] == nama_siswa
        ]

        st.dataframe(
            rincian_siswa[
                [
                    "Nomor",
                    "Materi",
                    "Jawaban Siswa",
                    "Jawaban Benar",
                    "Kategori"
                ]
            ],
            use_container_width=True,
            hide_index=True
        )

    # -----------------------------------------------------
    # Ekspor Excel
    # -----------------------------------------------------

    st.divider()

    st.subheader("📥 Ekspor Data Excel")

    if st.button(
        "Buat Laporan Excel",
        use_container_width=True
    ):

        output = io.BytesIO()

        with pd.ExcelWriter(
            output,
            engine="openpyxl"
        ) as writer:

            hasil.drop(
                columns=["Detail Jawaban"],
                errors="ignore"
            ).to_excel(
                writer,
                sheet_name="Ringkasan Tes",
                index=False
            )

            hasil[
                [
                    "Nama Siswa",
                    "Tanggal",
                    "Skor",
                    "Total Soal",
                    "Jumlah Miskonsepsi",
                    "Jumlah Paham"
                ]
            ].to_excel(
                writer,
                sheet_name="Data Siswa",
                index=False
            )

            if semua_detail:

                detail_df.to_excel(
                    writer,
                    sheet_name="Rincian Diagnosis",
                    index=False
                )

                analisis_materi.to_excel(
                    writer,
                    sheet_name="Analisis Materi"
                )

            if not pelanggaran.empty:

                pelanggaran.to_excel(
                    writer,
                    sheet_name="Pelanggaran Ujian",
                    index=False
                )

        st.download_button(
            label="Unduh Laporan Excel",
            data=output.getvalue(),
            file_name="laporan_miskonseption.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True
        )


# =========================================================
# 43. FUNGSI PENGATUR HALAMAN
# =========================================================

def tampilkan_halaman():

    halaman = st.session_state.halaman

    # -----------------------------------------------------
    # Halaman umum
    # -----------------------------------------------------

    if halaman == "Beranda":

        halaman_beranda()

    elif halaman == "Login":

        halaman_login()

    elif halaman == "Registrasi":

        halaman_registrasi()

    # -----------------------------------------------------
    # Halaman siswa
    # -----------------------------------------------------

    elif halaman == "Dashboard Siswa":

        if hanya_siswa():

            halaman_dashboard_siswa()

        else:

            st.error(
                "Anda tidak memiliki akses ke halaman ini."
            )

    elif halaman == "Tes Diagnostik":

        if hanya_siswa():

            halaman_tes()

        else:

            st.error(
                "Anda tidak memiliki akses ke halaman ini."
            )

    elif halaman == "Hasil Diagnosis":

        if hanya_siswa():

            halaman_hasil_diagnosis()

        else:

            st.error(
                "Anda tidak memiliki akses ke halaman ini."
            )

    elif halaman == "Peta Miskonsepsi":

        if hanya_siswa():

            halaman_peta_miskonsepsi()

        else:

            st.error(
                "Anda tidak memiliki akses ke halaman ini."
            )

    elif halaman == "Materi Remedial":

        if hanya_siswa():

            halaman_remedial()

        else:

            st.error(
                "Anda tidak memiliki akses ke halaman ini."
            )

    elif halaman == "Laboratorium Virtual":

        if hanya_siswa():

            halaman_laboratorium()

        else:

            st.error(
                "Anda tidak memiliki akses ke halaman ini."
            )

    elif halaman == "Riwayat Tes":

        if hanya_siswa():

            halaman_riwayat()

        else:

            st.error(
                "Anda tidak memiliki akses ke halaman ini."
            )

    # -----------------------------------------------------
    # Halaman guru
    # -----------------------------------------------------

    elif halaman == "Dashboard Guru":

        if hanya_guru():

            halaman_guru()

        else:

            st.error(
                "Anda tidak memiliki akses ke halaman guru."
            )

    else:

        st.warning(
            "Halaman tidak ditemukan."
        )

        st.session_state.halaman = "Beranda"

        st.rerun()


# =========================================================
# 44. FUNGSI UTAMA APLIKASI
# =========================================================

def main():

    # Sidebar navigasi
    halaman_sidebar()

    # Tampilan halaman utama
    tampilkan_halaman()


# =========================================================
# 45. MENJALANKAN APLIKASI
# =========================================================

if __name__ == "__main__":

    main()


# =========================================================
# 46. RESPONSIVE DESIGN UNTUK HP, TABLET, DAN LAPTOP
# =========================================================

st.markdown("""
<style>

/* =========================================
   1. WARNA DASAR DAN TAMPILAN UTAMA
========================================= */

:root {
    --warna-utama: #2457A7;
    --warna-gelap: #17345F;
    --warna-latar: #F4F7FC;
    --warna-kartu: #FFFFFF;
    --warna-teks: #1B2638;
    --warna-teks-kedua: #536176;
    --warna-garis: #DCE4F0;
}

.stApp {
    background-color: var(--warna-latar);
    color: var(--warna-teks);
}

/* Area konten */
.main .block-container {
    max-width: 1200px;
    padding-top: 1.5rem;
    padding-bottom: 3rem;
    padding-left: 2rem;
    padding-right: 2rem;
}

/* =========================================
   2. TULISAN AGAR LEBIH JELAS
========================================= */

.stApp p,
.stApp li,
.stApp label,
.stApp .stMarkdown,
.stApp .stText,
.stApp [data-testid="stCaptionContainer"] {
    color: var(--warna-teks);
    line-height: 1.65;
}

.stApp h1 {
    color: var(--warna-gelap);
    font-size: 2rem;
    font-weight: 800;
}

.stApp h2 {
    color: var(--warna-gelap);
    font-size: 1.65rem;
    font-weight: 750;
}

.stApp h3 {
    color: var(--warna-utama);
    font-size: 1.3rem;
    font-weight: 700;
}

/* Teks kecil tetap terbaca */
[data-testid="stCaptionContainer"] p {
    font-size: 0.9rem;
    color: var(--warna-teks-kedua);
}

/* =========================================
   3. KARTU DAN KOTAK INFORMASI
========================================= */

[data-testid="stMetric"],
[data-testid="stExpander"],
div[data-testid="stForm"],
div[data-testid="stAlert"] {
    border-radius: 14px;
}

[data-testid="stMetric"] {
    background: var(--warna-kartu);
    border: 1px solid var(--warna-garis);
    padding: 15px;
}

[data-testid="stMetricLabel"] {
    color: var(--warna-teks-kedua);
    font-weight: 600;
}

[data-testid="stMetricValue"] {
    color: var(--warna-gelap);
    font-weight: 800;
}

/* =========================================
   4. TOMBOL
========================================= */

.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button {
    background-color: var(--warna-utama);
    color: #FFFFFF !important;
    border: 1px solid var(--warna-utama);
    border-radius: 10px;
    min-height: 44px;
    font-weight: 700;
    padding: 0.55rem 1rem;
    transition: 0.2s ease;
}

.stButton > button p,
.stDownloadButton > button p,
.stFormSubmitButton > button p {
    color: #FFFFFF !important;
    font-weight: 700;
}

.stButton > button:hover,
.stDownloadButton > button:hover,
.stFormSubmitButton > button:hover {
    background-color: var(--warna-gelap);
    border-color: var(--warna-gelap);
    color: #FFFFFF !important;
}

/* =========================================
   5. INPUT DAN PILIHAN JAWABAN
========================================= */

.stTextInput input,
.stNumberInput input,
.stTextArea textarea {
    background-color: #FFFFFF !important;
    color: var(--warna-teks) !important;
    border: 1px solid #B8C7DA !important;
    border-radius: 9px;
    font-size: 16px !important;
    min-height: 44px;
}

[data-baseweb="select"] > div {
    background-color: #FFFFFF !important;
    color: var(--warna-teks) !important;
    border-color: #B8C7DA !important;
    min-height: 44px;
}

.stRadio label,
.stCheckbox label {
    color: var(--warna-teks) !important;
    font-size: 1rem;
    line-height: 1.5;
}

/* =========================================
   6. TABEL DAN TAB
========================================= */

[data-testid="stDataFrame"] {
    border: 1px solid var(--warna-garis);
    border-radius: 10px;
    overflow: hidden;
}

.stTabs [data-baseweb="tab"] {
    color: var(--warna-teks);
    font-weight: 700;
    font-size: 0.95rem;
}

.stTabs [aria-selected="true"] {
    color: var(--warna-utama) !important;
}

/* =========================================
   7. SIDEBAR
========================================= */

[data-testid="stSidebar"] {
    background-color: #EAF0FA;
}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span {
    color: var(--warna-teks);
}

/* =========================================
   8. TAMPILAN TABLET
========================================= */

@media (max-width: 900px) {

    .main .block-container {
        padding-left: 1.2rem;
        padding-right: 1.2rem;
    }

    .stApp h1 {
        font-size: 1.8rem;
    }

    .stApp h2 {
        font-size: 1.45rem;
    }

    .stApp h3 {
        font-size: 1.2rem;
    }
}

/* =========================================
   9. TAMPILAN HP
========================================= */

@media (max-width: 600px) {

    /* Ruang konten HP */
    .main .block-container {
        padding-top: 1rem;
        padding-left: 0.85rem;
        padding-right: 0.85rem;
        padding-bottom: 2rem;
    }

    /* Ukuran tulisan */
    .stApp {
        font-size: 16px;
    }

    .stApp p,
    .stApp li,
    .stApp label,
    .stApp .stMarkdown {
        font-size: 15px;
        line-height: 1.65;
    }

    .stApp h1 {
        font-size: 1.55rem;
        line-height: 1.3;
    }

    .stApp h2 {
        font-size: 1.3rem;
        line-height: 1.35;
    }

    .stApp h3 {
        font-size: 1.12rem;
        line-height: 1.4;
    }

    /* Tombol lebih mudah disentuh */
    .stButton > button,
    .stDownloadButton > button,
    .stFormSubmitButton > button {
        width: 100%;
        min-height: 48px;
        font-size: 15px;
        white-space: normal;
    }

    /* Input tidak terlalu kecil */
    .stTextInput input,
    .stNumberInput input,
    .stTextArea textarea {
        font-size: 16px !important;
        min-height: 46px;
    }

    /* Pilihan jawaban */
    .stRadio label,
    .stCheckbox label {
        font-size: 15px !important;
        line-height: 1.55;
        padding-top: 4px;
        padding-bottom: 4px;
    }

    /* Kartu metrik */
    [data-testid="stMetric"] {
        padding: 11px;
        margin-bottom: 8px;
    }

    [data-testid="stMetricLabel"] {
        font-size: 12px;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.35rem;
    }

    /* Tab bisa digeser */
    .stTabs [data-baseweb="tab-list"] {
        gap: 5px;
        overflow-x: auto;
        flex-wrap: nowrap;
    }

    .stTabs [data-baseweb="tab"] {
        font-size: 13px;
        padding: 8px 10px;
        white-space: nowrap;
    }

    /* Tabel tetap bisa digeser */
    [data-testid="stDataFrame"] {
        max-width: 100%;
        overflow-x: auto;
    }

    /* Gambar menyesuaikan layar */
    [data-testid="stImage"] img {
        max-width: 100%;
        height: auto;
    }

    /* Jarak antarbagian */
    [data-testid="stVerticalBlock"] {
        gap: 0.75rem;
    }

    /* Tulisan sidebar */
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label {
        font-size: 15px;
    }
}

/* =========================================
   10. MENCEGAH KONTEN MELEBAR KELUAR LAYAR
========================================= */

.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    max-width: 100%;
    overflow-wrap: break-word;
}

pre,
code {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
}

</style>
""", unsafe_allow_html=True)
