#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_bust_ai_controls_target_guard"
RUNTIME_BASE = 0x8000F800

CONTROLS_CAVE_OFF = 0xE8300
CONTROLS_CAVE_ADDR = RUNTIME_BASE + CONTROLS_CAVE_OFF
CONTROLS_CAVE_LEN = 0x100
CONTROLS_RETURN_STOCK = 0x800601B4

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "s3": 19,
    "ra": 31,
}


def find_exe() -> Path:
    hits = list(Path(".").glob(EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest().upper()


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


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jr(rs: str) -> int:
    return ins_r(REG[rs], 0, 0, 0, 0x08)


def lbu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x24, REG[rs], REG[rt], off)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def nop() -> int:
    return 0


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


def old_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        addiu("t0", "zero", 0),
        addiu("t0", "t0", -1),
        bne("t0", "zero", "stock"),
        nop(),
        lw("v1", 0x0D0C, "v0"),
        beq("v1", "zero", "stock"),
        nop(),
        lhu("t0", 0x043C, "v1"),
        nop(),
        bne("t0", "zero", "return_one"),
        addiu("v1", "v1", 0x043C),
        lbu("t0", 0x0009, "v1"),
        addiu("t1", "zero", 1),
        beq("t0", "t1", "return_one"),
        nop(),
        "stock",
        lw("v1", 0x0D0C, "v0"),
        j(CONTROLS_RETURN_STOCK),
        nop(),
        "return_one",
        jr("ra"),
        addiu("v0", "zero", 1),
    ]
    blob = pack_labeled(items, CONTROLS_CAVE_ADDR)
    return blob + bytes(CONTROLS_CAVE_LEN - len(blob))


def new_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        addiu("t0", "zero", 0),
        addiu("t0", "t0", -1),
        bne("t0", "zero", "stock"),
        nop(),
        lw("v1", 0x0D0C, "v0"),
        beq("v1", "zero", "stock"),
        nop(),
        # Only the perp currently assigned to the player car may consume the
        # player's arrest-control input. This avoids triggering pull-over code
        # on unrelated AI racer/perp objects.
        lw("t2", 0x006C, "s3"),
        nop(),
        bne("t2", "v1", "stock"),
        nop(),
        lw("t2", 0x0000, "s3"),
        nop(),
        beq("t2", "v1", "stock"),
        nop(),
        lhu("t0", 0x043C, "v1"),
        nop(),
        bne("t0", "zero", "return_one"),
        addiu("v1", "v1", 0x043C),
        lbu("t0", 0x0009, "v1"),
        addiu("t1", "zero", 1),
        beq("t0", "t1", "return_one"),
        nop(),
        "stock",
        lw("v1", 0x0D0C, "v0"),
        j(CONTROLS_RETURN_STOCK),
        nop(),
        "return_one",
        jr("ra"),
        addiu("v0", "zero", 1),
    ]
    blob = pack_labeled(items, CONTROLS_CAVE_ADDR)
    if len(blob) > CONTROLS_CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob + bytes(CONTROLS_CAVE_LEN - len(blob))


def main() -> int:
    parser = argparse.ArgumentParser(description="PROD3: target-gate player bust controls.")
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    old = old_cave()
    new = new_cave()
    current = bytes(data[CONTROLS_CAVE_OFF : CONTROLS_CAVE_OFF + CONTROLS_CAVE_LEN])
    if current not in {old, new}:
        raise SystemExit(
            f"controls cave is not old/new at 0x{CONTROLS_CAVE_OFF:X}: "
            f"{current[:16].hex(' ')}"
        )

    if args.revert:
        data[CONTROLS_CAVE_OFF : CONTROLS_CAVE_OFF + CONTROLS_CAVE_LEN] = old
    else:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        data[CONTROLS_CAVE_OFF : CONTROLS_CAVE_OFF + CONTROLS_CAVE_LEN] = new

    if bytes(data) != original:
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(bytes(data))}")
    print("player bust controls target guard:", "reverted" if args.revert else "patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
