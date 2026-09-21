#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROD3_EXE = next(ROOT.glob("PROD 3*/NFS4.EXE"))
BACKUP_SUFFIX = ".orig_before_reverse_hp_cop_spawn_direction"

# AIHigh_Cop::CheckForNewTriggers chooses the side on which it looks for the
# next cop trigger. Track direction is authoritative; current speed is not.
PATCH_OFF = 0x56AA0
STOCK_WORD = 0x8EA20564  # lw v0,0x564(s5): currentSpeed
PATCH_WORD = 0x8EA20554  # lw v0,0x554(s5): direction


def patch_exe(path: Path, apply: bool) -> None:
    data = bytearray(path.read_bytes())
    actual = struct.unpack_from("<I", data, PATCH_OFF)[0]
    expected = (STOCK_WORD, PATCH_WORD)
    if actual not in expected:
        raise SystemExit(
            f"unexpected instruction at 0x{PATCH_OFF:X}: 0x{actual:08X}"
        )

    if not apply:
        state = "patched" if actual == PATCH_WORD else "stock"
        print(f"validated {path} ({state})")
        return

    backup = Path(str(path) + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(path, backup)

    struct.pack_into("<I", data, PATCH_OFF, PATCH_WORD)
    path.write_bytes(data)
    print(f"patched {path}")
    print(f"md5={hashlib.md5(data).hexdigest().upper()}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Use track direction for reverse-HP cop trigger scanning"
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    patch_exe(PROD3_EXE, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
