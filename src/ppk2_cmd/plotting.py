"""
High-resolution waveform and power plotting for PPK2.
"""

from typing import Optional, TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from .analysis import MeasurementResult


def generate_plot(result: "MeasurementResult", filename: str = "ppk2_plot.png", title: Optional[str] = None):
    """Generate and save a waveform and power plot."""
    import matplotlib.pyplot as plt

    print(f"Generating plot: {filename}...")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw={'height_ratios': [3, 1]})

    # Downsample points for smooth rendering if needed
    stride = max(1, len(result.current_ma) // 200_000)
    t_plot = result.timestamps_s[::stride]
    i_plot = result.current_ma[::stride]

    # 1. Main Current Waveform (mA)
    ax1.plot(t_plot, i_plot, color="#007acc", alpha=0.8, linewidth=0.7, label="Current (mA)")

    # Rolling Average (100ms window)
    window = int(max(10, (result.sample_rate_sps * 0.1) // stride))
    if len(i_plot) > window:
        rolling_avg = np.convolve(i_plot, np.ones(window)/window, mode='valid')
        t_rolling = t_plot[window-1:]
        ax1.plot(t_rolling, rolling_avg, color="#e63946", linewidth=1.5, label="Rolling Avg (100ms)")

    # Stats reference line
    mean_ma = result.mean_ua / 1000.0
    ax1.axhline(mean_ma, color="#2a9d8f", linestyle="--", alpha=0.8, label=f"Mean: {mean_ma:.3f} mA")

    ax1.set_ylabel("Current (mA)", fontsize=11, fontweight="bold")
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.legend(loc="upper right", framealpha=0.9)

    plot_title = title or f"PPK2 Power Profile ({result.voltage_mv} mV, {result.duration_s:.1f}s, {len(result.current_ua):,} samples)"
    ax1.set_title(plot_title, fontsize=13, fontweight="bold", pad=12)

    # 2. Power Waveform (mW)
    p_plot = i_plot * (result.voltage_mv / 1000.0)
    ax2.plot(t_plot, p_plot, color="#f4a261", linewidth=0.7)
    ax2.set_xlabel("Time (seconds)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Power (mW)", fontsize=11, fontweight="bold")
    ax2.grid(True, linestyle=":", alpha=0.6)

    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close()
    print(f"  Plot saved successfully as '{filename}'.")
