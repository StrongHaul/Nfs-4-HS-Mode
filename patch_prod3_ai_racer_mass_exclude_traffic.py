#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from patch_opponent_racers_prod2 import MASS_CAVE_OFF, MASS_HOOK_OFF, runtime
from patch_player_physics_prod import HEAVY_CHEAT_MASS_PREFIX, HEAVY_CHEAT_MULT_PATCHES


BACKUP_SUFFIX = ".orig_prod3_ai_racer_mass_exclude_traffic"
DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
MASS_RETURN_ADDR = 0x800A2750
MASS_CAVE_LEN = 0x70

TON1_TRUCK_COLLISION_MASS_UNITS = 0  # zero keeps each AI racer's calculated stock mass

REG = {
    "zero": 0,
    "v0": 2,
    "a2": 6,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "s0": 16,
}


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_r(rs: int, rt: int, rd: int, sh: int, fn: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (sh << 6) | fn


def ins_j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def addu(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x21)


def andi(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0C, REG[rs], REG[rt], imm)


def ori(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0D, REG[rs], REG[rt], imm)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def nop() -> int:
    return 0


def sll(rd: str, rt: str, shamt: int) -> int:
    return ins_r(0, REG[rt], REG[rd], shamt, 0x00)


def sra(rd: str, rt: str, shamt: int) -> int:
    return ins_r(0, REG[rt], REG[rd], shamt, 0x03)


def sltiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0B, REG[rs], REG[rt], imm)


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


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
    return struct.pack("<" + "I" * len(words), *words)


def mass_cave() -> bytes:
    pc = runtime(MASS_CAVE_OFF)
    items: list[int | str | tuple[str, str, str, str]] = [
        sw("a2", 0x00B8, "s0"),
        lw("t0", 0x0288, "s0"),
        nop(),
        lw("t0", 0x0004, "t0"),
        nop(),
        andi("t0", "t0", 0x0002),
        beq("t0", "zero", "normal"),
        nop(),
        # Keep the live selector at its established cheat address 0x80055450.
        nop(),
        nop(),
        nop(),
        nop(),
        nop(),
        nop(),
        nop(),
        nop(),
        nop(),
        nop(),
        nop(),
        nop(),
        ori("t0", "zero", TON1_TRUCK_COLLISION_MASS_UNITS),
        beq("t0", "zero", "normal"),
        nop(),
        sll("t0", "t0", 10),
        sw("t0", 0x00B8, "s0"),
        "normal",
        j(MASS_RETURN_ADDR),
        nop(),
    ]
    cave = pack_labeled(items, pc)
    if len(cave) > MASS_CAVE_LEN:
        raise SystemExit(f"cave too large: {len(cave)} > {MASS_CAVE_LEN}")
    return cave.ljust(MASS_CAVE_LEN, b"\x00")


def find_prod3_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    exe = find_prod3_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    hook = pack([j(runtime(MASS_CAVE_OFF))])
    actual_hook = bytes(data[MASS_HOOK_OFF : MASS_HOOK_OFF + 4])
    if actual_hook not in [bytes.fromhex("b8 00 06 ae"), hook, pack([j(runtime(0xE8024))])]:
        raise SystemExit(f"unexpected mass hook bytes: {actual_hook.hex(' ')}")

    data[MASS_HOOK_OFF : MASS_HOOK_OFF + 4] = hook
    cave = mass_cave()
    data[MASS_CAVE_OFF : MASS_CAVE_OFF + len(cave)] = cave

    prefix = bytes(data).find(HEAVY_CHEAT_MASS_PREFIX)
    if prefix < 0:
        raise SystemExit("heavy prefix not found")
    mult_off = prefix + len(HEAVY_CHEAT_MASS_PREFIX)
    player_mult = bytes(data[mult_off : mult_off + 8])
    old_player_hook = pack([j(runtime(0x45D00)), nop()])
    if player_mult not in [*HEAVY_CHEAT_MULT_PATCHES.values(), old_player_hook]:
        raise SystemExit(f"unexpected heavy mult bytes: {data[mult_off:mult_off+8].hex(' ')}")
    data[mult_off : mult_off + 8] = HEAVY_CHEAT_MULT_PATCHES["1.5"]

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"patched {exe}")
    print(
        "AI racer collision mass selector defaults to stock mass (zero); nonzero option units are shifted << 10, "
        "gated by carInfo->carClass & 2"
    )
    print("player heavy multiplier restored to stable x1.5")
    print(f"md5 {hashlib.md5(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
