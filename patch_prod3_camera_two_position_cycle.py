#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROD3_EXE = next(ROOT.glob("PROD 3*/NFS4.EXE"))
BACKUP_SUFFIX = ".orig_before_prod3_camera_two_position_cycle"

LOAD_BASE_DELTA = 0x8000F800
CAVE_OFF = 0x454AC
CAVE_ADDR = CAVE_OFF + LOAD_BASE_DELTA
HOOK_OFF = 0x76C20

STOCK_HOOK = struct.pack("<I", 0x94A20072)  # lhu v0,114(a1)


def word(value: int) -> bytes:
    return struct.pack("<I", value & 0xFFFFFFFF)


def jal(address: int) -> int:
    return 0x0C000000 | ((address >> 2) & 0x03FFFFFF)


def build_cave() -> bytes:
    # Player 0 alternates internal camera modes 2 and 6.
    # Mode 2 is the tuned near view; mode 6 is the stock far HeliCam.
    words = [
        0x3C1A8012,  # lui   k0,0x8012
        0x975AF20C,  # lhu   k0,-0xdf4(k0)
        0x94A20072,  # lhu   v0,114(a1)
        0x1340000F,  # beq   k0,zero,stock_return
        0x00000000,
        0x1620000D,  # bne   s1,zero,stock_return
        0x00000000,
        0x24420001,  # addiu v0,v0,1
        0xA4A20072,  # sh    v0,114(a1)
        0x30420001,  # andi  v0,v0,1
        0x00021080,  # sll   v0,v0,2
        0x24420002,  # addiu v0,v0,2 (mode 2 or mode 6)
        0xA4A20070,  # sh    v0,112(a1)
        0x08021923,  # j     0x8008648c
        0x00000000,
        0x00000000,
        0x00000000,
        0x00000000,
        0x00000000,
        0x03E00008,  # stock_return: jr ra
        0x00000000,
    ]
    return b"".join(word(value) for value in words)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=PROD3_EXE)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    data = bytearray(args.exe.read_bytes())
    cave = build_cave()
    patched_hook = word(jal(CAVE_ADDR))
    actual_hook = bytes(data[HOOK_OFF : HOOK_OFF + 4])
    if actual_hook not in (STOCK_HOOK, patched_hook):
        raise SystemExit(
            f"unexpected hook bytes at 0x{HOOK_OFF:X}: {actual_hook.hex(' ')}"
        )

    actual_cave = bytes(data[CAVE_OFF : CAVE_OFF + len(cave)])
    if actual_cave not in (bytes(len(cave)), cave) and actual_cave[:12] != cave[:12]:
        raise SystemExit(
            f"code cave 0x{CAVE_OFF:X} is occupied: {actual_cave.hex(' ')}"
        )

    if not args.apply:
        print(f"validated {args.exe}")
        print(f"hook 0x{HOOK_OFF:X} -> 0x{CAVE_ADDR:08X}")
        return 0

    backup = Path(str(args.exe) + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(args.exe, backup)

    data[CAVE_OFF : CAVE_OFF + len(cave)] = cave
    data[HOOK_OFF : HOOK_OFF + 4] = patched_hook
    args.exe.write_bytes(data)
    print(f"patched {args.exe}")
    print(f"MD5: {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
