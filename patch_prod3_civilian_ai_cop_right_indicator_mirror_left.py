#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


RUNTIME_BASE = 0x8000F800
DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"

HOOK_OFF = 0x458B8
HOOK_ADDR = RUNTIME_BASE + HOOK_OFF
HOOK_LEN = 0x10
EXPECTED_HOOK = bytes.fromhex(
    "88 00 4a 35 ba 08 aa a6 04 00 00 10 00 00 00 00"
)

# Reserved zero tail of the isolated civilian-AI-cop phase cave.
CAVE_OFF = 0x45BC8
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x0C
RETURN_ADDR = 0x800550D4

REG = {"zero": 0, "t2": 10, "s5": 21, "s6": 22}


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

    if bytes(data[HOOK_OFF:HOOK_OFF + HOOK_LEN]) != EXPECTED_HOOK:
        raise SystemExit("unexpected right-indicator branch; refusing to patch")
    if any(data[CAVE_OFF:CAVE_OFF + CAVE_LEN]):
        raise SystemExit("reserved phase-cave tail is occupied")

    # s6 is zero for the player path and nonzero for an AI cop. Both paths
    # begin with the left-channel phase 0x80; only the player keeps the stock
    # right-channel offset 0x08.
    hook = words(
        branch(0x04, "s6", "zero", HOOK_ADDR, CAVE_ADDR),
        i(0x0D, "t2", "t2", 0x80),
        j(RETURN_ADDR),
        i(0x29, "s5", "t2", 0x08BA),
    )
    cave = words(
        i(0x0D, "t2", "t2", 0x08),
        j(RETURN_ADDR),
        i(0x29, "s5", "t2", 0x08BA),
    )
    data[HOOK_OFF:HOOK_OFF + HOOK_LEN] = hook
    data[CAVE_OFF:CAVE_OFF + CAVE_LEN] = cave
    exe.write_bytes(data)
    print(f"patched: {exe}")
    print(f"md5: {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
