#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


BACKUP_SUFFIX = ".orig_player_lod_exe"

# Prototype NFS4.EXE, R3DCar_Instantiate3DCar:
#   800AF064: j 800AF078
#   800AF068: sh a0,0x08C0(s4)   ; player/human car uses high LOD suffix "h"
#
# Patch delay slot to:
#   800AF068: sb a0,0x08B2(s4)   ; player/human car uses simple LOD suffix "s"
#
# PS-X EXE load base is 0x80010000, payload starts at file offset 0x800.
EXE_PATCHES = [
    {
        "file_offset": 0x9F868,
        "old": bytes.fromhex("c0 08 84 a6"),  # sh a0,0x08C0(s4)
        "new": bytes.fromhex("b2 08 84 a2"),  # sb a0,0x08B2(s4)
        "description": "force human/player car from high LOD flag to simple LOD flag",
    }
]

CPE_PATCHES = [
    {
        "file_offset": 0xA20AF,
        "old": bytes.fromhex("c0 08 84 a6"),  # sh a0,0x08C0(s4)
        "new": bytes.fromhex("b2 08 84 a2"),  # sb a0,0x08B2(s4)
        "description": "force human/player car from high LOD flag to simple LOD flag in CPE",
    }
]


def patches_for(path: Path) -> list[dict[str, object]]:
    if path.suffix.upper() == ".CPE":
        return CPE_PATCHES
    return EXE_PATCHES


def apply_patch(path: Path, apply: bool) -> None:
    data = bytearray(path.read_bytes())
    for patch in patches_for(path):
        off = patch["file_offset"]
        old = patch["old"]
        new = patch["new"]
        actual = bytes(data[off : off + len(old)])
        if actual == new:
            print(f"{path.name}: already patched at 0x{off:X}: {patch['description']}")
            continue
        if actual != old:
            raise SystemExit(
                f"{path.name}: unexpected bytes at 0x{off:X}: "
                f"{actual.hex(' ')}; expected {old.hex(' ')}"
            )
        print(f"{path.name}: patch 0x{off:X}: {old.hex(' ')} -> {new.hex(' ')}")
        if apply:
            data[off : off + len(old)] = new

    if apply:
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
        path.write_bytes(data)
        print("done: patched player LOD in EXE")
    else:
        print("dry run only; pass --apply to write changes")


def restore(path: Path) -> None:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        raise SystemExit(f"backup not found: {backup.name}")
    path.write_bytes(backup.read_bytes())
    print(f"restored {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch NFS4 prototype EXE to use simple LOD for player car.")
    parser.add_argument("--exe", default="NFS4.EXE", help="Path to NFS4.EXE")
    parser.add_argument("--cpe", default=None, help="Optional path to NFS4.CPE")
    parser.add_argument("--apply", action="store_true", help="Write patched EXE")
    parser.add_argument("--restore", action="store_true", help="Restore .orig_player_lod_exe backup")
    args = parser.parse_args()

    paths = [Path(args.exe)]
    if args.cpe:
        paths.append(Path(args.cpe))
    for path in paths:
        if args.restore:
            restore(path)
        else:
            apply_patch(path, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
