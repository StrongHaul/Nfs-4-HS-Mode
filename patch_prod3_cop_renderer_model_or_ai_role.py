#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

BASE = 0x8000F800
GATE_OFF = 0xA114C
HOOK_OFF = 0xA1154
CAVE_OFF = 0x453DC
CAVE_ADDR = BASE + CAVE_OFF
RETURN_ADDR = 0x800B095C

def i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)

def j(addr: int) -> int:
    return (0x02 << 26) | ((addr >> 2) & 0x03FFFFFF)

def pack(*values: int) -> bytes:
    return struct.pack("<" + "I" * len(values), *values)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", nargs="?", type=Path)
    args = parser.parse_args()
    hits = sorted(Path(".").glob("PROD 3*/NFS4.EXE"))
    exe = args.exe or (hits[0] if len(hits) == 1 else None)
    if exe is None:
        raise SystemExit(f"expected one PROD3 executable, found {len(hits)}")
    data = bytearray(exe.read_bytes())
    patched_hook = pack(j(CAVE_ADDR), 0x30820008)
    old_unsafe_hook = pack(j(CAVE_ADDR), 0x96A408B4)
    gate = bytes(data[GATE_OFF:GATE_OFF + 8])
    if gate not in {pack(0x30560020, 0x96A408B4), old_unsafe_hook}:
        raise SystemExit("unexpected renderer role gate")
    hook = bytes(data[HOOK_OFF:HOOK_OFF + 8])
    if hook not in {pack(0, 0x30820008), patched_hook}:
        raise SystemExit("unexpected renderer post-gate hook")
    current_cave = bytes(data[CAVE_OFF:CAVE_OFF + 0x24])
    if current_cave != bytes(0x24) and gate != old_unsafe_hook:
        raise SystemExit("renderer gate cave is occupied")
    cave = pack(
        i(0x09, 23, 2, -0x16),
        i(0x0B, 2, 2, 6),
        (22 << 21) | (2 << 16) | (22 << 11) | 0x25,
        j(RETURN_ADDR),
        0,
    )
    data[CAVE_OFF:CAVE_OFF + 0x24] = bytes(0x24)
    data[CAVE_OFF:CAVE_OFF + len(cave)] = cave
    data[GATE_OFF:GATE_OFF + 8] = pack(0x30560020, 0x96A408B4)
    data[HOOK_OFF:HOOK_OFF + 8] = pack(j(CAVE_ADDR), 0x30820008)
    exe.write_bytes(data)
    print(hashlib.md5(data).hexdigest().upper())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
