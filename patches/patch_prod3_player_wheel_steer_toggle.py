#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path


BACKUP_SUFFIX = ".orig_before_player_wheel_steer_toggle"

PATCHES = [
    (0x0A1790, bytes.fromhex("50 04 b0 8e"), bytes.fromhex("21 80 00 00"), "visual wheel steer main"),
    (0x0A1F84, bytes.fromhex("50 04 a2 8e"), bytes.fromhex("21 10 00 00"), "visual wheel steer part A"),
    (0x0A1FFC, bytes.fromhex("50 04 b0 8e"), bytes.fromhex("21 80 00 00"), "visual wheel steer part B"),
]


def prod3_exe() -> Path:
    hits = list(Path(".").glob("PROD 3*/NFS4.EXE"))
    if len(hits) != 1:
        raise SystemExit(f"expected one PROD 3*/NFS4.EXE, found {len(hits)}")
    return hits[0]


def main() -> int:
    exe = prod3_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    backup = exe.with_name(exe.name + BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_bytes(original)

    for off, stock, disabled, name in PATCHES:
        actual = bytes(data[off : off + 4])
        if actual not in (stock, disabled):
            raise SystemExit(f"unexpected bytes for {name} at 0x{off:X}: {actual.hex(' ')}")
        data[off : off + 4] = stock
        print(f"{name}: {actual.hex(' ')} -> {stock.hex(' ')}")

    exe.write_bytes(data)
    final = exe.read_bytes()
    print(f"patched {exe}")
    print(f"backup {backup}")
    print("player wheel steering animation is stock by default; cheat can disable it")
    print(f"md5 {hashlib.md5(final).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
