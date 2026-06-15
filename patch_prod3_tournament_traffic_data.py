#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ROOT_GLOB = "PROD 3*/ZTOURN*.TRN"
BACKUP_SUFFIX = ".orig_before_prod3_tournament_traffic_data"
TOURN_RECORD_SIZE = 0x54
TRAFFIC_OFF = 4


def plausible_tournament_record(data: bytes, off: int) -> bool:
    if off + TOURN_RECORD_SIZE > len(data):
        return False
    rec = data[off : off + TOURN_RECORD_SIZE]
    tid, num_tracks, track_off, car_class, traffic, knockout, num_cars = rec[:7]
    prizes = [int.from_bytes(rec[24 + i * 4 : 28 + i * 4], "little") for i in range(6)]
    fee = int.from_bytes(rec[48:52], "little")
    personalities = rec[52:57]
    opponents = rec[57:62]
    upgrades = rec[62:67]
    laps = rec[69]
    return (
        1 <= tid <= 80
        and 1 <= num_tracks <= 10
        and track_off < 80
        and car_class <= 5
        and traffic in (0, 1)
        and knockout <= 1
        and 2 <= num_cars <= 8
        and laps <= 9
        and all(0 <= x <= 200000 for x in prizes)
        and 0 <= fee <= 100000
        and all(x < 32 for x in personalities)
        and all(x < 80 for x in opponents)
        and all(x < 16 for x in upgrades)
    )


def normal_tournament_offsets(data: bytes) -> list[int]:
    hits = [
        off
        for off in range(0, len(data) - TOURN_RECORD_SIZE + 1)
        if plausible_tournament_record(data, off)
    ]
    if len(hits) < 5:
        raise SystemExit(f"found only {len(hits)} plausible tournament records")
    # The first five records are the ordinary Tournament ladder. Later records
    # are knockout/special-event entries; leave them alone for HP stability.
    return hits[:5]


def patch_file(path: Path, *, revert: bool) -> None:
    data = bytearray(path.read_bytes())
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if revert:
        if not backup.exists():
            raise SystemExit(f"missing backup: {backup}")
        path.write_bytes(backup.read_bytes())
        print(f"reverted {path}")
        return

    offsets = normal_tournament_offsets(data)
    if not backup.exists():
        backup.write_bytes(data)
    changed = False
    for off in offsets:
        traffic_at = off + TRAFFIC_OFF
        old = data[traffic_at]
        if old not in (0, 1):
            raise SystemExit(f"unexpected traffic byte at 0x{traffic_at:X}: 0x{old:02X}")
        if old != 1:
            data[traffic_at] = 1
            changed = True
    if changed:
        path.write_bytes(data)
    patched = ", ".join(f"0x{off + TRAFFIC_OFF:X}" for off in offsets)
    print(f"patched {path}")
    print(f"normal Tournament fTraffic bytes: {patched}")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: enable ordinary Tournament traffic via ZTOURN data."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    files = sorted(Path(".").glob(ROOT_GLOB))
    if len(files) != 3:
        raise SystemExit(f"expected 3 {ROOT_GLOB} files, found {len(files)}")
    for path in files:
        patch_file(path, revert=args.revert)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
