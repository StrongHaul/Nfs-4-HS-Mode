#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


RUNTIME_BASE = 0x8000F800
DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"

FILTER_OFF = 0x45800
FILTER_ADDR = RUNTIME_BASE + FILTER_OFF
FILTER_STOCK = bytes.fromhex("3c 00 a8 16 00 00 00 00")

LIST_CAVE_OFF = 0x45A18
LIST_CAVE_ADDR = RUNTIME_BASE + LIST_CAVE_OFF
LIST_CAVE_LEN = 0x38
PHASE_CAVE_OFF = 0x45BB0
PHASE_CAVE_ADDR = RUNTIME_BASE + PHASE_CAVE_OFF
PHASE_CAVE_LEN = 0x30

COP_LIST = 0x80110D78
GAME_TICKS = 0x8011F368
STROBE_BODY = 0x8005502C
STROBE_SKIP = 0x800550F4

REG = {"zero": 0, "v1": 3, "t0": 8, "t1": 9, "s5": 21, "s7": 23}


def i(op: int, rs: str, rt: str, imm: int) -> int:
    return (op << 26) | (REG[rs] << 21) | (REG[rt] << 16) | (imm & 0xFFFF)


def r(rs: str, rt: str, rd: str, sh: int, fn: int) -> int:
    return (REG[rs] << 21) | (REG[rt] << 16) | (REG[rd] << 11) | (sh << 6) | fn


def j(addr: int) -> int:
    return (0x02 << 26) | ((addr >> 2) & 0x03FFFFFF)


def branch(op: int, rs: str, rt: str, pc: int, target: int) -> int:
    return i(op, rs, rt, (target - (pc + 4)) >> 2)


def pack(words: list[int], length: int) -> bytes:
    result = struct.pack("<" + "I" * len(words), *words)
    return result.ljust(length, b"\x00")


def list_cave() -> bytes:
    loop = LIST_CAVE_ADDR + 0x14
    words = [
        branch(0x04, "t0", "zero", LIST_CAVE_ADDR, STROBE_SKIP),
        0,
        i(0x0F, "zero", "t0", COP_LIST >> 16),
        i(0x09, "t0", "t0", COP_LIST & 0xFFFF),
        i(0x09, "t0", "t1", 16),
        i(0x23, "t0", "v1", 0),
        0,
        branch(0x04, "s5", "v1", LIST_CAVE_ADDR + 0x1C, PHASE_CAVE_ADDR),
        i(0x09, "t0", "t0", 4),
        branch(0x05, "t0", "t1", LIST_CAVE_ADDR + 0x24, loop),
        0,
        j(STROBE_SKIP),
        0,
        0,
    ]
    return pack(words, LIST_CAVE_LEN)


def phase_cave() -> bytes:
    words = [
        i(0x0F, "zero", "t0", (GAME_TICKS + 0x8000) >> 16),
        i(0x23, "t0", "t1", GAME_TICKS & 0xFFFF),
        0,
        r("zero", "t1", "t1", 1, 0x00),
        j(STROBE_BODY),
        0,
    ]
    return pack(words, PHASE_CAVE_LEN)


def find_exe() -> Path:
    matches = sorted(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(matches) != 1:
        raise SystemExit(f"expected one PROD3 NFS4.EXE, found {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("exe", nargs="?", type=Path)
    args = parser.parse_args()
    exe = args.exe or find_exe()
    data = bytearray(exe.read_bytes())

    if bytes(data[FILTER_OFF:FILTER_OFF + 8]) != FILTER_STOCK:
        raise SystemExit("unexpected strobe dispatcher; use checkpoint C1691 first")
    for off, length, name in (
        (LIST_CAVE_OFF, LIST_CAVE_LEN, "list cave"),
        (PHASE_CAVE_OFF, PHASE_CAVE_LEN, "phase cave"),
    ):
        if any(data[off:off + length]):
            raise SystemExit(f"{name} is occupied; refusing to patch")

    # The delay-slot test is true only for civilian model indices (< 0x16).
    data[FILTER_OFF:FILTER_OFF + 8] = struct.pack(
        "<2I",
        branch(0x05, "s5", "t0", FILTER_ADDR, LIST_CAVE_ADDR),
        i(0x0A, "s7", "t0", 0x16),
    )
    data[LIST_CAVE_OFF:LIST_CAVE_OFF + LIST_CAVE_LEN] = list_cave()
    data[PHASE_CAVE_OFF:PHASE_CAVE_OFF + PHASE_CAVE_LEN] = phase_cave()
    exe.write_bytes(data)
    print(f"patched: {exe}")
    print(f"md5: {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
