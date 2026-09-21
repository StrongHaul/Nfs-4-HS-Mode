#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

BASE = 0x8000F800
HOOK_OFF = 0xE806C
HOOK_ADDR = BASE + HOOK_OFF
CAVE_OFF = 0xE80D8
CAVE_ADDR = BASE + CAVE_OFF
PHASE = 0x800F7874
PLAYER_HELPER = 0x800551B0

def i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)

def r(rs: int, rt: int, rd: int, sh: int, fn: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (sh << 6) | fn

def j(addr: int) -> int:
    return (0x02 << 26) | ((addr >> 2) & 0x03FFFFFF)

def pack(*values: int) -> bytes:
    return struct.pack("<" + "I" * len(values), *values)

def main() -> int:
    hits = sorted(Path(".").glob("PROD 3*/NFS4.EXE"))
    if len(hits) != 1:
        raise SystemExit(f"expected one PROD3 executable, found {len(hits)}")
    exe = hits[0]
    data = bytearray(exe.read_bytes())
    stock_hook = pack(j(PLAYER_HELPER), 0)
    patched_hook = pack(j(CAVE_ADDR), 0)
    if bytes(data[HOOK_OFF:HOOK_OFF + 8]) not in {stock_hook, patched_hook}:
        raise SystemExit("unexpected reverse-phase dispatch")

    cave = pack(
        i(0x23, 18, 8, 0x260),       # lw t0,0x260(s2)
        i(0x0C, 8, 8, 0x20),         # andi t0,t0,0x20
        i(0x04, 8, 0, 4),            # beq t0,zero,player helper
        i(0x0F, 0, 8, 0x8012),       # lui t0,0x8012
        i(0x23, 8, 9, 0xF368),       # lw t1,0x8011F368
        j(PHASE),
        r(0, 9, 9, 1, 0),            # sll t1,t1,1
        j(PLAYER_HELPER),
        0,
    )
    current = bytes(data[CAVE_OFF:CAVE_OFF + len(cave)])
    if current not in {bytes(len(cave)), cave}:
        raise SystemExit("reverse-phase cave is occupied")
    data[CAVE_OFF:CAVE_OFF + len(cave)] = cave
    data[HOOK_OFF:HOOK_OFF + 8] = patched_hook
    exe.write_bytes(data)
    print(hashlib.md5(data).hexdigest().upper())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
