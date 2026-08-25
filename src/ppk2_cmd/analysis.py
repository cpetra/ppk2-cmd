"""
Data analysis, statistics, and result models for PPK2 measurements.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import numpy as np


@dataclass
class SecondStats:
    second: int
    t_start: float
    t_end: float
    num_samples: int
    mean_ua: float
    mean_ma: float
    min_ma: float
    max_ma: float
    power_mw: float


@dataclass
class MeasurementResult:
    timestamps_s: np.ndarray
    current_ua: np.ndarray
    current_ma: np.ndarray
    voltage_mv: int
    duration_s: float
    sample_rate_sps: float
    mean_ua: float
    min_ua: float
    max_ua: float
    std_ua: float
    avg_power_mw: float
    digital_channels: Optional[List[List[int]]] = None

    def get_per_second_stats(self) -> List[SecondStats]:
        """Compute statistical breakdown for each 1-second interval."""
        total_samples = len(self.current_ua)
        if total_samples == 0 or self.duration_s <= 0:
            return []

        num_seconds = max(1, int(round(self.duration_s)))
        samples_per_sec = total_samples / self.duration_s
        stats: List[SecondStats] = []

        for sec in range(1, num_seconds + 1):
            idx_start = int((sec - 1) * samples_per_sec)
            idx_end = int(sec * samples_per_sec) if sec < num_seconds else total_samples
            sec_samples_ua = self.current_ua[idx_start:idx_end]
            if len(sec_samples_ua) == 0:
                continue

            sec_ma = sec_samples_ua / 1000.0
            avg_ua = float(np.mean(sec_samples_ua))
            avg_ma = avg_ua / 1000.0
            pwr_mw = avg_ma * (self.voltage_mv / 1000.0)

            stats.append(SecondStats(
                second=sec,
                t_start=float(sec - 1),
                t_end=float(min(sec, self.duration_s)),
                num_samples=len(sec_samples_ua),
                mean_ua=avg_ua,
                mean_ma=avg_ma,
                min_ma=float(np.min(sec_ma)),
                max_ma=float(np.max(sec_ma)),
                power_mw=pwr_mw
            ))
        return stats

    def print_summary(self):
        """Print overall measurement summary."""
        print("\n" + "=" * 55)
        print("            PPK2 MEASUREMENT SUMMARY")
        print("=" * 55)
        print(f"Total Samples:     {len(self.current_ua):,}")
        print(f"Actual Duration:   {self.duration_s:.2f} s")
        print(f"Sample Rate:       {self.sample_rate_sps:,.1f} samples/sec")
        print(f"Voltage:           {self.voltage_mv} mV ({self.voltage_mv/1000:.2f} V)")
        print(f"Average Current:   {self.mean_ua:,.2f} µA  ({self.mean_ua/1000:,.3f} mA)")
        print(f"Min Current:       {self.min_ua:,.2f} µA  ({self.min_ua/1000:,.3f} mA)")
        print(f"Max Current:       {self.max_ua:,.2f} µA  ({self.max_ua/1000:,.3f} mA)")
        print(f"Std Dev:           {self.std_ua:,.2f} µA  ({self.std_ua/1000:,.3f} mA)")
        print(f"Average Power:     {self.avg_power_mw:,.3f} mW")
        print("=" * 55)

    def print_per_second(self):
        """Print tabular per-second breakdown table."""
        stats = self.get_per_second_stats()
        if not stats:
            self.print_summary()
            return

        print("\n" + "=" * 65)
        print(f"      PER-SECOND AVERAGE CURRENT & POWER ({self.voltage_mv/1000:.1f}V)")
        print("=" * 65)
        for s in stats:
            print(f"  Second {s.second:2d} (t={s.t_start:4.1f}s - {s.t_end:4.1f}s):  "
                  f"{s.mean_ua:10.2f} µA  ({s.mean_ma:8.3f} mA)  |  {s.power_mw:8.3f} mW")
        print("-" * 65)
        print(f"  OVERALL AVERAGE:          {self.mean_ua:10.2f} µA  ({self.mean_ua/1000:8.3f} mA)  |  {self.avg_power_mw:8.3f} mW")
        print("=" * 65)

    def save_csv(self, filename: str):
        """Save sample data to CSV file."""
        print(f"Saving {len(self.current_ua):,} samples to CSV: {filename}...")
        header = "time_s,current_uA,current_mA"
        data = np.column_stack((self.timestamps_s, self.current_ua, self.current_ma))
        np.savetxt(filename, data, delimiter=",", header=header, comments="", fmt="%.6f,%.3f,%.6f")
        print(f"  CSV saved successfully ({os.path.getsize(filename) / (1024*1024):.2f} MB).")

    def save_npz(self, filename: str):
        """Save sample data to compressed NumPy archive."""
        print(f"Saving samples to compressed NPZ: {filename}...")
        np.savez_compressed(
            filename,
            time_s=self.timestamps_s,
            current_uA=self.current_ua,
            current_mA=self.current_ma,
            voltage_mV=self.voltage_mv
        )
        print(f"  NPZ saved successfully ({os.path.getsize(filename) / (1024*1024):.2f} MB).")

    def save_json(self, filename: str):
        """Save measurement summary and per-second statistics to JSON."""
        print(f"Saving summary to JSON: {filename}...")
        payload = {
            "voltage_mv": self.voltage_mv,
            "duration_s": self.duration_s,
            "sample_rate_sps": self.sample_rate_sps,
            "total_samples": len(self.current_ua),
            "mean_ua": self.mean_ua,
            "mean_ma": self.mean_ua / 1000.0,
            "min_ua": self.min_ua,
            "max_ua": self.max_ua,
            "std_ua": self.std_ua,
            "avg_power_mw": self.avg_power_mw,
            "per_second": [
                {
                    "second": s.second,
                    "t_start": s.t_start,
                    "t_end": s.t_end,
                    "samples": s.num_samples,
                    "mean_ua": s.mean_ua,
                    "mean_ma": s.mean_ma,
                    "power_mw": s.power_mw
                }
                for s in self.get_per_second_stats()
            ]
        }
        with open(filename, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"  JSON summary saved successfully.")

    def plot(self, filename: str = "ppk2_plot.png", title: Optional[str] = None):
        """Generate and save waveform plot."""
        from .plotting import generate_plot
        generate_plot(self, filename=filename, title=title)
