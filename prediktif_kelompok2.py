
import time
import board
import busio
import adafruit_adxl34x
import math
import numpy as np
import glob
import paho.mqtt.client as mqtt
import json
import RPi.GPIO as GPIO
import os


# =====================================
# KONFIGURASI BUZZER GPIO 17
# =====================================

BUZZER_PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(BUZZER_PIN, GPIO.OUT)
GPIO.output(BUZZER_PIN, GPIO.LOW)


# =====================================
# THRESHOLD PREDICTIVE MAINTENANCE
# =====================================

RMS_THRESHOLD = 5.0
PEAK_THRESHOLD = 10.0
TEMP_THRESHOLD = 30.0


# =====================================
# KONFIGURASI THINGSBOARD MQTT
# =====================================

MQTT_BROKER = "eu.thingsboard.cloud"
MQTT_PORT = 1883

# Simpan token sebagai environment variable TB_ACCESS_TOKEN
ACCESS_TOKEN = "gjo4EaecLjR4ZwdHW4HZ"

if not ACCESS_TOKEN:
    raise SystemExit("ACCESS_TOKEN belum dikonfigurasi!")

MQTT_TOPIC_TELEMETRY = "v1/devices/me/telemetry"
MQTT_TOPIC_ATTRIBUTES = "v1/devices/me/attributes"

INTERVAL_KIRIM = 1.0


# =====================================
# INISIALISASI MQTT
# =====================================

client = mqtt.Client(
    client_id="RaspberryPi4_Monitoring"
)

client.username_pw_set(ACCESS_TOKEN)

client.reconnect_delay_set(
    min_delay=1,
    max_delay=30
)

print("Menghubungkan ke ThingsBoard...")

try:

    client.connect(
        MQTT_BROKER,
        MQTT_PORT,
        keepalive=60
    )

    client.loop_start()

    print("Permintaan koneksi MQTT berhasil!")

except Exception as e:

    print("Koneksi MQTT gagal:", e)

    GPIO.output(BUZZER_PIN, GPIO.LOW)
    GPIO.cleanup()

    raise SystemExit


# =====================================
# FUNGSI PENGIRIMAN MQTT
# =====================================

def kirim_mqtt(topic, data):

    try:

        if not client.is_connected():
            print("MQTT terputus. Menunggu koneksi kembali...")
            return False

        payload = json.dumps(data)

        hasil = client.publish(
            topic,
            payload,
            qos=1
        )

        if hasil.rc != mqtt.MQTT_ERR_SUCCESS:

            print("Gagal memasukkan pesan ke antrean MQTT!")
            return False

        hasil.wait_for_publish(timeout=3)

        if hasil.is_published():

            print("Berhasil mengirim:", topic)
            print("Payload:", payload)

            return True

        else:

            print("Pengiriman MQTT belum terkonfirmasi:", topic)

            return False

    except Exception as e:

        print("Kesalahan pengiriman MQTT:", e)

        return False


# =====================================
# INISIALISASI KOMUNIKASI I2C
# =====================================

try:

    i2c = busio.I2C(
        board.SCL,
        board.SDA
    )

    # =====================================
    # INISIALISASI SENSOR ADXL345
    # =====================================

    accelerometer = adafruit_adxl34x.ADXL345(i2c)

    print("Sensor ADXL345 berhasil diinisialisasi")

    # =====================================
    # INISIALISASI SENSOR DS18B20
    # =====================================

    base_dir = "/sys/bus/w1/devices/"

    device_folder = glob.glob(base_dir + "28*")

    if not device_folder:

        raise RuntimeError(
            "Sensor DS18B20 tidak ditemukan!"
        )

    device_file = device_folder[0] + "/w1_slave"

    print("Sensor DS18B20 berhasil ditemukan")
    print("GPIO 4 - Komunikasi 1-Wire")

except Exception as e:

    print("Kesalahan inisialisasi sensor:", e)

    GPIO.output(BUZZER_PIN, GPIO.LOW)
    GPIO.cleanup()

    client.loop_stop()
    client.disconnect()

    raise SystemExit


# =====================================
# FUNGSI MEMBACA SUHU DS18B20
# =====================================

def baca_suhu():

    try:

        with open(device_file, "r") as file:
            lines = file.readlines()

        if len(lines) < 2:
            return None

        if "YES" not in lines[0]:
            return None

        posisi = lines[1].find("t=")

        if posisi == -1:
            return None

        suhu = float(
            lines[1][posisi + 2:]
        ) / 1000.0

        return suhu

    except (OSError, ValueError):

        return None


# =====================================
# KALIBRASI OTOMATIS ADXL345
# =====================================

JUMLAH_SAMPEL = 100
INTERVAL = 0.01

print("--------------------------------------")
print("Memulai kalibrasi otomatis...")
print("Pastikan sensor dalam keadaan diam!")

total_x = 0.0
total_y = 0.0
total_z = 0.0

for i in range(JUMLAH_SAMPEL):

    x, y, z = accelerometer.acceleration

    total_x += x
    total_y += y
    total_z += z

    time.sleep(INTERVAL)


offset_x = total_x / JUMLAH_SAMPEL
offset_y = total_y / JUMLAH_SAMPEL
offset_z = total_z / JUMLAH_SAMPEL


print("\nKalibrasi selesai!")

print("Offset X : {:.3f} m/s^2".format(offset_x))
print("Offset Y : {:.3f} m/s^2".format(offset_y))
print("Offset Z : {:.3f} m/s^2".format(offset_z))


# =====================================
# PENGATURAN PENGUKURAN GETARAN
# =====================================

JUMLAH_DATA = 100
INTERVAL_BACA = 0.01

FREKUENSI_SAMPLING = 1 / INTERVAL_BACA

print("--------------------------------------")

print("Frekuensi Sampling : {:.1f} Hz".format(
    FREKUENSI_SAMPLING
))

print("Pengiriman data setiap 1 detik")
print("Tekan CTRL+C untuk berhenti")


# =====================================
# PROGRAM UTAMA
# =====================================

try:

    while True:

        waktu_mulai = time.monotonic()

        # =====================================
        # PENAMPUNG DATA GETARAN
        # =====================================

        data_x = []
        data_y = []
        data_z = []

        # =====================================
        # PENGAMBILAN DATA ADXL345
        # =====================================

        for i in range(JUMLAH_DATA):

            x, y, z = accelerometer.acceleration

            # Menghilangkan offset dan gravitasi
            getaran_x = x - offset_x
            getaran_y = y - offset_y
            getaran_z = z - offset_z

            data_x.append(getaran_x)
            data_y.append(getaran_y)
            data_z.append(getaran_z)

            time.sleep(INTERVAL_BACA)

        # =====================================
        # MEMBACA SUHU DS18B20
        # =====================================

        suhu = baca_suhu()

        # =====================================
        # KONVERSI ARRAY NUMPY
        # =====================================

        data_x = np.array(data_x)
        data_y = np.array(data_y)
        data_z = np.array(data_z)

        # =====================================
        # PERHITUNGAN RMS XYZ
        # =====================================

        rms_x = math.sqrt(np.mean(data_x**2))
        rms_y = math.sqrt(np.mean(data_y**2))
        rms_z = math.sqrt(np.mean(data_z**2))

        # =====================================
        # PERHITUNGAN RMS TOTAL
        # =====================================

        rms_total = math.sqrt(
            rms_x**2 +
            rms_y**2 +
            rms_z**2
        )

        # =====================================
        # PERHITUNGAN PEAK XYZ
        # =====================================

        peak_x = np.max(np.abs(data_x))
        peak_y = np.max(np.abs(data_y))
        peak_z = np.max(np.abs(data_z))

        # =====================================
        # PERHITUNGAN PEAK TOTAL
        # =====================================

        data_total = np.sqrt(
            data_x**2 +
            data_y**2 +
            data_z**2
        )

        peak_total = np.max(data_total)

        # =====================================
        # PERHITUNGAN FFT TOTAL
        # =====================================

        data_total_fft = (
            data_total - np.mean(data_total)
        )

        window = np.hanning(JUMLAH_DATA)

        data_window = data_total_fft * window

        fft_result = np.fft.rfft(data_window)

        amplitudo = (
            2.0 * np.abs(fft_result) / np.sum(window)
        )

        frekuensi = np.fft.rfftfreq(
            JUMLAH_DATA,
            d=INTERVAL_BACA
        )

        amplitudo[0] = 0

        indeks_dominan = np.argmax(amplitudo)

        frekuensi_dominan_total = frekuensi[
            indeks_dominan
        ]

        amplitudo_dominan_total = amplitudo[
            indeks_dominan
        ]

        # =====================================
        # PREDICTIVE MAINTENANCE ALERT
        # =====================================

        alerts = []

        # Pengecekan getaran
        vib_alert = (
            rms_total > RMS_THRESHOLD or
            peak_total > PEAK_THRESHOLD
        )

        # Pengecekan suhu
        temp_alert = (
            suhu is not None and
            suhu > TEMP_THRESHOLD
        )

        if vib_alert:

            alerts.append("GETARAN TIDAK NORMAL!")

        if temp_alert:

            alerts.append("SUHU TINGGI!")

        # =====================================
        # STATUS ALERT DAN BUZZER
        # =====================================

        if alerts:

            alert_status = True

            alert_message = ", ".join(alerts)

            GPIO.output(
                BUZZER_PIN,
                GPIO.HIGH
            )

        else:

            alert_status = False

            alert_message = "NORMAL"

            GPIO.output(
                BUZZER_PIN,
                GPIO.LOW
            )

        # =====================================
        # MENAMPILKAN HASIL PENGUKURAN
        # =====================================

        print("\n========== HASIL PENGUKURAN ==========")

        print("\n--- SUHU ---")

        if suhu is not None:

            print("Suhu DS18B20 : {:.2f} Â°C".format(suhu))

        else:

            print("Suhu DS18B20 : Gagal membaca sensor")

        print("\n--- GETARAN RMS ---")

        print("RMS X     : {:.3f} m/s^2".format(rms_x))
        print("RMS Y     : {:.3f} m/s^2".format(rms_y))
        print("RMS Z     : {:.3f} m/s^2".format(rms_z))
        print("RMS Total : {:.3f} m/s^2".format(rms_total))

        print("\n--- GETARAN PEAK ---")

        print("Peak X     : {:.3f} m/s^2".format(peak_x))
        print("Peak Y     : {:.3f} m/s^2".format(peak_y))
        print("Peak Z     : {:.3f} m/s^2".format(peak_z))
        print("Peak Total : {:.3f} m/s^2".format(peak_total))

        print("\n--- FREKUENSI DAN AMPLITUDO DOMINAN TOTAL ---")

        print(
            "Frekuensi Dominan Total : {:.2f} Hz".format(
                frekuensi_dominan_total
            )
        )

        print(
            "Amplitudo Dominan Total : {:.3f} m/s^2".format(
                amplitudo_dominan_total
            )
        )

        print("\n--- PREDICTIVE MAINTENANCE ALERT ---")

        print("Alert Status  :", alert_status)
        print("Alert Message :", alert_message)

        # =====================================
        # PENGIRIMAN ATTRIBUTES THINGSBOARD
        # =====================================

        attr_payload = {

            "alert_status": alert_status,

            "alert_message": alert_message

        }

        print("\n--- MQTT ATTRIBUTES ---")

        kirim_mqtt(
            MQTT_TOPIC_ATTRIBUTES,
            attr_payload
        )

        # =====================================
        # DATA TELEMETRY THINGSBOARD
        # =====================================

        telemetry = {

            "rms_x": float(rms_x),
            "rms_y": float(rms_y),
            "rms_z": float(rms_z),
            "rms_total": float(rms_total),

            "peak_x": float(peak_x),
            "peak_y": float(peak_y),
            "peak_z": float(peak_z),
            "peak_total": float(peak_total),

            "frekuensi_dominan_total": float(
                frekuensi_dominan_total
            ),

            "amplitudo_dominan_total": float(
                amplitudo_dominan_total
            )

        }

        # Suhu hanya dikirim jika pembacaan berhasil
        if suhu is not None:

            telemetry["suhu"] = float(suhu)

        # =====================================
        # PENGIRIMAN TELEMETRY THINGSBOARD
        # =====================================

        print("\n--- MQTT TELEMETRY ---")

        kirim_mqtt(
            MQTT_TOPIC_TELEMETRY,
            telemetry
        )

        print("--------------------------------------")

        # =====================================
        # PENGATURAN INTERVAL PENGIRIMAN
        # =====================================

        waktu_proses = (
            time.monotonic() - waktu_mulai
        )

        waktu_tunggu = (
            INTERVAL_KIRIM - waktu_proses
        )

        if waktu_tunggu > 0:

            time.sleep(waktu_tunggu)


except KeyboardInterrupt:

    print("\nProgram dihentikan oleh pengguna.")

except Exception as e:

    print("\nTerjadi kesalahan pada program:", e)

finally:

    # =====================================
    # PEMBERSIHAN GPIO
    # =====================================

    GPIO.output(
        BUZZER_PIN,
        GPIO.LOW
    )

    GPIO.cleanup()

    # =====================================
    # MEMUTUSKAN KONEKSI MQTT
    # =====================================

    print("\nMemutuskan koneksi MQTT...")

    client.loop_stop()

    client.disconnect()

    print("Koneksi ThingsBoard ditutup.")
    print("Pembacaan sensor selesai.")

