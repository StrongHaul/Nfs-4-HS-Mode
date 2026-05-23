#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_bust_ai_safe_no_cops_guard"
RUNTIME_BASE = 0x8000F800

NO_COPS_GUARD_CAVE_OFF = 0xE8400
NO_COPS_GUARD_CAVE_ADDR = RUNTIME_BASE + NO_COPS_GUARD_CAVE_OFF
NO_COPS_GUARD_CAVE_LEN = 0x80
NO_COPS_GUARD_CONTINUE_ADDR = 0x800632E4
NO_COPS_GUARD_RETURN_ADDR = 0x8006343C
CANDIDATE_CAVE_ADDR = 0x800F7A00

REG = {
    "zero": 0,
    "v0": 2,
    "t0": 8,
    "t1": 9,
    "s2": 18,
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


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def srl(rd: str, rt: str, sh: int) -> int:
    return ins_r(0, REG[rt], REG[rd], sh, 0x02)


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


def old_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        bne("v0", "zero", "continue"),
        nop(),
        lui("t0", hi(CANDIDATE_CAVE_ADDR)),
        lhu("t0", lo(CANDIDATE_CAVE_ADDR), "t0"),
        nop(),
        beq("t0", "zero", "return"),
        nop(),
        "continue",
        j(NO_COPS_GUARD_CONTINUE_ADDR),
        nop(),
        "return",
        j(NO_COPS_GUARD_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, NO_COPS_GUARD_CAVE_ADDR)
    return blob + bytes(NO_COPS_GUARD_CAVE_LEN - len(blob))


def new_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        bne("v0", "zero", "continue"),
        nop(),
        lui("t0", hi(CANDIDATE_CAVE_ADDR)),
        lhu("t0", lo(CANDIDATE_CAVE_ADDR), "t0"),
        nop(),
        beq("t0", "zero", "return"),
        nop(),
        # The old bypass continued even when the cop/update pointer loaded into
        # s2 was not initialized. That can freeze SR/HP races with AI racers.
        srl("t1", "s2", 24),
        addiu("t0", "zero", 0x80),
        bne("t1", "t0", "return"),
        nop(),
        "continue",
        j(NO_COPS_GUARD_CONTINUE_ADDR),
        nop(),
        "return",
        j(NO_COPS_GUARD_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, NO_COPS_GUARD_CAVE_ADDR)
    if len(blob) > NO_COPS_GUARD_CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob + bytes(NO_COPS_GUARD_CAVE_LEN - len(blob))


def main() -> int:
    parser = argparse.ArgumentParser(description="PROD3: guard player-bust no-cops bypass.")
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    old = old_cave()
    new = new_cave()
    current = bytes(data[NO_COPS_GUARD_CAVE_OFF : NO_COPS_GUARD_CAVE_OFF + NO_COPS_GUARD_CAVE_LEN])
    if current not in {old, new}:
        raise SystemExit(
            f"no-cops guard cave is not old/new at 0x{NO_COPS_GUARD_CAVE_OFF:X}: "
            f"{current[:16].hex(' ')}"
        )

    if args.revert:
        data[NO_COPS_GUARD_CAVE_OFF : NO_COPS_GUARD_CAVE_OFF + NO_COPS_GUARD_CAVE_LEN] = old
    else:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        data[NO_COPS_GUARD_CAVE_OFF : NO_COPS_GUARD_CAVE_OFF + NO_COPS_GUARD_CAVE_LEN] = new

    if bytes(data) != original:
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(bytes(data))}")
    print("player bust AI no-cops guard:", "reverted" if args.revert else "patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
