
"""Heart Rate + Spectral Data Logger with PPG HR Calculation (Dual BLE)
Connects to:
1. BLE Heart Rate device (watch)
2. ESP32 with AS7265X spectral sensor over BLE

Calculates heart rate from spectral channels and compares with watch HR.
"""

import asyncio
import csv
import os
import struct
from datetime import datetime
from collections import deque
import requests
import threading

import numpy as np
from scipy import signal

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

# Smoothing parameters
SMOOTHING_WINDOW = 5  # Moving average over 5 samples (~250ms at 20Hz)

HEART_RATE_SERVICE_UUID = "0000180D-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT_UUID = "00002A37-0000-1000-8000-00805f9b34fb"

# ESP32 Spectral BLE UUIDs (must match the Arduino code)
SPECTRAL_SERVICE_UUID = "12345678-1234-1234-1234-123456789012"
SPECTRAL_CHAR_UUID = "87654321-4321-4321-4321-210987654321"

CSV_FILE = "heart_rate_spectral_log.csv"

# Spectral channel names (3 channels for robust HR)
SPECTRAL_CHANNELS = ["S_680nm", "S_870nm", "S_730nm"]

# PPG processing parameters - OPTIMIZED FOR SPEED & ROBUSTNESS
PPG_BUFFER_SIZE = 25  # Keep last 25 samples (~1.25 seconds at 20Hz) - FAST response!
HR_CALCULATION_INTERVAL = 1  # Calculate HR every sample (20 Hz)
SAMPLING_RATE = 20.0  # 20 Hz sampling rate (50ms Arduino delay)


def parse_heart_rate(data: bytearray) -> int:
    """Parse heart rate from the Heart Rate Measurement characteristic packet."""
    flags = data[0]
    if flags & 0x01:
        # 16-bit heart rate value
        heart_rate = struct.unpack_from("<H", data, 1)[0]
    else:
        # 8-bit heart rate value
        heart_rate = data[1]
    return heart_rate


def parse_spectral_data(data: bytes) -> list:
    """Parse 3 spectral channels from ESP32 BLE: 680nm, 870nm, 730nm (comma-separated)."""
    try:
        data_str = data.decode().strip()
        values = data_str.split(',')
        if len(values) >= 3:
            return [float(v) for v in values[:3]]  # Return [680nm, 870nm, 730nm]
        else:
            return None
    except Exception as e:
        return None


def smooth_spectral_data(raw_values: list, smooth_buffers: dict, window: int = 5) -> list:
    """Apply moving average smoothing to spectral channels to reduce noise."""
    if not raw_values or len(raw_values) < 3:
        return raw_values
    
    smoothed = []
    for i, channel_name in enumerate(["s_680nm", "s_870nm", "s_730nm"]):
        smooth_buffers[channel_name].append(raw_values[i])
        # Calculate moving average
        avg = np.mean(list(smooth_buffers[channel_name]))
        smoothed.append(avg)
    
    return smoothed


def calculate_hr_from_single_channel(channel_buffer: deque, sampling_rate: float = 20.0) -> int:
    """Calculate HR from a single PPG channel using FFT."""
    if len(channel_buffer) < 8:
        return None
    
    try:
        ppg_array = np.array(list(channel_buffer), dtype=np.float32)
        
        # Quick signal quality check
        if np.std(ppg_array) < 0.05:
            return None
        
        # Remove DC
        ppg_centered = ppg_array - np.mean(ppg_array)
        
        # FFT (no windowing for speed)
        fft = np.abs(np.fft.fft(ppg_centered))[:len(ppg_centered)//2]
        freqs = np.fft.fftfreq(len(ppg_centered), 1/sampling_rate)[:len(ppg_centered)//2]
        
        # Find frequency in HR range (0.7-3.5 Hz = 42-210 BPM)
        valid_idx = (freqs > 0.7) & (freqs < 3.5)
        if not np.any(valid_idx):
            return None
        
        # Get dominant frequency
        peak_idx = np.argmax(fft[valid_idx])
        peak_freq = freqs[valid_idx][peak_idx]
        
        # Convert to BPM
        bpm = int(peak_freq * 60)
        
        if 40 <= bpm <= 200:
            return bpm
            
    except:
        pass
    
    return None


def calculate_hr_from_multi_channel(buffers: dict, sampling_rate: float = 20.0) -> int:
    """Calculate HR from 3 channels independently, use MEDIAN voting for robustness."""
    hr_values = []
    
    for channel_name in ["S_680nm", "S_870nm", "S_730nm"]:
        if channel_name in buffers:
            # Check if channel has valid data (not all zeros)
            channel_data = list(buffers[channel_name])
            if len(channel_data) > 0 and any(v > 0.1 for v in channel_data):  # At least some non-zero values
                hr = calculate_hr_from_single_channel(buffers[channel_name], sampling_rate)
                if hr is not None:
                    hr_values.append(hr)
    
    # If no channels have good data, try 680nm alone
    if len(hr_values) == 0:
        hr = calculate_hr_from_single_channel(buffers["S_680nm"], sampling_rate)
        if hr is not None:
            return hr
    
    # Return median of valid HR estimates (robust to noise)
    if len(hr_values) > 0:
        return int(np.median(hr_values))
    
    return None


def ensure_csv_headers() -> None:
    """Create the CSV file with headers if it does not already exist."""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode="w", newline="") as f:
            writer = csv.writer(f)
            header = ["timestamp", "watch_hr", "prototype_hr", "S_680nm", "S_870nm", "S_730nm"]
            writer.writerow(header)
        print(f"Created '{CSV_FILE}' with headers.")


def log_to_csv(timestamp: str, watch_hr: int = None, prototype_hr: int = None, spectral_data: list = None) -> list:
    """Queue a record for CSV (returns data to batch)."""
    row = [timestamp, watch_hr if watch_hr is not None else "", prototype_hr if prototype_hr is not None else ""]
    if spectral_data and len(spectral_data) >= 3:
        row.extend([spectral_data[0], spectral_data[1], spectral_data[2]])  # S_680nm, S_870nm, S_730nm
    else:
        row.extend(["", "", ""])  # Add 3 empty columns if no data
    return row


def flush_csv_buffer(buffer: list) -> None:
    """Write batched records to CSV file."""
    if not buffer:
        return
    with open(CSV_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(buffer)
    buffer.clear()


def send_to_dashboard(timestamp: str, watch_hr: int, prototype_hr: int, spectral_data: list) -> None:
    """Send data point to web dashboard (non-blocking)."""
    try:
        data = {
            "timestamp": timestamp,
            "watch_hr": watch_hr if watch_hr else None,
            "prototype_hr": prototype_hr if prototype_hr else None,
            "s_680nm": spectral_data[0] if spectral_data and len(spectral_data) > 0 else None,
            "s_870nm": spectral_data[1] if spectral_data and len(spectral_data) > 1 else None,
            "s_730nm": spectral_data[2] if spectral_data and len(spectral_data) > 2 else None,
        }
        # Send asynchronously to avoid blocking BLE reads
        def post_to_server():
            try:
                requests.post("http://localhost:5000/api/upload", json=data, timeout=0.5)
            except:
                pass  # Silently fail if dashboard not running
        
        threading.Thread(target=post_to_server, daemon=True).start()
    except Exception as e:
        pass  # Fail silently


async def scan_for_devices() -> list[BLEDevice]:
    """Scan for nearby BLE devices."""
    print("Scanning for BLE devices (5 seconds)...\n")
    devices = await BleakScanner.discover(timeout=5.0)
    return devices


async def select_devices(devices: list[BLEDevice]) -> tuple:
    """Let user select two devices: watch and ESP32."""
    if len(devices) < 2:
        raise RuntimeError(f"Need at least 2 devices. Found {len(devices)}. Make sure both are powered and nearby.")

    print("Discovered devices:")
    for i, device in enumerate(devices):
        print(f"  [{i}] {device.name or '(unknown)'} — {device.address}")

    print()
    watch_device = None
    esp_device = None

    while watch_device is None:
        try:
            choice = int(input(f"Select watch device (Heart Rate) [0-{len(devices) - 1}]: "))
            if 0 <= choice < len(devices):
                watch_device = devices[choice]
                print(f"  → Selected: {watch_device.name or watch_device.address}\n")
        except ValueError:
            pass

    while esp_device is None:
        try:
            choice = int(input(f"Select ESP32 Spectral device [0-{len(devices) - 1}]: "))
            if 0 <= choice < len(devices) and devices[choice] != watch_device:
                esp_device = devices[choice]
                print(f"  → Selected: {esp_device.name or esp_device.address}\n")
            elif devices[choice] == watch_device:
                print("  → That's the same device!")
        except ValueError:
            pass

    return watch_device, esp_device


async def run_dual_logger(watch_device: BLEDevice, esp_device: BLEDevice) -> None:
    """Connect to both devices and log data synchronized by heart rate timing."""
    ensure_csv_headers()

    # Separate buffer for each spectral channel (3-channel voting)
    ppg_buffers = {
        "S_680nm": deque(maxlen=PPG_BUFFER_SIZE),
        "S_870nm": deque(maxlen=PPG_BUFFER_SIZE),
        "S_730nm": deque(maxlen=PPG_BUFFER_SIZE),
    }
    
    # Smoothing buffers (moving average)
    smooth_buffers = {
        "s_680nm": deque(maxlen=SMOOTHING_WINDOW),
        "s_870nm": deque(maxlen=SMOOTHING_WINDOW),
        "s_730nm": deque(maxlen=SMOOTHING_WINDOW),
    }
    
    sample_count = 0
    csv_buffer = []  # Batch CSV writes for speed

    async with BleakClient(watch_device.address) as watch_client:
        if not watch_client.is_connected:
            raise ConnectionError(f"Failed to connect to watch at {watch_device.address}")
        print("✓ Connected to watch")

        async with BleakClient(esp_device.address) as esp_client:
            if not esp_client.is_connected:
                raise ConnectionError(f"Failed to connect to ESP32 at {esp_device.address}")
            print("✓ Connected to ESP32")
            print("\nStarting synchronized data acquisition. Press Ctrl+C to stop.\n")
            print("=" * 90)

            async def heart_rate_handler(sender, data: bytearray) -> None:
                """Ultra-fast live monitoring loop with 3-channel voting."""
                nonlocal sample_count
                
                watch_hr = parse_heart_rate(data)
                timestamp = datetime.now().isoformat(timespec="seconds")
                display_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Read spectral data (3 channels)
                try:
                    spectral_bytes = await esp_client.read_gatt_char(SPECTRAL_CHAR_UUID)
                    spectral_data = parse_spectral_data(spectral_bytes)
                except:
                    spectral_data = None

                # Update buffers with new data
                prototype_hr = None
                smoothed_data = None  # Initialize for logging
                if spectral_data and len(spectral_data) == 3:
                    # Apply smoothing to reduce noise
                    smoothed_data = smooth_spectral_data(spectral_data, smooth_buffers, SMOOTHING_WINDOW)
                    
                    # Load smoothed values into respective buffers
                    ppg_buffers["S_680nm"].append(smoothed_data[0])
                    ppg_buffers["S_870nm"].append(smoothed_data[1])
                    ppg_buffers["S_730nm"].append(smoothed_data[2])
                    sample_count += 1
                    
                    # Calculate HR using median voting from 3 channels
                    prototype_hr = calculate_hr_from_multi_channel(ppg_buffers, SAMPLING_RATE)

                # Display (use smoothed data)
                display_data = smoothed_data if smoothed_data else spectral_data
                print(f"[{display_ts}] Watch HR: {watch_hr:3d} BPM", end="")
                if prototype_hr is not None:
                    diff = abs(watch_hr - prototype_hr)
                    print(f" | Prototype HR: {prototype_hr:3d} BPM (Δ {diff:2d})", end="")
                else:
                    print(f" | Prototype HR: ---- BPM", end="")
                
                if display_data and len(display_data) == 3:
                    print(f" | [680nm: {display_data[0]:.2f} | 870nm: {display_data[1]:.2f} | 730nm: {display_data[2]:.2f}]")
                else:
                    print()

                # Batch CSV writes (every 5 samples = 250ms at 20Hz)
                row = log_to_csv(timestamp, watch_hr, prototype_hr, display_data)
                csv_buffer.append(row)
                if len(csv_buffer) >= 5:
                    flush_csv_buffer(csv_buffer)
                
                # Send to dashboard (non-blocking)
                send_to_dashboard(timestamp, watch_hr, prototype_hr, display_data)

            # Subscribe to heart rate notifications
            await watch_client.start_notify(HEART_RATE_MEASUREMENT_UUID, heart_rate_handler)

            try:
                while True:
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                pass
            finally:
                await watch_client.stop_notify(HEART_RATE_MEASUREMENT_UUID)
                # Flush remaining CSV buffer
                flush_csv_buffer(csv_buffer)
                print("\n" + "=" * 90)
                print("Stopped data acquisition.")


async def main() -> None:
    try:
        devices = await scan_for_devices()
        watch_device, esp_device = await select_devices(devices)
        await run_dual_logger(watch_device, esp_device)
    except ConnectionError as exc:
        print(f"\n[Connection Error] {exc}")
    except RuntimeError as exc:
        print(f"\n[Error] {exc}")
    except KeyboardInterrupt:
        print("\nLogging stopped by user.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")
