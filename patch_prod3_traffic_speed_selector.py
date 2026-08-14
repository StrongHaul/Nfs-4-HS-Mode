#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import shutil
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXE = next(ROOT.glob("PROD 3*/NFS4.EXE"))
DELTA = 0x8000F800
HOOK_OFF = 0x5FE68
RETURN_ADDR = 0x8006F670
CAVE_OFF = 0x4627C
CAVE_ADDR = CAVE_OFF + DELTA
SPEED_VALUE_ADDR = 0x8011F23C

def words(*values: int) -> bytes:
    return b"".join(struct.pack("<I", v & 0xFFFFFFFF) for v in values)

def branch(op: int, rs: int, rt: int, source: int, target: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (((target - source - 4) // 4) & 0xFFFF)

def jump(address: int) -> int:
    return 0x08000000 | ((address >> 2) & 0x03FFFFFF)

def i_type(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)

def r_type(rs: int, rt: int, rd: int, shamt: int, funct: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (shamt << 6) | funct

def main() -> None:
    data = bytearray(EXE.read_bytes())
    stock_addr = CAVE_ADDR + 0x34
    cave = words(
        i_type(0x0F, 0, 1, (SPEED_VALUE_ADDR + 0x8000) >> 16),
        i_type(0x23, 1, 1, SPEED_VALUE_ADDR),  # lw at,selector(at)
        0x00000000,
        branch(0x04, 1, 0, CAVE_ADDR + 0x0C, stock_addr),
        0x00000000,
        r_type(0, 2, 8, 31, 0x03),            # sra t0,v0,31
        r_type(1, 0, 2, 0, 0x21),             # addu v0,at,zero
        r_type(2, 8, 2, 0, 0x26),             # xor v0,v0,t0
        r_type(2, 8, 2, 0, 0x23),             # subu v0,v0,t0
        0xAE02055C,
        0xAE020560,
        jump(RETURN_ADDR),
        0x00000000,
        0xAE02055C,                            # stock path
        0xAE020560,
        jump(RETURN_ADDR),
        0x00000000,
    )
    legacy_cave = words(
        branch(0x01, 2, 0, CAVE_ADDR, CAVE_ADDR + 0x10),
        0x3C020030,
        jump(CAVE_ADDR + 0x14),
        0x00000000,
        0x00021023,
        0xAE02055C,
        0xAE020560,
        jump(RETURN_ADDR),
        0x00000000,
    )
    hook_stock = words(0xAE02055C, 0xAE020560)
    hook_patch = words(jump(CAVE_ADDR), 0x00000000)
    actual = bytes(data[HOOK_OFF:HOOK_OFF + 8])
    if actual not in (hook_stock, hook_patch):
        raise SystemExit(f"unexpected hook: {actual.hex(' ')}")
    cave_actual = bytes(data[CAVE_OFF:CAVE_OFF + len(cave)])
    legacy_padded = legacy_cave + bytes(len(cave) - len(legacy_cave))
    previous_dispatcher = bytes.fromhex("12 80 01 3C 3C F2 21 8C")
    if cave_actual not in (bytes(len(cave)), cave, legacy_padded) and not cave_actual.startswith(previous_dispatcher):
        raise SystemExit("dispatcher cave is occupied")
    backup = Path(str(EXE) + ".orig_before_prod3_traffic_speed_selector")
    if not backup.exists():
        shutil.copy2(EXE, backup)
    data[HOOK_OFF:HOOK_OFF + 8] = hook_patch
    data[CAVE_OFF:CAVE_OFF + len(cave)] = cave
    EXE.write_bytes(data)
    print(f"MD5: {hashlib.md5(data).hexdigest().upper()}")

if __name__ == "__main__":
    main()
