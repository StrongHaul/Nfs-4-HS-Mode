#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import patch_prod3_player_supercop_siren_cheat as siren


BACKUP_SUFFIX = ".orig_prod3_player_supercop_siren_on_demand"

STOCK_SIREN_ON_CALL = bytes.fromhex(
    "60 02 45 8e"  # lw a1,0x260(s2)
    "a0 e8 01 0c"  # jal SirenOn
)

STOCK_UPDATE_SIREN_CALL = bytes.fromhex(
    "60 02 42 8e"  # lw v0,0x260(s2)
    "20 00 a6 8f"  # lw a2,0x20(sp)
)


def patch(exe: Path) -> None:
    data = bytearray(exe.read_bytes())

    # Keep the cave installed, but leave stock callsites active by default.
    data[siren.CAVE_OFF : siren.CAVE_OFF + siren.CAVE_LEN] = siren.build_cave()
    data[siren.SOUND_PLAYER_SIREN_ON_HOOK_OFF : siren.SOUND_PLAYER_SIREN_ON_HOOK_OFF + 8] = STOCK_SIREN_ON_CALL
    data[siren.SOUND_PLAYER_UPDATE_SIREN_HOOK_OFF : siren.SOUND_PLAYER_UPDATE_SIREN_HOOK_OFF + 8] = STOCK_UPDATE_SIREN_CALL

    # Revert failed volume experiments defensively.
    data[0x6ACC4 : 0x6ACC4 + 8] = siren.EXPECTED_UPDATE_SIREN_VOLUME_BYTES
    data[0x6AA40 : 0x6AA40 + 4] = siren.STOCK_SUPERCOP_START_VOLUME_BYTES
    data[0x6A9C4 : 0x6A9C4 + 8] = siren.EXPECTED_QUICK_SIREN_SAMPLE_BYTES

    backup = exe.with_name(exe.name + BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_bytes(exe.read_bytes())

    exe.write_bytes(data)
    print(f"patched: {exe}")
    print(f"md5: {hashlib.md5(data).hexdigest()}")
    print()
    print("No cheats / off = stock player siren code.")
    print()
    print("cheat ON, super-cop siren:")
    print("800765D0 5480")
    print("800765D2 0801")
    print("800765D4 0000")
    print("800765D6 0000")
    print("800765E4 5494")
    print("800765E6 0801")
    print("800765E8 0000")
    print("800765EA 0000")
    print("80055204 0001")
    print("80055258 0001")
    print()
    print("cheat OFF, restore stock:")
    print("800765D0 0260")
    print("800765D2 8E45")
    print("800765D4 E8A0")
    print("800765D6 0C01")
    print("800765E4 0260")
    print("800765E6 8E42")
    print("800765E8 0020")
    print("800765EA 8FA6")
    print("80055204 0000")
    print("80055258 0000")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=None)
    args = parser.parse_args()
    exe = args.exe or next(Path.cwd().glob(siren.DEFAULT_EXE_GLOB))
    patch(exe)


if __name__ == "__main__":
    main()
