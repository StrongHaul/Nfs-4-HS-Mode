#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_car_30114878_sync"
RUNTIME_BASE = 0x8000F800

# Car object setup loop. The stock delay slot computes:
#   v0 = raceSetupBase + 0x3D4 + slot * 0xB4
# and the hook stores that carData pointer into Car_tObj+0x288.
#
# External DuckStation/GameShark car replacement cheats commonly write only
# the player primary setup byte at 0x80114878. In SR/HP that can leave the
# replay/setup mirror and the word-sized car id field inconsistent. Sync the
# player slot right before the car object is initialized, without touching the
# shared renderer at 0x800C19FC.
HOOK_OFF = 0x7B8DC
RETURN_ADDR = 0x8008B0E4
STOCK = bytes.fromhex(
    "21 10 42 02"  # addu v0,s2,v0
    "88 02 02 ae"  # sw v0,0x288(s0)
)

OLD_CAVE_OFF = 0xE8024
OLD_CAVE_ADDR = RUNTIME_BASE + OLD_CAVE_OFF
OLD_CAVE = bytes.fromhex(
    "02 00 08 24"  # addiu t0,zero,2
    "02 00 28 16"  # bne s1,t0,store
    "00 00 00 00"  # nop
    "88 04 62 26"  # addiu v0,s3,0x488
    "88 02 02 ae"  # sw v0,0x288(s0)
    "39 2c 02 08"  # j 0x8008B0E4
)
OLD_CAVE_LEN = len(OLD_CAVE)

CAVE_OFF = 0xE8500
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x58

PLAYER_SLOT = 0
SECOND_AI_SLOT = 2
FIRST_AI_CARDATA_OFF_FROM_SETUP_BASE = 0x488
PLAYER_MIRROR_CAR_ID_ADDR = 0x801187F8

REG = {
    "zero": 0,
    "v0": 2,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "s0": 16,
    "s1": 17,
    "s2": 18,
    "s3": 19,
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


def addu(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x21)


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


def lbu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x24, REG[rs], REG[rt], off)


def sb(rt: str, off: int, rs: str) -> int:
    return ins_i(0x28, REG[rs], REG[rt], off)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def nop() -> int:
    return 0


def hi(addr: int) -> int:
    return ((addr + 0x8000) >> 16) & 0xFFFF


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


def make_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # The hook delay slot has already computed the stock carData pointer.
        addiu("t0", "zero", PLAYER_SLOT),
        bne("s1", "t0", "check_second_ai"),
        nop(),
        # GameShark 30xxxxxx codes write one byte. Normalize the primary
        # word's low byte and mirror it into the replay/setup copy.
        lbu("t1", 0, "v0"),
        sw("zero", 0, "v0"),
        sb("t1", 0, "v0"),
        lui("t2", hi(PLAYER_MIRROR_CAR_ID_ADDR)),
        sw("zero", lo(PLAYER_MIRROR_CAR_ID_ADDR), "t2"),
        sb("t1", lo(PLAYER_MIRROR_CAR_ID_ADDR), "t2"),
        beq("zero", "zero", "store"),
        nop(),
        "check_second_ai",
        # Preserve the existing PROD3 behavior: second AI shares first AI carData.
        addiu("t0", "zero", SECOND_AI_SLOT),
        bne("s1", "t0", "store"),
        nop(),
        addiu("v0", "s3", FIRST_AI_CARDATA_OFF_FROM_SETUP_BASE),
        "store",
        sw("v0", 0x0288, "s0"),
        j(RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, CAVE_ADDR)
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob + bytes(CAVE_LEN - len(blob))


def main() -> int:
    parser = argparse.ArgumentParser(description="PROD3: sync player 30114878 car cheat before car init.")
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    old_hook = pack([j(OLD_CAVE_ADDR), addu("v0", "s2", "v0")])
    new_hook = pack([j(CAVE_ADDR), addu("v0", "s2", "v0")])
    cave = make_cave()

    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + len(STOCK)])
    if current_hook not in {STOCK, old_hook, new_hook}:
        raise SystemExit(f"unexpected carData hook bytes: {current_hook.hex(' ')}")

    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {bytes(CAVE_LEN), cave}:
        raise SystemExit(f"new cave is not empty/known at 0x{CAVE_OFF:X}: {current_cave[:16].hex(' ')}")

    current_old_cave = bytes(data[OLD_CAVE_OFF : OLD_CAVE_OFF + OLD_CAVE_LEN])
    if current_hook == old_hook and current_old_cave != OLD_CAVE:
        raise SystemExit(f"old cave is not the known second-AI stub: {current_old_cave.hex(' ')}")

    if args.revert:
        data[HOOK_OFF : HOOK_OFF + len(STOCK)] = old_hook
        data[OLD_CAVE_OFF : OLD_CAVE_OFF + OLD_CAVE_LEN] = OLD_CAVE
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    else:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        data[HOOK_OFF : HOOK_OFF + len(STOCK)] = new_hook
        data[OLD_CAVE_OFF : OLD_CAVE_OFF + OLD_CAVE_LEN] = bytes(OLD_CAVE_LEN)
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = cave

    if bytes(data) != original:
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(bytes(data))}")
    print("player 30114878 car cheat sync:", "reverted" if args.revert else "patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
