#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROD3_EXE = next(ROOT.glob("PROD 3*/NFS4.EXE"))
BACKUP_SUFFIX = ".orig_before_prod3_ai_simplification_distance_toggle_v2"
LOAD_BASE_DELTA = 0x8000F800

MID_THRESHOLD_ADDR = 0x8011F230
FAR_THRESHOLD_ADDR = 0x8011F234
MID_THRESHOLD_OFF = MID_THRESHOLD_ADDR - LOAD_BASE_DELTA
FAR_THRESHOLD_OFF = FAR_THRESHOLD_ADDR - LOAD_BASE_DELTA

CAVE_OFF = 0x459D0
CAVE_ADDR = CAVE_OFF + LOAD_BASE_DELTA
FIRST_HOOK_OFF = 0x92688
SECOND_HOOK_OFF = 0x92764


def word(value: int) -> bytes:
    return struct.pack("<I", value & 0xFFFFFFFF)


def words(values: tuple[int, ...]) -> bytes:
    return b"".join(word(value) for value in values)


def jal(address: int) -> int:
    return 0x0C000000 | ((address >> 2) & 0x03FFFFFF)


def build_cave() -> bytes:
    # at=0: return far threshold in s1 and distance in v0.
    # at=1: return intermediate threshold in v0 and distance in v1.
    return words((
        0x3C1A8012,  # lui k0,0x8012
        0x14200005,  # bne at,zero,mid
        0x00000000,
        0x8F51F234,  # lw s1,-3532(k0)
        0x8E02008C,  # lw v0,140(s0)
        0x03E00008,
        0x00000000,
        0x8F42F230,  # mid: lw v0,-3536(k0)
        0x8E03008C,  # lw v1,140(s0)
        0x03E00008,
        0x00000000,
    ))


def patch_exe(path: Path, apply: bool) -> None:
    data = bytearray(path.read_bytes())
    cave = build_cave()
    first_stock = words((0x8E02008C, 0x3C110060))
    first_patch = words((jal(CAVE_ADDR), 0x24010000))
    second_stock = words((0x8E03008C, 0x3C020048))
    second_patch = words((jal(CAVE_ADDR), 0x24010001))

    checks = (
        (FIRST_HOOK_OFF, first_stock, first_patch, "far threshold hook"),
        (SECOND_HOOK_OFF, second_stock, second_patch, "intermediate threshold hook"),
    )
    for offset, stock, patched, name in checks:
        actual = bytes(data[offset : offset + len(patched)])
        if actual not in (stock, patched):
            raise SystemExit(f"{name}: unexpected bytes at 0x{offset:X}: {actual.hex(' ')}")

    actual_cave = bytes(data[CAVE_OFF : CAVE_OFF + len(cave)])
    if actual_cave not in (bytes(len(cave)), cave):
        raise SystemExit(f"code cave 0x{CAVE_OFF:X} is occupied: {actual_cave.hex(' ')}")

    defaults = ((MID_THRESHOLD_OFF, 0x00480000), (FAR_THRESHOLD_OFF, 0x00600000))
    for offset, value in defaults:
        actual = struct.unpack_from("<I", data, offset)[0]
        if actual not in (0, value):
            raise SystemExit(f"RAM default slot 0x{offset:X} is occupied: 0x{actual:08X}")

    if not apply:
        print(f"validated {path}")
        print(f"helper: 0x{CAVE_ADDR:08X}")
        return

    backup = Path(str(path) + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(path, backup)

    data[CAVE_OFF : CAVE_OFF + len(cave)] = cave
    for offset, _stock, patched, _name in checks:
        data[offset : offset + len(patched)] = patched
    for offset, value in defaults:
        struct.pack_into("<I", data, offset, value)

    path.write_bytes(data)
    print(f"patched {path}")
    print(f"MD5: {hashlib.md5(data).hexdigest().upper()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=PROD3_EXE)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    patch_exe(args.exe, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
