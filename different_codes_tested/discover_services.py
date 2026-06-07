"""
Discover available BLE services and characteristics on a device.
Useful for finding the correct UUIDs for non-standard devices.
"""

import asyncio

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice


async def scan_for_devices() -> list[BLEDevice]:
    """Scan for nearby BLE devices."""
    print("Scanning for BLE devices (5 seconds)...\n")
    devices = await BleakScanner.discover(timeout=5.0)
    return devices


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


async def discover_services(device: BLEDevice) -> None:
    """Connect to device and list all services and characteristics."""
    print(f"\nConnecting to '{device.name or device.address}'...")
    async with BleakClient(device.address) as client:
        if not client.is_connected:
            raise ConnectionError(f"Failed to connect to {device.address}")

        print(f"Connected!\n")
        print("=" * 80)
        print("SERVICES AND CHARACTERISTICS")
        print("=" * 80)

        for service in client.services:
            print(f"\n[SERVICE] {service.uuid}")
            print(f"  Description: {service.description}")

            for characteristic in service.characteristics:
                props = ", ".join(characteristic.properties)
                print(f"  └─ [CHAR] {characteristic.uuid}")
                print(f"     Description: {characteristic.description}")
                print(f"     Properties: {props}")

                # Try to read the characteristic if readable
                if "read" in characteristic.properties:
                    try:
                        value = await client.read_gatt_char(characteristic.uuid)
                        print(f"     Value: {value.hex()}")
                    except Exception as e:
                        print(f"     Value: (couldn't read - {type(e).__name__})")


async def main() -> None:
    try:
        devices = await scan_for_devices()
        device = await select_device(devices)
        await discover_services(device)
    except ConnectionError as exc:
        print(f"[Connection Error] {exc}")
    except RuntimeError as exc:
        print(f"[Error] {exc}")
    except KeyboardInterrupt:
        print("\nExiting.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")
