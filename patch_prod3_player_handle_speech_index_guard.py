#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_handle_speech_index_guard"

# Existing cave from patch_prod3_player_bust_sr_pullover_hud_guard.py at
# runtime 0x800F7A44. The first instruction was:
#
#   sltiu t0,s1,2
#
# That accidentally allows only car indices 0/1 to reach the stock
# MobileSpeaker::Catch path. Arresting cops usually have indices >= 2, so
# police arrest speech gets skipped. Keep the safety guard, but allow the normal
# small Cars_gList range used by gameplay.
GUARD_OFF = 0xE8244
OLD_GUARD = 0x2E280002  # sltiu t0,s1,2
NEW_GUARD = 0x2E280008  # sltiu t0,s1,8


def find_exe() -> Path:
    hits = list(Path(".").glob(EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest().upper()


def read_u32(data: bytes | bytearray, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def write_u32(data: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", data, off, value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    current = read_u32(data, GUARD_OFF)
    if current not in {OLD_GUARD, NEW_GUARD}:
        raise SystemExit(f"unexpected speech guard word at 0x{GUARD_OFF:X}: 0x{current:08X}")

    write_u32(data, GUARD_OFF, OLD_GUARD if args.revert else NEW_GUARD)

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(bytes(data))}")
    print("HandleSpeech car-index guard:", "0..1" if args.revert else "0..7")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
