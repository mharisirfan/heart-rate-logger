"""
BLE Heart Rate Logger
Connects to a Bluetooth Low Energy heart rate device (e.g. Garmin watch)
and logs live heart rate values to heart_rate_log.csv.
"""

import asyncio
import csv
import os
import struct
from datetime import datetime

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

HEART_RATE_SERVICE_UUID = "0000180D-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT_UUID = "00002A37-0000-1000-8000-00805f9b34fb"
CSV_FILE = "heart_rate_log.csv"


def parse_heart_rate(data: bytearray) -> int:
    """
    Parse heart rate from the Heart Rate Measurement characteristic packet.

    Flags byte (data[0]):
      Bit 0 — Heart Rate Value Format:
              0 = UINT8  (data[1])
              1 = UINT16 (data[1:3], little-endian)
    """
    flags = data[0]
    if flags & 0x01:
        # 16-bit heart rate value
        heart_rate = struct.unpack_from("<H", data, 1)[0]
    else:
        # 8-bit heart rate value
        heart_rate = data[1]
    return heart_rate


def ensure_csv_headers() -> None:
    """Create the CSV file with headers if it does not already exist."""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, mode="w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "heart_rate"])
        print(f"Created '{CSV_FILE}' with headers.")


def log_to_csv(timestamp: str, heart_rate: int) -> None:
    """Append a single heart rate reading to the CSV file."""
    with open(CSV_FILE, mode="a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, heart_rate])


async def scan_for_devices() -> list[BLEDevice]:
    """Scan for nearby BLE devices and return those advertising the Heart Rate Service."""
    print("Scanning for BLE devices (5 seconds)...\n")
    devices = await BleakScanner.discover(timeout=5.0, return_adv=False)

    # Prefer devices that advertise the Heart Rate Service, but show all so the
    # user can still pick one manually if service advertisement is missing.
    hr_devices = [d for d in devices if HEART_RATE_SERVICE_UUID.lower() in
                  (s.lower() for s in (d.metadata.get("uuids") or []))]

    if hr_devices:
        return hr_devices

    # Fallback: return all discovered devices
    return list(devices)


async def select_device(devices: list[BLEDevice]) -> BLEDevice:
    """Print a numbered list of devices and let the user pick one."""
    if not devices:
        raise RuntimeError("No BLE devices found. Make sure Bluetooth is enabled.")

    print("Discovered devices:")
    for i, device in enumerate(devices):
        print(f"  [{i}] {device.name or '(unknown)'} — {device.address}")

    print()
    while True:
        try:
            choice = int(input(f"Select device [0-{len(devices) - 1}]: "))
            if 0 <= choice < len(devices):
                return devices[choice]
        except ValueError:
            pass
        print("Invalid selection, please try again.")


async def run_heart_rate_monitor(device: BLEDevice) -> None:
    """Connect to the selected device and stream heart rate notifications."""
    ensure_csv_headers()

    def notification_handler(sender, data: bytearray) -> None:  # noqa: ARG001
        heart_rate = parse_heart_rate(data)
        timestamp = datetime.now().isoformat(timespec="seconds")
        display_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{display_ts}] Heart Rate: {heart_rate} BPM")
        log_to_csv(timestamp, heart_rate)

    print(f"\nConnecting to '{device.name or device.address}'...")
    async with BleakClient(device.address) as client:
        if not client.is_connected:
            raise ConnectionError(f"Failed to connect to {device.address}")

        print(f"Connected. Subscribing to Heart Rate Measurement notifications.")
        print("Press Ctrl+C to stop.\n")

        await client.start_notify(HEART_RATE_MEASUREMENT_UUID, notification_handler)

        # Keep the connection alive until interrupted
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await client.stop_notify(HEART_RATE_MEASUREMENT_UUID)
            print("\nStopped notifications.")


async def main() -> None:
    try:
        devices = await scan_for_devices()
        device = await select_device(devices)
        await run_heart_rate_monitor(device)
    except ConnectionError as exc:
        print(f"[Connection Error] {exc}")
    except RuntimeError as exc:
        print(f"[Error] {exc}")
    except KeyboardInterrupt:
        print("\nLogging stopped by user.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")
