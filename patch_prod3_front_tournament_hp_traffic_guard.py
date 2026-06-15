#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


FRONT_GLOB = "PROD 3*/FRONT.BIN"
BACKUP_SUFFIX = ".orig_before_prod3_front_tournament_hp_traffic_guard"
RUNTIME_BASE = 0x80010000

PATCH_OFF = 0x18514
PATCH_LEN = 0x2C

SKIP_ADDR = RUNTIME_BASE + 0x185F0
FRONTEND_BASE_HI = 0x8011
FRONTEND_RACE_TYPE_LO = 0x58BC
TOURNAMENT_MANAGER_NUM_RACERS_LO = 0x4AE8

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "a1": 5,
    "t0": 8,
    "s1": 17,
    "s4": 20,
}


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def addu(rd: str, rs: str, rt: str) -> int:
    return (REG[rs] << 21) | (REG[rt] << 16) | (REG[rd] << 11) | 0x21


def beq(rs: str, rt: str, pc: int, target: int) -> int:
    return ins_i(0x04, REG[rs], REG[rt], (target - (pc + 4)) >> 2)


def bne(rs: str, rt: str, pc: int, target: int) -> int:
    return ins_i(0x05, REG[rs], REG[rt], (target - (pc + 4)) >> 2)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lbu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x24, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


STOCK = bytes.fromhex(
    "11 80 02 3c"  # lui v0,0x8011
    "bc 58 43 90"  # lbu v1,0x58bc(v0) ; frontEnd.raceType
    "02 00 02 24"  # addiu v0,zero,2
    "33 00 62 14"  # bne v1,v0,skip
    "00 00 00 00"  # nop
    "04 00 a2 90"  # lbu v0,4(a1) ; fTraffic
    "00 00 00 00"  # nop
    "2f 00 40 10"  # beq v0,zero,skip
    "21 88 00 00"  # addu s1,zero,zero
    "11 80 02 3c"  # lui v0,0x8011
    "2c 55 54 24"  # addiu s4,v0,0x552c
)


def runtime(off: int) -> int:
    return RUNTIME_BASE + off


PATCHED = pack(
    [
        lui("t0", FRONTEND_BASE_HI),
        lbu("v1", FRONTEND_RACE_TYPE_LO, "t0"),
        addiu("v0", "zero", 2),
        bne("v1", "v0", runtime(0x18520), SKIP_ADDR),
        lw("v1", TOURNAMENT_MANAGER_NUM_RACERS_LO, "t0"),
        addiu("v0", "zero", 6),
        bne("v1", "v0", runtime(0x1852C), SKIP_ADDR),
        lbu("v0", 4, "a1"),
        beq("v0", "zero", runtime(0x18534), SKIP_ADDR),
        addu("s1", "zero", "zero"),
        addiu("s4", "t0", 0x552C),
    ]
)

PREVIOUS_TIER_PATCHED = pack(
    [
        lui("t0", FRONTEND_BASE_HI),
        lbu("v1", FRONTEND_RACE_TYPE_LO, "t0"),
        addiu("v0", "zero", 2),
        bne("v1", "v0", runtime(0x18520), SKIP_ADDR),
        lbu("v1", 0x5922, "t0"),
        bne("v1", "zero", runtime(0x18528), SKIP_ADDR),
        lbu("v0", 4, "a1"),
        beq("v0", "zero", runtime(0x18530), SKIP_ADDR),
        addu("s1", "zero", "zero"),
        addiu("s4", "t0", 0x552C),
        0,
    ]
)

PREVIOUS_PATCHED = pack(
    [
        lui("t0", FRONTEND_BASE_HI),
        lbu("v1", FRONTEND_RACE_TYPE_LO, "t0"),
        addiu("v0", "zero", 2),
        bne("v1", "v0", runtime(0x18520), SKIP_ADDR),
        lbu("v1", 0x58BB, "t0"),
        addiu("v0", "zero", 1),
        beq("v1", "v0", runtime(0x1852C), SKIP_ADDR),
        lbu("v0", 4, "a1"),
        beq("v0", "zero", runtime(0x18534), SKIP_ADDR),
        addu("s1", "zero", "zero"),
        addiu("s4", "t0", 0x552C),
    ]
)

WRONG_TIER_ADDR_PATCHED = pack(
    [
        lui("t0", FRONTEND_BASE_HI),
        lbu("v1", FRONTEND_RACE_TYPE_LO, "t0"),
        addiu("v0", "zero", 2),
        bne("v1", "v0", runtime(0x18520), SKIP_ADDR),
        lbu("v1", 0x59DA, "t0"),
        bne("v1", "zero", runtime(0x18528), SKIP_ADDR),
        lbu("v0", 4, "a1"),
        beq("v0", "zero", runtime(0x18530), SKIP_ADDR),
        addu("s1", "zero", "zero"),
        addiu("s4", "t0", 0x552C),
        0,
    ]
)


def find_front() -> Path:
    hits = list(Path(".").glob(FRONT_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {FRONT_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: skip Tournament traffic unless tournament has six racers."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    front = find_front()
    original = front.read_bytes()
    data = bytearray(original)

    current = bytes(data[PATCH_OFF : PATCH_OFF + PATCH_LEN])
    if current not in {
        STOCK,
        PATCHED,
        PREVIOUS_PATCHED,
        PREVIOUS_TIER_PATCHED,
        WRONG_TIER_ADDR_PATCHED,
    }:
        raise SystemExit(f"unexpected bytes at 0x{PATCH_OFF:X}: {current.hex(' ')}")

    backup = front.with_name(front.name + BACKUP_SUFFIX)
    if args.revert:
        data[PATCH_OFF : PATCH_OFF + PATCH_LEN] = STOCK
    else:
        if not backup.exists():
            backup.write_bytes(original)
        data[PATCH_OFF : PATCH_OFF + PATCH_LEN] = PATCHED

    if bytes(data) != original:
        front.write_bytes(data)

    print(("reverted" if args.revert else "patched"), front)
    print("Tournament traffic: enabled only when tournamentManager.fNumRacers == 6")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
