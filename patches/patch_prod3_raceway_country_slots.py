#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_raceway_country_slots"

# Track-country table embedded in the player cop livery mode cave.
# Slots: 0 Snowy, 1 Highway, 2 Coastal, 3 France, 4 Park, 5 Celtic,
# 6 Germany, 7 UK, 8 Raceway 2, 9 Raceway, 10 Raceway 3.
TABLE_OFF = 0x45BE0
OLD_TABLE = bytes([
    2,  # Snowy -> German
    4,  # Highway -> US/Canada
    4,  # Coastal -> US/Canada
    1,  # France -> French
    4,  # Park -> US/Canada
    0,  # Celtic -> UK
    2,  # Germany -> German
    0,  # UK -> UK
    4,  # Raceway -> was US/Canada
    4,  # Raceway 2 -> US/Canada
    4,  # Raceway 3 -> was US/Canada
    0,
    0,
    0,
    0,
    0,
])
PREVIOUS_NEW_TABLE = bytes([
    2,  # Snowy -> German
    4,  # Highway -> US/Canada
    4,  # Coastal -> US/Canada
    1,  # France -> French
    4,  # Park -> US/Canada
    0,  # Celtic -> UK
    2,  # Germany -> German
    0,  # UK -> UK
    4,  # Raceway 2 -> US/Canada
    1,  # Raceway -> French
    2,  # Raceway 3 -> German
    0,
    0,
    0,
    0,
    0,
])
NEW_TABLE = bytes([
    4,  # Snowy -> US/Canada
    4,  # Highway -> US/Canada
    4,  # Coastal -> US/Canada
    1,  # France -> French
    4,  # Park -> US/Canada
    3,  # Celtic / Scotland -> Australian
    2,  # Germany -> German
    0,  # UK -> UK
    4,  # Raceway 2 -> US/Canada
    1,  # Raceway -> French
    2,  # Raceway 3 -> German
    0,
    0,
    0,
    0,
    0,
])
PREVIOUS_SCOTLAND_UK_TABLE = bytes([
    4, 4, 4, 1, 4, 0, 2, 0, 4, 1, 2, 0, 0, 0, 0, 0,
])
PREVIOUS_SWAPPED_TABLE = bytes([
    2,
    4,
    4,
    1,
    4,
    0,
    2,
    0,
    1,  # Previous wrong assumption: Raceway -> slot 8
    4,
    2,
    0,
    0,
    0,
    0,
    0,
])


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: set cop-livery country slots for Raceway tracks."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    current = bytes(data[TABLE_OFF : TABLE_OFF + len(OLD_TABLE)])
    if current not in {OLD_TABLE, PREVIOUS_NEW_TABLE, NEW_TABLE, PREVIOUS_SCOTLAND_UK_TABLE, PREVIOUS_SWAPPED_TABLE}:
        raise SystemExit(f"unexpected table at 0x{TABLE_OFF:X}: {current.hex(' ')}")

    data[TABLE_OFF : TABLE_OFF + len(OLD_TABLE)] = OLD_TABLE if args.revert else NEW_TABLE

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(("reverted" if args.revert else "patched"), exe)
    print("Snowy=US/Canada; Scotland=Australian; Raceway=French, Raceway 2=US/Canada, Raceway 3=German")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
