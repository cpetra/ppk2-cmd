"""
Core measurement session and acquisition engine for PPK2.
"""

import sys
import time
from datetime import datetime
from typing import Optional, List
import numpy as np
from ppk2_api.ppk2_api import PPK2_API, PPK2_MP, PPK2_Command

from .discovery import get_active_ppk2_port
from .analysis import MeasurementResult


def init_ppk2_connection(ppk: PPK2_API):
    """
    Safely initialize serial communication:
    Stops any leftover streaming and drains serial buffer before reading metadata.
    """
    try:
        ppk._write_serial((PPK2_Command.AVERAGE_STOP,))
        time.sleep(0.05)
        while ppk.ser.in_waiting > 0:
            ppk.ser.read(ppk.ser.in_waiting)
            time.sleep(0.02)
    except Exception:
        pass
    ppk.get_modifiers()


def downsample_array(arr: np.ndarray, target_sps: int, native_sps: float) -> np.ndarray:
    """Downsample an array to target_sps using block-averaging."""
    if target_sps >= native_sps or len(arr) == 0:
        return arr
    factor = int(round(native_sps / target_sps))
    if factor <= 1:
        return arr
    trim_len = len(arr) - (len(arr) % factor)
    if trim_len == 0:
        return arr
    return arr[:trim_len].reshape(-1, factor).mean(axis=1)


def _format_time(seconds: float, show_ms: bool = True) -> str:
    """Format seconds into human-readable string (mm:ss.s or ss.ss)."""
    if seconds >= 60:
        mins = int(seconds // 60)
        secs = seconds % 60
        if show_ms:
            return f"{mins:02d}:{secs:04.1f}"
        return f"{mins:02d}:{int(secs):02d}"
    else:
        if show_ms:
            return f"{seconds:4.1f}s"
        return f"{int(seconds):2d}s"


class PPK2Session:
    """
    Manages a connected PPK2 device session with context manager support.
    """
    def __init__(
        self,
        port: Optional[str] = None,
        mode: str = "source",
        voltage_mv: int = 5000,
        dut_power: bool = True,
        use_mp: bool = False,
        timeout: float = 1.0
    ):
        self.port = get_active_ppk2_port(port)
        if not self.port:
            raise RuntimeError("No active PPK2 device found.")
        self.mode = mode
        self.voltage_mv = voltage_mv
        self.dut_power = dut_power
        self.use_mp = use_mp
        self.timeout = timeout
        self._ppk = None
        self._measuring = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self):
        """Open serial port and initialize PPK2 configuration."""
        print(f"Connecting to PPK2 on '{self.port}'...")
        cls = PPK2_MP if self.use_mp else PPK2_API
        self._ppk = cls(self.port, timeout=self.timeout)

        # Initialize connection and drain leftover buffer
        init_ppk2_connection(self._ppk)

        # Configure mode & voltage
        if self.mode == "source":
            self._ppk.use_source_meter()
            time.sleep(0.05)
            self._ppk.set_source_voltage(self.voltage_mv)
            time.sleep(0.1)
            if self.dut_power:
                self._ppk.toggle_DUT_power("ON")
                time.sleep(0.2)
        else:
            self._ppk.use_ampere_meter()
            self._ppk.set_source_voltage(self.voltage_mv)

    def sample(
        self,
        duration_s: float = 10.0,
        wait_before_s: float = 0.0,
        target_sps: Optional[int] = None,
        live_stream: bool = True
    ) -> MeasurementResult:
        """
        Record continuous samples for duration_s seconds with live second-by-second updates.
        Supports software downsampling via target_sps.
        """
        if not self._ppk:
            raise RuntimeError("PPK2 is not connected.")

        start_dt = datetime.now()
        start_time_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")

        if wait_before_s > 0:
            print(f"Start Time:   {start_time_str}")
            print(f"Warm-up wait: {wait_before_s:.1f}s before sampling (DUT powered at {self.voltage_mv} mV)...")
            t_wait_start = time.time()
            while (time.time() - t_wait_start) < wait_before_s:
                w_elapsed = time.time() - t_wait_start
                w_rem = max(0.0, wait_before_s - w_elapsed)
                sys.stdout.write(f"\r\033[2K  Warm-up: {_format_time(w_elapsed)} / {_format_time(wait_before_s)} (Remaining: {_format_time(w_rem)})...")
                sys.stdout.flush()
                time.sleep(0.1)
            sys.stdout.write("\r\033[2K")
            sys.stdout.flush()
        else:
            print(f"Start Time:   {start_time_str}")

        rate_info = f"at target {target_sps:,} SPS" if target_sps else "at native ~100 kSPS"
        print(f"Sampling for {_format_time(duration_s, show_ms=False)} ({rate_info})...\n")

        if live_stream:
            print("=" * 72)
            print(f"  LIVE MEASUREMENTS ({self.voltage_mv/1000:.1f}V) - {start_time_str}")
            print("=" * 72)

        self._ppk.start_measuring()
        self._measuring = True

        samples: List[float] = []
        raw_digital: List[int] = []
        start_time = time.time()
        
        last_reported_sec = 0
        last_sec_sample_idx = 0
        last_ui_update = 0.0
        live_ma = 0.0

        try:
            while (time.time() - start_time) < duration_s:
                data = self._ppk.get_data()
                if data:
                    raw, bits = self._ppk.get_samples(data)
                    if raw:
                        samples.extend(raw)
                        live_ma = raw[-1] / 1000.0
                    if bits:
                        raw_digital.extend(bits)

                now = time.time()
                cur_elapsed = now - start_time
                cur_sec = int(cur_elapsed)

                # Output completed second summary when clock passes a full second
                if live_stream and cur_sec > last_reported_sec and len(samples) > 0:
                    for s_num in range(last_reported_sec + 1, cur_sec + 1):
                        s_idx_end = int(len(samples) * (s_num / cur_elapsed)) if cur_elapsed > 0 else len(samples)
                        s_idx_end = min(len(samples), max(last_sec_sample_idx + 1, s_idx_end))
                        sec_slice = samples[last_sec_sample_idx:s_idx_end]
                        if len(sec_slice) > 0:
                            s_mean_ua = float(np.mean(sec_slice))
                            s_mean_ma = s_mean_ua / 1000.0
                            s_power_mw = s_mean_ma * (self.voltage_mv / 1000.0)
                            # Wipe line clean and print permanent second milestone
                            sys.stdout.write(
                                f"\r\033[2K  [Second {s_num:3d} | t={s_num-1:3d}.0s-{s_num:3d}.0s]  "
                                f"{s_mean_ua:10.2f} µA  ({s_mean_ma:8.3f} mA)  |  {s_power_mw:8.3f} mW\n"
                            )
                            sys.stdout.flush()
                            last_sec_sample_idx = s_idx_end
                    last_reported_sec = cur_sec

                # Live in-place status line between second marks
                if now - last_ui_update >= 0.08:
                    cur_mean_ma = (sum(samples) / len(samples) / 1000.0) if samples else 0.0
                    cur_power_mw = cur_mean_ma * (self.voltage_mv / 1000.0)
                    pct = min(1.0, cur_elapsed / duration_s) if duration_s > 0 else 1.0
                    t_cur_str = _format_time(cur_elapsed)
                    t_tot_str = _format_time(duration_s)
                    
                    sys.stdout.write(
                        f"\r\033[2K  -> [{t_cur_str} / {t_tot_str} ({pct*100:4.1f}%)] "
                        f"Live: {live_ma:7.3f} mA | Avg: {cur_mean_ma:7.3f} mA | {cur_power_mw:7.3f} mW"
                    )
                    sys.stdout.flush()
                    last_ui_update = now

                time.sleep(0.005)

        except KeyboardInterrupt:
            # Wipe ticker cleanly before printing Ctrl+C notice
            sys.stdout.write("\r\033[2K")
            sys.stdout.flush()
            print("  [!] Measurement stopped early by user (Ctrl+C). Finalizing collected samples...")

        elapsed = time.time() - start_time
        self.stop_measuring()

        # Clear active status line
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()

        raw_samples_ua = np.array(samples, dtype=np.float64)
        native_sps = len(raw_samples_ua) / elapsed if elapsed > 0 else 0.0

        # Apply downsampling if target_sps requested
        if target_sps and target_sps < native_sps:
            current_ua = downsample_array(raw_samples_ua, target_sps, native_sps)
            effective_sps = float(target_sps)
        else:
            current_ua = raw_samples_ua
            effective_sps = native_sps

        current_ma = current_ua / 1000.0
        t = np.linspace(0, elapsed, len(current_ua), endpoint=False)

        channels = None
        if raw_digital and hasattr(self._ppk, "digital_channels"):
            try:
                channels = self._ppk.digital_channels(raw_digital)
            except Exception:
                pass

        mean_ua = float(np.mean(raw_samples_ua)) if len(raw_samples_ua) > 0 else 0.0
        min_ua = float(np.min(raw_samples_ua)) if len(raw_samples_ua) > 0 else 0.0
        max_ua = float(np.max(raw_samples_ua)) if len(raw_samples_ua) > 0 else 0.0
        std_ua = float(np.std(raw_samples_ua)) if len(raw_samples_ua) > 0 else 0.0
        avg_power_mw = (mean_ua / 1000.0) * (self.voltage_mv / 1000.0)

        return MeasurementResult(
            timestamps_s=t,
            current_ua=current_ua,
            current_ma=current_ma,
            voltage_mv=self.voltage_mv,
            duration_s=elapsed,
            sample_rate_sps=effective_sps,
            mean_ua=mean_ua,
            min_ua=min_ua,
            max_ua=max_ua,
            std_ua=std_ua,
            avg_power_mw=avg_power_mw,
            start_time=start_time_str,
            digital_channels=channels
        )

    def stop_measuring(self):
        """Stop sampling and safely turn off DUT power."""
        if self._measuring and self._ppk:
            try:
                self._ppk.stop_measuring()
            except Exception:
                pass
            self._measuring = False

        if self.mode == "source" and self.dut_power and self._ppk:
            try:
                self._ppk.toggle_DUT_power("OFF")
            except Exception:
                pass

    def close(self):
        """Cleanly close PPK2 session and ensure power is off."""
        self.stop_measuring()
        if self._ppk and hasattr(self._ppk, "ser") and self._ppk.ser and self._ppk.ser.is_open:
            try:
                self._ppk.ser.close()
            except Exception:
                pass
        self._ppk = None


def generate_mock_measurement(
    voltage_mv: int = 5000,
    duration_s: float = 10.0,
    wait_before_s: float = 0.0,
    target_sps: Optional[int] = None
) -> MeasurementResult:
    """Generate synthetic PPK2 measurement data for testing without hardware."""
    start_dt = datetime.now()
    start_time_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")

    if wait_before_s > 0:
        print(f"Start Time:   {start_time_str}")
        print(f"Waiting {wait_before_s:.1f}s before sampling (mock mode)...")
        time.sleep(min(1.0, wait_before_s))
    else:
        print(f"Start Time:   {start_time_str}")

    effective_sps = float(target_sps) if target_sps and target_sps < 100_000 else 100_000.0
    num_samples = int(duration_s * effective_sps)
    print(f"\n--- Running Mock Simulation ({duration_s:.1f}s @ {voltage_mv}mV, {effective_sps:,.0f} SPS) ---")
    time.sleep(0.3)

    t = np.linspace(0, duration_s, num_samples, endpoint=False)
    base_ma = 18.5 + np.random.normal(0, 0.3, num_samples)
    pulses = (np.sin(2 * np.pi * 0.2 * t) > 0.8) * (35.0 + np.random.normal(0, 1.2, num_samples))
    startup = np.exp(-t * 2) * 40.0
    current_ma = base_ma + pulses + startup
    current_ua = current_ma * 1000.0

    mean_ua = float(np.mean(current_ua))
    min_ua = float(np.min(current_ua))
    max_ua = float(np.max(current_ua))
    std_ua = float(np.std(current_ua))
    avg_power_mw = (mean_ua / 1000.0) * (voltage_mv / 1000.0)

    return MeasurementResult(
        timestamps_s=t,
        current_ua=current_ua,
        current_ma=current_ma,
        voltage_mv=voltage_mv,
        duration_s=duration_s,
        sample_rate_sps=effective_sps,
        mean_ua=mean_ua,
        min_ua=min_ua,
        max_ua=max_ua,
        std_ua=std_ua,
        avg_power_mw=avg_power_mw,
        start_time=start_time_str
    )


def measure(
    port: Optional[str] = None,
    mode: str = "source",
    voltage_mv: int = 5000,
    duration_s: float = 10.0,
    wait_before_s: float = 0.0,
    target_sps: Optional[int] = None,
    live_stream: bool = True,
    use_mp: bool = False,
    dut_power: bool = True,
    mock: bool = False
) -> MeasurementResult:
    """High-level function to measure power profile."""
    if mock:
        return generate_mock_measurement(
            voltage_mv=voltage_mv,
            duration_s=duration_s,
            wait_before_s=wait_before_s,
            target_sps=target_sps
        )

    with PPK2Session(
        port=port,
        mode=mode,
        voltage_mv=voltage_mv,
        dut_power=dut_power,
        use_mp=use_mp
    ) as session:
        return session.sample(
            duration_s=duration_s,
            wait_before_s=wait_before_s,
            target_sps=target_sps,
            live_stream=live_stream
        )
