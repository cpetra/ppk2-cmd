"""
Command-line interface for ppk2-cmd.
"""

import argparse
import sys
from .discovery import find_ppk2_candidate_ports, probe_port, print_wsl2_help
from .core import measure


def cmd_list(args):
    """Scan and list connected PPK2 devices."""
    print("Scanning for connected PPK2 devices...")
    candidates = find_ppk2_candidate_ports()
    if not candidates:
        print("No serial ports found.")
        print_wsl2_help()
        return

    found = 0
    for port in candidates:
        meta = probe_port(port)
        if meta is not None:
            found += 1
            print(f"  [ACTIVE PPK2] Port: {port}")
            cal = meta.get("Calibrated", "Unknown")
            hw = meta.get("HW", "Unknown")
            print(f"                Hardware: {hw} | Calibrated: {cal}")
        else:
            print(f"  [OTHER/DFU]   Port: {port}")

    if found == 0:
        print("\nNo active PPK2 communication ports responded.")
        print_wsl2_help()


def cmd_measure(args):
    """Perform a measurement session."""
    try:
        res = measure(
            port=args.port,
            mode=args.mode,
            voltage_mv=args.voltage,
            duration_s=args.duration,
            wait_before_s=args.wait,
            use_mp=args.mp,
            dut_power=not args.no_dut_power,
            mock=args.mock
        )
    except RuntimeError as e:
        print(f"Error: {e}")
        print_wsl2_help()
        sys.exit(1)

    if args.summary_only:
        res.print_summary()
    else:
        res.print_per_second()

    if args.csv:
        res.save_csv(args.csv)
    if args.npz:
        res.save_npz(args.npz)
    if args.json:
        res.save_json(args.json)
    if args.plot:
        res.plot(args.plot)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ppk2-cmd",
        description="Command-line tool and Python API for Nordic Power Profiler Kit II (PPK2)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Subcommand: list / scan
    parser_list = subparsers.add_parser("list", help="Scan and list connected PPK2 devices")
    parser_list.set_defaults(func=cmd_list)

    # Subcommand: measure (default)
    parser_measure = subparsers.add_parser("measure", help="Measure power consumption")
    _add_measure_args(parser_measure)
    parser_measure.set_defaults(func=cmd_measure)

    # Also add arguments directly to top-level parser for convenience (e.g. `ppk2-cmd --duration 10`)
    _add_measure_args(parser)
    parser.set_defaults(func=cmd_measure)

    return parser


def _add_measure_args(p: argparse.ArgumentParser):
    p.add_argument("-p", "--port", type=str, help="Serial port (e.g. /dev/ttyACM0, COM3)")
    p.add_argument("-v", "--voltage", type=int, default=5000,
                   help="Voltage in mV (800 to 5000 mV). Default: 5000 (5.0V)")
    p.add_argument("-d", "--duration", type=float, default=10.0,
                   help="Sampling duration in seconds. Default: 10.0")
    p.add_argument("-w", "--wait", type=float, default=0.0,
                   help="Wait/warm-up time before measurement in seconds. Default: 0.0")
    p.add_argument("-m", "--mode", choices=["source", "ampere"], default="source",
                   help="Operating mode: 'source' (power DUT) or 'ampere'. Default: source")
    p.add_argument("--no-dut-power", action="store_true",
                   help="Do not toggle DUT power on in source mode")
    p.add_argument("--summary-only", action="store_true",
                   help="Print only overall summary instead of per-second breakdown table")
    p.add_argument("--mp", action="store_true",
                   help="Use multi-threaded background reader")
    p.add_argument("--csv", type=str, metavar="FILE.csv",
                   help="Export all raw samples to a CSV file")
    p.add_argument("--npz", type=str, metavar="FILE.npz",
                   help="Export all raw samples to a compressed NumPy .npz file")
    p.add_argument("--json", type=str, metavar="FILE.json",
                   help="Export statistics summary and per-second metrics to JSON")
    p.add_argument("--plot", type=str, nargs="?", const="ppk2_plot.png", metavar="FILE.png",
                   help="Generate a waveform plot PNG (default: ppk2_plot.png)")
    p.add_argument("--mock", action="store_true",
                   help="Run mock simulation without physical hardware")


def main():
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        cmd_measure(args)


if __name__ == "__main__":
    main()
