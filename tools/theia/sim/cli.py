#!/usr/bin/env python3
"""
Standalone CLI for the host-side tiny_vm simulator.

Run a compiled bytecode image, with mocked host services, and emit whatever
the program wrote via print_u32 / print_hex32 to stdout.

Usage:
    tools/theia/sim/cli.py <bin>
    tools/theia/sim/cli.py <bin> --trace
    tools/theia/sim/cli.py <bin> --halt-banner   # emit 'tiny_vm: halt' after HALT
"""

from __future__ import annotations

import argparse
import pathlib
import sys


def _ensure_package_on_path() -> None:
    here = pathlib.Path(__file__).resolve().parent
    # The package is `tools/theia/sim`; we need `tools/theia` on sys.path
    # so that `from sim import ...` works whether invoked directly or via -m.
    sys.path.insert(0, str(here.parent))


_ensure_package_on_path()

from sim.host_calls import DefaultHostCalls, HostLog  # noqa: E402
from sim.tiny_vm_sim import (  # noqa: E402
    TinyVmSim,
    TINY_VM_HALT,
    TINY_VM_STEP_LIMIT,
    status_name,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a tiny_vm .bin in the host-side simulator")
    parser.add_argument("bin", type=pathlib.Path, help="compiled .bin to execute")
    parser.add_argument(
        "--trace",
        action="store_true",
        help="print one trace line per executed opcode to stderr",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=None,
        help="max steps to execute (default: 10M safety cap)",
    )
    parser.add_argument(
        "--halt-banner",
        action="store_true",
        help="emit 'tiny_vm: halt' after a clean HALT to mirror firmware",
    )
    args = parser.parse_args(argv)

    code = args.bin.read_bytes()
    log = HostLog()
    vm = TinyVmSim(code, host=DefaultHostCalls(log))

    if args.trace:
        def trace(result):
            print(
                f"pc={result.pc_before:04x} op={result.op:02x} status={status_name(result.status)} "
                f"sp={vm.sp} top={vm.stack[-1] if vm.stack else '-'}",
                file=sys.stderr,
            )
        vm.add_trace_listener(trace)

    status = vm.run(step_budget=args.budget)
    sys.stdout.write(log.stdout_text)
    if status == TINY_VM_HALT and args.halt_banner:
        sys.stdout.write("tiny_vm: halt\n")
    sys.stdout.flush()
    if status == TINY_VM_HALT:
        return 0
    if status == TINY_VM_STEP_LIMIT:
        print(f"sim: step budget exhausted ({status_name(status)})", file=sys.stderr)
        return 2
    print(f"sim: terminated with {status_name(status)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
