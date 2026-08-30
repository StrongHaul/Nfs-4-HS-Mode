#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXE_GLOB = "PROD 3*/NFS4.EXE"
CAR_TYPE_LOAD_OFF = 0x54C50
STOCK = 0x8C660000  # lw a2,0(v1)
DIABLO_COP = 0x2406001B  # addiu a2,zero,0x1B

# Police model IDs bypass the ordinary model speed cap, but replacement
# civilian models do not. These two in-place branches set x1.3 speed headroom
# while preserving the initialized copTopSpeed and the cop acceleration entry.
UPGRADE_PATCHES = {
    0x54C6C: (0x8C43000C, None, 0x3C030001),
    0x54C70: (0x00000000, 0x34633333, 0x34634CCD),
    0x54C74: (0xACA306C8, None, 0xACA3077C),
    0x54C98: (0x8C430008, None, 0x3C030001),
    0x54C9C: (0x00000000, 0x34633333, 0x34634CCD),
    0x54CA0: (0xACA306C8, None, 0xACA3077C),
}


def find_exe() -> Path:
    matches = sorted(Path(".").glob(EXE_GLOB))
    if len(matches) != 1:
        raise SystemExit(f"expected one PROD3 NFS4.EXE, found {len(matches)}")
    return matches[0]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Use the safe Diablo Cop tuning entry for AI cops on replacement cars."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    data = bytearray(exe.read_bytes())
    current = struct.unpack_from("<I", data, CAR_TYPE_LOAD_OFF)[0]
    if current not in {STOCK, DIABLO_COP}:
        raise SystemExit(f"unexpected instruction at 0x{CAR_TYPE_LOAD_OFF:X}: 0x{current:08X}")

    replacement = STOCK if args.revert else DIABLO_COP
    struct.pack_into("<I", data, CAR_TYPE_LOAD_OFF, replacement)

    for off, (stock_word, legacy_word, patched_word) in UPGRADE_PATCHES.items():
        current_word = struct.unpack_from("<I", data, off)[0]
        known_words = {stock_word, patched_word}
        if legacy_word is not None:
            known_words.add(legacy_word)
        if current_word not in known_words:
            raise SystemExit(f"unexpected instruction at 0x{off:X}: 0x{current_word:08X}")
        struct.pack_into("<I", data, off, stock_word if args.revert else patched_word)

    exe.write_bytes(data)

    print(f"NFS4.EXE {md5(exe)}")
    print(
        "AI cop tuning fallback: "
        + ("stock" if args.revert else "Diablo Cop + x1.3 civilian speed headroom")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
