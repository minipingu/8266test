# ESP8266 3-LED Controller via ThingsBoard MQTT (MicroPython)

Program MicroPython (`main.py`) untuk mengontrol 3 LED (**Red**, **Yellow**, **Green**) secara bersamaan lewat **1 Switch** di **ThingsBoard** (protokol MQTT) sekaligus menyinkronkan status indikator LED di dashboard ThingsBoard.

## 1. Pemetaan Pin Hardware

| Warna LED | Pin NodeMCU | GPIO ESP8266 | Keterangan |
| :--- | :--- | :--- | :--- |
| **Red** | `D0` | `GPIO16` | Output digital aktif-HIGH |
| **Yellow** | `D1` | `GPIO5` | Output digital aktif-HIGH |
| **Green** | `D2` | `GPIO4` | Output digital aktif-HIGH |

**Rangkaian standar (aktif-HIGH):**
`Pin (D0 / D1 / D2)` → `Resistor (220Ω–330Ω)` → `Anoda LED (+)` → `Katoda LED (-)` → `G (GND)`

> **Catatan:** Jangan gunakan pin berlabel `S3, S2, S1, SC, S0, SK` untuk LED/sensor karena pin tersebut terhubung ke memori SPI Flash internal (GPIO6–GPIO11) dan dapat membuat ESP8266 *crash* atau gagal boot.

## 2. Prasyarat

- **Git Bash** (atau MSYS2 `UCRT64`).
- **Python 3** dengan `mpremote` terpasang (cek dengan `mpremote --version` di Git Bash).
- **Driver USB-Serial CH340** terdeteksi (misal `COM6`; sesuaikan jika port COM di Device Manager berbeda).
- **Firmware MicroPython** sudah terpasang di ESP8266.

## 3. Flash Firmware MicroPython (Sekali saja)

Lewati langkah ini jika ESP8266 sudah terpasang MicroPython.  
*(Perhatian: proses flash akan menghapus program/sketch lama yang ada di ESP8266.)*

1. Pastikan file firmware **ESP8266_GENERIC** (misal `ESP8266_GENERIC-20260824-v1.29.0.bin`, atau versi terbaru dari https://micropython.org/download/ESP8266_GENERIC/) ada di folder proyek (`~/Desktop/8266test`).
2. Pastikan tidak ada aplikasi lain yang membuka `COM6` (tutup Arduino Serial Monitor, PuTTY, dll.), lalu jalankan di **Git Bash**:

```bash
cd ~/Desktop/8266test

python "C:/Users/Administrator/AppData/Local/Arduino15/packages/esp8266/hardware/esp8266/3.1.2/tools/esptool/esptool.py" --port COM6 erase_flash

python "C:/Users/Administrator/AppData/Local/Arduino15/packages/esp8266/hardware/esp8266/3.1.2/tools/esptool/esptool.py" --port COM6 --baud 460800 write_flash --flash_size=detect 0 ESP8266_GENERIC-20260824-v1.29.0.bin
```

*(Sesuaikan nama file `.bin` jika memakai versi lain. Jika memakai `esptool` via pip, jalankan `pip install esptool` lalu ganti path skrip dengan `esptool`. Jika upload gagal di baud `460800`, ubah menjadi `--baud 115200`.)*

## 4. Menjalankan `main.py` via Git Bash

Sebelum menjalankan, pastikan konfigurasi di file `.env` sudah diisi (`WIFI_SSID`, `WIFI_PASSWORD`, `THINGSBOARD_HOST`, dan `ACCESS_TOKEN` — lihat template pada `.env.example`).

Gunakan `deploy.py` untuk meng-upload atau menjalankan `main.py` ke ESP8266 (`deploy.py` otomatis ikut meng-upload `.env` ke `:.env` di flash ESP8266 dan mengatur `DTR=False, RTS=False` sebelum membuka port serial agar chip **CH340** tidak tertahan di mode reset).

### Opsi A — Upload Permanen & Pantau Koneksi (Disarankan)
Menyimpan `main.py` ke flash ESP8266 (`:main.py`) agar otomatis berjalan setiap board mendapat daya/reset, lalu memantau log koneksi selama 12 detik:

```bash
cd ~/Desktop/8266test
python deploy.py --port COM6 --file main.py --target main.py --monitor-seconds 12
```

### Opsi B — Tes Sementara di RAM (Tanpa Mengubah Flash)
```bash
cd ~/Desktop/8266test
python deploy.py --port COM6 --file main.py --run-only --monitor-seconds 12
```

### Output Berhasil Terhubung
```text
WiFi terhubung, IP: ...
Terhubung ke ThingsBoard: eu.thingsboard.cloud
Status terkirim ke ThingsBoard: {"led": false, ...}
```

### Upload Tanpa Memantau Output
```bash
python deploy.py --port COM6 --file main.py --target main.py --monitor-seconds 0
```

### File Pendukung Lainnya
- `test_relay.py`: tes switching relay HL-52S V1.0 satu per satu tiap 1 detik (`python deploy.py --port COM6 --file test_relay.py --run-only --monitor-seconds 5.0`).
- `thingsboard_relay.py`: kontrol 2 channel relay HL-52S V1.0 via 2 switch ThingsBoard.

## 5. Penyesuaian & Troubleshooting

- **Konfigurasi ThingsBoard & Wi-Fi:** Edit `WIFI_SSID`, `WIFI_PASSWORD`, `THINGSBOARD_HOST` (misal `eu.thingsboard.cloud` atau `thingsboard.cloud`), dan `ACCESS_TOKEN` di `.env`, lalu upload ulang dengan `python deploy.py`.
- **Lewati upload `.env`:** Tambahkan flag `--skip-env` pada `deploy.py` jika hanya ingin memperbarui `main.py` tanpa mengunggah ulang `.env`.
- **Sinkronisasi Switch & Indikator LED ThingsBoard:** `main.py` menangani RPC `setValue`/`getValue` (serta alias `setState`/`setStatus`/`setLed`/`setSwitch`/`setAll`) dan mengirim status `led`, `status`, `state`, `value`, `red`, `yellow`, `green` ke telemetry & attributes.
- **LED menyala terbalik (aktif-LOW / modul common-anode):** Tukar nilai `LED_ON = 0` dan `LED_OFF = 1` di `main.py`.
- **`PermissionError(13, 'A device attached to the system is not functioning.', None, 31)` pada `COM6`:** Driver USB-Serial CH340 sedang macet. Cabut-pasang kabel USB atau restart device di **Git Bash (Administrator)**:
  ```bash
  pnputil /restart-device "USB\VID_1A86&PID_7523\6&BE2F9E&0&3"
  ```
- **Mengapa tidak memakai `mpremote` langsung?** Pada `mpremote 1.29.0` di Windows, port CH340 (`VID 0x1A86`) dibuka dengan `DTR=True, RTS=True`, yang dapat menahan rangkaian auto-reset NodeMCU sehingga muncul error `could not enter raw repl`. Gunakan `python deploy.py` sebagai gantinya.
- **Port COM berbeda:** Cek port yang terdeteksi dengan `mpremote devs`, lalu ganti `COM6` pada perintah di atas.
