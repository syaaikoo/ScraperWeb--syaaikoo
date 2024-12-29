import logging

# Konfigurasi umum
KONFIGURASI = {
    'MAKS_PERCOBAAN': 3,
    'BATAS_WAKTU': 30,
    'MAKS_THREAD': 5,
    'CACHE_EXPIRY': 3600,  # 1 jam dalam detik
    'GUNAKAN_CACHE_FILE': True,
    'CACHE_FILE': 'phantom_web_cache.json',
    'BATAS_PERMINTAAN': 10,  # Jumlah permintaan maksimum per menit
    'GUNAKAN_PROXY': False,
    'PROXY': {
        'http': 'http://proxy.example.com:8080',
        'https': 'https://proxy.example.com:8080'
    },
    'VERIFIKASI_SSL': True,
    'LOG_LEVEL': logging.INFO,
    'LOG_FILE': 'phantom_web.log'
}

# User-Agent
AGEN_PENGGUNA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
]

# Header permintaan
HEADER = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

# Kode error
KODE_ERROR = {
    'KONEKSI_GAGAL': 1001,
    'BATAS_WAKTU_TERLAMPAUI': 1002,
    'KESALAHAN_SSL': 1003,
    'BATAS_PERMINTAAN_TERLAMPAUI': 1004,
    'KESALAHAN_PARSING': 1005
}

# Pesan error
PESAN_ERROR = {
    KODE_ERROR['KONEKSI_GAGAL']: "Gagal terhubung ke server. Periksa koneksi internet Anda.",
    KODE_ERROR['BATAS_WAKTU_TERLAMPAUI']: "Waktu permintaan habis. Server terlalu lama merespons.",
    KODE_ERROR['KESALAHAN_SSL']: "Terjadi kesalahan SSL. Coba aktifkan opsi 'VERIFIKASI_SSL' di konfigurasi.",
    KODE_ERROR['BATAS_PERMINTAAN_TERLAMPAUI']: "Batas permintaan terlampaui. Coba lagi nanti.",
    KODE_ERROR['KESALAHAN_PARSING']: "Gagal mengurai konten HTML. Struktur halaman mungkin telah berubah."
}

# Fungsi untuk dapetin pesan error
def dapatkan_pesan_error(kode):
    return PESAN_ERROR.get(kode, "Terjadi kesalahan yang tidak diketahui.")

