#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_light_object_visibility_blink"
RUNTIME_BASE = 0x8000F800

# R3DCar_InsertCarFacet: first object-visibility loop, just before it stores
# the computed per-object visibility byte into data_80117B64[s4].
# This is below the car object filters, so we avoid DrawC_PrimStart entirely.
HOOK_OFF = 0xA1B04
HOOK_ADDR = RUNTIME_BASE + HOOK_OFF
RETURN_ADDR = 0x800B130C

# Free low executable cave; kept clear of the existing 0x457F0 strobe cave.
CAVE_OFF = 0x45000
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x180

PLAYER_CAR_OBJ_PTR_ADDR = 0x80110D0C
PLAYER_STROBE_COUNTER_ADDR = 0x800550FC

REG = {
    "zero": 0,
    "v0": 2,
    "a0": 4,
    "a1": 5,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "t3": 11,
    "s4": 20,
    "s5": 21,
    "s7": 23,
    "sp": 29,
}


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


def ins_r(rs: int, rt: int, rd: int, sh: int, fn: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (sh << 6) | fn


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def andi(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0C, REG[rs], REG[rt], imm)


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def nop() -> int:
    return 0


def sb(rt: str, off: int, rs: str) -> int:
    return ins_i(0x28, REG[rs], REG[rt], off)


def slti(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0A, REG[rs], REG[rt], imm)


def sltiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0B, REG[rs], REG[rt], imm)


def srl(rd: str, rt: str, shamt: int) -> int:
    return ins_r(0, REG[rt], REG[rd], shamt, 0x02)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def hi(addr: int) -> int:
    return (addr >> 16) & 0xFFFF


def lo(addr: int) -> int:
    return addr & 0xFFFF


def pack_labeled(items: list[int | str | tuple[str, str, str, str]], base_pc: int) -> bytes:
    labels: dict[str, int] = {}
    pc = base_pc
    for item in items:
        if isinstance(item, str):
            labels[item] = pc
        else:
            pc += 4

    words: list[int] = []
    pc = base_pc
    for item in items:
        if isinstance(item, str):
            continue
        if isinstance(item, tuple):
            kind, rs, rt, target = item
            op = 0x04 if kind == "beq" else 0x05
            item = ins_i(op, REG[rs], REG[rt], (labels[target] - (pc + 4)) >> 2)
        words.append(item)
        pc += 4
    return pack(words)


def restore_and_return() -> list[int]:
    return [
        lw("t0", 0, "sp"),
        lw("t1", 4, "sp"),
        lw("t2", 8, "sp"),
        lw("t3", 12, "sp"),
        addiu("sp", "sp", 16),
        addiu("a0", "a0", 6),
        j(RETURN_ADDR),
        nop(),
    ]


def make_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        addiu("sp", "sp", -16),
        sw("t0", 0, "sp"),
        sw("t1", 4, "sp"),
        sw("t2", 8, "sp"),
        sw("t3", 12, "sp"),
        # Only player car, only civilian slots.
        lui("t0", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
        lw("t1", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t0"),
        nop(),
        bne("s5", "t1", "store"),
        nop(),
        slti("t1", "s7", 0x16),
        beq("t1", "zero", "store"),
        nop(),
        # Target the six early light-ish object slots handled by the secondary
        # visibility switch: s4 = 6..11. Preserve stock a1 on the active side
        # so flare type/color stays original; zero it only on hidden phases.
        addiu("t1", "s4", -6),
        sltiu("t2", "t1", 6),
        beq("t2", "zero", "store"),
        nop(),
        lui("t2", hi(PLAYER_STROBE_COUNTER_ADDR)),
        lw("t2", lo(PLAYER_STROBE_COUNTER_ADDR), "t2"),
        nop(),
        srl("t2", "t2", 3),
        andi("t2", "t2", 0x0007),
        slti("t3", "t2", 2),
        bne("t3", "zero", "left_on"),
        nop(),
        addiu("t3", "t2", -3),
        sltiu("t3", "t3", 2),
        bne("t3", "zero", "right_on"),
        nop(),
        # Off gap: hide all six objects.
        beq("zero", "zero", "hide"),
        nop(),
        "left_on",
        # Treat even s4 slots as the left side, odd as right. If this pair
        # mapping is reversed on a specific model, the rhythm still alternates;
        # only left/right naming would be swapped.
        andi("t3", "s4", 1),
        bne("t3", "zero", "hide"),
        nop(),
        beq("zero", "zero", "store"),
        nop(),
        "right_on",
        andi("t3", "s4", 1),
        beq("t3", "zero", "hide"),
        nop(),
        beq("zero", "zero", "store"),
        nop(),
        "hide",
        addiu("a1", "zero", 0),
        "store",
        sb("a1", 0, "v0"),
        *restore_and_return(),
    ]
    blob = pack_labeled(items, CAVE_ADDR)
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob + bytes(CAVE_LEN - len(blob))


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: blink player light objects by overriding the object visibility byte."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    stock_hook = pack([sb("a1", 0, "v0"), addiu("a0", "a0", 6)])
    patched_hook = pack([j(CAVE_ADDR), nop()])
    cave = make_cave()

    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {stock_hook, patched_hook}:
        raise SystemExit(f"unexpected object visibility hook bytes: {current_hook.hex(' ')}")

    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {bytes(CAVE_LEN), cave}:
        raise SystemExit(f"cave is not empty/known at 0x{CAVE_OFF:X}: {current_cave[:16].hex(' ')}")

    if args.revert:
        data[HOOK_OFF : HOOK_OFF + 8] = stock_hook
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    else:
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = cave
        data[HOOK_OFF : HOOK_OFF + 8] = patched_hook

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(bytes(data))}")
    print("player light object visibility blink:", "reverted" if args.revert else "patched")
    print("no DrawC hook; no cheat gate; AI/cops/traffic are not touched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
