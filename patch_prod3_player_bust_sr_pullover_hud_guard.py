#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_bust_sr_pullover_hud_guard"
RUNTIME_BASE = 0x8000F800

# AIHigh_Player::HandlePullOver, just before:
#   Cars_gList[s1] -> ...
#
# The player-bust-AI cheat can complete a Single Race AI racer arrest while s1
# is garbage. Letting that path index the global car list can hang. Keep the
# stock speech path for every valid car slot, including AI cops, and skip only
# clearly invalid indices.
HOOK_OFF = 0x535DC
RETURN_ADDR = 0x80062DE4
SKIP_ADDR = 0x80062E14
STOCK = bytes.fromhex(
    "11 80 03 3c"  # lui v1,0x8011
    "a0 0c 63 24"  # addiu v1,v1,0x0CA0
)

# First safe word after the 0x800F7A3C jump delay slot and before 0x800F7B00.
CAVE_OFF = 0xE8244
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0xBC
OLD_CAVE_LEN = 0x40

REG = {
    "zero": 0,
    "v1": 3,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "s0": 16,
    "s1": 17,
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


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def sltiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0B, REG[rs], REG[rt], imm)


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
            _, rs, rt, target = item
            item = ins_i(0x04, REG[rs], REG[rt], (labels[target] - (pc + 4)) >> 2)
        words.append(item)
        pc += 4
    return pack(words)


def make_old_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        sltiu("t0", "s1", 2),
        beq("t0", "zero", "skip"),
        nop(),
        lui("v1", 0x8011),
        addiu("v1", "v1", 0x0CA0),
        j(RETURN_ADDR),
        nop(),
        "skip",
        j(SKIP_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, CAVE_ADDR)
    if len(blob) > OLD_CAVE_LEN:
        raise SystemExit(f"old cave too large: 0x{len(blob):X}")
    return blob + bytes(OLD_CAVE_LEN - len(blob))


def make_player_guard_cave(player_index_limit: int) -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        lw("t0", 0x0000, "s0"),      # AIHigh_Base::carObj_
        lui("t1", 0x8011),
        lw("t2", 0x0D0C, "t1"),     # Cars_gHumanRaceCarList[0]
        nop(),
        beq("t0", "t2", "player_car"),
        nop(),
        lw("t2", 0x0D10, "t1"),     # Cars_gHumanRaceCarList[1]
        nop(),
        beq("t0", "t2", "player_car"),
        nop(),
        # AI perps keep the strict historical guard.
        sltiu("t0", "s1", 2),
        beq("t0", "zero", "skip"),
        nop(),
        beq("zero", "zero", "allow"),
        nop(),
        "player_car",
        # The player can be arrested by cop cars with indices >= 2.
        sltiu("t0", "s1", player_index_limit),
        beq("t0", "zero", "skip"),
        nop(),
        "allow",
        lui("v1", 0x8011),
        addiu("v1", "v1", 0x0CA0),
        j(RETURN_ADDR),
        nop(),
        "skip",
        j(SKIP_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, CAVE_ADDR)
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob + bytes(CAVE_LEN - len(blob))


def make_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        sltiu("t0", "s1", 9),
        beq("t0", "zero", "skip"),
        nop(),
        lui("v1", 0x8011),
        addiu("v1", "v1", 0x0CA0),
        j(RETURN_ADDR),
        nop(),
        "skip",
        j(SKIP_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, CAVE_ADDR)
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob + bytes(CAVE_LEN - len(blob))


def main() -> int:
    parser = argparse.ArgumentParser(description="PROD3: guard SR player-bust pull-over HUD index.")
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    hook = pack([j(CAVE_ADDR), nop()])
    cave = make_cave()
    old_cave = make_old_cave() + bytes(CAVE_LEN - OLD_CAVE_LEN)
    previous_player9_cave = make_player_guard_cave(9)
    previous_player8_cave = make_player_guard_cave(8)
    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + len(STOCK)])
    if current_hook not in {STOCK, hook}:
        raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")

    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {bytes(CAVE_LEN), cave, old_cave, previous_player8_cave, previous_player9_cave}:
        raise SystemExit(f"cave is not empty/known at 0x{CAVE_OFF:X}: {current_cave[:16].hex(' ')}")

    if args.revert:
        data[HOOK_OFF : HOOK_OFF + len(STOCK)] = STOCK
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    else:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = cave
        data[HOOK_OFF : HOOK_OFF + len(STOCK)] = hook

    if bytes(data) != original:
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(bytes(data))}")
    print("SR player-bust pull-over HUD guard:", "reverted" if args.revert else "patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
