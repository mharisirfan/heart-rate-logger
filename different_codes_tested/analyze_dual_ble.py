"""
R-only Heart Rate + Spectral Data Logger

ESP32 sends:
sample,millis,R

This logger:
- reads Garmin/watch HR via BLE
- reads ESP32 R-channel spectral value via BLE
- calculates prototype HR from R only
- logs everything to CSV
- sends live values to dashboard

Demo-focused version:
- faster prototype HR appearance
- moderate smoothing
- no jump rejection lock-up
"""

import asyncio
import csv
import os
import struct
from datetime import datetime
from collections import deque

import requests
import numpy as np
from scipy import signal
from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice


HEART_RATE_MEASUREMENT_UUID = "00002A37-0000-1000-8000-00805f9b34fb"
SPECTRAL_CHAR_UUID = "87654321-4321-4321-4321-210987654321"

CSV_FILE = "heart_rate_spectral_log.csv"
DASHBOARD_URL = "http://127.0.0.1:5000/api/upload"

PPG_BUFFER_SIZE = 90
MIN_SAMPLES_FOR_HR = 35

HR_HISTORY_SIZE = 5
MIN_CONFIDENCE = 0.12
HR_UPDATE_INTERVAL_MS = 1000
LAST_HR_UPDATE_MS = 0

latest_watch_hr = None
latest_prototype_hr = None


def parse_heart_rate(data: bytearray) -> int:
    flags = data[0]
    if flags & 0x01:
        return struct.unpack_from("<H", data, 1)[0]
    return data[1]


def parse_spectral_data(data: bytes):
    try:
        text = data.decode(errors="ignore").strip()
        parts = text.split(",")

        if len(parts) < 3:
            return None

        sample = int(parts[0])
        esp_millis = int(parts[1])
        r_value = float(parts[2])

        return sample, esp_millis, r_value

    except Exception:
        return None


def estimate_sampling_rate(timestamps_ms):
    if len(timestamps_ms) < 3:
        return None

    t = np.array(timestamps_ms, dtype=float) / 1000.0
    diffs = np.diff(t)
    diffs = diffs[diffs > 0]

    if len(diffs) == 0:
        return None

    return 1.0 / np.mean(diffs)


def calculate_hr_fft(channel_values, timestamps_ms):
    if len(channel_values) < MIN_SAMPLES_FOR_HR:
        return None, 0.0

    fs = estimate_sampling_rate(timestamps_ms)
    if fs is None or fs < 1.5:
        return None, 0.0

    x = np.array(channel_values, dtype=float)

    if np.std(x) < 0.001:
        return None, 0.0

    baseline = np.mean(x)

    if abs(baseline) > 0.001:
        x = (x - baseline) / baseline
    else:
        x = signal.detrend(x)

    # Remove sharp one-sample spikes
    if len(x) >= 5:
        x = signal.medfilt(x, kernel_size=3)

    low = 0.7
    high = min(2.0, fs / 2.0 - 0.1)

    if high <= low:
        return None, 0.0

    try:
        b, a = signal.butter(
            2,
            [low / (fs / 2), high / (fs / 2)],
            btype="band"
        )
        x_filt = signal.filtfilt(b, a, x)
    except Exception:
        x_filt = signal.detrend(x)

    freqs = np.fft.rfftfreq(len(x_filt), d=1 / fs)
    spectrum = np.abs(np.fft.rfft(x_filt)) ** 2

    mask = (freqs >= low) & (freqs <= high)
    if not np.any(mask):
        return None, 0.0

    band_freqs = freqs[mask]
    band_power = spectrum[mask]

    total_power = np.sum(band_power)
    if total_power <= 0:
        return None, 0.0

    peak_index = np.argmax(band_power)
    peak_freq = band_freqs[peak_index]
    peak_power = band_power[peak_index]

    confidence = peak_power / total_power
    bpm = int(round(peak_freq * 60))

    if 40 <= bpm <= 130 and confidence >= MIN_CONFIDENCE:
        return bpm, confidence

    return None, confidence


def ensure_csv_headers():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "pc_timestamp",
                "esp_sample",
                "esp_millis",
                "watch_hr",
                "prototype_hr",
                "best_channel",
                "confidence",
                "D",
                "F",
                "R"
            ])


def send_to_dashboard(timestamp, watch_hr, prototype_hr, r_value):
    payload = {
        "timestamp": timestamp,
        "watch_hr": watch_hr,
        "prototype_hr": prototype_hr,
        "D": 0,
        "F": 0,
        "R": r_value,
    }

    try:
        requests.post(
            DASHBOARD_URL,
            json=payload,
            timeout=1.0
        )
    except Exception as e:
        print("Dashboard send failed:", e)


async def scan_for_devices():
    print("Scanning for BLE devices...\n")
    devices = await BleakScanner.discover(timeout=5.0)

    print("Discovered devices:")
    for i, d in enumerate(devices):
        print(f"[{i}] {d.name or '(unknown)'} — {d.address}")

    return devices


async def select_devices(devices):
    watch_idx = int(input("\nSelect watch device: "))
    esp_idx = int(input("Select ESP32 device: "))

    return devices[watch_idx], devices[esp_idx]


async def run_logger(watch_device: BLEDevice, esp_device: BLEDevice):
    global latest_watch_hr, latest_prototype_hr, LAST_HR_UPDATE_MS

    ensure_csv_headers()

    r_buffer = deque(maxlen=PPG_BUFFER_SIZE)
    timestamps_ms = deque(maxlen=PPG_BUFFER_SIZE)
    hr_history = deque(maxlen=HR_HISTORY_SIZE)

    async with BleakClient(watch_device.address) as watch_client:
        print("✓ Connected to watch")

        async with BleakClient(esp_device.address) as esp_client:
            print("✓ Connected to ESP32")
            print("\nStarting R-only demo logging. Press Ctrl+C to stop.\n")

            csv_buffer = []

            def watch_handler(sender, data):
                global latest_watch_hr
                latest_watch_hr = parse_heart_rate(data)

            def spectral_handler(sender, data):
                global latest_prototype_hr, LAST_HR_UPDATE_MS

                parsed = parse_spectral_data(data)
                if parsed is None:
                    return

                esp_sample, esp_millis, r_value = parsed

                r_buffer.append(r_value)
                timestamps_ms.append(esp_millis)

                confidence = 0.0

                if esp_millis - LAST_HR_UPDATE_MS >= HR_UPDATE_INTERVAL_MS:
                    new_hr, confidence = calculate_hr_fft(r_buffer, timestamps_ms)
                    LAST_HR_UPDATE_MS = esp_millis

                    if new_hr is not None:
                        hr_history.append(new_hr)
                        latest_prototype_hr = int(round(np.median(hr_history)))

                now = datetime.now().isoformat(timespec="seconds")
                fs = estimate_sampling_rate(timestamps_ms)

                watch_hr_str = str(latest_watch_hr) if latest_watch_hr else "---"
                proto_hr_str = str(latest_prototype_hr) if latest_prototype_hr else "---"
                fs_str = f"{fs:.2f} Hz" if fs else "---"
                conf_str = f"{confidence:.2f}" if confidence else "---"

                print(
                    f"[{now}] "
                    f"Fs={fs_str} | "
                    f"Watch HR: {watch_hr_str:>3} BPM | "
                    f"Prototype HR: {proto_hr_str:>3} BPM | "
                    f"Best=R | Conf={conf_str} | "
                    f"D=0.00, F=0.00, R={r_value:.2f}"
                )

                csv_buffer.append([
                    now,
                    esp_sample,
                    esp_millis,
                    latest_watch_hr if latest_watch_hr else "",
                    latest_prototype_hr if latest_prototype_hr else "",
                    "R",
                    confidence if confidence else "",
                    0,
                    0,
                    r_value
                ])

                send_to_dashboard(
                    esp_millis,
                    latest_watch_hr,
                    latest_prototype_hr,
                    r_value
                )

                if len(csv_buffer) >= 10:
                    with open(CSV_FILE, "a", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerows(csv_buffer)
                    csv_buffer.clear()

            await watch_client.start_notify(
                HEART_RATE_MEASUREMENT_UUID,
                watch_handler
            )

            await esp_client.start_notify(
                SPECTRAL_CHAR_UUID,
                spectral_handler
            )

            try:
                while True:
                    await asyncio.sleep(1)

            finally:
                await watch_client.stop_notify(HEART_RATE_MEASUREMENT_UUID)
                await esp_client.stop_notify(SPECTRAL_CHAR_UUID)

                if csv_buffer:
                    with open(CSV_FILE, "a", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerows(csv_buffer)

                print("\nStopped logging.")


async def main():
    devices = await scan_for_devices()
    watch_device, esp_device = await select_devices(devices)
    await run_logger(watch_device, esp_device)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")