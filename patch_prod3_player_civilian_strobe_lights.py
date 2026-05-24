#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_civilian_strobe_lights"
RUNTIME_BASE = 0x8000F800

# R3DCar_InsertCarFacetII: stock cop-car gate before the palCopy strobe block.
HOOK_OFF = 0xA11D8
HOOK_ADDR = RUNTIME_BASE + HOOK_OFF

# Free zero area in the low executable cave range.
CAVE_OFF = 0x457F0
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x90

STOCK_ON_ADDR = 0x800B09E0
FORCE_ON_ADDR = 0x800B09F4
FORCE_OFF_ADDR = 0x800B0A34
SKIP_ADDR = 0x800B0A6C

PLAYER_CAR_OBJ_PTR_ADDR = 0x80110D0C
PLAYER_BUST_CHEAT_ADDR = 0x800F7A00

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "t0": 8,
    "t1": 9,
    "s5": 21,
    "s6": 22,
}


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


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
            op = 0x04 if kind == "beq" else 0x05
            item = ins_i(op, REG[rs], REG[rt], (labels[target] - (pc + 4)) >> 2)
        words.append(item)
        pc += 4
    return pack(words)


def cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Keep stock behavior for real cop cars.
        bne("s6", "zero", "stock_on"),
        lui("t0", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
        # For civilian cars, only player 1 can borrow the cop strobe block.
        lw("t0", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t0"),
        lui("t1", hi(PLAYER_BUST_CHEAT_ADDR)),
        bne("s5", "t0", "skip"),
        lhu("t1", lo(PLAYER_BUST_CHEAT_ADDR), "t1"),
        addiu("t1", "t1", -1),
        bne("t1", "zero", "force_off"),
        nop(),
        # Cheat active: enter the stock "speechSource & 2 is true" path.
        j(FORCE_ON_ADDR),
        nop(),
        # Cheat inactive: clear any palCopy strobe state we may have left.
        "force_off",
        j(FORCE_OFF_ADDR),
        nop(),
        "skip",
        j(SKIP_ADDR),
        nop(),
        "stock_on",
        j(STOCK_ON_ADDR),
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


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: let player civilian cars use cop-style strobe light flashing while player-arrest cheat is active."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    stock_hook = pack([beq_word := ins_i(0x04, REG["s6"], REG["zero"], 0x24), nop()])
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

    print(f"NFS4.EXE {md5(bytes(data))}")
    print("player civilian strobe lights:", "reverted" if args.revert else "patched")
    print("controlled by existing player-arrest cheat: 800F7A00 0001")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
