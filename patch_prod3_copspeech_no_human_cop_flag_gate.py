#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_copspeech_no_human_cop_flag_gate"
RUNTIME_BASE = 0x8000F800

# AudioClc_SoundCars, PROD3 runtime 0x80076BE8:
#
#   andi  v0,v0,0x0200
#   bne   v0,zero,0x80076C20
#   addiu a0,v1,0x0D0C
#
# Stock only preloads cop-speech vehicle patches when a human player car has
# carFlags & 0x200. Our player-can-bust-AI implementation intentionally avoids
# setting that flag because stock SR/HP HUD code can cast the player AI object
# as a BTC human cop and hang. Keep the stock raceType/HudBustedOverlay/numPerps
# checks, but always enter this existing preload block after the raceType check.
HOOK_OFF = 0x673E8
STOCK_BRANCH = 0x1440000D  # bne v0,zero,0x80076C20
PATCH_JUMP = 0x0801DB08   # j   0x80076C20


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest().upper()


def read_u32(data: bytes | bytearray, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def write_u32(data: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", data, off, value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    data = bytearray(exe.read_bytes())
    original = bytes(data)

    current = read_u32(data, HOOK_OFF)
    known = {STOCK_BRANCH, PATCH_JUMP}
    if current not in known:
        raise SystemExit(
            f"unexpected word at 0x{HOOK_OFF:X} "
            f"(runtime 0x{RUNTIME_BASE + HOOK_OFF:08X}): 0x{current:08X}"
        )

    write_u32(data, HOOK_OFF, STOCK_BRANCH if args.revert else PATCH_JUMP)

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(exe)}")
    print(
        "cop-speech human-cop flag gate: {}".format(
            "stock" if args.revert else "bypassed"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
