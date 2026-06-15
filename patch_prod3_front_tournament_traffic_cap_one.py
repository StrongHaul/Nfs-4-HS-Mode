#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


FRONT_GLOB = "PROD 3*/FRONT.BIN"
BACKUP_SUFFIX = ".orig_before_prod3_front_tournament_traffic_cap_one"

# Front_InitTourneyTraffic loop limit:
#   stock:   addiu s5,zero,3
#   patched: addiu s5,zero,1
#
# This keeps ordinary Tournament traffic present, but avoids overfilling the
# HP Tournament composition when cops are added later.
LIMIT_OFF = 0x18548
STOCK_LIMIT = bytes.fromhex("03 00 15 24")
PATCHED_LIMIT = bytes.fromhex("01 00 15 24")


def find_front() -> Path:
    hits = list(Path(".").glob(FRONT_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {FRONT_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: cap frontend Tournament traffic to one car."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    front = find_front()
    original = front.read_bytes()
    data = bytearray(original)

    current = bytes(data[LIMIT_OFF : LIMIT_OFF + 4])
    if current not in {STOCK_LIMIT, PATCHED_LIMIT}:
        raise SystemExit(f"unexpected bytes at 0x{LIMIT_OFF:X}: {current.hex(' ')}")

    backup = front.with_name(front.name + BACKUP_SUFFIX)
    if args.revert:
        data[LIMIT_OFF : LIMIT_OFF + 4] = STOCK_LIMIT
    else:
        if not backup.exists():
            backup.write_bytes(original)
        data[LIMIT_OFF : LIMIT_OFF + 4] = PATCHED_LIMIT

    if bytes(data) != original:
        front.write_bytes(data)

    print(("reverted" if args.revert else "patched"), front)
    print("Tournament frontend traffic cap: 1")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
