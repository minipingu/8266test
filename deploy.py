"""Upload and run a MicroPython script on ESP8266 via CH340 serial on Windows."""

from __future__ import annotations

import argparse
from pathlib import Path
import time

import serial


RAW_REPL_BANNER = b"raw REPL; CTRL-B to exit\r\n>"
CHUNK_SIZE = 256


def open_serial_ch340(port: str, baud: int, timeout: float = 1.0) -> serial.Serial:
    """Open serial port with DTR/RTS cleared so CH340 does not trap ESP8266 in reset."""
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.timeout = timeout
    # Must be cleared before open() for NodeMCU CH340 auto-reset circuits.
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


def read_until(ser: serial.Serial, marker: bytes, timeout: float = 5.0) -> bytes:
    """Read bytes from serial until marker appears or timeout expires."""
    deadline = time.monotonic() + timeout
    buf = bytearray()
    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting > 0:
            buf.extend(ser.read(waiting))
            if marker in buf:
                return bytes(buf)
        else:
            time.sleep(0.02)
    return bytes(buf)


def enter_raw_repl(ser: serial.Serial, timeout: float = 5.0) -> None:
    """Interrupt running code and switch MicroPython into raw REPL mode."""
    time.sleep(1.2)
    ser.write(b"\r\x03\x03")
    time.sleep(0.2)
    ser.reset_input_buffer()
    ser.write(b"\r\x01")
    resp = read_until(ser, RAW_REPL_BANNER, timeout=timeout)
    if RAW_REPL_BANNER not in resp:
        raise RuntimeError(f"Gagal masuk MicroPython raw REPL. Respons: {resp!r}")


def exec_raw(ser: serial.Serial, code: str, timeout: float = 5.0) -> bytes:
    """Execute Python code in raw REPL and return stdout bytes."""
    ser.write(code.encode("utf-8") + b"\x04")
    response = read_until(ser, b"\x04>", timeout=timeout)
    ok_idx = response.find(b"OK")
    if ok_idx == -1 or not response.endswith(b"\x04>"):
        raise RuntimeError(f"Respons raw REPL tidak valid: {response!r}")

    parts = response[ok_idx + 2 : -2].split(b"\x04")
    if len(parts) != 2:
        raise RuntimeError(f"Format respons raw REPL tidak terduga: {response!r}")

    stdout_bytes, stderr_bytes = parts[0], parts[1]
    if stderr_bytes:
        raise RuntimeError(stderr_bytes.decode("utf-8", errors="replace"))
    return stdout_bytes


def upload_file(ser: serial.Serial, local_path: Path, remote_name: str) -> None:
    """Write a local file onto the ESP8266 MicroPython filesystem."""
    if not local_path.is_file():
        raise FileNotFoundError(f"File tidak ditemukan: {local_path}")

    data = local_path.read_bytes()
    exec_raw(ser, f"import os\nf = open({remote_name!r}, 'wb')")
    try:
        for offset in range(0, len(data), CHUNK_SIZE):
            chunk = data[offset : offset + CHUNK_SIZE]
            exec_raw(ser, f"f.write({chunk!r})")
    finally:
        exec_raw(ser, "f.close()")

    stat_out = exec_raw(ser, f"print(os.stat({remote_name!r})[6])")
    remote_size = int(stat_out.decode("utf-8", errors="replace").strip())
    if remote_size != len(data):
        raise RuntimeError(
            f"Ukuran file di ESP8266 tidak cocok ({remote_size} != {len(data)} bytes)."
        )


def hard_reset(ser: serial.Serial) -> None:
    """Exit raw REPL and pulse RTS to reset ESP8266 into normal boot."""
    ser.write(b"\x02")
    ser.dtr = False
    ser.rts = True
    time.sleep(0.1)
    ser.rts = False


def run_file_in_ram(ser: serial.Serial, local_path: Path, timeout: float = 5.0) -> None:
    """Execute a local MicroPython file directly in RAM without overwriting flash."""
    if not local_path.is_file():
        raise FileNotFoundError(f"File tidak ditemukan: {local_path}")

    data = local_path.read_bytes()
    # Pace writes into 128-byte chunks to avoid overflowing the ESP8266 UART RX buffer.
    for offset in range(0, len(data), 128):
        ser.write(data[offset : offset + 128])
        time.sleep(0.02)
    ser.write(b"\x04")

    resp = read_until(ser, b"OK", timeout=timeout)
    ok_idx = resp.find(b"OK")
    if ok_idx == -1:
        raise RuntimeError(f"ESP8266 tidak merespons OK saat menjalankan {local_path}: {resp!r}")

    trailing = resp[ok_idx + 2 :]
    if trailing:
        print(trailing.decode("utf-8", errors="replace"), end="", flush=True)


def monitor_serial(ser: serial.Serial, duration_seconds: float) -> None:
    """Print serial output from ESP8266 for a fixed duration."""
    if duration_seconds <= 0:
        return
    print(f"--- Output Serial ({duration_seconds:.1f}s) ---")
    deadline = time.monotonic() + duration_seconds
    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting > 0:
            text = ser.read(waiting).decode("utf-8", errors="replace")
            print(text, end="", flush=True)
        else:
            time.sleep(0.05)
    print("\n--- Selesai memantau (ESP8266 tetap berjalan) ---")


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description="Upload & jalankan script MicroPython ke ESP8266")
    parser.add_argument("--port", default="COM6", help="Port serial ESP8266 (default: COM6)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--file", default="main.py", help="File Python lokal (default: main.py)")
    parser.add_argument("--target", default="main.py", help="Nama file di ESP8266 (default: main.py)")
    parser.add_argument("--env", default=".env", help="File .env lokal untuk ikut di-upload (default: .env)")
    parser.add_argument(
        "--skip-env",
        action="store_true",
        help="Lewati upload file .env ke ESP8266",
    )
    parser.add_argument(
        "--run-only",
        action="store_true",
        help="Jalankan langsung di RAM tanpa menimpa file di flash ESP8266",
    )
    parser.add_argument(
        "--monitor-seconds",
        type=float,
        default=4.0,
        help="Durasi pantau output setelah reset dalam detik (0 untuk lewati)",
    )
    return parser.parse_args()


def main() -> int:
    """Connect to ESP8266, upload or run script, and optionally monitor output."""
    args = parse_args()
    local_path = Path(args.file)
    env_path = Path(args.env)
    ser: serial.Serial | None = None

    try:
        ser = open_serial_ch340(args.port, args.baud)
        enter_raw_repl(ser)
        if not args.skip_env and env_path.is_file():
            upload_file(ser, env_path, ".env")
            print(f"Upload sukses: {env_path} -> :.env ({env_path.stat().st_size} bytes)")
        if args.run_only:
            print(f"Menjalankan di RAM: {local_path}")
            run_file_in_ram(ser, local_path)
            monitor_serial(ser, args.monitor_seconds)
        else:
            upload_file(ser, local_path, args.target)
            print(f"Upload sukses: {local_path} -> :{args.target} ({local_path.stat().st_size} bytes)")
            hard_reset(ser)
            monitor_serial(ser, args.monitor_seconds)
        return 0
    except serial.SerialException as exc:
        print(f"Gagal mengakses port {args.port}: {exc}")
        return 1
    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    finally:
        if ser is not None and ser.is_open:
            ser.dtr = False
            ser.rts = False
            ser.close()


if __name__ == "__main__":
    raise SystemExit(main())
