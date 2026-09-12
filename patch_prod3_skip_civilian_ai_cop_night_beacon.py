#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import struct
from pathlib import Path


BASE = 0x8000F800
HOOK_OFF = 0x6EC94
CAVE_OFF = 0x45D20
CAVE_ADDR = BASE + CAVE_OFF
SKIP = 0x8007E508
CONTINUE = 0x8007E49C


def i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def j(addr: int) -> int:
    return (2 << 26) | ((addr >> 2) & 0x03FFFFFF)


def pack(*words: int) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def main() -> int:
    matches = sorted(Path(".").glob("PROD 3*/NFS4.EXE"))
    if len(matches) != 1:
        raise SystemExit(f"expected one PROD3 executable, found {len(matches)}")
    exe = matches[0]
    data = bytearray(exe.read_bytes())
    if hashlib.md5(data).hexdigest().upper() != "45C66058338BDB9F2F7A583C88CD2F8B":
        raise SystemExit("expected confirmed stable executable")
    if bytes(data[HOOK_OFF:HOOK_OFF + 8]) != pack(0x94C2087E, 0):
        raise SystemExit("unexpected night-beacon source hook")

    # The end of the steer-multiply cave is followed by unused aligned words.
    cave = pack(
        i(0x23, 6, 2, 0x260),        # lw v0,0x260(a2)
        i(0x0C, 2, 2, 0x20),         # andi v0,v0,0x20
        i(0x04, 2, 0, 6),            # beq v0,zero,continue
        0,
        i(0x25, 6, 2, 0x8BC),       # lhu v0,0x8bc(a2)
        i(0x09, 2, 2, -0x16),       # addiu v0,v0,-0x16
        i(0x0B, 2, 2, 6),           # sltiu v0,v0,6
        i(0x04, 2, 0, 4),           # beq v0,zero,skip
        0,
        i(0x25, 6, 2, 0x87E),       # continue: stock lhu v0,0x87e(a2)
        j(CONTINUE),
        0,
        j(SKIP),                    # skip civilian AI cop source
        0,
    )
    if any(data[CAVE_OFF:CAVE_OFF + len(cave)]):
        raise SystemExit("night-beacon cave is occupied")
    data[CAVE_OFF:CAVE_OFF + len(cave)] = cave
    data[HOOK_OFF:HOOK_OFF + 8] = pack(j(CAVE_ADDR), 0)
    exe.write_bytes(data)
    print(hashlib.md5(data).hexdigest().upper())


if __name__ == "__main__":
    raise SystemExit(main())
