#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


BACKUP_SUFFIX = ".orig_before_prod3_hot_pursuit_raceway_traffic"
DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
RUNTIME_BASE = 0x8000F800

CARS_STARTUP_HOOK_OFF = 0x7B864
CARS_STARTUP_RETURN_ADDR = RUNTIME_BASE + CARS_STARTUP_HOOK_OFF + 8
AICOP_STARTUP_CALL_OFF = 0xA7AD4
AICOP_STARTUP_ADDR = 0x800671AC
AICOP_STARTUP_RETURN_ADDR = RUNTIME_BASE + AICOP_STARTUP_CALL_OFF + 8
TRAFFIC_RUNTIME_FLAG_ORI_OFF = 0x7778C
TRAFFIC_RESPAWN_BASE_STORE_OFF = 0x587C4
TRAFFIC_LIVE_AREA_CHECK_OFF = 0x58650
LEGACY_CAVE_OFF = 0x45200
LEGACY_CAVE_LEN = 0x180
HP_SECOND_RACER_CAVE_OFF = 0x44400
HP_SECOND_RACER_CAVE_LEN = 0x300
PRE_AICOP_CAVE_OFF = 0x45000
PRE_AICOP_CAVE_LEN = 0x180
CAVE_OFF = 0x45600
CAVE_LEN = 0x300
ENABLE_ADDR = 0x80054B7C

GAMESETUP_DATA_ADDR = 0x801144A4
GAME_TYPE_OFF = 0x0000
NUM_CARS_OFF = 0x03C4
COP_AI_ENABLE_OFF = 0x0014
NUM_OPPONENT_RACE_CARS_OFF = 0x03CC
CAR_DATA_ARRAY_OFF = 0x03D4
CAR_DATA_SIZE = 0x00B4
CAR_FLAGS_OFF = 0x0004
PERSONALITY_OFF = 0x0050
STARTING_POS_OFF = 0x0054
TRAFFIC_FLAG = 0x0004
AI_RACER_FLAG = 0x0002
COP_FLAG = 0x0018
MAX_CARS = 9
TARGET_TRAFFIC = 3
SR_FULL_GRID_COP_ID = 0x0018
SR_FULL_GRID_TRAFFIC_ID = 0x002C
RACEWAY_COP_SOURCE_SLOT_OFF = CAR_DATA_ARRAY_OFF + (2 * CAR_DATA_SIZE)
RACEWAY_COP_SLOT_1_OFF = CAR_DATA_ARRAY_OFF + (3 * CAR_DATA_SIZE)
RACEWAY_TRAFFIC_SLOT_OFF = CAR_DATA_ARRAY_OFF + (6 * CAR_DATA_SIZE)
FIXED_TRAFFIC_SLOT_1_OFF = CAR_DATA_ARRAY_OFF + (6 * CAR_DATA_SIZE)
FIXED_TRAFFIC_SLOT_2_OFF = CAR_DATA_ARRAY_OFF + (7 * CAR_DATA_SIZE)
FIXED_TRAFFIC_SLOT_3_OFF = CAR_DATA_ARRAY_OFF + (8 * CAR_DATA_SIZE)
EXTRA_RACER_SOURCE_SLOT_OFF = CAR_DATA_ARRAY_OFF + (1 * CAR_DATA_SIZE)
HP_EXTRA_RACER_FIXED_SLOT_OFF = CAR_DATA_ARRAY_OFF + (3 * CAR_DATA_SIZE)
HP_COP_FIXED_SLOT_1_OFF = CAR_DATA_ARRAY_OFF + (4 * CAR_DATA_SIZE)
HP_TRAFFIC_FIXED_SLOT_OFF = CAR_DATA_ARRAY_OFF + (7 * CAR_DATA_SIZE)
PERSONALITY_NEMESIS_2 = 1
PERSONALITY_TRAFFIC = 8
SR_COP_SLOT_1_OFF = CAR_DATA_ARRAY_OFF + (4 * CAR_DATA_SIZE)
SR_COP_SLOT_2_OFF = CAR_DATA_ARRAY_OFF + (5 * CAR_DATA_SIZE)
SR_COP_SLOT_3_OFF = CAR_DATA_ARRAY_OFF + (6 * CAR_DATA_SIZE)
SR_COP_SLOT_4_OFF = CAR_DATA_ARRAY_OFF + (7 * CAR_DATA_SIZE)
SR_TRAFFIC_SLOT_OFF = CAR_DATA_ARRAY_OFF + (8 * CAR_DATA_SIZE)

STOCK_HOOK = bytes.fromhex("b8 ff bd 27 44 00 bf af")
STOCK_AICOP_STARTUP_CALL = bytes.fromhex("6b 9c 01 0c 00 00 00 00")
STOCK_TRAFFIC_RUNTIME_FLAG_ORI = bytes.fromhex("10 00 42 34")
PATCHED_TRAFFIC_RUNTIME_FLAG_ORI = bytes.fromhex("10 04 42 34")
STOCK_TRAFFIC_RESPAWN_BASE_STORE = bytes.fromhex("78 05 63 ae")  # sw v1,0x578(s3)
PATCHED_TRAFFIC_RESPAWN_BASE_STORE = bytes.fromhex("78 05 73 ae")  # sw s3,0x578(s3)
STOCK_TRAFFIC_LIVE_AREA_CHECK = bytes.fromhex("e8 ff bd 27 10 00 b0 af")
PATCHED_TRAFFIC_LIVE_AREA_CHECK = bytes.fromhex("08 00 e0 03 21 10 00 00")

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "t3": 11,
    "t4": 12,
    "t5": 13,
    "t6": 14,
    "t7": 15,
    "t8": 24,
    "t9": 25,
    "sp": 29,
    "ra": 31,
}


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


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jal(addr: int) -> int:
    return ins_j(0x03, addr)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def sll(rd: str, rt: str, shamt: int) -> int:
    return ins_r(0, REG[rt], REG[rd], shamt, 0x00)


def slti(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0A, REG[rs], REG[rt], imm)


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
        # Original instruction replaced by hook delay slot already ran:
        # addiu sp,sp,-72. Keep the second original prologue instruction.
        sw("ra", 0x0044, "sp"),
        lui("t0", hi(ENABLE_ADDR)),
        lhu("t1", lo(ENABLE_ADDR), "t0"),
        beq("t1", "zero", "done"),
        nop(),
        lui("t0", hi(GAMESETUP_DATA_ADDR)),
        addiu("t0", "t0", lo(GAMESETUP_DATA_ADDR)),
        lw("t1", GAME_TYPE_OFF, "t0"),
        addiu("t2", "zero", 0),
        beq("t1", "t2", "mode_ok"),
        nop(),
        addiu("t2", "zero", 1),
        beq("t1", "t2", "mode_ok"),
        nop(),
        addiu("t2", "zero", 5),
        bne("t1", "t2", "done"),
        nop(),
        "mode_ok",
        addu("v1", "t1", "zero"),  # keep mode for Raceway no-traffic branch
        lw("t1", NUM_CARS_OFF, "t0"),
        nop(),
        slti("t6", "t1", 1),
        bne("t6", "zero", "done"),
        nop(),
        slti("t6", "t1", MAX_CARS + 1),
        beq("t6", "zero", "done"),
        nop(),
        addiu("t2", "t0", CAR_DATA_ARRAY_OFF),
        addiu("t3", "zero", 0),  # traffic count
        addiu("t4", "zero", 0),  # last traffic carData*
        addiu("t5", "zero", 0),  # index
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
        slti("t6", "t3", TARGET_TRAFFIC),
        beq("t6", "zero", "done"),
        nop(),
        beq("t4", "zero", "raceway_no_traffic_slots"),
        nop(),
        "add_loop",
        # Existing-traffic HP/SR tracks already have valid traffic entries.
        # Cloning them here can corrupt the HP composition in PROD3 with the
        # two-racer frontend patch, turning the added slots into HSV racers.
        # Keep this feature limited to no-traffic Raceway/GT setups below.
        beq("zero", "zero", "done"),
        nop(),
        "raceway_no_traffic_slots",
        addiu("t6", "zero", 1),
        beq("v1", "t6", "raceway_fixed_slots"),
        nop(),
        addiu("t6", "zero", 5),
        beq("v1", "t6", "raceway_fixed_slots"),
        nop(),
        "raceway_single_race_traffic",
        slti("t6", "t1", MAX_CARS),
        beq("t6", "zero", "done"),
        nop(),
        # Single Race Raceway/GT tracks have no active traffic entries and no
        # cops. Add one traffic car only; keep player/opponents untouched.
        sll("t6", "t1", 7),
        sll("t7", "t1", 5),
        addu("t6", "t6", "t7"),
        sll("t7", "t1", 4),
        addu("t6", "t6", "t7"),
        sll("t7", "t1", 2),
        addu("t6", "t6", "t7"),
        addiu("t2", "t0", CAR_DATA_ARRAY_OFF),
        addu("t2", "t2", "t6"),
        addiu("t8", "t0", FIXED_TRAFFIC_SLOT_3_OFF),
        addu("t9", "t2", "zero"),
        addiu("t6", "zero", CAR_DATA_SIZE // 4),
        "rw_sr_traffic_copy",
        lw("t7", 0x0000, "t8"),
        addiu("t8", "t8", 4),
        sw("t7", 0x0000, "t9"),
        addiu("t9", "t9", 4),
        addiu("t6", "t6", -1),
        bne("t6", "zero", "rw_sr_traffic_copy"),
        nop(),
        addiu("t6", "zero", 0x002C),
        sw("t6", 0x0000, "t2"),
        addiu("t6", "zero", TRAFFIC_FLAG),
        sw("t6", CAR_FLAGS_OFF, "t2"),
        addiu("t1", "t1", 1),
        sw("t1", NUM_CARS_OFF, "t0"),
        beq("zero", "zero", "done"),
        nop(),
        "raceway_fixed_slots",
        # Raceway/GT HP already has the correct racer/cop composition from
        # FRONT.BIN. With two AI racers, slot 2 is no longer a cop, so cloning
        # "cops" here turns extra slots into HSV racers. Only append traffic.
        slti("t6", "t1", MAX_CARS),
        beq("t6", "zero", "done"),
        nop(),
        sll("t6", "t1", 7),
        sll("t7", "t1", 5),
        addu("t6", "t6", "t7"),
        sll("t7", "t1", 4),
        addu("t6", "t6", "t7"),
        sll("t7", "t1", 2),
        addu("t6", "t6", "t7"),
        addiu("t9", "t0", CAR_DATA_ARRAY_OFF),
        addu("t9", "t9", "t6"),
        addiu("t8", "t0", FIXED_TRAFFIC_SLOT_3_OFF),
        addiu("t6", "zero", CAR_DATA_SIZE // 4),
        "rw_traffic_copy",
        lw("t7", 0x0000, "t8"),
        addiu("t8", "t8", 4),
        sw("t7", 0x0000, "t9"),
        addiu("t9", "t9", 4),
        addiu("t6", "t6", -1),
        bne("t6", "zero", "rw_traffic_copy"),
        nop(),
        sll("t6", "t1", 7),
        sll("t7", "t1", 5),
        addu("t6", "t6", "t7"),
        sll("t7", "t1", 4),
        addu("t6", "t6", "t7"),
        sll("t7", "t1", 2),
        addu("t6", "t6", "t7"),
        addiu("t2", "t0", CAR_DATA_ARRAY_OFF),
        addu("t2", "t2", "t6"),
        addiu("t6", "zero", 0x002C),
        sw("t6", 0x0000, "t2"),
        addiu("t6", "zero", TRAFFIC_FLAG),
        sw("t6", CAR_FLAGS_OFF, "t2"),
        addiu("t6", "zero", PERSONALITY_TRAFFIC),
        sw("t6", PERSONALITY_OFF, "t2"),
        addiu("t1", "t1", 1),
        sw("t1", NUM_CARS_OFF, "t0"),
        "done",
        "exit",
        j(CARS_STARTUP_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, runtime(CAVE_OFF))
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X} > 0x{CAVE_LEN:X}")
    return blob.ljust(CAVE_LEN, b"\x00")


def hp_second_racer_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        lui("t0", hi(ENABLE_ADDR)),
        lhu("t1", lo(ENABLE_ADDR), "t0"),
        beq("t1", "zero", "stable"),
        nop(),
        lui("t0", hi(GAMESETUP_DATA_ADDR)),
        addiu("t0", "t0", lo(GAMESETUP_DATA_ADDR)),
        lw("t1", GAME_TYPE_OFF, "t0"),
        addiu("t2", "zero", 1),
        bne("t1", "t2", "stable"),
        nop(),
        lw("t1", NUM_OPPONENT_RACE_CARS_OFF, "t0"),
        addiu("t2", "zero", 2),
        slti("t6", "t1", 2),
        beq("t6", "zero", "stable"),
        nop(),
        lw("t1", NUM_CARS_OFF, "t0"),
        nop(),
        slti("t6", "t1", 3),
        bne("t6", "zero", "stable"),
        nop(),
        slti("t6", "t1", MAX_CARS + 1),
        beq("t6", "zero", "stable"),
        nop(),
        addiu("t2", "t0", CAR_DATA_ARRAY_OFF),
        addiu("t3", "zero", 0),  # traffic count
        addiu("t5", "zero", 0),
        "hp_scan",
        beq("t5", "t1", "hp_scan_done"),
        nop(),
        lw("t6", CAR_FLAGS_OFF, "t2"),
        nop(),
        andi("t6", "t6", TRAFFIC_FLAG),
        beq("t6", "zero", "hp_not_traffic"),
        nop(),
        addiu("t3", "t3", 1),
        "hp_not_traffic",
        addiu("t5", "t5", 1),
        beq("zero", "zero", "hp_scan"),
        addiu("t2", "t2", CAR_DATA_SIZE),
        "hp_scan_done",
        beq("t3", "zero", "hp_no_traffic_fixed"),
        nop(),
        slti("t6", "t1", MAX_CARS),
        beq("t6", "zero", "stable"),
        nop(),
        # Dynamic append: clone the first AI racer into the next free slot.
        sll("t6", "t1", 7),
        sll("t7", "t1", 5),
        addu("t6", "t6", "t7"),
        sll("t7", "t1", 4),
        addu("t6", "t6", "t7"),
        sll("t7", "t1", 2),
        addu("t6", "t6", "t7"),
        addiu("t2", "t0", CAR_DATA_ARRAY_OFF),
        addu("t2", "t2", "t6"),
        addiu("t8", "t0", EXTRA_RACER_SOURCE_SLOT_OFF),
        addu("t9", "t2", "zero"),
        addiu("t6", "zero", CAR_DATA_SIZE // 4),
        "hp_append_racer_copy",
        lw("t7", 0x0000, "t8"),
        addiu("t8", "t8", 4),
        sw("t7", 0x0000, "t9"),
        addiu("t9", "t9", 4),
        addiu("t6", "t6", -1),
        bne("t6", "zero", "hp_append_racer_copy"),
        nop(),
        addiu("t6", "zero", AI_RACER_FLAG),
        sw("t6", CAR_FLAGS_OFF, "t2"),
        addiu("t6", "zero", PERSONALITY_NEMESIS_2),
        sw("t6", PERSONALITY_OFF, "t2"),
        addiu("t6", "zero", 2),
        sw("t6", STARTING_POS_OFF, "t2"),
        sw("t6", NUM_OPPONENT_RACE_CARS_OFF, "t0"),
        addiu("t1", "t1", 1),
        sw("t1", NUM_CARS_OFF, "t0"),
        beq("zero", "zero", "stable"),
        nop(),
        "hp_no_traffic_fixed",
        # Raceway/GT path: build the full stable HP set ourselves so the
        # existing no-traffic branch does not overwrite the added racer.
        addiu("t8", "t0", EXTRA_RACER_SOURCE_SLOT_OFF),
        addiu("t9", "t0", HP_EXTRA_RACER_FIXED_SLOT_OFF),
        addiu("t6", "zero", CAR_DATA_SIZE // 4),
        "hp_fixed_racer_copy",
        lw("t7", 0x0000, "t8"),
        addiu("t8", "t8", 4),
        sw("t7", 0x0000, "t9"),
        addiu("t9", "t9", 4),
        addiu("t6", "t6", -1),
        bne("t6", "zero", "hp_fixed_racer_copy"),
        nop(),
        addiu("t2", "t0", HP_EXTRA_RACER_FIXED_SLOT_OFF),
        addiu("t6", "zero", AI_RACER_FLAG),
        sw("t6", CAR_FLAGS_OFF, "t2"),
        addiu("t6", "zero", PERSONALITY_NEMESIS_2),
        sw("t6", PERSONALITY_OFF, "t2"),
        addiu("t6", "zero", 2),
        sw("t6", STARTING_POS_OFF, "t2"),
        addiu("t4", "t0", RACEWAY_COP_SOURCE_SLOT_OFF),
        addiu("t9", "t0", HP_COP_FIXED_SLOT_1_OFF),
        addiu("t5", "zero", 3),
        "hp_fixed_cop_outer",
        addu("t8", "t4", "zero"),
        addiu("t6", "zero", CAR_DATA_SIZE // 4),
        "hp_fixed_cop_copy",
        lw("t7", 0x0000, "t8"),
        addiu("t8", "t8", 4),
        sw("t7", 0x0000, "t9"),
        addiu("t9", "t9", 4),
        addiu("t6", "t6", -1),
        bne("t6", "zero", "hp_fixed_cop_copy"),
        nop(),
        addiu("t5", "t5", -1),
        bne("t5", "zero", "hp_fixed_cop_outer"),
        nop(),
        addiu("t8", "t0", FIXED_TRAFFIC_SLOT_3_OFF),
        addiu("t9", "t0", HP_TRAFFIC_FIXED_SLOT_OFF),
        addiu("t6", "zero", CAR_DATA_SIZE // 4),
        "hp_fixed_traffic_copy",
        lw("t7", 0x0000, "t8"),
        addiu("t8", "t8", 4),
        sw("t7", 0x0000, "t9"),
        addiu("t9", "t9", 4),
        addiu("t6", "t6", -1),
        bne("t6", "zero", "hp_fixed_traffic_copy"),
        nop(),
        addiu("t2", "t0", HP_TRAFFIC_FIXED_SLOT_OFF),
        addiu("t6", "zero", SR_FULL_GRID_TRAFFIC_ID),
        sw("t6", 0x0000, "t2"),
        addiu("t6", "zero", TRAFFIC_FLAG),
        sw("t6", CAR_FLAGS_OFF, "t2"),
        addiu("t6", "zero", PERSONALITY_TRAFFIC),
        sw("t6", PERSONALITY_OFF, "t2"),
        addiu("t6", "zero", 2),
        sw("t6", NUM_OPPONENT_RACE_CARS_OFF, "t0"),
        addiu("t6", "zero", 8),
        sw("t6", NUM_CARS_OFF, "t0"),
        sw("ra", 0x0044, "sp"),
        j(CARS_STARTUP_RETURN_ADDR),
        nop(),
        "stable",
        j(runtime(CAVE_OFF)),
        nop(),
    ]
    blob = pack_labeled(items, runtime(HP_SECOND_RACER_CAVE_OFF))
    if len(blob) > HP_SECOND_RACER_CAVE_LEN:
        raise SystemExit(
            f"HP second-racer cave too large: 0x{len(blob):X} > 0x{HP_SECOND_RACER_CAVE_LEN:X}"
        )
    return blob.ljust(HP_SECOND_RACER_CAVE_LEN, b"\x00")


def pre_aicop_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        lui("t0", hi(ENABLE_ADDR)),
        lhu("t1", lo(ENABLE_ADDR), "t0"),
        beq("t1", "zero", "call_original"),
        nop(),
        lui("t0", hi(GAMESETUP_DATA_ADDR)),
        addiu("t0", "t0", lo(GAMESETUP_DATA_ADDR)),
        lw("t1", GAME_TYPE_OFF, "t0"),
        addiu("t2", "zero", 0),
        bne("t1", "t2", "call_original"),
        nop(),
        lw("t1", NUM_CARS_OFF, "t0"),
        slti("t2", "t1", 6),
        bne("t2", "zero", "call_original"),
        nop(),
        addiu("t2", "zero", 1),
        sw("t2", COP_AI_ENABLE_OFF, "t0"),
        addiu("t2", "t0", SR_COP_SLOT_1_OFF),
        addiu("t6", "zero", SR_FULL_GRID_COP_ID),
        sw("t6", 0x0000, "t2"),
        addiu("t6", "zero", COP_FLAG),
        sw("t6", CAR_FLAGS_OFF, "t2"),
        addiu("t4", "t0", SR_COP_SLOT_1_OFF),
        addiu("t9", "t0", SR_COP_SLOT_2_OFF),
        addiu("t5", "zero", 3),
        "sr_pre_copy_outer",
        addu("t8", "t4", "zero"),
        addiu("t6", "zero", CAR_DATA_SIZE // 4),
        "sr_pre_copy",
        lw("t7", 0x0000, "t8"),
        addiu("t8", "t8", 4),
        sw("t7", 0x0000, "t9"),
        addiu("t9", "t9", 4),
        addiu("t6", "t6", -1),
        bne("t6", "zero", "sr_pre_copy"),
        nop(),
        addiu("t5", "t5", -1),
        bne("t5", "zero", "sr_pre_copy_outer"),
        nop(),
        addiu("t2", "t0", SR_TRAFFIC_SLOT_OFF),
        addiu("t6", "zero", SR_FULL_GRID_TRAFFIC_ID),
        sw("t6", 0x0000, "t2"),
        addiu("t6", "zero", TRAFFIC_FLAG),
        sw("t6", CAR_FLAGS_OFF, "t2"),
        addiu("t6", "zero", MAX_CARS),
        sw("t6", NUM_CARS_OFF, "t0"),
        "call_original",
        jal(AICOP_STARTUP_ADDR),
        nop(),
        j(AICOP_STARTUP_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, runtime(PRE_AICOP_CAVE_OFF))
    if len(blob) > PRE_AICOP_CAVE_LEN:
        raise SystemExit(
            f"pre-AICop cave too large: 0x{len(blob):X} > 0x{PRE_AICOP_CAVE_LEN:X}"
        )
    return blob.ljust(PRE_AICOP_CAVE_LEN, b"\x00")


def find_prod3_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Clone Hot Pursuit traffic carData entries and add stable Raceway traffic "
            "for Hot Pursuit/Single Race."
        )
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_prod3_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    hook = pack([j(runtime(CAVE_OFF)), addiu("sp", "sp", -72)])
    hp_second_racer_hook = pack(
        [j(runtime(HP_SECOND_RACER_CAVE_OFF)), addiu("sp", "sp", -72)]
    )
    legacy_hook = pack([j(runtime(LEGACY_CAVE_OFF)), addiu("sp", "sp", -72)])
    pre_aicop_hook = pack([j(runtime(PRE_AICOP_CAVE_OFF)), nop()])
    blob = cave()
    hp_second_racer_blob = hp_second_racer_cave()
    pre_blob = pre_aicop_cave()

    current_hook = bytes(data[CARS_STARTUP_HOOK_OFF : CARS_STARTUP_HOOK_OFF + 8])
    if current_hook not in {STOCK_HOOK, hook, hp_second_racer_hook, legacy_hook}:
        raise SystemExit(
            f"unexpected Cars_StartUp hook bytes at 0x{CARS_STARTUP_HOOK_OFF:X}: "
            f"{current_hook.hex(' ')}"
        )

    current_aicop_call = bytes(
        data[AICOP_STARTUP_CALL_OFF : AICOP_STARTUP_CALL_OFF + 8]
    )
    if current_aicop_call not in {STOCK_AICOP_STARTUP_CALL, pre_aicop_hook}:
        raise SystemExit(
            f"unexpected AICop_StartUp call bytes at 0x{AICOP_STARTUP_CALL_OFF:X}: "
            f"{current_aicop_call.hex(' ')}"
        )

    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {b"\x00" * CAVE_LEN, blob} and current_hook != hook:
        raise SystemExit(f"cave is not empty/known at 0x{CAVE_OFF:X}")

    current_hp_second_racer_cave = bytes(
        data[HP_SECOND_RACER_CAVE_OFF : HP_SECOND_RACER_CAVE_OFF + HP_SECOND_RACER_CAVE_LEN]
    )
    if current_hp_second_racer_cave not in {
        b"\x00" * HP_SECOND_RACER_CAVE_LEN,
        hp_second_racer_blob,
    }:
        raise SystemExit(
            f"HP second-racer cave is not empty/known at 0x{HP_SECOND_RACER_CAVE_OFF:X}"
        )

    current_pre_cave = bytes(
        data[PRE_AICOP_CAVE_OFF : PRE_AICOP_CAVE_OFF + PRE_AICOP_CAVE_LEN]
    )
    if current_pre_cave not in {b"\x00" * PRE_AICOP_CAVE_LEN, pre_blob}:
        raise SystemExit(f"pre-AICop cave is not empty/known at 0x{PRE_AICOP_CAVE_OFF:X}")

    current_runtime_flag = bytes(
        data[TRAFFIC_RUNTIME_FLAG_ORI_OFF : TRAFFIC_RUNTIME_FLAG_ORI_OFF + 4]
    )
    if current_runtime_flag not in {
        STOCK_TRAFFIC_RUNTIME_FLAG_ORI,
        PATCHED_TRAFFIC_RUNTIME_FLAG_ORI,
    }:
        raise SystemExit(
            f"unexpected traffic runtime flag bytes at 0x{TRAFFIC_RUNTIME_FLAG_ORI_OFF:X}: "
            f"{current_runtime_flag.hex(' ')}"
        )

    current_respawn_base = bytes(
        data[TRAFFIC_RESPAWN_BASE_STORE_OFF : TRAFFIC_RESPAWN_BASE_STORE_OFF + 4]
    )
    if current_respawn_base not in {
        STOCK_TRAFFIC_RESPAWN_BASE_STORE,
        PATCHED_TRAFFIC_RESPAWN_BASE_STORE,
    }:
        raise SystemExit(
            f"unexpected traffic respawn base bytes at 0x{TRAFFIC_RESPAWN_BASE_STORE_OFF:X}: "
            f"{current_respawn_base.hex(' ')}"
        )

    current_live_area_check = bytes(
        data[TRAFFIC_LIVE_AREA_CHECK_OFF : TRAFFIC_LIVE_AREA_CHECK_OFF + 8]
    )
    if current_live_area_check not in {
        STOCK_TRAFFIC_LIVE_AREA_CHECK,
        PATCHED_TRAFFIC_LIVE_AREA_CHECK,
    }:
        raise SystemExit(
            f"unexpected traffic live-area check bytes at 0x{TRAFFIC_LIVE_AREA_CHECK_OFF:X}: "
            f"{current_live_area_check.hex(' ')}"
        )

    if args.revert:
        data[CARS_STARTUP_HOOK_OFF : CARS_STARTUP_HOOK_OFF + 8] = STOCK_HOOK
        data[AICOP_STARTUP_CALL_OFF : AICOP_STARTUP_CALL_OFF + 8] = (
            STOCK_AICOP_STARTUP_CALL
        )
        data[PRE_AICOP_CAVE_OFF : PRE_AICOP_CAVE_OFF + PRE_AICOP_CAVE_LEN] = (
            b"\x00" * PRE_AICOP_CAVE_LEN
        )
        data[
            HP_SECOND_RACER_CAVE_OFF : HP_SECOND_RACER_CAVE_OFF + HP_SECOND_RACER_CAVE_LEN
        ] = b"\x00" * HP_SECOND_RACER_CAVE_LEN
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = b"\x00" * CAVE_LEN
        data[TRAFFIC_RUNTIME_FLAG_ORI_OFF : TRAFFIC_RUNTIME_FLAG_ORI_OFF + 4] = (
            STOCK_TRAFFIC_RUNTIME_FLAG_ORI
        )
        data[TRAFFIC_RESPAWN_BASE_STORE_OFF : TRAFFIC_RESPAWN_BASE_STORE_OFF + 4] = (
            STOCK_TRAFFIC_RESPAWN_BASE_STORE
        )
        data[TRAFFIC_LIVE_AREA_CHECK_OFF : TRAFFIC_LIVE_AREA_CHECK_OFF + 8] = (
            STOCK_TRAFFIC_LIVE_AREA_CHECK
        )
    else:
        # The Single Race pseudo-HP prehook can hang map loading in multiple
        # modes. Keep it reverted while preserving the stable traffic/Raceway
        # Cars_StartUp hook.
        data[AICOP_STARTUP_CALL_OFF : AICOP_STARTUP_CALL_OFF + 8] = (
            STOCK_AICOP_STARTUP_CALL
        )
        data[PRE_AICOP_CAVE_OFF : PRE_AICOP_CAVE_OFF + PRE_AICOP_CAVE_LEN] = (
            b"\x00" * PRE_AICOP_CAVE_LEN
        )
        # The HP second-racer wrapper hangs map loading in DuckStation. Keep
        # the stable HP/Raceway traffic hook active, but leave this experiment
        # cleared unless a separate test script explicitly enables it.
        data[
            HP_SECOND_RACER_CAVE_OFF : HP_SECOND_RACER_CAVE_OFF + HP_SECOND_RACER_CAVE_LEN
        ] = b"\x00" * HP_SECOND_RACER_CAVE_LEN
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = blob
        data[CARS_STARTUP_HOOK_OFF : CARS_STARTUP_HOOK_OFF + 8] = hook
        # Keep the failed traffic respawn/live-area experiments reverted.
        data[TRAFFIC_RUNTIME_FLAG_ORI_OFF : TRAFFIC_RUNTIME_FLAG_ORI_OFF + 4] = (
            STOCK_TRAFFIC_RUNTIME_FLAG_ORI
        )
        data[TRAFFIC_RESPAWN_BASE_STORE_OFF : TRAFFIC_RESPAWN_BASE_STORE_OFF + 4] = (
            STOCK_TRAFFIC_RESPAWN_BASE_STORE
        )
        data[TRAFFIC_LIVE_AREA_CHECK_OFF : TRAFFIC_LIVE_AREA_CHECK_OFF + 8] = (
            STOCK_TRAFFIC_LIVE_AREA_CHECK
        )

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    mode = "reverted" if args.revert else "patched"
    print(f"{mode}: {exe}")
    print(f"hook runtime 0x{runtime(CARS_STARTUP_HOOK_OFF):08X} -> cave 0x{runtime(CAVE_OFF):08X}")
    print(f"enable cheat: 80054B7C 0001 (off: 80054B7C 0000)")
    print("Single Race pseudo-HP prehook reverted; stable traffic/Raceway hook active")
    print("Raceway/GT: Hot Pursuit keeps 4 cops + 1 traffic; Single Race adds 1 traffic only")
    print("Hot Pursuit second AI racer wrapper disabled after load hang")
    print("third traffic replacement only: 80114E18 00?? and 80118D98 00??")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
