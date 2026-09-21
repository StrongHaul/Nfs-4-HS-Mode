#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

BACKUP_SUFFIX = ".orig_before_player_collision_mass_toggle"
FLAG_ADDR = 0x8011F21C
PEC_FLAG_ADDR = 0x801144DC
PEC_FLAG_OFF = 0x104CDC
MASS_OFF_VALUE = 0x0008
MASS_ON_VALUE = 0x000A
CHEAT_NAME = "[\u041c\u043e\u0438\\\u0423\u0432\u0435\u043b\u0438\u0447\u0435\u043d\u043d\u0430\u044f \u043c\u0430\u0441\u0441\u0430 \u043a\u043e\u043b\u043b\u0438\u0437\u0438\u0438 \u0438\u0433\u0440\u043e\u043a\u0430]"
CHT_PATH = Path("PROD3_player_collision_mass_toggle.cht")


def prod3_exe() -> Path:
    hits = list(Path(".").glob("PROD 3*/NFS4.EXE"))
    if len(hits) != 1:
        raise SystemExit(f"expected one PROD 3*/NFS4.EXE, found {len(hits)}")
    return hits[0]


def emit_cheat() -> str:
    lines = [
        CHEAT_NAME,
        "Type = Gameshark",
        "Activation = EndFrame",
        "Option = \u0412\u044b\u043a\u043b:0",
        "Option = \u0412\u043a\u043b:1",
        f"8{FLAG_ADDR & 0xFFFFFF:07X} 000?",
        f"D{FLAG_ADDR & 0xFFFFFF:07X} 0000",
        f"8{PEC_FLAG_ADDR & 0xFFFFFF:07X} {MASS_OFF_VALUE:04X}",
        f"D{FLAG_ADDR & 0xFFFFFF:07X} 0001",
        f"8{PEC_FLAG_ADDR & 0xFFFFFF:07X} {MASS_ON_VALUE:04X}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    exe = prod3_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    actual = int.from_bytes(data[PEC_FLAG_OFF:PEC_FLAG_OFF+2], "little")
    if actual not in (0x0000, 0x0002, 0x0008, 0x000A):
        raise SystemExit(f"unexpected data_801144dc at 0x{PEC_FLAG_OFF:X}: 0x{actual:04X}")

    if actual != MASS_OFF_VALUE:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        data[PEC_FLAG_OFF:PEC_FLAG_OFF+2] = MASS_OFF_VALUE.to_bytes(2, "little")
        exe.write_bytes(data)
        print(f"data_801144dc default: 0x{actual:04X} -> 0x{MASS_OFF_VALUE:04X}")
    else:
        print(f"data_801144dc default: already 0x{MASS_OFF_VALUE:04X}")

    CHT_PATH.write_text(emit_cheat(), encoding="utf-8", newline="\n")
    final = exe.read_bytes()
    print(f"patched {exe}")
    print(f"cheat {CHT_PATH}")
    print("player collision mass is off by default; cheat On restores data_801144dc bit 0x0002")
    print(f"md5 {hashlib.md5(final).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
