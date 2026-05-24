#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from patch_player_physics_prod import HEAVY_CHEAT_MASS_PREFIX, HEAVY_CHEAT_MULT_PATCHES


BACKUP_SUFFIX = ".orig_prod3_duckstation_mass"
DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
STEERING_RATIO_USE_OFF = 0x9DD3C
DUCK_SAFE_STEERING_RATIO = bytes.fromhex("00 00 00 00")
KNOWN_STEERING_RATIO = [
    DUCK_SAFE_STEERING_RATIO,
    bytes.fromhex("00 10 42 24"),
    bytes.fromhex("00 18 42 24"),
    bytes.fromhex("00 28 42 24"),
    bytes.fromhex("00 40 42 24"),
]


def find_default_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Tune PROD3 DuckStation player collision mass.")
    parser.add_argument("--exe", type=Path, help="Path to PROD3 NFS4.EXE")
    parser.add_argument(
        "--heavy-mult",
        choices=sorted(str(x) for x in HEAVY_CHEAT_MULT_PATCHES),
        default="1.5",
        help="DuckStation collision mass multiplier",
    )
    parser.add_argument("--apply", action="store_true", help="Write patched EXE")
    args = parser.parse_args()

    path = args.exe or find_default_exe()
    data = bytearray(path.read_bytes())
    original = bytes(data)

    ratio = bytes(data[STEERING_RATIO_USE_OFF : STEERING_RATIO_USE_OFF + 4])
    if ratio not in KNOWN_STEERING_RATIO:
        raise SystemExit(f"unexpected steering ratio bytes: {ratio.hex(' ')}")
    if ratio != DUCK_SAFE_STEERING_RATIO:
        print(f"steering ratio: {ratio.hex(' ')} -> {DUCK_SAFE_STEERING_RATIO.hex(' ')}")
        data[STEERING_RATIO_USE_OFF : STEERING_RATIO_USE_OFF + 4] = DUCK_SAFE_STEERING_RATIO
    else:
        print("steering ratio: already DuckStation-safe")

    prefix_off = bytes(data).find(HEAVY_CHEAT_MASS_PREFIX)
    if prefix_off < 0:
        raise SystemExit("heavy mass prefix not found")
    mult_off = prefix_off + len(HEAVY_CHEAT_MASS_PREFIX)
    heavy_mult = "1.5" if args.heavy_mult == "1.5" else int(args.heavy_mult)
    new_mult = HEAVY_CHEAT_MULT_PATCHES[heavy_mult]
    old_mult = bytes(data[mult_off : mult_off + len(new_mult)])
    if old_mult not in HEAVY_CHEAT_MULT_PATCHES.values():
        raise SystemExit(f"unexpected heavy multiplier bytes: {old_mult.hex(' ')}")
    if old_mult != new_mult:
        print(f"heavy mass multiplier: {old_mult.hex(' ')} -> {new_mult.hex(' ')}")
        data[mult_off : mult_off + len(new_mult)] = new_mult
    else:
        print(f"heavy mass multiplier: already x{args.heavy_mult}")

    if args.apply and bytes(data) != original:
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        path.write_bytes(data)
        print(f"done: patched {path}")
    elif not args.apply:
        print("dry run only; pass --apply to write changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
