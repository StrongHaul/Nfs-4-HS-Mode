#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


BACKUP_SUFFIX = ".orig_duckstation_physics_compat_prod2"
DEFAULT_EXE_GLOB = "PROD 2*/NFS4.EXE"

# DuckStation is sensitive to this steering-ratio delay-slot tweak:
# stock:    00 00 00 00  nop
# ePSXe ok: 00 40 42 24  addiu v0,v0,0x4000
# In DuckStation the patched version makes the car crawl and slide as if grip
# collapsed, so keep this one stock while preserving the other physics patches.
STEERING_RATIO_USE_OFF = 0x9DD3C
STOCK_NOP = bytes.fromhex("00 00 00 00")
PATCHED_ADD = bytes.fromhex("00 40 42 24")


def find_default_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="DuckStation compatibility fix for PROD2 player physics.")
    parser.add_argument("--exe", type=Path, help="Path to PROD2 NFS4.EXE")
    parser.add_argument("--apply", action="store_true", help="Write patched EXE")
    parser.add_argument("--revert", action="store_true", help="Restore ePSXe steering-ratio tweak")
    args = parser.parse_args()

    path = args.exe or find_default_exe()
    data = bytearray(path.read_bytes())
    new = PATCHED_ADD if args.revert else STOCK_NOP
    old = STOCK_NOP if args.revert else PATCHED_ADD
    actual = bytes(data[STEERING_RATIO_USE_OFF : STEERING_RATIO_USE_OFF + 4])

    if actual == new:
        print(f"steering ratio DuckStation fix: already {'reverted' if args.revert else 'patched'}")
        return 0
    if actual != old:
        raise SystemExit(
            f"unexpected bytes at 0x{STEERING_RATIO_USE_OFF:X}: {actual.hex(' ')}; "
            f"expected {old.hex(' ')}"
        )
    print(f"steering ratio DuckStation fix: {actual.hex(' ')} -> {new.hex(' ')}")
    if args.apply:
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(bytes(data))
        data[STEERING_RATIO_USE_OFF : STEERING_RATIO_USE_OFF + 4] = new
        path.write_bytes(data)
    else:
        print("dry run only; pass --apply to write changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
