"""
Core measurement session and acquisition engine for PPK2.
"""

import sys
import time
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


def _format_progress_bar(elapsed: float, total: float, rate_sps: float, current_ma: float, bar_len: int = 24) -> str:
    """Format a single-line live terminal progress bar."""
    pct = min(1.0, max(0.0, elapsed / total)) if total > 0 else 1.0
    filled = int(bar_len * pct)
    bar = "=" * filled + (">" if filled < bar_len else "") + " " * (bar_len - filled - (1 if filled < bar_len else 0))
    return f"\r  [{bar}] {elapsed:5.1f}s / {total:5.1f}s ({pct*100:4.1f}%) | {rate_sps/1000:5.1f} kSps | Live: {current_ma:7.3f} mA"


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

    def sample(self, duration_s: float = 10.0, wait_before_s: float = 0.0) -> MeasurementResult:
        """
        Record continuous samples for duration_s seconds at ~100 kSps with live progress.
        Gracefully handles Ctrl+C (KeyboardInterrupt).
        """
        if not self._ppk:
            raise RuntimeError("PPK2 is not connected.")

        if wait_before_s > 0:
            print(f"Warm-up wait: {wait_before_s:.1f}s before sampling (DUT powered at {self.voltage_mv} mV)...")
            t_wait_start = time.time()
            while (time.time() - t_wait_start) < wait_before_s:
                w_elapsed = time.time() - t_wait_start
                w_rem = max(0.0, wait_before_s - w_elapsed)
                sys.stdout.write(f"\r  Warm-up: {w_elapsed:4.1f}s / {wait_before_s:4.1f}s (Remaining: {w_rem:4.1f}s)...")
                sys.stdout.flush()
                time.sleep(0.1)
            sys.stdout.write("\r" + " " * 65 + "\r")
            sys.stdout.flush()

        print(f"Sampling for {duration_s:.1f} seconds (~{int(duration_s * 100_000):,} samples expected)...")
        self._ppk.start_measuring()
        self._measuring = True

        samples: List[float] = []
        raw_digital: List[int] = []
        start_time = time.time()
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
                if now - last_ui_update >= 0.1:
                    cur_elapsed = now - start_time
                    rate = len(samples) / cur_elapsed if cur_elapsed > 0 else 0.0
                    sys.stdout.write(_format_progress_bar(cur_elapsed, duration_s, rate, live_ma))
                    sys.stdout.flush()
                    last_ui_update = now

                time.sleep(0.005)

        except KeyboardInterrupt:
            print("\n  [!] Measurement interrupted by user (Ctrl+C). Processing captured samples...")

        elapsed = time.time() - start_time
        self.stop_measuring()

        # Clear progress line
        sys.stdout.write("\r" + " " * 75 + "\r")
        sys.stdout.flush()

        current_ua = np.array(samples, dtype=np.float64)
        current_ma = current_ua / 1000.0
        t = np.linspace(0, elapsed, len(current_ua), endpoint=False)

        channels = None
        if raw_digital and hasattr(self._ppk, "digital_channels"):
            try:
                channels = self._ppk.digital_channels(raw_digital)
            except Exception:
                pass

        sps = len(current_ua) / elapsed if elapsed > 0 else 0.0
        mean_ua = float(np.mean(current_ua)) if len(current_ua) > 0 else 0.0
        min_ua = float(np.min(current_ua)) if len(current_ua) > 0 else 0.0
        max_ua = float(np.max(current_ua)) if len(current_ua) > 0 else 0.0
        std_ua = float(np.std(current_ua)) if len(current_ua) > 0 else 0.0
        avg_power_mw = (mean_ua / 1000.0) * (self.voltage_mv / 1000.0)

        return MeasurementResult(
            timestamps_s=t,
            current_ua=current_ua,
            current_ma=current_ma,
            voltage_mv=self.voltage_mv,
            duration_s=elapsed,
            sample_rate_sps=sps,
            mean_ua=mean_ua,
            min_ua=min_ua,
            max_ua=max_ua,
            std_ua=std_ua,
            avg_power_mw=avg_power_mw,
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
    wait_before_s: float = 0.0
) -> MeasurementResult:
    """Generate synthetic PPK2 measurement data for testing without hardware."""
    if wait_before_s > 0:
        print(f"Waiting {wait_before_s:.1f}s before sampling (mock mode)...")
        time.sleep(min(1.0, wait_before_s))

    print(f"\n--- Running Mock Simulation ({duration_s:.1f}s @ {voltage_mv}mV) ---")
    time.sleep(0.3)
    num_samples = int(duration_s * 100_000)
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
        sample_rate_sps=100_000.0,
        mean_ua=mean_ua,
        min_ua=min_ua,
        max_ua=max_ua,
        std_ua=std_ua,
        avg_power_mw=avg_power_mw
    )


def measure(
    port: Optional[str] = None,
    mode: str = "source",
    voltage_mv: int = 5000,
    duration_s: float = 10.0,
    wait_before_s: float = 0.0,
    use_mp: bool = False,
    dut_power: bool = True,
    mock: bool = False
) -> MeasurementResult:
    """High-level function to measure power profile."""
    if mock:
        return generate_mock_measurement(
            voltage_mv=voltage_mv,
            duration_s=duration_s,
            wait_before_s=wait_before_s
        )

    with PPK2Session(
        port=port,
        mode=mode,
        voltage_mv=voltage_mv,
        dut_power=dut_power,
        use_mp=use_mp
    ) as session:
        return session.sample(duration_s=duration_s, wait_before_s=wait_before_s)
