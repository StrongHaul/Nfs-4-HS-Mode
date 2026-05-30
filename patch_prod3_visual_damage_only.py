#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
RUNTIME_BASE = 0x8000F800
CHEAT_FLAG_ADDR = 0x8011F204

# Default-off cheat implementation. NFS4.EXE stays stock; the ON code patches
# only RAM instructions that turn accumulated damage into weak engine/handling.
# Newton_AddDamageZone is not touched, so visual damage and damage stats remain.

PATCH_BLOCKS = [
    (
        0x05F898,
        "AISpeeds damage factor",
        bytes.fromhex("e8 ff bd 27 10 00 b0 af 21 80 80 00 14 00 bf af"),
        bytes.fromhex("01 00 02 3c 78 07 82 ac 08 00 e0 03 00 00 00 00"),
    ),
    (
        0x05CA70,
        "AIPhysic rear damage factor",
        bytes.fromhex("e8 ff bd 27 10 00 bf af 28 02 83 8c"),
        bytes.fromhex("21 10 00 00 08 00 e0 03 00 00 00 00"),
    ),
    (0x09BF10, "engine sputter damage[1]", bytes.fromhex("1c 02 24 8e"), bytes.fromhex("21 20 00 00")),
    (0x09BF14, "engine sputter damage[5]", bytes.fromhex("2c 02 23 8e"), bytes.fromhex("21 18 00 00")),
    (0x09DA54, "front steering damage[0]", bytes.fromhex("18 02 a2 8e"), bytes.fromhex("21 10 00 00")),
    (0x09DA58, "front steering damage[1]", bytes.fromhex("1c 02 a3 8e"), bytes.fromhex("21 18 00 00")),
    (0x09DA64, "front steering damage[2]", bytes.fromhex("20 02 a3 8e"), bytes.fromhex("21 18 00 00")),
    (0x09DA68, "front steering damage[9]", bytes.fromhex("3c 02 a4 8e"), bytes.fromhex("21 20 00 00")),
    (0x09DC84, "brake damage[9]", bytes.fromhex("3c 02 a3 8e"), bytes.fromhex("21 18 00 00")),
    (0x09DD8C, "rear grip damage[4]", bytes.fromhex("28 02 a2 8e"), bytes.fromhex("21 10 00 00")),
    (0x09DD90, "rear grip damage[5]", bytes.fromhex("2c 02 a3 8e"), bytes.fromhex("21 18 00 00")),
    (0x09DD9C, "rear grip damage[6]", bytes.fromhex("30 02 a3 8e"), bytes.fromhex("21 18 00 00")),
    (0x09DDA0, "rear grip damage[9]", bytes.fromhex("3c 02 a4 8e"), bytes.fromhex("21 20 00 00")),
]


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest().upper()


def halfword_codes(off: int, blob: bytes) -> list[str]:
    if len(blob) % 2:
        raise ValueError("blob length must be even")
    addr = RUNTIME_BASE + off
    lines: list[str] = []
    for i in range(0, len(blob), 2):
        value = struct.unpack_from("<H", blob, i)[0]
        lines.append(f"{addr + i:08X} {value:04X}")
    return lines


def cheat_lines(*, patched: bool) -> list[str]:
    lines: list[str] = []
    for off, _, stock, patch in PATCH_BLOCKS:
        lines.extend(halfword_codes(off, patch if patched else stock))
    return lines


def verify_default_off(data: bytes) -> None:
    for off, name, stock, patch in PATCH_BLOCKS:
        current = bytes(data[off : off + len(stock)])
        if current == stock:
            continue
        if current == patch:
            raise SystemExit(
                f"{name} is hardpatched at 0x{off:X}; run restore/disable codes or revert before stable default-off."
            )
        raise SystemExit(f"unexpected bytes for {name} at 0x{off:X}: {current.hex(' ')}")


def print_cheats() -> None:
    print("[Visual damage only ON]")
    for line in cheat_lines(patched=True):
        print(line)
    print()
    print("[Visual damage only OFF / restore stock]")
    for line in cheat_lines(patched=False):
        print(line)


def conditional_code(condition_value: int, write_line: str) -> list[str]:
    addr, value = write_line.split()
    compare_addr = 0xD0000000 | (CHEAT_FLAG_ADDR & 0x00FFFFFF)
    return [f"{compare_addr:08X} {condition_value:04X}", f"{addr} {value}"]


def print_conditional_cheat_section() -> None:
    print("[Мои\\Damage только визуальный]")
    print("Type = Gameshark")
    print("Activation = EndFrame")
    print("Option = Выкл:0")
    print("Option = Вкл:1")
    print(f"{CHEAT_FLAG_ADDR:08X} 000?")
    for line in cheat_lines(patched=False):
        for cond_line in conditional_code(0, line):
            print(cond_line)
    for line in cheat_lines(patched=True):
        for cond_line in conditional_code(1, line):
            print(cond_line)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: emit default-off Gameshark codes for visual-only car damage."
    )
    parser.add_argument("--codes-only", action="store_true")
    parser.add_argument("--conditional-section", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    data = exe.read_bytes()
    verify_default_off(data)
    if args.conditional_section:
        print_conditional_cheat_section()
        return 0

    if not args.codes_only:
        print(f"NFS4.EXE {md5(data)}")
        print("visual damage only is default-off in the EXE")
        print()
    print_cheats()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
