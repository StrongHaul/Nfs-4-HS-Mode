#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


BACKUP_SUFFIX = ".orig_player_lod_prod"

# Retail/PROD SLUS-00826 NFS4.EXE, same code path as the Feb 23 prototype:
# R3DCar_Instantiate3DCar human/player branch.
#
# Prototype equivalent:
#   800AF064: j 800AF078
#   800AF068: sh a0,0x08C0(s4)   ; player/human car uses high LOD suffix "h"
#
# PROD equivalent at file offset 0xA0500:
#   sh a0,0x08C0(s4)
#
# Patch to:
#   sb a0,0x08B2(s4)             ; player/human car uses simple LOD suffix "s"
PATCH = {
    "file_offset": 0xA0500,
    "old": bytes.fromhex("c0 08 84 a6"),
    "new": bytes.fromhex("b2 08 84 a2"),
    "description": "force player/human car to simple/bot LOD in PROD NFS4.EXE",
}


def apply_patch(path: Path, apply: bool) -> None:
    data = bytearray(path.read_bytes())
    off = PATCH["file_offset"]
    old = PATCH["old"]
    new = PATCH["new"]
    actual = bytes(data[off : off + len(old)])

    if actual == new:
        print(f"{path.name}: already patched at 0x{off:X}: {PATCH['description']}")
    elif actual == old:
        print(f"{path.name}: patch 0x{off:X}: {old.hex(' ')} -> {new.hex(' ')}")
        if apply:
            data[off : off + len(old)] = new
    else:
        raise SystemExit(
            f"{path.name}: unexpected bytes at 0x{off:X}: "
            f"{actual.hex(' ')}; expected {old.hex(' ')}"
        )

    if apply:
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
        path.write_bytes(data)
        print("done: patched PROD player LOD")
    else:
        print("dry run only; pass --apply to write changes")


def restore(path: Path) -> None:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        raise SystemExit(f"backup not found: {backup.name}")
    path.write_bytes(backup.read_bytes())
    print(f"restored {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch PROD NFS4.EXE to use bot/simple LOD for player car.")
    parser.add_argument("--exe", default="NFS4.EXE", help="Path to PROD NFS4.EXE")
    parser.add_argument("--apply", action="store_true", help="Write patched EXE")
    parser.add_argument("--restore", action="store_true", help="Restore .orig_player_lod_prod backup")
    args = parser.parse_args()

    path = Path(args.exe)
    if args.restore:
        restore(path)
    else:
        apply_patch(path, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
