#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


RUNTIME_BASE = 0x8000F800
DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"

SIDE_BRANCH_OFF = 0x458AC
SIDE_BRANCH_ADDR = RUNTIME_BASE + SIDE_BRANCH_OFF
EXPECTED_SIDE_BRANCH = bytes.fromhex("06 00 00 11 ba 08 a0 a6")

# Final three reserved words in the isolated phase cave.
CAVE_OFF = 0x45BD4
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x0C
LEFT_PATH_ADDR = 0x800550C8

REG = {"zero": 0, "t0": 8, "s5": 21}


def i(op: int, rs: str, rt: str, imm: int) -> int:
    return (op << 26) | (REG[rs] << 21) | (REG[rt] << 16) | (imm & 0xFFFF)


def j(addr: int) -> int:
    return (0x02 << 26) | ((addr >> 2) & 0x03FFFFFF)


def branch(op: int, rs: str, rt: str, pc: int, target: int) -> int:
    return i(op, rs, rt, (target - (pc + 4)) >> 2)


def words(*values: int) -> bytes:
    return struct.pack("<" + "I" * len(values), *values)


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

    if bytes(data[SIDE_BRANCH_OFF:SIDE_BRANCH_OFF + 8]) != EXPECTED_SIDE_BRANCH:
        raise SystemExit("unexpected side-selection branch; refusing to patch")
    if any(data[CAVE_OFF:CAVE_OFF + CAVE_LEN]):
        raise SystemExit("conditional right-channel clear cave is occupied")

    # Only the left-side branch enters the clear helper. The right side keeps
    # its low-nibble animation state and can complete the double pulse.
    data[SIDE_BRANCH_OFF:SIDE_BRANCH_OFF + 8] = words(
        branch(0x04, "t0", "zero", SIDE_BRANCH_ADDR, CAVE_ADDR),
        0,
    )
    data[CAVE_OFF:CAVE_OFF + CAVE_LEN] = words(
        i(0x29, "s5", "zero", 0x08BA),
        j(LEFT_PATH_ADDR),
        0,
    )
    exe.write_bytes(data)
    print(f"patched: {exe}")
    print(f"md5: {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
