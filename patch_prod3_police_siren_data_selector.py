#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROD3_EXE = next(ROOT.glob("PROD 3*/NFS4.EXE"))
BACKUP_SUFFIX = ".orig_before_prod3_police_siren_data_selector"

PATCHES = {
    0x45A00: (0x8E450260, 0x3C058012),  # lw a1,0x260(s2) -> lui a1,0x8012
    0x45A04: (0x24050000, 0x94A5F22C),  # addiu a1,zero,0 -> lhu a1,0xF22C(a1)
    0x45A50: (0x8E420260, 0x3C028012),  # lw v0,0x260(s2) -> lui v0,0x8012
    0x45A58: (0x24020000, 0x9442F22C),  # addiu v0,zero,0 -> lhu v0,0xF22C(v0)
}


def word(value: int) -> bytes:
    return struct.pack("<I", value & 0xFFFFFFFF)


def patch_exe(path: Path, apply: bool) -> None:
    data = bytearray(path.read_bytes())
    for offset, (stock, patched) in PATCHES.items():
        actual = struct.unpack_from("<I", data, offset)[0]
        if actual not in (stock, patched):
            raise SystemExit(
                f"unexpected word at 0x{offset:X}: 0x{actual:08X}; "
                f"expected 0x{stock:08X} or 0x{patched:08X}"
            )

    if not apply:
        print(f"validated {path}")
        print("selector: 0x8011F22C")
        return

    backup = Path(str(path) + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(path, backup)

    for offset, (_stock, patched) in PATCHES.items():
        data[offset : offset + 4] = word(patched)
    path.write_bytes(data)
    print(f"patched {path}")
    print(f"MD5: {hashlib.md5(data).hexdigest().upper()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=PROD3_EXE)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    patch_exe(args.exe, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
