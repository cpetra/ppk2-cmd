# ppk2-cmd

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Command-line tool and Python library for the **Nordic Semiconductor Power Profiler Kit II (PPK2)**. 

Captures continuous, high-resolution current and power samples at **~100,000 samples/sec (100 kSps)** with automatic port discovery, WSL2 support, tabular per-second metrics, data export, and waveform plotting.

---

## Features

- **Smart Auto-Discovery**: Automatically finds and probes the active PPK2 measurement interface (handles dual CDC ACM ports on WSL2, Linux, and Windows).
- **Flexible CLI**: Measure with custom voltage, duration, pre-sampling wait delays, and mode selection (Source Meter / Ampere Meter).
- **Per-Second Breakdown**: Displays average current (µA / mA) and power (mW) for each second of capture.
- **Data Exporting**: Export raw samples to compressed `.npz` (NumPy), `.csv`, or `.json` summary stats.
- **High-Res Plotting**: Generates publication-quality waveforms with rolling averages and power consumption graphs.
- **Clean Python API**: Use `measure()` or `with PPK2Session() as ppk:` in your own scripts and test benches.
- **Mock Simulation Mode**: Test test benches and data pipelines even when physical hardware is not connected.

---

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd ppk2-cmd

# Install with uv (recommended)
uv sync

# Or install with pip in editable mode
pip install -e .
```

---

## Command-Line Usage

### 1. Discover Connected Devices
```bash
ppk2-cmd list
```
*Output:*
```
Scanning for connected PPK2 devices...
  [OTHER/DFU]   Port: /dev/ttyACM1
  [ACTIVE PPK2] Port: /dev/ttyACM0
                Hardware: 49885 | Calibrated: 0
```

### 2. Measure Power Profile
```bash
# 10-second measurement at 5.0V (default):
ppk2-cmd

# Custom duration and voltage (e.g., 30s @ 3.3V):
ppk2-cmd --duration 30 --voltage 3300

# Pre-measurement wait/warm-up delay (e.g., wait 5s, sample 30s):
ppk2-cmd --duration 30 --voltage 5000 --wait 5.0

# Ampere meter mode (external power supplied to DUT):
ppk2-cmd --mode ampere --voltage 3300 --duration 10.0
```

### 3. Save Waveform Plot and Export Data
```bash
# Save high-resolution chart (ppk2_plot.png):
ppk2-cmd --duration 10 --plot

# Export raw samples to compressed NumPy (.npz) and CSV:
ppk2-cmd --duration 10 --plot power_chart.png --npz samples.npz --csv samples.csv --json stats.json
```

### 4. Mock / Simulation Test (No hardware connected)
```bash
ppk2-cmd --mock --duration 5 --plot mock_chart.png
```

---

## CLI Options

| Option | Description | Default |
|---|---|---|
| `-d`, `--duration` | Sampling duration in seconds | `10.0` |
| `-v`, `--voltage` | Output voltage in mV (`800` to `5000`) | `5000` (5.0V) |
| `-w`, `--wait` | Pre-measurement delay in seconds | `0.0` |
| `-m`, `--mode` | `source` (internal power) or `ampere` (external power) | `source` |
| `-p`, `--port` | Explicit serial port | Auto-probed |
| `--summary-only` | Show only overall summary instead of per-second breakdown | `False` |
| `--plot [FILE.png]` | Generate waveform & power plot | `ppk2_plot.png` |
| `--npz FILE.npz` | Export raw numpy sample arrays | None |
| `--csv FILE.csv` | Export raw timestamps & currents to CSV | None |
| `--json FILE.json` | Export summary stats & per-second metrics to JSON | None |
| `--no-dut-power` | Do not toggle DUT power on in source mode | `False` |
| `--mock` | Run simulation without physical device | `False` |

---

## Python API Usage

### High-Level `measure()` API
```python
from ppk2_cmd import measure

# 10-second measurement at 5.0V
result = measure(voltage_mv=5000, duration_s=10.0)

# Access raw NumPy arrays (~100k samples per second)
t = result.timestamps_s   # numpy array [0.000s ... 10.000s]
i_ma = result.current_ma  # numpy array of current in mA
i_ua = result.current_ua  # numpy array of current in µA

# Summary Metrics
print(f"Total samples:   {len(i_ma):,}")
print(f"Average current: {result.mean_ua / 1000:.3f} mA")
print(f"Peak current:    {result.max_ua / 1000:.3f} mA")
print(f"Average power:   {result.avg_power_mw:.3f} mW")

# Print per-second table
result.print_per_second()

# Export data and plot
result.plot("waveform.png")
result.save_npz("raw_data.npz")
result.save_csv("raw_data.csv")
```

### Context Manager `PPK2Session` API
```python
from ppk2_cmd import PPK2Session

with PPK2Session(voltage_mv=3300, mode="source") as ppk:
    # Run test 1
    res1 = ppk.sample(duration_s=5.0)
    
    # Wait or perform external action
    # ...
    
    # Run test 2
    res2 = ppk.sample(duration_s=10.0)
```

---

## WSL2 USB Passthrough Guide

If running inside WSL2 on Windows:

1. **In Windows PowerShell (Run as Administrator)**:
   ```powershell
   # Install usbipd if needed:
   winget install --interactive --exact dorssel.usbipd-win

   # List devices and find BUSID for PPK2:
   usbipd list

   # Attach to WSL2:
   usbipd bind --busid <BUSID>      # (First time only)
   usbipd attach --wsl --busid <BUSID> --auto-attach
   ```

2. **In WSL2**:
   ```bash
   sudo chmod 666 /dev/ttyACM0
   ppk2-cmd list
   ```

---

## License

MIT License.
