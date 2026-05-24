#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

from patch_prod3_player_cop_livery_entry_scratch import (
    COP_INDEX_OFF,
    ENABLE_OFF,
    ENABLE_ADDR,
    ENTRY_CAVE_OFF,
    GET_FILENAME_ADDR,
    GET_FILENAME_CAVE_LEN,
    GET_FILENAME_CAVE_OFF,
    GET_FILENAME_HOOK_OFF,
    INSTANTIATE_ENTRY_HOOK_OFF,
    INSTANTIATE_ENTRY_RETURN_ADDR,
    RUNTIME_BASE,
    SLOT0_PATCHED_INDEX,
    STOCK_INDEX,
    GLOBAL_ALL_SLOTS_INDEX,
    entry_cave as old_entry_cave,
    get_filename_cave as old_get_filename_cave,
)


BACKUP_SUFFIX = ".orig_prod3_player_cop_livery_playerdata"
DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"

PLAYER_CAR_DATA_ADDR = 0x80114878
PLAYER_CAR_COUNTRY_ADDR = PLAYER_CAR_DATA_ADDR + 0xA0
CARS_COP_LIST_ADDR = 0x80110D78
TRACK_NUMBER_GP_OFF = 0x0F88
TRACK_COUNTRY_TABLE_OFF = ENTRY_CAVE_OFF + 0xE0
TRACK_COUNTRY_TABLE_ADDR = RUNTIME_BASE + TRACK_COUNTRY_TABLE_OFF

# Cop country slots used by R3DCar_GetCarName:
# 0=b/UK-style, 1=f/French, 2=g/German, 3=a, 4=u/US-Canada.
# Debug ZTUNING track order:
# 0 Snowy, 1 Highway, 2 Coastal, 3 France, 4 Park, 5 Celtic,
# 6 Germany, 7 UK, 8-10 GT tracks, 11 undefined.
TRACK_COUNTRY_SLOTS = bytes([
    2,  # Snowy
    4,  # Highway
    4,  # Coastal
    1,  # France
    4,  # Park / Canada
    0,  # Celtic
    2,  # Germany
    0,  # UK
    4,  # GT1 / Raceway 2
    1,  # GT2 / Raceway
    2,  # GT3 / Raceway 3
    0,  # Undefined
    0,
    0,
    0,
    0,
])

# Free space before the AI-racer mass cave starts at 0x45C00.
PLAYER_LIVERY_CAVE_LEN = 0xF0

REG = {
    "zero": 0,
    "v0": 2,
    "a2": 6,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "s5": 21,
    "gp": 28,
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


def lbu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x24, REG[rs], REG[rt], off)


def andi(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0C, REG[rs], REG[rt], imm)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


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
            kind, rs, rt, target = item
            op = 0x04 if kind == "beq" else 0x05
            item = ins_i(op, REG[rs], REG[rt], (labels[target] - (pc + 4)) >> 2)
        words.append(item)
        pc += 4
    return pack(words)


def hi(addr: int) -> int:
    return (addr >> 16) & 0xFFFF


def lo(addr: int) -> int:
    return addr & 0xFFFF


def cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Delay slot at hook already executes: addiu v0,s5,-22.
        lui("t0", hi(ENABLE_ADDR)),
        lw("t1", lo(ENABLE_ADDR), "t0"),
        beq("t1", "zero", "finish"),
        nop(),
        addiu("a2", "zero", 1),
        beq("t1", "a2", "country_from_track"),
        nop(),
        addiu("a2", "zero", 2),
        bne("t1", "a2", "finish"),
        nop(),
        lui("t0", hi(PLAYER_CAR_DATA_ADDR)),
        lbu("t1", lo(PLAYER_CAR_DATA_ADDR), "t0"),
        addiu("a2", "zero", 0x18),
        beq("t1", "a2", "bmw"),
        nop(),
        addiu("a2", "zero", 0x1A),
        beq("t1", "a2", "porsche"),
        nop(),
        addiu("a2", "zero", 0x1B),
        bne("t1", "a2", "finish"),
        nop(),
        addiu("a2", "zero", 4),  # Diablo SV Cop -> u/US
        sw("a2", lo(PLAYER_CAR_COUNTRY_ADDR), "t0"),
        beq("zero", "zero", "finish"),
        nop(),
        "bmw",
        addiu("a2", "zero", 1),  # BMW M5 Cop -> f/French
        sw("a2", lo(PLAYER_CAR_COUNTRY_ADDR), "t0"),
        beq("zero", "zero", "finish"),
        nop(),
        "porsche",
        addiu("a2", "zero", 2),  # Porsche 911 Cop -> g/German
        sw("a2", lo(PLAYER_CAR_COUNTRY_ADDR), "t0"),
        beq("zero", "zero", "finish"),
        nop(),
        "country_from_track",
        lw("t2", TRACK_NUMBER_GP_OFF, "gp"),
        lui("t0", hi(TRACK_COUNTRY_TABLE_ADDR)),
        andi("t2", "t2", 0x000F),
        addiu("t0", "t0", lo(TRACK_COUNTRY_TABLE_ADDR)),
        # Delay slot: index table by selected track number.
        addu("t0", "t0", "t2"),
        lbu("a2", 0x0000, "t0"),
        lui("t0", hi(PLAYER_CAR_DATA_ADDR)),
        sw("a2", lo(PLAYER_CAR_COUNTRY_ADDR), "t0"),
        "finish",
        sltiu("v0", "v0", 6),
        j(INSTANTIATE_ENTRY_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, runtime(ENTRY_CAVE_OFF))
    if len(blob) > TRACK_COUNTRY_TABLE_OFF - ENTRY_CAVE_OFF:
        raise SystemExit(
            f"cave too large: 0x{len(blob):X} > 0x{TRACK_COUNTRY_TABLE_OFF - ENTRY_CAVE_OFF:X}"
        )
    blob = blob.ljust(TRACK_COUNTRY_TABLE_OFF - ENTRY_CAVE_OFF, b"\x00")
    blob += TRACK_COUNTRY_SLOTS
    return blob.ljust(PLAYER_LIVERY_CAVE_LEN, b"\x00")


def old_custom_only_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Delay slot at hook already executes: addiu v0,s5,-22.
        lui("t0", hi(ENABLE_ADDR)),
        lw("t1", lo(ENABLE_ADDR), "t0"),
        beq("t1", "zero", "finish"),
        nop(),
        lui("t0", hi(PLAYER_CAR_DATA_ADDR)),
        lbu("t1", lo(PLAYER_CAR_DATA_ADDR), "t0"),
        addiu("a2", "zero", 0x18),
        beq("t1", "a2", "bmw"),
        nop(),
        addiu("a2", "zero", 0x1A),
        beq("t1", "a2", "porsche"),
        nop(),
        addiu("a2", "zero", 0x1B),
        bne("t1", "a2", "finish"),
        nop(),
        addiu("a2", "zero", 4),
        sw("a2", lo(PLAYER_CAR_COUNTRY_ADDR), "t0"),
        beq("zero", "zero", "finish"),
        nop(),
        "bmw",
        addiu("a2", "zero", 1),
        sw("a2", lo(PLAYER_CAR_COUNTRY_ADDR), "t0"),
        beq("zero", "zero", "finish"),
        nop(),
        "porsche",
        addiu("a2", "zero", 2),
        sw("a2", lo(PLAYER_CAR_COUNTRY_ADDR), "t0"),
        "finish",
        sltiu("v0", "v0", 6),
        j(INSTANTIATE_ENTRY_RETURN_ADDR),
        nop(),
    ]
    return pack_labeled(items, runtime(ENTRY_CAVE_OFF)).ljust(PLAYER_LIVERY_CAVE_LEN, b"\x00")


def old_ai_cop_country_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Delay slot at hook already executes: addiu v0,s5,-22.
        lui("t0", hi(ENABLE_ADDR)),
        lw("t1", lo(ENABLE_ADDR), "t0"),
        beq("t1", "zero", "finish"),
        nop(),
        addiu("a2", "zero", 1),
        beq("t1", "a2", "country_from_ai_cop"),
        nop(),
        addiu("a2", "zero", 2),
        bne("t1", "a2", "finish"),
        nop(),
        lui("t0", hi(PLAYER_CAR_DATA_ADDR)),
        lbu("t1", lo(PLAYER_CAR_DATA_ADDR), "t0"),
        addiu("a2", "zero", 0x18),
        beq("t1", "a2", "bmw"),
        nop(),
        addiu("a2", "zero", 0x1A),
        beq("t1", "a2", "porsche"),
        nop(),
        addiu("a2", "zero", 0x1B),
        bne("t1", "a2", "finish"),
        nop(),
        addiu("a2", "zero", 4),
        sw("a2", lo(PLAYER_CAR_COUNTRY_ADDR), "t0"),
        beq("zero", "zero", "finish"),
        nop(),
        "bmw",
        addiu("a2", "zero", 1),
        sw("a2", lo(PLAYER_CAR_COUNTRY_ADDR), "t0"),
        beq("zero", "zero", "finish"),
        nop(),
        "porsche",
        addiu("a2", "zero", 2),
        sw("a2", lo(PLAYER_CAR_COUNTRY_ADDR), "t0"),
        beq("zero", "zero", "finish"),
        nop(),
        "country_from_ai_cop",
        lui("t0", hi(CARS_COP_LIST_ADDR)),
        lw("t2", lo(CARS_COP_LIST_ADDR), "t0"),
        beq("t2", "zero", "finish"),
        nop(),
        lw("t2", 0x0288, "t2"),
        beq("t2", "zero", "finish"),
        nop(),
        lbu("a2", 0x00A0, "t2"),
        lui("t0", hi(PLAYER_CAR_DATA_ADDR)),
        sw("a2", lo(PLAYER_CAR_COUNTRY_ADDR), "t0"),
        "finish",
        sltiu("v0", "v0", 6),
        j(INSTANTIATE_ENTRY_RETURN_ADDR),
        nop(),
    ]
    return pack_labeled(items, runtime(ENTRY_CAVE_OFF)).ljust(PLAYER_LIVERY_CAVE_LEN, b"\x00")


def find_prod3_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3 player cop livery by changing only player carData country slot."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_prod3_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    stock_entry = pack([addiu("v0", "s5", -22), sltiu("v0", "v0", 6)])
    patched_entry = pack([j(runtime(ENTRY_CAVE_OFF)), addiu("v0", "s5", -22)])
    current_entry = bytes(data[INSTANTIATE_ENTRY_HOOK_OFF : INSTANTIATE_ENTRY_HOOK_OFF + 8])
    if current_entry not in [stock_entry, patched_entry]:
        raise SystemExit(f"unexpected Instantiate entry bytes: {current_entry.hex(' ')}")
    data[INSTANTIATE_ENTRY_HOOK_OFF : INSTANTIATE_ENTRY_HOOK_OFF + 8] = (
        stock_entry if args.revert else patched_entry
    )

    stock_get_filename = pack([lw("a2", 0x00A0, "v0"), jal(GET_FILENAME_ADDR)])
    old_get_filename_hook = pack([j(runtime(GET_FILENAME_CAVE_OFF)), lw("a2", 0x00A0, "v0")])
    current_get_filename = bytes(data[GET_FILENAME_HOOK_OFF : GET_FILENAME_HOOK_OFF + 8])
    if current_get_filename not in [stock_get_filename, old_get_filename_hook]:
        raise SystemExit(f"unexpected GetFileName hook bytes: {current_get_filename.hex(' ')}")
    data[GET_FILENAME_HOOK_OFF : GET_FILENAME_HOOK_OFF + 8] = stock_get_filename

    current_index = bytes(data[COP_INDEX_OFF : COP_INDEX_OFF + len(STOCK_INDEX)])
    if current_index not in [STOCK_INDEX, SLOT0_PATCHED_INDEX, GLOBAL_ALL_SLOTS_INDEX]:
        raise SystemExit(f"unexpected cop-index table: {current_index.hex(' ')}")
    data[COP_INDEX_OFF : COP_INDEX_OFF + len(STOCK_INDEX)] = STOCK_INDEX

    new_cave = cave()
    broken_mode_cave = bytearray(new_cave)
    get_filename_rel = GET_FILENAME_CAVE_OFF - ENTRY_CAVE_OFF
    broken_mode_cave[get_filename_rel : get_filename_rel + GET_FILENAME_CAVE_LEN] = (
        b"\x00" * GET_FILENAME_CAVE_LEN
    )
    broken_mode_cave = bytes(broken_mode_cave)
    old_cave_len = 0x80
    safe_entry_caves = [
        b"\x00" * PLAYER_LIVERY_CAVE_LEN,
        new_cave,
        broken_mode_cave,
        old_custom_only_cave(),
        old_ai_cop_country_cave(),
        old_entry_cave(require_enable=True).ljust(PLAYER_LIVERY_CAVE_LEN, b"\x00"),
        old_entry_cave(require_enable=False).ljust(PLAYER_LIVERY_CAVE_LEN, b"\x00"),
    ]
    current_entry_cave = bytes(data[ENTRY_CAVE_OFF : ENTRY_CAVE_OFF + PLAYER_LIVERY_CAVE_LEN])
    current_old_entry_cave = bytes(data[ENTRY_CAVE_OFF : ENTRY_CAVE_OFF + old_cave_len])
    if current_entry_cave not in safe_entry_caves:
        old_known = current_old_entry_cave in [
            old_entry_cave(require_enable=True),
            old_entry_cave(require_enable=False),
        ] and current_entry_cave[old_cave_len:] == b"\x00" * (PLAYER_LIVERY_CAVE_LEN - old_cave_len)
        if not old_known:
            raise SystemExit(f"entry cave area is not empty/known at 0x{ENTRY_CAVE_OFF:X}; refusing")

    safe_get_filename_caves = [
        b"\x00" * GET_FILENAME_CAVE_LEN,
        new_cave[get_filename_rel : get_filename_rel + GET_FILENAME_CAVE_LEN],
        old_ai_cop_country_cave()[get_filename_rel : get_filename_rel + GET_FILENAME_CAVE_LEN],
        old_get_filename_cave(write_car_country=True),
        old_get_filename_cave(write_car_country=False),
    ]
    current_get_filename_cave = bytes(
        data[GET_FILENAME_CAVE_OFF : GET_FILENAME_CAVE_OFF + GET_FILENAME_CAVE_LEN]
    )
    if current_get_filename_cave not in safe_get_filename_caves:
        raise SystemExit(
            f"GetFileName cave area is not empty/known at 0x{GET_FILENAME_CAVE_OFF:X}; refusing"
        )

    data[ENTRY_CAVE_OFF : ENTRY_CAVE_OFF + PLAYER_LIVERY_CAVE_LEN] = (
        b"\x00" * PLAYER_LIVERY_CAVE_LEN if args.revert else new_cave
    )
    if not args.revert:
        data[ENABLE_OFF : ENABLE_OFF + 4] = b"\x00" * 4

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists() and not args.revert:
            backup.write_bytes(original)
        exe.write_bytes(data)

    action = "reverted" if args.revert else "patched"
    print(f"{action} {exe}")
    print("player carData only; modes: 0=off, 1=track country, 2=custom BMW/Porsche/Diablo")
    cheat_addr = 0x80000000 | (ENABLE_ADDR & 0x1FFFFF)
    print(f"GameShark mode flag: {cheat_addr:08X} 0000/0001/0002")
    print(f"md5 {hashlib.md5(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
