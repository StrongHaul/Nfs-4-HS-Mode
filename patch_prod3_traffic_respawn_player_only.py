#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_traffic_respawn_player_only"

# AILife_RCPickSliceAndDirection() chooses the reference car for a traffic
# reincarnation. Cars_gLifeBasisCarList[0] is the player; later entries are AI
# racers/cops. The stock code first chooses a random entry, then can replace it
# while scanning all other life-basis cars. It also keeps active traffic alive
# while it is near any life-basis car. Restrict both paths to entry zero.
PATCHES = (
    (
        0x58720,
        bytes.fromhex("04 DB A5 8C"),  # lw a1,Cars_gNumLifeBasisCars(a1)
        bytes.fromhex("01 00 05 24"),  # addiu a1,zero,1
        "select player as the only life basis",
    ),
    (
        0x58820,
        bytes.fromhex("2A 10 83 02"),  # slt v0,s4,Cars_gNumCars
        bytes.fromhex("21 10 00 00"),  # addu v0,zero,zero; take existing loop exit
        "skip AI/cop life-basis replacement scan",
    ),
    (
        0x59708,
        bytes.fromhex("04 DB 42 8C"),  # lw v0,Cars_gNumLifeBasisCars(v0)
        bytes.fromhex("01 00 02 24"),  # addiu v0,zero,1
        "test active traffic life area against player only",
    ),
    (
        0x59758,
        bytes.fromhex("04 DB 42 8C"),  # lw v0,Cars_gNumLifeBasisCars(v0)
        bytes.fromhex("01 00 02 24"),  # addiu v0,zero,1
        "stop active traffic life-area scan after player",
    ),
)


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: make traffic reincarnation position player-relative."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    for off, stock, player_only, name in PATCHES:
        current = bytes(data[off : off + len(stock)])
        if current not in {stock, player_only}:
            raise SystemExit(f"{name}: unexpected bytes at 0x{off:X}: {current.hex(' ')}")
        data[off : off + len(stock)] = stock if args.revert else player_only

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not args.revert and not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print("reverted" if args.revert else "patched", exe)
    print("traffic reincarnation reference: player only")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
