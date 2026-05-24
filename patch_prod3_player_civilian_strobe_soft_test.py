#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_civilian_strobe_soft_test"
RUNTIME_BASE = 0x8000F800

# R3DCar_InsertCarFacetII, immediately after the stock cop-flash block.
# Stock:
#   lw v0,0x0E50(gp)
#   nop
HOOK_OFF = 0xA126C
RETURN_ADDR = RUNTIME_BASE + HOOK_OFF + 8

# Free executable cave used only by this test.
CAVE_OFF = 0x457F0
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x90

PLAYER_CAR_OBJ_PTR_ADDR = 0x80110D0C

REG = {
    "zero": 0,
    "v0": 2,
    "t0": 8,
    "t1": 9,
    "s5": 21,
    "gp": 28,
}


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def ori(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0D, REG[rs], REG[rt], imm)


def sh(rt: str, off: int, rs: str) -> int:
    return ins_i(0x29, REG[rs], REG[rt], off)


def nop() -> int:
    return 0


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
            if kind != "bne":
                raise ValueError(kind)
            item = ins_i(0x05, REG[rs], REG[rt], (labels[target] - (pc + 4)) >> 2)
        words.append(item)
        pc += 4
    return pack(words)


def cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        lui("t0", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
        lw("t0", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t0"),
        nop(),
        bne("s5", "t0", "stock"),
        nop(),
        # Force only the lightweight render fields used by the normal strobe
        # animation. Do not enter the cop-only geometry path.
        addiu("t1", "zero", 0x80),
        sh("t1", 0x08B8, "s5"),
        addiu("t1", "zero", 0x88),
        sh("t1", 0x08BA, "s5"),
        lhu("t1", 0x08B4, "s5"),
        ori("t1", "t1", 0x33),
        sh("t1", 0x08B4, "s5"),
        lhu("t1", 0x08B6, "s5"),
        ori("t1", "t1", 0x02),
        sh("t1", 0x08B6, "s5"),
        "stock",
        lw("v0", 0x0E50, "gp"),
        j(RETURN_ADDR),
        nop(),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    stock_hook = pack([lw("v0", 0x0E50, "gp"), nop()])
    patched_hook = pack([j(CAVE_ADDR), nop()])
    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {stock_hook, patched_hook}:
        raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")

    blob = cave()
    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {bytes(CAVE_LEN), blob}:
        raise SystemExit(f"cave is not empty/known at 0x{CAVE_OFF:X}: {current_cave[:16].hex(' ')}")

    if args.revert:
        data[HOOK_OFF : HOOK_OFF + 8] = stock_hook
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    else:
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = blob
        data[HOOK_OFF : HOOK_OFF + 8] = patched_hook

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {hashlib.md5(bytes(data)).hexdigest().upper()}")
    print("player civilian strobe soft test:", "reverted" if args.revert else "patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
