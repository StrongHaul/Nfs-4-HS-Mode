#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
PATCH_OFF = 0x458B0
EXPECTED = b"\x00\x00\x00\x00"


def find_exe() -> Path:
    matches = sorted(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(matches) != 1:
        raise SystemExit(f"expected one PROD3 NFS4.EXE, found {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", nargs="?", type=Path)
    args = parser.parse_args()
    exe = args.exe or find_exe()
    data = bytearray(exe.read_bytes())

    if bytes(data[PATCH_OFF:PATCH_OFF + 4]) != EXPECTED:
        raise SystemExit("right-channel clear delay slot is not empty")

    # sh zero,0x8ba(s5). This delay slot executes before either side branch:
    # the right branch immediately enables 0x8ba again, while the left branch
    # leaves it cleared for the intended alternating pause.
    data[PATCH_OFF:PATCH_OFF + 4] = struct.pack("<I", 0xA6A008BA)
    exe.write_bytes(data)
    print(f"patched: {exe}")
    print(f"md5: {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
