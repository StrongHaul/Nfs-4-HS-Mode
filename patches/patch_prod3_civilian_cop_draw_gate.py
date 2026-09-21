#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

BASE = 0x8000F800
HOOK_OFF = 0x66D54
CAVE_OFF = 0x4533C
CAVE_ADDR = BASE + CAVE_OFF
ALLOW = 0x8007655C
FORCE_LIGHTS = 0x80076570
SKIP = 0x8007663C

def i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)

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
    patched_hook = pack(j(CAVE_ADDR), 0)
    if bytes(data[HOOK_OFF:HOOK_OFF + 8]) not in {pack(0x10400039, 0), patched_hook}:
        raise SystemExit("unexpected DrawC police-model gate")
    current_cave = bytes(data[CAVE_OFF:CAVE_OFF + 0x44])
    if current_cave != bytes(0x44) and bytes(data[HOOK_OFF:HOOK_OFF + 8]) != patched_hook:
        raise SystemExit("DrawC role gate cave is occupied")
    cave = pack(
        i(0x05, 2, 0, 12),
        i(0x23, 18, 8, 0x260),
        i(0x0C, 8, 8, 0x20),
        i(0x05, 8, 0, 7),
        i(0x0F, 0, 8, 0x8011),
        i(0x23, 8, 9, 0x0D0C),
        i(0x05, 18, 9, 8),
        i(0x0F, 0, 8, 0x8012),
        i(0x25, 8, 8, 0xF208),
        i(0x04, 8, 0, 5),
        0,
        j(FORCE_LIGHTS),
        0,
        j(ALLOW),
        0,
        j(SKIP),
        0,
    )
    data[CAVE_OFF:CAVE_OFF + 0x44] = bytes(0x44)
    data[CAVE_OFF:CAVE_OFF + len(cave)] = cave
    data[HOOK_OFF:HOOK_OFF + 8] = patched_hook
    exe.write_bytes(data)
    print(hashlib.md5(data).hexdigest().upper())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
