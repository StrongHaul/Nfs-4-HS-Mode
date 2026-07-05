#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

BACKUP_SUFFIX = ".orig_before_player_power_speed_toggle"
RUNTIME_BASE = 0x8000F800
FLAG_ADDR = 0x8011F218
CHEAT_NAME = "[\u041c\u043e\u0438\\\u0423\u0441\u0438\u043b\u0435\u043d\u043d\u043e\u0435 \u0443\u0441\u043a\u043e\u0440\u0435\u043d\u0438\u0435 \u0438 \u0441\u043a\u043e\u0440\u043e\u0441\u0442\u044c \u0438\u0433\u0440\u043e\u043a\u0430]"
CHT_PATH = Path("PROD3_player_power_speed_toggle.cht")

PATCHES = [
    (0x09A7B0, bytes.fromhex("00 00 00 00"), bytes.fromhex("40 10 02 00"), "engine torque x2 delay slot"),
    (0x099FAC, bytes.fromhex("01 00 05 3c"), bytes.fromhex("02 00 05 3c"), "derived torque table high half"),
    (0x099FC4, bytes.fromhex("66 26 a5 34"), bytes.fromhex("00 80 a5 34"), "derived torque table multiplier"),
    (0x09A80C, bytes.fromhex("13 00 02 3c"), bytes.fromhex("18 00 02 3c"), "power speed cap high half"),
]


def prod3_exe() -> Path:
    hits = list(Path(".").glob("PROD 3*/NFS4.EXE"))
    if len(hits) != 1:
        raise SystemExit(f"expected one PROD 3*/NFS4.EXE, found {len(hits)}")
    return hits[0]


def halfword_lines(flag_value: int, file_off: int, blob: bytes) -> list[str]:
    if len(blob) % 2:
        raise ValueError(f"odd patch length at 0x{file_off:X}")
    lines: list[str] = []
    addr = RUNTIME_BASE + file_off
    for index in range(0, len(blob), 2):
        value = int.from_bytes(blob[index:index+2], "little")
        lines.append(f"D{FLAG_ADDR & 0xFFFFFF:07X} {flag_value:04X}")
        lines.append(f"8{(addr + index) & 0xFFFFFF:07X} {value:04X}")
    return lines


def emit_cheat() -> str:
    lines = [
        CHEAT_NAME,
        "Type = Gameshark",
        "Activation = EndFrame",
        "Option = \u0412\u044b\u043a\u043b:0",
        "Option = \u0412\u043a\u043b:1",
        f"8{FLAG_ADDR & 0xFFFFFF:07X} 000?",
    ]
    for off, stock, _, _ in PATCHES:
        lines.extend(halfword_lines(0, off, stock))
    for off, _, enhanced, _ in PATCHES:
        lines.extend(halfword_lines(1, off, enhanced))
    return "\n".join(lines) + "\n"


def main() -> int:
    exe = prod3_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    backup = exe.with_name(exe.name + BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_bytes(original)

    changed = False
    for off, stock, enhanced, name in PATCHES:
        actual = bytes(data[off:off+len(stock)])
        if actual not in (stock, enhanced):
            raise SystemExit(f"unexpected bytes for {name} at 0x{off:X}: {actual.hex(' ')}")
        if actual != stock:
            data[off:off+len(stock)] = stock
            changed = True
            print(f"{name}: {actual.hex(' ')} -> {stock.hex(' ')}")
        else:
            print(f"{name}: already stock")

    if changed:
        exe.write_bytes(data)

    CHT_PATH.write_text(emit_cheat(), encoding="utf-8", newline="\n")
    final = exe.read_bytes()
    print(f"patched {exe}")
    print(f"backup {backup}")
    print(f"cheat {CHT_PATH}")
    print("player acceleration/speed/torque are stock by default; cheat On restores enhanced values")
    print(f"md5 {hashlib.md5(final).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
