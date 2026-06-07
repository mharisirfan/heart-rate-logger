"""
Heart Rate + Spectral Data Logger
Supports ESP32 format: sample,millis,S,T,U,V,W,K,L
"""

import asyncio
import struct
from datetime import datetime
from collections import deque

import numpy as np
from scipy import signal

from bleak import BleakClient, BleakScanner

HEART_RATE_MEASUREMENT_UUID = "00002A37-0000-1000-8000-00805f9b34fb"
SPECTRAL_CHAR_UUID = "87654321-4321-4321-4321-210987654321"

SPECTRAL_CHANNELS = ["S", "T", "U", "V", "W", "K", "L"]

PPG_BUFFER_SIZE = 250
TIME_BUFFER_SIZE = 250
HR_CALCULATION_INTERVAL = 5

latest_watch_hr = None
latest_prototype_hr = None
latest_best_channel = None
latest_fs = None

ppg_buffers = {ch: deque(maxlen=PPG_BUFFER_SIZE) for ch in SPECTRAL_CHANNELS}
time_buffer = deque(maxlen=TIME_BUFFER_SIZE)

sample_count = 0


def parse_heart_rate(data: bytearray) -> int:
    flags = data[0]
    if flags & 0x01:
        return struct.unpack_from("<H", data, 1)[0]
    return data[1]


def parse_spectral_data(data: bytes):
    """
    Expected ESP32 format:
    sample,millis,S,T,U,V,W,K,L
    """
    try:
        values = data.decode().strip().split(",")

        if len(values) >= 9:
            sample_id = int(values[0])
            esp_millis = int(values[1])
            spectral = [float(v) for v in values[2:9]]
            return sample_id, esp_millis, spectral

        # fallback for old format: S,T,U,V,W,K,L
        if len(values) >= 7:
            spectral = [float(v) for v in values[:7]]
            return None, None, spectral

    except Exception as e:
        print("Parse error:", e, "raw:", data)

    return None


def estimate_sampling_rate():
    if len(time_buffer) < 5:
        return None

    times = np.array(time_buffer, dtype=np.float64) / 1000.0
    diffs = np.diff(times)

    diffs = diffs[diffs > 0]
    if len(diffs) == 0:
        return None

    avg_dt = np.median(diffs)

    if avg_dt <= 0:
        return None

    return 1.0 / avg_dt


def calculate_hr_from_single_channel(buffer, fs):
    if fs is None or fs < 4:
        return None, 0

    if len(buffer) < int(fs * 8):
        return None, 0

    x = np.array(buffer, dtype=np.float32)

    if np.std(x) < 0.5:
        return None, 0

    x = x - np.mean(x)

    low = 0.8
    high = min(2.2, fs / 2 - 0.1)

    if high <= low:
        return None, 0

    try:
        b, a = signal.butter(
            2,
            [low / (fs / 2), high / (fs / 2)],
            btype="bandpass"
        )
        y = signal.filtfilt(b, a, x)
    except Exception:
        return None, 0

    freqs, power = signal.welch(
        y,
        fs=fs,
        nperseg=min(len(y), 128)
    )

    mask = (freqs >= low) & (freqs <= high)

    if not np.any(mask):
        return None, 0

    freqs = freqs[mask]
    power = power[mask]

    if np.sum(power) <= 0:
        return None, 0

    idx = np.argmax(power)
    bpm = freqs[idx] * 60

    quality = power[idx] / np.sum(power)

    if 45 <= bpm <= 150:
        return int(round(bpm)), quality

    return None, 0


def calculate_hr(fs):
    results = []

    for ch in SPECTRAL_CHANNELS:
        bpm, q = calculate_hr_from_single_channel(ppg_buffers[ch], fs)

        if bpm is not None and q > 0.05:
            results.append((bpm, q, ch))

    if not results:
        return None, None

    results.sort(key=lambda x: x[1], reverse=True)

    return results[0][0], results[0][2]


async def spectral_handler(sender, data):
    global sample_count, latest_prototype_hr, latest_best_channel, latest_fs

    parsed = parse_spectral_data(data)

    if parsed is None:
        return

    sample_id, esp_millis, spectral = parsed

    if len(spectral) != 7:
        return

    if any(v <= 0 for v in spectral):
        return

    if esp_millis is not None:
        time_buffer.append(esp_millis)

    for i, ch in enumerate(SPECTRAL_CHANNELS):
        ppg_buffers[ch].append(spectral[i])

    sample_count += 1

    if sample_count % HR_CALCULATION_INTERVAL == 0:
        latest_fs = estimate_sampling_rate()

        if latest_fs is not None:
            hr, best = calculate_hr(latest_fs)
            latest_prototype_hr = hr
            latest_best_channel = best


async def heart_handler(sender, data):
    global latest_watch_hr

    latest_watch_hr = parse_heart_rate(data)
    ts = datetime.now().strftime("%H:%M:%S")

    print(f"[{ts}] Watch: {latest_watch_hr:3d}", end="")
    print(f" | Samples: {sample_count}", end="")

    if latest_fs is not None:
        print(f" | fs: {latest_fs:.2f}Hz", end="")
    else:
        print(" | fs: --", end="")

    if latest_prototype_hr is not None:
        diff = abs(latest_watch_hr - latest_prototype_hr)
        print(f" | Prototype: {latest_prototype_hr:3d} | Δ {diff:2d} | {latest_best_channel}")
    else:
        print(" | Prototype: ----")


async def main():
    print("Scanning for BLE devices...")
    devices = await BleakScanner.discover(timeout=5.0)

    for i, d in enumerate(devices):
        print(i, d.name, d.address)

    w = int(input("Select watch: "))
    e = int(input("Select ESP32: "))

    watch = devices[w]
    esp = devices[e]

    async with BleakClient(watch.address) as wc, BleakClient(esp.address) as ec:
        print("Connected")

        await ec.start_notify(SPECTRAL_CHAR_UUID, spectral_handler)
        print("ESP streaming started")

        await wc.start_notify(HEART_RATE_MEASUREMENT_UUID, heart_handler)
        print("Collecting data... wait for buffer warmup")

        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())