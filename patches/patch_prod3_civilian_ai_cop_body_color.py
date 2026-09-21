#!/usr/bin/env python3
"""Select body scheme zero for civilian models assigned a non-racer role."""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


BASE = 0x8000F800
EXE_GLOB = "PROD 3*/NFS4.EXE"

COLOR_HOOK_OFF = 0xA0450
COLOR_RETURN = 0x800AFC58
COLOR_HOOK_STOCK = struct.pack("<II", 0xA6820840, 0x90A40040)

# This span is the intentional racer fallthrough in the stable mass helper.
# Redirect that fallthrough to its selector, then use the skipped words as a
# callable helper without changing address 0x80055450 or its cheat options.
MASS_FALLTHROUGH_OFF = 0x45C1C
MASS_FALLTHROUGH_STOCK = bytes(8)
MASS_SELECTOR = 0x80055450
HELPER_OFF = 0x45C24
HELPER_ADDR = BASE + HELPER_OFF
HELPER_LEN = 0x28

REG = {
    "zero": 0, "a0": 4, "a1": 5, "t0": 8, "t1": 9,
    "s4": 20, "s5": 21,
}


def i(op: int, rs: str, rt: str, imm: int) -> int:
    return (op << 26) | (REG[rs] << 21) | (REG[rt] << 16) | (imm & 0xFFFF)


def j(addr: int) -> int:
    return (0x02 << 26) | ((addr >> 2) & 0x03FFFFFF)


def branch(op: int, rs: str, rt: str, pc: int, target: int) -> int:
    return i(op, rs, rt, (target - (pc + 4)) >> 2)


def pack(values: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(values), *values)


def build_helper() -> bytes:
    done = HELPER_ADDR + 0x1C
    body = pack([
        i(0x23, "a1", "t0", 4),                  # carInfo->carClass
        i(0x0B, "s5", "t1", 0x16),              # load-delay: civilian model
        i(0x0C, "t0", "t0", 2),                 # racer class bit
        branch(0x05, "t0", "zero", HELPER_ADDR + 0x0C, done),
        0,
        branch(0x04, "t1", "zero", HELPER_ADDR + 0x14, done),
        0,
        i(0x29, "s4", "zero", 0x840),            # body scheme zero
        j(COLOR_RETURN),
        i(0x24, "a1", "a0", 0x40),              # original lw a0,0x40(a1)
    ])
    assert len(body) == HELPER_LEN
    return body


def find_exe() -> Path:
    matches = sorted(Path(".").glob(EXE_GLOB))
    if len(matches) != 1:
        raise SystemExit(f"expected one PROD3 NFS4.EXE, found {len(matches)}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    data = bytearray(exe.read_bytes())
    helper = build_helper()
    hook = pack([j(HELPER_ADDR), 0xA6820840])
    fallthrough = pack([j(MASS_SELECTOR), 0])

    if bytes(data[COLOR_HOOK_OFF:COLOR_HOOK_OFF + 8]) not in {COLOR_HOOK_STOCK, hook}:
        raise SystemExit("unexpected car-color initialization hook")
    if bytes(data[MASS_FALLTHROUGH_OFF:MASS_FALLTHROUGH_OFF + 8]) not in {
        MASS_FALLTHROUGH_STOCK, fallthrough
    }:
        raise SystemExit("unexpected mass-helper fallthrough")
    if bytes(data[HELPER_OFF:HELPER_OFF + HELPER_LEN]) not in {bytes(HELPER_LEN), helper}:
        raise SystemExit("color helper span is occupied")

    if args.revert:
        data[COLOR_HOOK_OFF:COLOR_HOOK_OFF + 8] = COLOR_HOOK_STOCK
        data[MASS_FALLTHROUGH_OFF:MASS_FALLTHROUGH_OFF + 8] = MASS_FALLTHROUGH_STOCK
        data[HELPER_OFF:HELPER_OFF + HELPER_LEN] = bytes(HELPER_LEN)
    else:
        data[HELPER_OFF:HELPER_OFF + HELPER_LEN] = helper
        data[MASS_FALLTHROUGH_OFF:MASS_FALLTHROUGH_OFF + 8] = fallthrough
        data[COLOR_HOOK_OFF:COLOR_HOOK_OFF + 8] = hook

    exe.write_bytes(data)
    print(f"NFS4.EXE {hashlib.md5(data).hexdigest().upper()}")
    print(f"civilian AI-cop body scheme: {'stock' if args.revert else 'scheme 0'}")


if __name__ == "__main__":
    main()
