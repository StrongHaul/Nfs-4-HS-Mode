#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROD3_EXE = next(ROOT.glob("PROD 3*/NFS4.EXE"))

PATCHES = [
    (0x56CC8, bytes.fromhex("c4 0c 51 24"), bytes.fromhex("78 0d 51 24"), "CheckForCops scan Cars_gCopCarList"),
    (0x56CD0, bytes.fromhex("ec da 42 8c"), bytes.fromhex("00 db 42 8c"), "CheckForCops use Cars_gNumCopCars"),
    (0x56E08, bytes.fromhex("13 00 00 10"), bytes.fromhex("13 00 40 14"), "CopCheck stock AI object state gate"),
]

CHEAT_BLOCK = """[???\\?????? ???????? ????????-??????]
Type = Gameshark
Activation = EndFrame
Option = ????:0
Option = ???:1
8011F220 000?
D011F220 0000
800664C8 0D78
D011F220 0000
800664D0 DB00
D011F220 0000
8006660A 1440
D011F220 0001
800664C8 0CC4
D011F220 0001
800664D0 DAEC
D011F220 0001
8006660A 1000
"""


def write_cheat_fragment() -> None:
    (ROOT / "PROD3_traffic_yield_toggle.cht").write_text(CHEAT_BLOCK, encoding="utf-8")


def patch_exe(path: Path, apply: bool) -> None:
    data = bytearray(path.read_bytes())
    changed = False
    for off, on_bytes, stock_bytes, name in PATCHES:
        actual = bytes(data[off : off + len(stock_bytes)])
        if actual == stock_bytes:
            print(f"{name}: stock at 0x{off:X}")
            continue
        if actual != on_bytes:
            raise SystemExit(
                f"{name}: unexpected bytes at 0x{off:X}: {actual.hex(' ')}; "
                f"expected {on_bytes.hex(' ')} or {stock_bytes.hex(' ')}"
            )
        print(f"{name}: restore stock 0x{off:X}: {actual.hex(' ')} -> {stock_bytes.hex(' ')}")
        data[off : off + len(stock_bytes)] = stock_bytes
        changed = True

    if apply and changed:
        path.write_bytes(data)
        print("NFS4.EXE updated; traffic-yield feature is now controlled by cheat 8011F220.")
    elif not apply:
        print("dry-run only; pass --apply to write")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=PROD3_EXE)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    patch_exe(args.exe, args.apply)
    write_cheat_fragment()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
