#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROD3_EXE = next(ROOT.glob("PROD 3*/NFS4.EXE"))
BACKUP_SUFFIX = ".orig_before_prod3_ai_racer_difficulty"

LOAD_BASE_DELTA = 0x8000F800
CAVE_OFF = 0x45444
CAVE_ADDR = CAVE_OFF + LOAD_BASE_DELTA
FLAG_ADDR = 0x8011F228

SPEED_HOOK_OFF = 0x5EE5C
AGGRESSION_HOOK_OFFSETS = (0x54718, 0x5476C)


def word(value: int) -> bytes:
    return struct.pack("<I", value & 0xFFFFFFFF)


def jal(address: int) -> int:
    return 0x0C000000 | ((address >> 2) & 0x03FFFFFF)


def branch(op: int, rs: int, rt: int, source: int, target: int) -> int:
    displacement = (target - (source + 4)) // 4
    return (op << 26) | (rs << 21) | (rt << 16) | (displacement & 0xFFFF)


def build_cave() -> tuple[bytes, int, int]:
    speed_addr = CAVE_ADDR
    speed_words = [
        0x3C1A8012,
        0x975AF228,
        0x0000D812,
        branch(0x04, 26, 0, speed_addr + 0x0C, speed_addr + 0x38),
        0x00000000,
        0x24010001,
        branch(0x04, 26, 1, speed_addr + 0x18, speed_addr + 0x30),
        0x00000000,
        0x001BD043,
        0x037AD821,
        branch(0x04, 0, 0, speed_addr + 0x28, speed_addr + 0x38),
        0x00000000,
        0x001BD083,
        0x037AD821,
        0x03600013,
        0x03E00008,
        0x00000000,
    ]

    aggression_addr = speed_addr + len(speed_words) * 4
    # Keep the stock path/line mask for every difficulty. The old mode 2
    # cleared a0 here, which made racers pace the player on the same line.
    aggression_words = [
        0x00641824,
        0x03E00008,
        0x00000000,
        0x00000000,
        0x00000000,
        0x00000000,
        0x00000000,
        0x00000000,
        0x00000000,
    ]
    blob = b"".join(word(value) for value in speed_words + aggression_words)
    return blob, speed_addr, aggression_addr


def patch_exe(path: Path, apply: bool) -> None:
    data = bytearray(path.read_bytes())
    cave, speed_addr, aggression_addr = build_cave()
    patches = [
        (SPEED_HOOK_OFF, word(jal(speed_addr)), word(0x00000000), "opponent top-speed hook"),
        *[
            (
                offset,
                word(jal(aggression_addr)) + word(0x00621821),
                word(0x00621821) + word(0x00641824),
                f"opponent aggression hook 0x{offset:X}",
            )
            for offset in AGGRESSION_HOOK_OFFSETS
        ],
    ]

    cave_actual = bytes(data[CAVE_OFF : CAVE_OFF + len(cave)])
    if cave_actual not in (bytes(len(cave)), cave) and cave_actual[:12] != cave[:12]:
        raise SystemExit(f"code cave 0x{CAVE_OFF:X} is occupied: {cave_actual.hex(' ')}")

    for offset, patched, stock, name in patches:
        actual = bytes(data[offset : offset + len(patched)])
        if actual not in (stock, patched):
            raise SystemExit(
                f"{name}: unexpected bytes at 0x{offset:X}: {actual.hex(' ')}; "
                f"expected {stock.hex(' ')} or {patched.hex(' ')}"
            )

    if not apply:
        print(f"validated {path}")
        print(f"speed hook: 0x{speed_addr:08X}")
        print(f"aggression hook: 0x{aggression_addr:08X}")
        return

    backup = Path(str(path) + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(path, backup)

    data[CAVE_OFF : CAVE_OFF + len(cave)] = cave
    for offset, patched, _stock, _name in patches:
        data[offset : offset + len(patched)] = patched
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
