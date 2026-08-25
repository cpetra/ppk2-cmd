"""
Device discovery and port probing for Nordic Power Profiler Kit II.
"""

import glob
import os
import serial.tools.list_ports
from typing import Optional, List, Dict, Any
from ppk2_api.ppk2_api import PPK2_API


def find_ppk2_candidate_ports() -> List[str]:
    """Find all potential serial port candidates for PPK2."""
    candidates: List[str] = []

    # 1. Check pyserial / ppk2_api device listing
    try:
        devices = PPK2_API.list_devices()
        if devices:
            candidates.extend(devices)
    except Exception:
        pass

    # 2. Check /dev/ttyACM* and /dev/ttyUSB* on Linux / WSL2
    if os.name != "nt":
        for path in sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")):
            if path not in candidates:
                candidates.append(path)

    # 3. On Windows, check COM ports
    if os.name == "nt":
        for port in serial.tools.list_ports.comports():
            if port.device not in candidates:
                candidates.append(port.device)

    return candidates


def probe_port(port: str, timeout: float = 0.5) -> Optional[Dict[str, Any]]:
    """
    Probe a serial port to verify if it responds with valid PPK2 metadata.
    Returns metadata dict if valid PPK2 data port, or None.
    """
    try:
        ppk = PPK2_API(port, timeout=timeout)
        modifiers = ppk.get_modifiers()
        modifiers_copy = dict(ppk.modifiers) if hasattr(ppk, "modifiers") else {}
        ppk.ser.close()
        if modifiers:
            return modifiers_copy
    except Exception:
        pass
    return None


def get_active_ppk2_port(user_port: Optional[str] = None) -> Optional[str]:
    """
    Locate and return the active PPK2 communication port.
    If multiple ports exist (e.g. /dev/ttyACM0 and /dev/ttyACM1), probes each.
    """
    if user_port:
        return user_port

    candidates = find_ppk2_candidate_ports()
    if not candidates:
        return None

    if len(candidates) == 1:
        return candidates[0]

    # Probe candidates to find active PPK2 data port
    for candidate in sorted(candidates):
        if probe_port(candidate) is not None:
            return candidate

    # Fallback to first candidate
    return candidates[0]


def print_wsl2_help():
    """Display troubleshooting instructions for attaching PPK2 to WSL2."""
    print("=" * 70)
    print("  NO PPK2 DEVICE FOUND")
    print("=" * 70)
    print("If you are running in WSL2 and your PPK2 is plugged into Windows:")
    print()
    print("1. In Windows PowerShell (Run as Administrator):")
    print("     winget install --interactive --exact dorssel.usbipd-win   # (if not installed)")
    print("     usbipd list")
    print()
    print("2. Find the BUSID for 'Power Profiler Kit II' or 'nRF Connect USB CDC'")
    print("     usbipd bind --busid <BUSID>      # (only needed once)")
    print("     usbipd attach --wsl --busid <BUSID> --auto-attach")
    print()
    print("3. In WSL2, verify the serial port:")
    print("     ls -l /dev/ttyACM*")
    print("     sudo chmod 666 /dev/ttyACM0")
    print()
    print("Tip: Test without hardware using: ppk2-cmd --mock")
    print("=" * 70)
