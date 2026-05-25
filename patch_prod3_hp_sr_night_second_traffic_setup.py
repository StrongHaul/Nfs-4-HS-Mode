#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_hp_sr_night_second_traffic_setup"
RUNTIME_BASE = 0x8000F800

# GameSetup_StartUp, after FrontEndDataStream has been parsed into
# GameSetup_gData and immediately before the stream memory is purged.
HOOK_OFF = 0x08D1C4
RETURN_ADDR = RUNTIME_BASE + HOOK_OFF + 8
PURGEMEMADR_ADDR = 0x800E612C

# Unused aligned area near the optional player-bust caves. This region is
# zeroed in the current stable PROD3 image and is not used by the active patch
# set.
CAVE_OFF = 0x0FFAD0
CAVE_LEN = 0x0240

ENABLE_ADDR = 0x80054B7C
GAMESETUP_DATA_ADDR = 0x801144A4
GAME_TYPE_OFF = 0x0000
NUM_CARS_OFF = 0x03C4
CAR_DATA_ARRAY_OFF = 0x03D4
CAR_DATA_SIZE = 0x00B4
CAR_FLAGS_OFF = 0x0004
PERSONALITY_OFF = 0x0050
TRAFFIC_FLAG = 0x0004
PERSONALITY_TRAFFIC = 8
SINGLE_RACE_GAME_TYPE = 0
HOT_PURSUIT_GAME_TYPE = 1
MAX_CARS = 9

REG = {
    "zero": 0,
    "a0": 4,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "t3": 11,
    "t4": 12,
    "t5": 13,
    "t6": 14,
    "t7": 15,
    "s2": 18,
    "t8": 24,
    "t9": 25,
}


Branch = tuple[str, str, str, str]
Item = int | str | Branch


def runtime(off: int) -> int:
    return RUNTIME_BASE + off


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


def beq(rs: str, rt: str, target: str) -> Branch:
    return ("beq", rs, rt, target)


def bne(rs: str, rt: str, target: str) -> Branch:
    return ("bne", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jal(addr: int) -> int:
    return ins_j(0x03, addr)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def slti(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0A, REG[rs], REG[rt], imm)


def nop() -> int:
    return 0


def hi(addr: int) -> int:
    return (addr >> 16) & 0xFFFF


def lo(addr: int) -> int:
    return addr & 0xFFFF


def pack_labeled(items: list[Item], base_pc: int) -> bytes:
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
    items: list[Item] = [
        lui("t0", hi(ENABLE_ADDR)),
        lhu("t1", lo(ENABLE_ADDR), "t0"),
        beq("t1", "zero", "finish"),
        nop(),
        lui("t0", hi(GAMESETUP_DATA_ADDR)),
        addiu("t0", "t0", lo(GAMESETUP_DATA_ADDR)),
        lw("t1", GAME_TYPE_OFF, "t0"),
        beq("t1", "zero", "mode_ok"),
        nop(),
        addiu("t6", "zero", HOT_PURSUIT_GAME_TYPE),
        bne("t1", "t6", "finish"),
        nop(),
        "mode_ok",
        lw("t1", NUM_CARS_OFF, "t0"),
        slti("t6", "t1", 1),
        bne("t6", "zero", "finish"),
        nop(),
        slti("t6", "t1", MAX_CARS),
        beq("t6", "zero", "finish"),
        nop(),
        addiu("t2", "t0", CAR_DATA_ARRAY_OFF),
        addiu("t3", "zero", 0),
        addiu("t4", "zero", 0),
        addiu("t5", "zero", 0),
        "scan_loop",
        beq("t5", "t1", "scan_done"),
        nop(),
        lw("t6", CAR_FLAGS_OFF, "t2"),
        nop(),
        andi("t6", "t6", TRAFFIC_FLAG),
        beq("t6", "zero", "not_traffic"),
        nop(),
        addiu("t3", "t3", 1),
        addu("t4", "t2", "zero"),
        "not_traffic",
        addiu("t5", "t5", 1),
        beq("zero", "zero", "scan_loop"),
        addiu("t2", "t2", CAR_DATA_SIZE),
        "scan_done",
        addiu("t6", "zero", 1),
        bne("t3", "t6", "finish"),
        nop(),
        beq("t4", "zero", "finish"),
        nop(),
        # t2 now points at the first free carData slot because the scan loop
        # advances it after each visited car.
        addu("t8", "t4", "zero"),
        addu("t9", "t2", "zero"),
        addiu("t6", "zero", CAR_DATA_SIZE // 4),
        "copy_loop",
        lw("t7", 0x0000, "t8"),
        addiu("t8", "t8", 4),
        sw("t7", 0x0000, "t9"),
        addiu("t9", "t9", 4),
        addiu("t6", "t6", -1),
        bne("t6", "zero", "copy_loop"),
        nop(),
        addiu("t6", "zero", TRAFFIC_FLAG),
        sw("t6", CAR_FLAGS_OFF, "t2"),
        addiu("t6", "zero", PERSONALITY_TRAFFIC),
        sw("t6", PERSONALITY_OFF, "t2"),
        addiu("t1", "t1", 1),
        sw("t1", NUM_CARS_OFF, "t0"),
        "finish",
        jal(PURGEMEMADR_ADDR),
        addu("a0", "s2", "zero"),
        j(RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, runtime(CAVE_OFF))
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X} > 0x{CAVE_LEN:X}")
    return blob.ljust(CAVE_LEN, b"\x00")


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "PROD3: with 80054B7C enabled, duplicate the single night traffic "
            "car after GameSetup parses the frontend stream."
        )
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    stock_hook = pack([jal(PURGEMEMADR_ADDR), addu("a0", "s2", "zero")])
    patched_hook = pack([j(runtime(CAVE_OFF)), addu("a0", "s2", "zero")])
    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {stock_hook, patched_hook}:
        raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")

    blob = cave()
    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {b"\x00" * CAVE_LEN, blob}:
        raise SystemExit(f"cave is not empty/known at 0x{CAVE_OFF:X}: {current_cave[:16].hex(' ')}")

    if args.revert:
        data[HOOK_OFF : HOOK_OFF + 8] = stock_hook
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = b"\x00" * CAVE_LEN
    else:
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = blob
        data[HOOK_OFF : HOOK_OFF + 8] = patched_hook

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(("reverted" if args.revert else "patched"), exe)
    print(f"hook runtime 0x{runtime(HOOK_OFF):08X} -> cave 0x{runtime(CAVE_OFF):08X}")
    print("80054B7C enabled: SR/HP with exactly one traffic car gets a second cloned traffic slot")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
