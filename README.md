# ppk2-cmd

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Command-line tool and Python library for the **Nordic Semiconductor Power Profiler Kit II (PPK2)**. 

Captures continuous, high-resolution current and power samples at **~100,000 samples/sec (100 kSps)** with automatic port discovery, WSL2 support, warm-up delay support, tabular per-second metrics, data export, and waveform plotting.

---

## Features

- **Smart Auto-Discovery & `.env` Support**: Automatically finds and probes the active PPK2 measurement interface (handles dual CDC ACM ports on WSL2, Linux, and Windows), or configure once in `.env` for instant connection.
- **Warm-Up / Boot Delay (`--wait`)**: Turn on power and allow your target board to boot or stabilize before recording measurements.
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
git clone https://github.com/cpetra/ppk2-cmd.git
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

### 2. Measure Power Profile
```bash
# 10-second measurement at 5.0V (default):
ppk2-cmd

# Custom duration and voltage (e.g., 30s @ 3.3V):
ppk2-cmd --duration 30 --voltage 3300

# Power DUT, wait 5s for board to boot, then sample for 30s:
ppk2-cmd --voltage 5000 --wait 5.0 --duration 30

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
| `-w`, `--wait` | Warm-up / delay time in seconds before sampling starts (DUT is powered) | `0.0` |
| `-m`, `--mode` | `source` (internal power) or `ampere` (external power) | `source` |
| `-p`, `--port` | Explicit serial port | Auto-probed (or `.env`) |
| `--summary-only` | Show only overall summary instead of per-second breakdown | `False` |
| `--plot [FILE.png]` | Generate waveform & power plot | `ppk2_plot.png` |
| `--npz FILE.npz` | Export raw numpy sample arrays | None |
| `--csv FILE.csv` | Export raw timestamps & currents to CSV | None |
| `--json FILE.json` | Export summary stats & per-second metrics to JSON | None |
| `--no-dut-power` | Do not toggle DUT power on in source mode | `False` |
| `--mock` | Run simulation without physical device | `False` |

---

## Python API Usage

```python
from ppk2_cmd import measure

# Power DUT, wait 5.0s for stabilization, sample for 10.0s at 5.0V
result = measure(
    voltage_mv=5000,
    wait_before_s=5.0,
    duration_s=10.0
)

# Access all ~1,000,000 raw samples
print(f"Total samples:   {len(result.current_ma):,}")
print(f"Average current: {result.mean_ua / 1000:.3f} mA")
print(f"Average power:   {result.avg_power_mw:.3f} mW")

# Display per-second breakdown table
result.print_per_second()

# Export data and plot
result.plot("waveform.png")
result.save_npz("raw_samples.npz")
result.save_csv("raw_samples.csv")
```

---

## Environment Variables (`.env`)

Create a `.env` file in your working directory to customize default settings:

```ini
PPK2_PORT=/dev/ttyACM0
PPK2_VOLTAGE=5000
PPK2_DURATION=10.0
PPK2_MODE=source
```

---

## License

MIT License.
