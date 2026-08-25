"""
Core measurement session and acquisition engine for PPK2.
"""

import time
from typing import Optional, List, Tuple
import numpy as np
from ppk2_api.ppk2_api import PPK2_API, PPK2_MP, PPK2_Command, PPK2_Modes

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


def set_power(
    port: Optional[str] = None,
    state: str = "on",
    voltage_mv: int = 5000
):
    """
    Control PPK2 power output independently without running a measurement.
    Leaves the power on or off on the hardware and closes the serial port.
    """
    active_port = get_active_ppk2_port(port)
    if not active_port:
        raise RuntimeError("No active PPK2 device found.")

    print(f"Connecting to PPK2 on '{active_port}'...")
    ppk = PPK2_API(active_port, timeout=1.0)
    try:
        init_ppk2_connection(ppk)
        if state.lower() == "on":
            print(f"Configuring Source Meter at {voltage_mv} mV ({voltage_mv/1000:.2f}V)...")
            ppk.use_source_meter()
            time.sleep(0.05)
            ppk.set_source_voltage(voltage_mv)
            time.sleep(0.1)
            print("Turning DUT power ON...")
            ppk.toggle_DUT_power("ON")
            time.sleep(0.1)
            print(f"DUT power is now ON at {voltage_mv} mV (persists after exit).")
        else:
            print("Turning DUT power OFF...")
            ppk.toggle_DUT_power("OFF")
            time.sleep(0.1)
            print("DUT power is now OFF.")
    finally:
        if ppk and hasattr(ppk, "ser") and ppk.ser and ppk.ser.is_open:
            ppk.ser.close()


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
        preserve_power: bool = False,
        leave_power_on: bool = False,
        use_mp: bool = False,
        timeout: float = 1.0
    ):
        self.port = get_active_ppk2_port(port)
        if not self.port:
            raise RuntimeError("No active PPK2 device found.")
        self.mode = mode
        self.voltage_mv = voltage_mv
        self.dut_power = dut_power
        self.preserve_power = preserve_power
        self.leave_power_on = leave_power_on
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
            # If power is already running and preserve_power is True, do not re-trigger power toggle
            if self.dut_power and not self.preserve_power:
                self._ppk.toggle_DUT_power("ON")
                time.sleep(0.2)
        else:
            self._ppk.use_ampere_meter()
            self._ppk.set_source_voltage(self.voltage_mv)

    def sample(self, duration_s: float = 10.0, wait_before_s: float = 0.0) -> MeasurementResult:
        """
        Record continuous samples for duration_s seconds at ~100 kSps.
        """
        if not self._ppk:
            raise RuntimeError("PPK2 is not connected.")

        if wait_before_s > 0:
            print(f"Waiting {wait_before_s:.1f}s before sampling...")
            time.sleep(wait_before_s)

        print(f"Sampling for {duration_s:.1f} seconds (~{int(duration_s * 100_000):,} samples)...")
        self._ppk.start_measuring()
        self._measuring = True

        samples: List[float] = []
        raw_digital: List[int] = []
        start_time = time.time()

        while (time.time() - start_time) < duration_s:
            data = self._ppk.get_data()
            if data:
                raw, bits = self._ppk.get_samples(data)
                if raw:
                    samples.extend(raw)
                if bits:
                    raw_digital.extend(bits)
            time.sleep(0.005)

        elapsed = time.time() - start_time
        self.stop_measuring()

        current_ua = np.array(samples, dtype=np.float64)
        current_ma = current_ua / 1000.0
        t = np.linspace(0, elapsed, len(current_ua), endpoint=False)

        channels = None
        if raw_digital and hasattr(self._ppk, "digital_channels"):
            try:
                channels = self._ppk.digital_channels(raw_digital)
            except Exception:
                pass

        sps = len(current_ua) / elapsed if elapsed > 0 else 0
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
        """Stop sampling and optionally turn off DUT power."""
        if self._measuring and self._ppk:
            try:
                self._ppk.stop_measuring()
            except Exception:
                pass
            self._measuring = False

        if self.mode == "source" and self.dut_power and not self.leave_power_on and self._ppk:
            try:
                self._ppk.toggle_DUT_power("OFF")
            except Exception:
                pass

    def close(self):
        """Cleanly close PPK2 session."""
        self.stop_measuring()
        if self._ppk and hasattr(self._ppk, "ser") and self._ppk.ser and self._ppk.ser.is_open:
            try:
                self._ppk.ser.close()
            except Exception:
                pass
        self._ppk = None


def generate_mock_measurement(
    voltage_mv: int = 5000,
    duration_s: float = 10.0
) -> MeasurementResult:
    """Generate synthetic PPK2 measurement data for testing without hardware."""
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
    preserve_power: bool = False,
    leave_power_on: bool = False,
    use_mp: bool = False,
    dut_power: bool = True,
    mock: bool = False
) -> MeasurementResult:
    """High-level function to measure power profile."""
    if mock:
        return generate_mock_measurement(voltage_mv=voltage_mv, duration_s=duration_s)

    with PPK2Session(
        port=port,
        mode=mode,
        voltage_mv=voltage_mv,
        dut_power=dut_power,
        preserve_power=preserve_power,
        leave_power_on=leave_power_on,
        use_mp=use_mp
    ) as session:
        return session.sample(duration_s=duration_s, wait_before_s=wait_before_s)
