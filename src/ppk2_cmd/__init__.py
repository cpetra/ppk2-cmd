"""
ppk2-cmd: Command-line tool and Python library for Nordic Power Profiler Kit II (PPK2)
"""

from .core import PPK2Session, measure, set_power, generate_mock_measurement
from .analysis import MeasurementResult, SecondStats
from .discovery import find_ppk2_candidate_ports, probe_port, get_active_ppk2_port
from .plotting import generate_plot

__version__ = "0.1.0"
__all__ = [
    "PPK2Session",
    "measure",
    "set_power",
    "generate_mock_measurement",
    "MeasurementResult",
    "SecondStats",
    "find_ppk2_candidate_ports",
    "probe_port",
    "get_active_ppk2_port",
    "generate_plot",
]
