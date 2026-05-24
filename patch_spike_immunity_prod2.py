#!/usr/bin/env python3
from __future__ import annotations

import argparse
import struct
from pathlib import Path


BACKUP_SUFFIX = ".orig_spike_immunity_prod2"
DEFAULT_EXE_GLOB = "PROD 2*/NFS4.EXE"
RUNTIME_BASE = 0x8000F800

# Retail/PROD2 mapping from the Feb 23, 1999 prototype symbols:
#   Debug: Newton_CheckForSpikeBelts__FP13BO_tNewtonObj = 0x800A2A2C
#   PROD2: same function body signature is at file 0x93D38 / runtime 0x800A3538.
SPIKE_FUNC_OFF = 0x93D38
SPIKE_CONTINUE_ADDR = 0x800A3540
SPIKE_CAVE_OFF = 0x45C70

HUMAN_RACE_LIST_LOW = 0x0D0C
AIRACE_LIST_LOW = 0x0D30
HUMAN_RACE_COUNT_LOW = 0xDAF4
AIRACE_COUNT_LOW = 0xDAF8


REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "a0": 4,
    "a1": 5,
    "a2": 6,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "sp": 29,
    "ra": 31,
}


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_r(rs: int, rt: int, rd: int, sh: int, fn: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (sh << 6) | fn


def ins_j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


def runtime(off: int) -> int:
    return RUNTIME_BASE + off


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def addu(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x21)


def beq(rs: str, rt: str, pc: int, target: int) -> int:
    return ins_i(0x04, REG[rs], REG[rt], (target - (pc + 4)) >> 2)


def bne(rs: str, rt: str, pc: int, target: int) -> int:
    return ins_i(0x05, REG[rs], REG[rt], (target - (pc + 4)) >> 2)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jr(reg: str) -> int:
    return ins_r(REG[reg], 0, 0, 0, 0x08)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def nop() -> int:
    return 0


def spike_cave() -> bytes:
    pc = runtime(SPIKE_CAVE_OFF)
    check_airace = pc + 0x30
    human_loop = pc + 0x18
    airace_loop = pc + 0x48
    normal = pc + 0x60
    protected = pc + 0x70
    words = [
        lui("t0", 0x8011),
        addiu("t0", "t0", HUMAN_RACE_LIST_LOW),
        lui("t1", 0x8014),
        lw("t1", HUMAN_RACE_COUNT_LOW, "t1"),
        beq("t1", "zero", pc + 0x10, check_airace),
        nop(),
        lw("t2", 0x0000, "t0"),
        addiu("t0", "t0", 4),
        beq("t2", "a0", pc + 0x20, protected),
        addiu("t1", "t1", -1),
        bne("t1", "zero", pc + 0x28, human_loop),
        nop(),
        lui("t0", 0x8011),
        addiu("t0", "t0", AIRACE_LIST_LOW),
        lui("t1", 0x8014),
        lw("t1", AIRACE_COUNT_LOW, "t1"),
        beq("t1", "zero", pc + 0x40, normal),
        nop(),
        lw("t2", 0x0000, "t0"),
        addiu("t0", "t0", 4),
        beq("t2", "a0", pc + 0x50, protected),
        addiu("t1", "t1", -1),
        bne("t1", "zero", pc + 0x58, airace_loop),
        nop(),
        addiu("sp", "sp", -16),
        addu("a1", "a0", "zero"),
        j(SPIKE_CONTINUE_ADDR),
        nop(),
        jr("ra"),
        nop(),
    ]
    return pack(words)


def old_spike_cave_wrong_branch_targets() -> bytes:
    pc = runtime(SPIKE_CAVE_OFF)
    check_airace = pc + 0x2C
    human_loop = pc + 0x10
    airace_loop = pc + 0x3C
    normal = pc + 0x54
    protected = pc + 0x64
    words = [
        lui("t0", 0x8011),
        addiu("t0", "t0", HUMAN_RACE_LIST_LOW),
        lui("t1", 0x8014),
        lw("t1", HUMAN_RACE_COUNT_LOW, "t1"),
        beq("t1", "zero", pc + 0x10, check_airace),
        nop(),
        lw("t2", 0x0000, "t0"),
        addiu("t0", "t0", 4),
        beq("t2", "a0", pc + 0x20, protected),
        addiu("t1", "t1", -1),
        bne("t1", "zero", pc + 0x28, human_loop),
        nop(),
        lui("t0", 0x8011),
        addiu("t0", "t0", AIRACE_LIST_LOW),
        lui("t1", 0x8014),
        lw("t1", AIRACE_COUNT_LOW, "t1"),
        beq("t1", "zero", pc + 0x40, normal),
        nop(),
        lw("t2", 0x0000, "t0"),
        addiu("t0", "t0", 4),
        beq("t2", "a0", pc + 0x50, protected),
        addiu("t1", "t1", -1),
        bne("t1", "zero", pc + 0x58, airace_loop),
        nop(),
        addiu("sp", "sp", -16),
        addu("a1", "a0", "zero"),
        j(SPIKE_CONTINUE_ADDR),
        nop(),
        jr("ra"),
        nop(),
    ]
    return pack(words)


def find_default_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def patch_at(data: bytearray, off: int, old_options: list[bytes], new: bytes, name: str, apply: bool) -> None:
    actual = bytes(data[off : off + len(new)])
    if actual == new:
        print(f"{name}: already patched at 0x{off:X}")
        return
    if actual not in old_options:
        expected = " or ".join(x.hex(" ") for x in old_options)
        raise SystemExit(f"{name}: unexpected bytes at 0x{off:X}: {actual.hex(' ')}; expected {expected}")
    print(f"{name}: patch 0x{off:X}: {actual.hex(' ')} -> {new.hex(' ')}")
    if apply:
        data[off : off + len(new)] = new


def apply_patch(path: Path, apply: bool, revert: bool) -> None:
    original = path.read_bytes()
    data = bytearray(original)

    original_start = bytes.fromhex("f0 ff bd 27 21 28 80 00")
    hook = pack([j(runtime(SPIKE_CAVE_OFF)), nop()])
    cave = spike_cave()
    old_wrong_cave = old_spike_cave_wrong_branch_targets()

    patch_at(
        data,
        SPIKE_FUNC_OFF,
        [hook, original_start],
        original_start if revert else hook,
        "Newton_CheckForSpikeBelts entry hook",
        apply,
    )

    patch_at(
        data,
        SPIKE_CAVE_OFF,
        [b"\x00" * len(cave), cave, old_wrong_cave],
        b"\x00" * len(cave) if revert else cave,
        "player/racer spike immunity cave",
        apply,
    )

    if apply and bytes(data) != original:
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        path.write_bytes(data)
        print(f"done: patched {path}")
    elif not apply:
        print("dry run only; pass --apply to write changes")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patch PROD2 NFS4.EXE: player and racer bots ignore police spike belts."
    )
    parser.add_argument("--exe", type=Path, help="Path to PROD2 NFS4.EXE")
    parser.add_argument("--apply", action="store_true", help="Write patched EXE")
    parser.add_argument("--revert", action="store_true", help="Remove this spike-immunity patch")
    args = parser.parse_args()

    apply_patch(args.exe or find_default_exe(), args.apply, args.revert)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
