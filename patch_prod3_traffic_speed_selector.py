#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import shutil
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXE = next(ROOT.glob("PROD 3*/NFS4.EXE"))
DELTA = 0x8000F800

# The old implementation modified desiredSpeed/originalDesiredSpeed and made
# some traffic bodies slide. Its call site must remain stock.
OLD_HOOK_OFF = 0x5FE68
OLD_STOCK = (0xAE02055C, 0xAE020560)
OLD_PATCH = (0x0801569F, 0x00000000)

# Override only the final positive traffic speed. The original code applies
# travel direction immediately afterwards.
HOOK_OFF = 0x5FCE8
RETURN_ADDR = 0x8006F4EC
STOCK_HOOK = 0x8E220554
CAVE_OFF = 0x4627C
CAVE_ADDR = CAVE_OFF + DELTA
CAVE_LEN = 0x44
SPEED_VALUE_ADDR = 0x8011F23C


def i_type(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def r_type(rs: int, rt: int, rd: int, shamt: int, funct: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (shamt << 6) | funct


def jump(address: int) -> int:
    return 0x08000000 | ((address >> 2) & 0x03FFFFFF)


def words(*values: int) -> bytes:
    return struct.pack("<" + "I" * len(values), *values)


def build_cave() -> bytes:
    code = words(
        i_type(0x0F, 0, 2, (SPEED_VALUE_ADDR + 0x8000) >> 16),
        i_type(0x23, 2, 2, SPEED_VALUE_ADDR),
        0x00000000,
        i_type(0x04, 2, 0, 0x0002),
        0x00000000,
        r_type(2, 0, 16, 0, 0x21),
        STOCK_HOOK,
        jump(RETURN_ADDR),
        0x00000000,
    )
    return code.ljust(CAVE_LEN, b"\x00")


def main() -> None:
    data = bytearray(EXE.read_bytes())

    old_stock = words(*OLD_STOCK)
    old_patch = words(*OLD_PATCH)
    old_actual = bytes(data[OLD_HOOK_OFF : OLD_HOOK_OFF + 8])
    if old_actual not in (old_stock, old_patch):
        raise SystemExit(f"unexpected old traffic speed hook: {old_actual.hex(' ')}")
    data[OLD_HOOK_OFF : OLD_HOOK_OFF + 8] = old_stock

    hook = words(jump(CAVE_ADDR))
    actual_hook = bytes(data[HOOK_OFF : HOOK_OFF + 4])
    if actual_hook not in (words(STOCK_HOOK), hook):
        raise SystemExit(f"unexpected final speed hook: {actual_hook.hex(' ')}")

    cave = build_cave()
    actual_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if actual_cave not in (bytes(CAVE_LEN), cave):
        raise SystemExit("traffic speed selector cave is occupied")

    backup = Path(str(EXE) + ".orig_before_prod3_traffic_speed_selector_final_speed")
    if not backup.exists():
        shutil.copy2(EXE, backup)
    data[HOOK_OFF : HOOK_OFF + 4] = hook
    data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = cave
    EXE.write_bytes(data)
    print(f"Patched: {EXE}")
    print(f"MD5: {hashlib.md5(data).hexdigest().upper()}")


if __name__ == "__main__":
    main()
