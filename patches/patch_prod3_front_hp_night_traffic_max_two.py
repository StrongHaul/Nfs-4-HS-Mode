#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


FRONT_GLOB = "PROD 3*/FRONT.BIN"
BACKUP_SUFFIX = ".orig_before_prod3_front_hp_night_traffic_max_two"

# Front_InitTraffic:
#   if HP and night: maxTraffic = 1
# Change only that assignment to maxTraffic = 2. The normal FRONT traffic loop
# then appends the second traffic model and updates totalCars/model resources.
HP_NIGHT_MAX_TRAFFIC_OFF = 0x194BC
STOCK_HP_NIGHT_MAX_TRAFFIC = bytes.fromhex("01 00 06 24")  # addiu a2,zero,1
PATCHED_HP_NIGHT_MAX_TRAFFIC = bytes.fromhex("02 00 06 24")  # addiu a2,zero,2


def find_front() -> Path:
    hits = list(Path(".").glob(FRONT_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {FRONT_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: let FRONT create two traffic cars on HP night tracks."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    front = find_front()
    original = front.read_bytes()
    data = bytearray(original)

    current = bytes(data[HP_NIGHT_MAX_TRAFFIC_OFF : HP_NIGHT_MAX_TRAFFIC_OFF + 4])
    if current not in {STOCK_HP_NIGHT_MAX_TRAFFIC, PATCHED_HP_NIGHT_MAX_TRAFFIC}:
        raise SystemExit(
            f"unexpected bytes at 0x{HP_NIGHT_MAX_TRAFFIC_OFF:X}: {current.hex(' ')}"
        )

    data[HP_NIGHT_MAX_TRAFFIC_OFF : HP_NIGHT_MAX_TRAFFIC_OFF + 4] = (
        STOCK_HP_NIGHT_MAX_TRAFFIC if args.revert else PATCHED_HP_NIGHT_MAX_TRAFFIC
    )

    if bytes(data) != original:
        backup = front.with_name(front.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        front.write_bytes(data)

    print(("reverted" if args.revert else "patched"), front)
    print("HP night Front_InitTraffic maxTraffic = 2")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
