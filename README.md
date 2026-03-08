# BLE Heart Rate Logger

A Python tool that connects to a Bluetooth Low Energy (BLE) heart rate device (e.g. a Garmin watch) and logs live heart rate readings to a CSV file. This tool serves as the **ground truth data collector** for a larger research project comparing smartwatch HR against a custom multi-wavelength spectrometer-based sensing system.

---

## Project Context

This logger serves as the **ground truth data collector** for an MSc research project that investigates multi-spectral optical sensing for heart rate monitoring.

### The Broader Research System

```
Garmin Watch (BLE HR)
        │
        ▼
 heart_rate_logger.py  ──►  heart_rate_log.csv  (Ground Truth)
                                     │
                                     ▼
              ┌──────────────────────────────────┐
              │        Validation & Analysis      │
              │  Spectrometer HR  vs  Garmin HR   │
              │  MAE / RMSE / Correlation         │
              └──────────────────────────────────┘
                                     ▲
        ┌────────────────────────────┘
        │
ESP32-WROOM-32E + AS7265x Spectrometer Watch
  - 18 spectral channels (410–940 nm)
  - White / IR / UV LED illumination
  - Adjustable sampling rate (target ≥ 50 Hz)
  - Multi-wavelength spectral signal capture
```

### Why Multi-Wavelength?

Most wearables use only a single green LED (~525 nm) for heart rate sensing. This project instead uses the AS7265x spectrometer across all 18 spectral bands (410–940 nm) to:

- Compare signal quality (SNR) across wavelengths
- Identify the most robust channel per condition
- Investigate whether multi-channel fusion improves HR accuracy
- Potentially train an ML regression model using Garmin HR as labels

---

## This Repository — BLE HR Logger

### What It Does

1. Scans for nearby BLE devices
2. Prioritises devices advertising the standard Heart Rate Service (`0x180D`)
3. Lets the user select a device from a numbered list
4. Subscribes to Heart Rate Measurement notifications (`0x2A37`)
5. Parses both 8-bit and 16-bit HR formats per the BLE spec
6. Logs `timestamp, heart_rate` to `heart_rate_log.csv` in real time
7. Prints live readings to the console

### Example Output

```
Scanning for BLE devices (5 seconds)...

Discovered devices:
  [0] Garmin Forerunner — AA:BB:CC:DD:EE:FF

Select device [0-0]: 0

Connecting to 'Garmin Forerunner'...
Connected. Subscribing to Heart Rate Measurement notifications.
Press Ctrl+C to stop.

[2026-03-08 14:22:01] Heart Rate: 72 BPM
[2026-03-08 14:22:02] Heart Rate: 73 BPM
[2026-03-08 14:22:03] Heart Rate: 74 BPM
```

### CSV Output (`heart_rate_log.csv`)

```
timestamp,heart_rate
2026-03-08T14:22:01,72
2026-03-08T14:22:02,73
2026-03-08T14:22:03,74
```

---

## Setup

### Requirements

- Python 3.10+
- Bluetooth adapter (hardware)

### Install Dependencies

```bash
pip install bleak
```

### Garmin Watch Setup

Enable heart rate broadcast on your watch:

```
Settings → Sensors & Accessories → Wrist Heart Rate → Broadcast Heart Rate → On
```

This makes the watch act as a standard BLE Heart Rate sensor, readable by any BLE client without a proprietary SDK.

---

## Usage

```bash
python heart_rate_logger.py
```

Stop logging at any time with `Ctrl+C`. The CSV file is appended to on each run (headers are added only if the file does not exist).

---

## BLE Technical Details

| Field | Value |
|---|---|
| Heart Rate Service UUID | `0000180D-0000-1000-8000-00805f9b34fb` |
| HR Measurement Characteristic | `00002A37-0000-1000-8000-00805f9b34fb` |
| HR Format (flags bit 0 = 0) | UINT8 at `data[1]` |
| HR Format (flags bit 0 = 1) | UINT16 little-endian at `data[1:3]` |
| Typical update rate | 1 Hz |

---

## Roadmap

- [x] BLE device scan and selection
- [x] Live HR logging to CSV
- [ ] Auto-reconnect on connection drop
- [ ] Real-time HR plot (matplotlib)
- [ ] Session-based output folders with timestamps
- [ ] Synchronisation tool — align Garmin CSV with spectrometer CSV
- [ ] Validation metrics (MAE, RMSE, Bland–Altman)
- [ ] ML regression pipeline using Garmin HR as ground truth labels

---

## Author

**Haris Irfan** — MSc student, embedded systems & wearable sensing research
