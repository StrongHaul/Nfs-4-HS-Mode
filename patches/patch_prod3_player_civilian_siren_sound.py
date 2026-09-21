#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
RUNTIME_BASE = 0x8000F800
CHEAT_FLAG_ADDR = 0x8011F208

# AudioClc_SoundPlayersCar normally allows siren audio only for police car
# types and only while the siren flag bit is set. The conditional cheat below
# keeps NFS4.EXE stock and toggles only those two runtime branches.
PATCH_BLOCKS = [
    (
        0x066D54,
        "player car police type siren gate",
        bytes.fromhex("39 00 40 10"),
        bytes.fromhex("00 00 00 00"),
    ),
    (
        0x066D68,
        "player car siren bit gate",
        bytes.fromhex("25 00 40 10"),
        bytes.fromhex("00 00 00 00"),
    ),
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
        if current in (stock, patch):
            continue
        raise SystemExit(f"unexpected bytes for {name} at 0x{off:X}: {current.hex(' ')}")


def conditional_code(condition_value: int, write_line: str) -> list[str]:
    addr, value = write_line.split()
    compare_addr = 0xD0000000 | (CHEAT_FLAG_ADDR & 0x00FFFFFF)
    return [f"{compare_addr:08X} {condition_value:04X}", f"{addr} {value}"]


def print_conditional_cheat_section() -> None:
    print("[Мои\\Сирена на обычной машине игрока]")
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
        description="PROD3: emit a 0/1 conditional cheat for player civilian siren audio."
    )
    parser.add_argument("--conditional-section", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    data = exe.read_bytes()
    verify_default_off(data)

    if args.conditional_section:
        print_conditional_cheat_section()
    else:
        print(f"NFS4.EXE {md5(data)}")
        print("civilian player siren sound is implemented as a default-off conditional cheat")
        print()
        print_conditional_cheat_section()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
