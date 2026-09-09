#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXE_GLOB = "PROD 3*/NFS4.EXE"

# R3DCar_InsertCarFacetII normally derives s6 solely from model IDs 0x16..0x1B.
# For this diagnostic, derive it from the AI-cop role bit instead, allowing a
# civilian replacement to enter the existing stock police-light branch.
MODEL_SUB_OFF = 0xA1128
MODEL_TEST_OFF = 0xA114C
STOCK_MODEL_SUB = struct.pack("<I", 0x26E2FFEA)  # addiu v0,s7,-0x16
STOCK_MODEL_TEST = struct.pack("<I", 0x2C560006) # sltiu s6,v0,6
ROLE_LOAD = struct.pack("<I", 0x8EA20260)        # lw v0,0x260(s5)
ROLE_TEST = struct.pack("<I", 0x30560020)        # andi s6,v0,0x20


def find_exe() -> Path:
    matches = sorted(Path(".").glob(EXE_GLOB))
    if len(matches) != 1:
        raise SystemExit(f"expected one PROD3 NFS4.EXE, found {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Let every AI cop use the stock police-light renderer.")
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    data = bytearray(exe.read_bytes())
    current_sub = bytes(data[MODEL_SUB_OFF:MODEL_SUB_OFF + 4])
    current_test = bytes(data[MODEL_TEST_OFF:MODEL_TEST_OFF + 4])
    if current_sub not in {STOCK_MODEL_SUB, ROLE_LOAD}:
        raise SystemExit(f"unexpected model-sub instruction: {current_sub.hex(' ')}")
    if current_test not in {STOCK_MODEL_TEST, ROLE_TEST}:
        raise SystemExit(f"unexpected model-test instruction: {current_test.hex(' ')}")

    data[MODEL_SUB_OFF:MODEL_SUB_OFF + 4] = STOCK_MODEL_SUB if args.revert else ROLE_LOAD
    data[MODEL_TEST_OFF:MODEL_TEST_OFF + 4] = STOCK_MODEL_TEST if args.revert else ROLE_TEST
    exe.write_bytes(data)
    print(hashlib.md5(data).hexdigest().upper())
    print("stock light renderer for all AI cops:", "reverted" if args.revert else "enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
