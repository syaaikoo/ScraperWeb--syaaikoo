import sys
import subprocess
import pkg_resources
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import json
import xml.etree.ElementTree as ET
import time
import os
import random
import concurrent.futures
from functools import lru_cache
import csv
import logging
from ratelimit import limits, sleep_and_retry
import zipfile
import smtplib
from email.mime.text import MIMEText
import telegram
import asyncio
import multiprocessing
import boto3
from google.cloud import storage
from azure.storage.blob import BlobServiceClient
from textblob import TextBlob
import matplotlib.pyplot as plt

from konfigurasi import KONFIGURASI, AGEN_PENGGUNA, HEADER, KODE_ERROR, dapatkan_pesan_error
from output_config import OUTPUT_KONFIGURASI
from crawling_config import CRAWLING_KONFIGURASI
from parsing_config import PARSING_KONFIGURASI
from database_config import DATABASE_KONFIGURASI
from notification_config import NOTIFIKASI_KONFIGURASI
from security_config import KEAMANAN_KONFIGURASI
from analysis_config import ANALISIS_KONFIGURASI
from performance_config import KINERJA_KONFIGURASI
from storage_config import PENYIMPANAN_KONFIGURASI
from visualization_config import VISUALISASI_KONFIGURASI

def CEK_INSTALL_DEPENDESI():
    required = {
        'requests', 'beautifulsoup4', 'rich', 'langdetect', 'python-Wappalyzer',
        'ratelimit', 'textblob', 'matplotlib', 'boto3', 'google-cloud-storage',
        'azure-storage-blob', 'python-telegram-bot'
    }
    installed = {pkg.key for pkg in pkg_resources.working_set}
    missing = required - installed

    if missing:
        print("Tunggu sebentar lagi install dependesi...")
        python = sys.executable
        subprocess.check_call([python, '-m', 'pip', 'install', *missing], stdout=subprocess.DEVNULL)
        print("Dependensi berhasil diinstal.")
    
    global Console, Panel, Progress, SpinnerColumn, BarColumn, TextColumn, Syntax, Table
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
    from rich.syntax import Syntax
    from rich.table import Table
    from langdetect import detect
    from Wappalyzer import Wappalyzer, WebPage

CEK_INSTALL_DEPENDESI()

console = Console()

# Konfigurasi logging
logging.basicConfig(filename=KONFIGURASI['LOG_FILE'], level=KONFIGURASI['LOG_LEVEL'],
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Cache buat nyimpen hasil
hasil_cache = {}

def url_valid(url):
    parsed = urlparse(url)
    return bool(parsed.netloc) and bool(parsed.scheme)

@lru_cache(maxsize=100)
@sleep_and_retry
@limits(calls=KONFIGURASI['BATAS_PERMINTAAN'], period=60)
def ambil_kode_sumber(url, gunakan_cache=True):
    if gunakan_cache:
        if KONFIGURASI['GUNAKAN_CACHE_FILE']:
            try:
                with open(KONFIGURASI['CACHE_FILE'], 'r') as f:
                    cache_file = json.load(f)
                if url in cache_file and time.time() - cache_file[url]['waktu'] < KONFIGURASI['CACHE_EXPIRY']:
                    return cache_file[url]['data']
            except (FileNotFoundError, json.JSONDecodeError):
                pass
        elif url in hasil_cache and time.time() - hasil_cache[url]['waktu'] < KONFIGURASI['CACHE_EXPIRY']:
            return hasil_cache[url]['data']

    headers = HEADER.copy()
    headers["User-Agent"] = random.choice(AGEN_PENGGUNA)

    for percobaan in range(KONFIGURASI['MAKS_PERCOBAAN']):
        try:
            session = requests.Session()
            if KEAMANAN_KONFIGURASI['GUNAKAN_TOR']:
                session.proxies = {'http': KEAMANAN_KONFIGURASI['TOR_PROXY'], 'https': KEAMANAN_KONFIGURASI['TOR_PROXY']}
            
            response = session.get(
                url,
                headers=headers,
                timeout=KINERJA_KONFIGURASI['TIMEOUT_PERMINTAAN'],
                proxies=KONFIGURASI['PROXY'] if KONFIGURASI['GUNAKAN_PROXY'] else None,
                verify=KEAMANAN_KONFIGURASI['VERIFIKASI_SSL']
            )
            response.raise_for_status()
            
            waktu_muat = response.elapsed.total_seconds()
            ukuran_konten = len(response.content)
            soup = BeautifulSoup(response.text, PARSING_KONFIGURASI['PARSER'])
            sumber_eksternal = len([link for link in soup.find_all('link') if link.get('href', '').startswith('http')])
            
            hasil = (response.text, waktu_muat, ukuran_konten, sumber_eksternal)
            
            if gunakan_cache:
                if KONFIGURASI['GUNAKAN_CACHE_FILE']:
                    try:
                        with open(KONFIGURASI['CACHE_FILE'], 'r') as f:
                            cache_file = json.load(f)
                    except (FileNotFoundError, json.JSONDecodeError):
                        cache_file = {}
                    cache_file[url] = {'data': hasil, 'waktu': time.time()}
                    with open(KONFIGURASI['CACHE_FILE'], 'w') as f:
                        json.dump(cache_file, f)
                else:
                    hasil_cache[url] = {'data': hasil, 'waktu': time.time()}
            
            return hasil
        except requests.RequestException as e:
            if percobaan == KONFIGURASI['MAKS_PERCOBAAN'] - 1:
                if isinstance(e, requests.Timeout):
                    kode_error = KODE_ERROR['BATAS_WAKTU_TERLAMPAUI']
                elif isinstance(e, requests.SSLError):
                    kode_error = KODE_ERROR['KESALAHAN_SSL']
                else:
                    kode_error = KODE_ERROR['KONEKSI_GAGAL']
                pesan_error = dapatkan_pesan_error(kode_error)
                logging.error(f"Gagal mengambil {url}: {pesan_error}")
                raise Exception(pesan_error)
            time.sleep(2 ** percobaan)  # Exponential backoff

def parse_html(konten_html):
    return BeautifulSoup(konten_html, PARSING_KONFIGURASI['PARSER'])

def ekstrak_elemen_spesifik(sup):
    deskripsi_meta = sup.find('meta', attrs={'name': 'description'})
    kata_kunci_meta = sup.find('meta', attrs={'name': 'keywords'})
    tag_h1 = sup.find_all('h1')
    
    hasil = {
        'deskripsi_meta': deskripsi_meta['content'] if deskripsi_meta else None,
        'kata_kunci_meta': kata_kunci_meta['content'] if kata_kunci_meta else None,
        'tag_h1': [h1.text for h1 in tag_h1]
    }
    
    if PARSING_KONFIGURASI['EKSTRAK_JAVASCRIPT']:
        hasil['javascript'] = [script.string for script in sup.find_all('script') if script.string]
    
    if PARSING_KONFIGURASI['EKSTRAK_CSS']:
        hasil['css'] = [style.string for style in sup.find_all('style') if style.string]
    
    if PARSING_KONFIGURASI['EKSTRAK_KOMENTAR']:
        hasil['komentar'] = sup.find_all(text=lambda text: isinstance(text, Comment))
    
    return hasil

def ekspor_ke_format(data, tipe_format, nama_file):
    if tipe_format == 'json':
        with open(nama_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    elif tipe_format == 'xml':
        root = ET.Element("data_website")
        for kunci, nilai in data.items():
            anak = ET.SubElement(root, kunci)
            anak.text = str(nilai)
        tree = ET.ElementTree(root)
        tree.write(nama_file, encoding='utf-8', xml_declaration=True)
    elif tipe_format == 'csv':
        with open(nama_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(data.keys())
            writer.writerow(data.values())
    
    if OUTPUT_KONFIGURASI['KOMPRESI_OUTPUT']:
        with zipfile.ZipFile(f"{nama_file}.zip", 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(nama_file, os.path.basename(nama_file))
        os.remove(nama_file)
        console.print(f"[bold green]File telah dikompres dan disimpan sebagai {nama_file}.zip[/bold green]")
    else:
        console.print(f"[bold green]File telah disimpan sebagai {nama_file}[/bold green]")

def jelajahi_tautan_internal(url_dasar, maks_halaman=CRAWLING_KONFIGURASI['MAKS_HALAMAN_PER_DOMAIN']):
    dikunjungi = set()
    akan_dikunjungi = [url_dasar]
    hasil = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
    ) as progress:
        task = progress.add_task("[cyan]Menjelajahi tautan internal...", total=maks_halaman)

        with concurrent.futures.ThreadPoolExecutor(max_workers=KINERJA_KONFIGURASI['MAKS_KONKURENSI']) as executor:
            while akan_dikunjungi and len(dikunjungi) < maks_halaman:
                url = akan_dikunjungi.pop(0)
                if url not in dikunjungi:
                    dikunjungi.add(url)
                    future = executor.submit(ambil_kode_sumber, url)
                    try:
                        konten_html, _, _, _ = future.result()
                        if konten_html:
                            sup = parse_html(konten_html)
                            hasil.append({
                                'url': url,
                                'judul': sup.title.string if sup.title else None,
                                'elemen': ekstrak_elemen_spesifik(sup)
                            })
                            for tautan in sup.find_all('a', href=True):
                                url_lengkap = urljoin(url_dasar, tautan['href'])
                                if (url_lengkap.startswith(url_dasar) and
                                    url_lengkap not in dikunjungi and
                                    len(urlparse(url_lengkap).path.split('/')) <= CRAWLING_KONFIGURASI['MAKS_KEDALAMAN']):
                                    akan_dikunjungi.append(url_lengkap)
                    except Exception as e:
                        console.print(f"[bold red]Kesalahan menjelajahi {url}: {str(e)}[/bold red]")
                    
                    progress.update(task, advance=1)
                    time.sleep(CRAWLING_KONFIGURASI['JEDA_ANTAR_PERMINTAAN'])
    
    return hasil

def deteksi_bahasa_dan_teknologi(url, konten_html):
    try:
        bahasa = detect(konten_html)
    except:
        bahasa = "Tidak diketahui"
    
    wappalyzer = Wappalyzer.latest()
    halaman_web = WebPage.new_from_url(url)
    teknologi = wappalyzer.analyze_with_versions_and_categories(halaman_web)
    
    return bahasa, teknologi

def analisis_sentimen(teks):
    if ANALISIS_KONFIGURASI['ANALISIS_SENTIMEN']:
        analisis = TextBlob(teks)
        return analisis.sentiment.polarity
    return None

def ekstraksi_kata_kunci(teks):
    if ANALISIS_KONFIGURASI['EKSTRAKSI_KATA_KUNCI']:
        kata_kunci = TextBlob(teks).noun_phrases
        return kata_kunci[:ANALISIS_KONFIGURASI['MAKS_KATA_KUNCI']]
    return []

def ringkas_teks(teks):
    if ANALISIS_KONFIGURASI['RINGKASAN_OTOMATIS']:
        kalimat = TextBlob(teks).sentences
        return " ".join(str(kalimat[i]) for i in range(min(ANALISIS_KONFIGURASI['PANJANG_RINGKASAN'], len(kalimat))))
    return None

def simpan_ke_database(data):
    if DATABASE_KONFIGURASI['GUNAKAN_DATABASE']:
        # Implementasi penyimpanan ke database sesuai dengan jenis database yang dipilih
        pass

def kirim_notifikasi(pesan):
    if NOTIFIKASI_KONFIGURASI['KIRIM_EMAIL']:
        try:
            msg = MIMEText(pesan)
            msg['Subject'] = "Notifikasi Phantom Web"
            msg['From'] = NOTIFIKASI_KONFIGURASI['EMAIL_PENGIRIM']
            msg['To'] = NOTIFIKASI_KONFIGURASI['EMAIL_PENERIMA']

            with smtplib.SMTP(NOTIFIKASI_KONFIGURASI['SMTP_SERVER'], NOTIFIKASI_KONFIGURASI['SMTP_PORT']) as server:
                server.starttls()
                server.login(NOTIFIKASI_KONFIGURASI['EMAIL_PENGIRIM'], NOTIFIKASI_KONFIGURASI['EMAIL_PASSWORD'])
                server.send_message(msg)
            console.print("[bold green]Notifikasi email berhasil dikirim.[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Gagal mengirim notifikasi email: {str(e)}[/bold red]")

    if NOTIFIKASI_KONFIGURASI['KIRIM_TELEGRAM']:
        try:
            bot = telegram.Bot(token=NOTIFIKASI_KONFIGURASI['TELEGRAM_BOT_TOKEN'])
            asyncio.run(bot.send_message(chat_id=NOTIFIKASI_KONFIGURASI['TELEGRAM_CHAT_ID'], text=pesan))
            console.print("[bold green]Notifikasi Telegram berhasil dikirim.[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Gagal mengirim notifikasi Telegram: {str(e)}[/bold red]")

def simpan_hasil(data, nama_file):
    if PENYIMPANAN_KONFIGURASI['JENIS_PENYIMPANAN'] == 'lokal':
        with open(nama_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    elif PENYIMPANAN_KONFIGURASI['JENIS_PENYIMPANAN'] == 's3':
        s3 = boto3.client('s3',
                          aws_access_key_id=PENYIMPANAN_KONFIGURASI['AWS_ACCESS_KEY'],
                          aws_secret_access_key=PENYIMPANAN_KONFIGURASI['AWS_SECRET_KEY'])
        s3.put_object(Bucket=PENYIMPANAN_KONFIGURASI['BUCKET_NAMA'],
                      Key=nama_file,
                      Body=json.dumps(data, ensure_ascii=False, indent=4))
    elif PENYIMPANAN_KONFIGURASI['JENIS_PENYIMPANAN'] == 'gcs':
        client = storage.Client.from_service_account_json(PENYIMPANAN_KONFIGURASI['GCS_PRIVATE_KEY'])
        bucket = client.get_bucket(PENYIMPANAN_KONFIGURASI['BUCKET_NAMA'])
        blob = bucket.blob(nama_file)
        blob.upload_from_string(json.dumps(data, ensure_ascii=False, indent=4))
    elif PENYIMPANAN_KONFIGURASI['JENIS_PENYIMPANAN'] == 'azure':
        blob_service_client = BlobServiceClient.from_connection_string(PENYIMPANAN_KONFIGURASI['AZURE_CONNECTION_STRING'])
        container_client = blob_service_client.get_container_client(PENYIMPANAN_KONFIGURASI['BUCKET_NAMA'])
        blob_client = container_client.get_blob_client(nama_file)
        blob_client.upload_blob(json.dumps(data, ensure_ascii=False, indent=4))

def buat_visualisasi(data):
    if VISUALISASI_KONFIGURASI['BUAT_GRAFIK']:
        plt.figure(figsize=(10, 6))
        plt.style.use(VISUALISASI_KONFIGURASI['WARNA_TEMA'])
        
        if 'pie' in VISUALISASI_KONFIGURASI['JENIS_GRAFIK']:
            plt.pie(data.values(), labels=data.keys(), autopct='%1.1f%%')
            plt.title('Distribusi Data')
        
        if 'bar' in VISUALISASI_KONFIGURASI['JENIS_GRAFIK']:
            plt.bar(data.keys(), data.values())
            plt.title('Grafik Batang Data')
        
        if 'line' in VISUALISASI_KONFIGURASI['JENIS_GRAFIK']:
            plt.plot(data.keys(), data.values())
            plt.title('Grafik Garis Data')
        
        if VISUALISASI_KONFIGURASI['TAMPILKAN_LEGENDA']:
            plt.legend()
        
        plt.tight_layout()
        
        if VISUALISASI_KONFIGURASI['SIMPAN_GRAFIK']:
            plt.savefig(f"grafik.{VISUALISASI_KONFIGURASI['FORMAT_GRAFIK']}", dpi=VISUALISASI_KONFIGURASI['DPI_GRAFIK'])
            console.print(f"[bold green]Grafik telah disimpan sebagai grafik.{VISUALISASI_KONFIGURASI['FORMAT_GRAFIK']}[/bold green]")
        
        plt.show()

def periksa_pembaruan():
    versi_saat_ini = "9.9.9"  
    url_pembaruan = "https://api.github.com/repos/syaaikoo/phantom-web/releases/latest"
    try:
        response = requests.get(url_pembaruan)
        data = response.json()
        versi_terbaru = data['tag_name']
        if versi_terbaru > versi_saat_ini:
            console.print(f"[bold yellow]Pembaruan tersedia! Versi terbaru: {versi_terbaru}[/bold yellow]")
            console.print("[bold yellow]Kunjungi https://github.com/syaaikoo/phantom-web untuk mengunduh.[/bold yellow]")
        else:
            console.print("[bold green]Anda menggunakan versi terbaru.[/bold green]")
    except:
        console.print("[bold red]Gagal memeriksa pembaruan.[/bold red]")

def tampilkan_banner():
    banner = """
██████╗ ██╗  ██╗ █████╗ ███╗   ██╗████████╗ ██████╗ ███╗   ███╗    ██╗    ██╗███████╗██████╗ 
██╔══██╗██║  ██║██╔══██╗████╗  ██║╚══██╔══╝██╔═══██╗████╗ ████║    ██║    ██║██╔════╝██╔══██╗
██████╔╝███████║███████║██╔██╗ ██║   ██║   ██║   ██║██╔████╔██║    ██║ █╗ ██║█████╗  ██████╔╝
██╔═══╝ ██╔══██║██╔══██║██║╚██╗██║   ██║   ██║   ██║██║╚██╔╝██║    ██║███╗██║██╔══╝  ██╔══██╗
██║     ██║  ██║██║  ██║██║ ╚████║   ██║   ╚██████╔╝██║ ╚═╝ ██║    ╚███╔███╔╝███████╗██████╔╝
╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝     ╚══╝╚══╝ ╚══════╝╚═════╝ 
"""
    console.print(Panel(banner, title="[bold cyan]PHANTOM WEB[/bold cyan]", subtitle="[bold green]oleh @syaaikoo[/bold green]"))

def tampilkan_menu():
    table = Table(title="Menu Utama")
    table.add_column("Pilihan", style="cyan", no_wrap=True)
    table.add_column("Deskripsi", style="magenta")
    table.add_row("1", "Ambil kode sumber")
    table.add_row("2", "Jelajahi tautan internal")
    table.add_row("3", "Analisis performa website")
    table.add_row("4", "Deteksi bahasa dan teknologi")
    table.add_row("5", "Analisis sentimen dan ekstraksi kata kunci")
    table.add_row("6", "Buat visualisasi data")
    table.add_row("7", "Periksa pembaruan")
    table.add_row("8", "Keluar")
    console.print(table)

def main():
    tampilkan_banner()
    periksa_pembaruan()
    
    while True:
        tampilkan_menu()
        pilihan = console.input("[bold yellow]Pilih opsi (1-8): [/bold yellow]")
        
        if pilihan == "1":
            url = console.input("[bold green]Masukkin URL nya disini, pasti in bener yahh: [/bold green]")
            if not url_valid(url):
                console.print("[bold red]URL nya gak valid kocak. Coba cek lagi dah.[/bold red]")
                continue
            
            with console.status("[bold green]Mengambil kode sumber...[/bold green]") as status:
                try:
                    konten_html, waktu_muat, ukuran_konten, sumber_eksternal = ambil_kode_sumber(url)
                    console.print(f"[bold green]Berhasil mengambil kode sumber dari {url}[/bold green]")
                    console.print(f"Waktu muat: {waktu_muat:.2f} detik")
                    console.print(f"Ukuran konten: {ukuran_konten} byte")
                    console.print(f"Jumlah sumber eksternal: {sumber_eksternal}")
                    
                    simpan = console.input("[bold yellow]Simpan kode sumber? (y/n): [/bold yellow]").lower()
                    if simpan == 'y':
                        nama_file = console.input("[bold green]Masuk in nama file: [/bold green]")
                        with open(nama_file, 'w', encoding='utf-8') as file:
                            file.write(konten_html)
                        console.print(f"[bold green]Kode sumber disimpan ke {nama_file}[/bold green]")
                except Exception as e:
                    console.print(f"[bold red]Terjadi kesalahan: {str(e)}[/bold red]")
        
        elif pilihan == "2":
            url = console.input("[bold green]Masukkin URL dasar nya disini, pasti in bener yahh: [/bold green]")
            if not url_valid(url):
                console.print("[bold red]URL nya gak valid kocak. Coba cek lagi dah.[/bold red]")
                continue
            
            maks_halaman = console.input("[bold green]Masuk in jumlah maksimum halaman untuk dijelajahi: [/bold green]")
            try:
                maks_halaman = int(maks_halaman)
            except ValueError:
                console.print("[bold red]Jumlah halaman harus berupa angka. Silakan coba lagi.[/bold red]")
                continue
            
            hasil = jelajahi_tautan_internal(url, maks_halaman)
            console.print(f"[bold green]Berhasil menjelajahi {len(hasil)} halaman[/bold green]")
            
            simpan = console.input("[bold yellow]Simpan hasil penjelajahan? (y/n): [/bold yellow]").lower()
            if simpan == 'y':
                nama_file = console.input("[bold green]Masuk in nama file: [/bold green]")
                format_ekspor = console.input("[bold green]Pilih format ekspor (json/xml/csv): [/bold green]").lower()
                if format_ekspor in ['json', 'xml', 'csv']:
                    ekspor_ke_format(hasil, format_ekspor, nama_file)
                else:
                    console.print("[bold red]Format gak valid njirr Menyimpan sebagai JSON.[/bold red]")
                    ekspor_ke_format(hasil, 'json', nama_file)
        
        elif pilihan == "3":
            url = console.input("[bold green]Masukkin URL nya disini, pasti in bener yahh: [/bold green]")
            if not url_valid(url):
                console.print("[bold red]URL nya gak valid kocak. Coba cek lagi dah.[/bold red]")
                continue
            
            with console.status("[bold green]Menganalisis performa website...[/bold green]") as status:
                try:
                    _, waktu_muat, ukuran_konten, sumber_eksternal = ambil_kode_sumber(url)
                    console.print(f"[bold green]Analisis performa untuk {url}:[/bold green]")
                    console.print(f"Waktu muat: {waktu_muat:.2f} detik")
                    console.print(f"Ukuran konten: {ukuran_konten} byte")
                    console.print(f"Jumlah sumber eksternal: {sumber_eksternal}")
                except Exception as e:
                    console.print(f"[bold red]Terjadi kesalahan: {str(e)}[/bold red]")
        
        elif pilihan == "4":
            url = console.input("[bold green]Masukkin URL nya disini, pasti in bener yahh: [/bold green]")
            if not url_valid(url):
                console.print("[bold red]URL gak valid kocak. Cek lagi dah.[/bold red]")
                continue
            
            with console.status("[bold green]Mendeteksi bahasa dan teknologi...[/bold green]") as status:
                try:
                    konten_html, _, _, _ = ambil_kode_sumber(url)
                    bahasa, teknologi = deteksi_bahasa_dan_teknologi(url, konten_html)
                    console.print(f"[bold green]Hasil deteksi untuk {url}:[/bold green]")
                    console.print(f"Bahasa: {bahasa}")
                    console.print("[bold cyan]Teknologi yang digunakan:[/bold cyan]")
                    for tech, details in teknologi.items():
                        console.print(f"- {tech}: {', '.join(details.get('versions', ['Tidak diketahui']))}")
                except Exception as e:
                    console.print(f"[bold red]Terjadi kesalahan: {str(e)}[/bold red]")
        
        elif pilihan == "5":
            url = console.input("[bold green]Masukkin URL nya disini, pasti in bener yahh: [/bold green]")
            if not url_valid(url):
                console.print("[bold red]URL nya gak valid kocak. Coba cek lagi dah.[/bold red]")
                continue
            
            with console.status("[bold green]Menganalisis sentimen dan mengekstrak kata kunci...[/bold green]") as status:
                try:
                    konten_html, _, _, _ = ambil_kode_sumber(url)
                    soup = parse_html(konten_html)
                    teks = soup.get_text()
                    
                    sentimen = analisis_sentimen(teks)
                    kata_kunci = ekstraksi_kata_kunci(teks)
                    ringkasan = ringkas_teks(teks)
                    
                    console.print(f"[bold green]Hasil analisis untuk {url}:[/bold green]")
                    if sentimen is not None:
                        console.print(f"Sentimen: {sentimen:.2f} (-1 negatif, 1 positif)")
                    console.print(f"Kata kunci: {', '.join(kata_kunci)}")
                    if ringkasan:
                        console.print(f"Ringkasan: {ringkasan}")
                except Exception as e:
                    console.print(f"[bold red]Terjadi kesalahan: {str(e)}[/bold red]")
        
        elif pilihan == "6":
            url = console.input("[bold green]Masukin URL nya: [/bold green]")
            if not url_valid(url):
                console.print("[bold red]URL nya gak valid kocak. Coba cek lagi dah.[/bold red]")
                continue
            
            with console.status("[bold green]Mengambil data dan membuat visualisasi...[/bold green]") as status:
                try:
                    konten_html, waktu_muat, ukuran_konten, sumber_eksternal = ambil_kode_sumber(url)
                    soup = parse_html(konten_html)
                    
                    data = {
                        'Waktu Muat (s)': waktu_muat,
                        'Ukuran Konten (KB)': ukuran_konten / 1024,
                        'Sumber Eksternal': sumber_eksternal,
                        'Jumlah Tag': len(soup.find_all()),
                        'Jumlah Tautan': len(soup.find_all('a')),
                        'Jumlah Gambar': len(soup.find_all('img'))
                    }
                    
                    buat_visualisasi(data)
                except Exception as e:
                    console.print(f"[bold red]Terjadi kesalahan: {str(e)}[/bold red]")
        
        elif pilihan == "7":
            periksa_pembaruan()
        
        elif pilihan == "8":
            console.print("[bold green]Terima kasih telah menggunakan Phantom Web. Sampai jumpa![/bold green]")
            break
        
        else:
            console.print("[bold red]Pilihan gak valid njirr Silakan coba lagi.[/bold red]")

if __name__ == "__main__":
    main()

