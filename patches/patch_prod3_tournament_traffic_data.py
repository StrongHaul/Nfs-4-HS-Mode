#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ROOT_GLOB = "PROD 3*/ZTOURN*.TRN"
BACKUP_SUFFIX = ".orig_before_prod3_tournament_traffic_data"
TIER_RECORD_SIZE = 0x0C
TOURN_RECORD_SIZE = 0x54
TOURN_TRACK_RECORD_SIZE = 0x28
TRAFFIC_OFF = 4


def tournament_offsets_by_tier(data: bytes) -> tuple[list[int], list[int]]:
    if len(data) < 7 + TIER_RECORD_SIZE:
        raise SystemExit("file is too small for tournament header")
    num_tiers = data[6]
    if num_tiers < 1:
        raise SystemExit("missing tier0")

    pos = 7
    tier0_offsets: list[int] = []
    other_offsets: list[int] = []

    for tier_index in range(num_tiers):
        tier = data[pos : pos + TIER_RECORD_SIZE]
        num_tourn = tier[0]
        tourn_offset = tier[2]
        if tier_index == 0 and (num_tourn != 6 or tourn_offset != 0):
            raise SystemExit(
                f"unexpected tier0 layout: numTourn={num_tourn}, tournOffset={tourn_offset}"
            )
        pos += TIER_RECORD_SIZE

        for _ in range(num_tourn):
            if pos + TOURN_RECORD_SIZE > len(data):
                raise SystemExit("truncated tournament record")
            rec = data[pos : pos + TOURN_RECORD_SIZE]
            num_tracks = rec[1]
            traffic = rec[TRAFFIC_OFF]
            if traffic not in (0, 1):
                raise SystemExit(
                    f"unexpected traffic byte at 0x{pos + TRAFFIC_OFF:X}: 0x{traffic:02X}"
                )
            if tier_index == 0:
                tier0_offsets.append(pos)
            else:
                other_offsets.append(pos)
            pos += TOURN_RECORD_SIZE + num_tracks * TOURN_TRACK_RECORD_SIZE
    return tier0_offsets, other_offsets


def patch_file(path: Path, *, revert: bool) -> None:
    data = bytearray(path.read_bytes())
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if revert:
        if not backup.exists():
            raise SystemExit(f"missing backup: {backup}")
        path.write_bytes(backup.read_bytes())
        print(f"reverted {path}")
        return

    tier0_offsets, other_offsets = tournament_offsets_by_tier(data)
    if not backup.exists():
        backup.write_bytes(data)
    changed = False
    for off in tier0_offsets:
        traffic_at = off + TRAFFIC_OFF
        old = data[traffic_at]
        if old not in (0, 1):
            raise SystemExit(f"unexpected traffic byte at 0x{traffic_at:X}: 0x{old:02X}")
        if old != 1:
            data[traffic_at] = 1
            changed = True
    for off in other_offsets:
        traffic_at = off + TRAFFIC_OFF
        old = data[traffic_at]
        if old not in (0, 1):
            raise SystemExit(f"unexpected traffic byte at 0x{traffic_at:X}: 0x{old:02X}")
        if old != 0:
            data[traffic_at] = 0
            changed = True
    if changed:
        path.write_bytes(data)
    tier0_patched = ", ".join(f"0x{off + TRAFFIC_OFF:X}" for off in tier0_offsets)
    other_patched = ", ".join(f"0x{off + TRAFFIC_OFF:X}" for off in other_offsets)
    print(f"patched {path}")
    print(f"tier0 ordinary Tournament fTraffic=1 bytes: {tier0_patched}")
    print(f"tier1+ Tournament fTraffic=0 bytes: {other_patched}")
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
