#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXE_GLOB = "PROD 3*/NFS4.EXE"

# AudioClc_SoundCloseCar handles nearby non-player cars. Stock recognizes a
# siren by police model ID; use the authoritative AI-cop role bit instead so a
# civilian replacement model gets spatial siren audio without entering any
# police rendering or nighttime-light path.
SIREN_GATE_OFF = 0x66618
SIREN_STOCK = bytes.fromhex(
    "88 02 42 8E"
    "00 00 00 00"
    "00 00 42 8C"
    "00 00 00 00"
    "EA FF 42 24"
    "06 00 42 2C"
    "31 00 40 10"
    "00 00 00 00"
)
SIREN_AI_COP_ROLE = struct.pack(
    "<8I",
    0x8E420260,  # lw v0,0x260(s2): carFlags
    0x00000000,
    0x30420020,  # andi v0,v0,0x20: AI cop
    0x10400034,  # beq v0,zero,0x80075EF8
    0x00000000,
    0x00000000,
    0x00000000,
    0x00000000,
)


def find_exe() -> Path:
    matches = sorted(Path(".").glob(EXE_GLOB))
    if len(matches) != 1:
        raise SystemExit(f"expected one PROD3 NFS4.EXE, found {len(matches)}")
    return matches[0]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enable spatial siren audio for AI cops using civilian replacement models."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    data = bytearray(exe.read_bytes())
    current = bytes(data[SIREN_GATE_OFF : SIREN_GATE_OFF + len(SIREN_STOCK)])
    if current not in {SIREN_STOCK, SIREN_AI_COP_ROLE}:
        raise SystemExit(f"unexpected AI siren gate: {current.hex(' ')}")

    data[SIREN_GATE_OFF : SIREN_GATE_OFF + len(SIREN_STOCK)] = (
        SIREN_STOCK if args.revert else SIREN_AI_COP_ROLE
    )
    exe.write_bytes(data)

    print(f"NFS4.EXE {md5(exe)}")
    print("civilian AI cop siren: " + ("stock" if args.revert else "enabled"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
