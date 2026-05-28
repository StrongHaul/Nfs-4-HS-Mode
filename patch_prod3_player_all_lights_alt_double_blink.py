#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_all_lights_alt_double_blink"
RUNTIME_BASE = 0x8000F800

# DrawC_PrimStart: start of the stock R3DCar_InMenu / speechSource&2 light
# flash block. We override only the player civilian car while the player-arrest
# cheat is active, then jump past the stock block so it cannot overwrite the
# side-specific double blink masks.
HOOK_OFF = 0xB0B28
HOOK_ADDR = RUNTIME_BASE + HOOK_OFF
RETURN_ADDR = HOOK_ADDR + 8
AFTER_STOCK_FLASH_ADDR = 0x800C0580

# Empty executable cave in the low patch area.
CAVE_OFF = 0x45000
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x200

PLAYER_CAR_OBJ_PTR_ADDR = 0x80110D0C
PLAYER_BUST_CHEAT_ADDR = 0x800F7A00
PLAYER_STROBE_COUNTER_ADDR = 0x800550FC
R3DCAR_IN_MENU_ADDR = 0x8013E608

# PROD3 runtime base used by this DrawC mask cluster:
#   +0x00 DrawC_gOverlay/front damage
#   +0x02 rear/reverse damage mask
#   +0x30 tail light low mask
#   +0x32 tail light high mask
#   +0x34 white reverse light mask
#   +0x3A headlight mask
LIGHT_MASK_BASE_ADDR = 0x801207F8

REG = {
    "zero": 0,
    "v0": 2,
    "a0": 4,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "t3": 11,
    "s2": 18,
    "sp": 29,
}


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


def andi(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0C, REG[rs], REG[rt], imm)


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


def ori(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0D, REG[rs], REG[rt], imm)


def sh(rt: str, off: int, rs: str) -> int:
    return ins_i(0x29, REG[rs], REG[rt], off)


def slti(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0A, REG[rs], REG[rt], imm)


def sltiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0B, REG[rs], REG[rt], imm)


def srl(rd: str, rt: str, shamt: int) -> int:
    return ins_r(0, REG[rt], REG[rd], shamt, 0x02)


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


def make_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Do not touch menu rendering.
        lui("t0", hi(R3DCAR_IN_MENU_ADDR)),
        lw("t1", lo(R3DCAR_IN_MENU_ADDR), "t0"),
        nop(),
        bne("t1", "zero", "original"),
        nop(),
        # Player car only.
        lui("t0", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
        lw("t1", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t0"),
        nop(),
        bne("s2", "t1", "original"),
        nop(),
        # Civilian car types only; police models keep stock light behavior.
        lhu("t1", 0x08BC, "s2"),
        slti("t1", "t1", 0x16),
        beq("t1", "zero", "original"),
        nop(),
        # Same switch as the existing player-arrest/strobe cheat.
        lui("t0", hi(PLAYER_BUST_CHEAT_ADDR)),
        lhu("t1", lo(PLAYER_BUST_CHEAT_ADDR), "t0"),
        addiu("t1", "t1", -1),
        bne("t1", "zero", "original"),
        nop(),
        # t0 = DrawC mask base. First clear the always-on head/tail/reverse
        # bits, then add back only the active side for this double-blink phase.
        lui("t0", hi(LIGHT_MASK_BASE_ADDR)),
        addiu("t0", "t0", lo(LIGHT_MASK_BASE_ADDR)),
        lhu("t1", 0x3A, "t0"),
        andi("t1", "t1", 0x7E7E),
        sh("t1", 0x3A, "t0"),
        lhu("t1", 0x30, "t0"),
        andi("t1", "t1", 0x7F7F),
        sh("t1", 0x30, "t0"),
        lhu("t1", 0x32, "t0"),
        andi("t1", "t1", 0x7F7F),
        sh("t1", 0x32, "t0"),
        lhu("t1", 0x34, "t0"),
        andi("t1", "t1", 0x7F7F),
        sh("t1", 0x34, "t0"),
        # phase = (counter / 8) & 7; left 0,1; right 3,4; off otherwise.
        lui("t2", hi(PLAYER_STROBE_COUNTER_ADDR)),
        lw("t2", lo(PLAYER_STROBE_COUNTER_ADDR), "t2"),
        nop(),
        srl("t2", "t2", 3),
        andi("t2", "t2", 0x0007),
        slti("t3", "t2", 2),
        bne("t3", "zero", "left_on"),
        nop(),
        addiu("t3", "t2", -3),
        sltiu("t3", "t3", 2),
        bne("t3", "zero", "right_on"),
        nop(),
        "done",
        j(AFTER_STOCK_FLASH_ADDR),
        addiu("a0", "sp", 24),
        "left_on",
        lhu("t1", 0x08B4, "s2"),
        andi("t3", "t1", 0x0040),
        bne("t3", "zero", "left_front_ok"),
        nop(),
        lhu("t3", 0x00, "t0"),
        andi("t3", "t3", 0x0001),
        bne("t3", "zero", "left_rear"),
        nop(),
        "left_front_ok",
        lhu("t1", 0x3A, "t0"),
        ori("t1", "t1", 0x0081),
        sh("t1", 0x3A, "t0"),
        "left_rear",
        lhu("t3", 0x02, "t0"),
        andi("t3", "t3", 0x0001),
        bne("t3", "zero", "done"),
        nop(),
        lhu("t1", 0x30, "t0"),
        ori("t1", "t1", 0x0080),
        sh("t1", 0x30, "t0"),
        lhu("t1", 0x32, "t0"),
        ori("t1", "t1", 0x0080),
        sh("t1", 0x32, "t0"),
        lhu("t1", 0x34, "t0"),
        ori("t1", "t1", 0x0080),
        sh("t1", 0x34, "t0"),
        j(AFTER_STOCK_FLASH_ADDR),
        addiu("a0", "sp", 24),
        "right_on",
        lhu("t1", 0x08B4, "s2"),
        andi("t3", "t1", 0x0004),
        bne("t3", "zero", "right_front_ok"),
        nop(),
        lhu("t3", 0x00, "t0"),
        andi("t3", "t3", 0x0100),
        bne("t3", "zero", "right_rear"),
        nop(),
        "right_front_ok",
        lhu("t1", 0x3A, "t0"),
        ori("t1", "t1", 0x8100),
        sh("t1", 0x3A, "t0"),
        "right_rear",
        lhu("t3", 0x02, "t0"),
        andi("t3", "t3", 0x0100),
        bne("t3", "zero", "done"),
        nop(),
        lhu("t1", 0x30, "t0"),
        ori("t1", "t1", 0x8000),
        sh("t1", 0x30, "t0"),
        lhu("t1", 0x32, "t0"),
        ori("t1", "t1", 0x8000),
        sh("t1", 0x32, "t0"),
        lhu("t1", 0x34, "t0"),
        ori("t1", "t1", 0x8000),
        sh("t1", 0x34, "t0"),
        j(AFTER_STOCK_FLASH_ADDR),
        addiu("a0", "sp", 24),
        "original",
        lui("v0", 0x8014),
        lw("v0", -6648, "v0"),
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


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: make player front/rear/reverse lights use the alternating double blink rhythm."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    stock_hook = pack([lui("v0", 0x8014), lw("v0", -6648, "v0")])
    patched_hook = pack([j(CAVE_ADDR), nop()])
    cave = make_cave()

    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {stock_hook, patched_hook}:
        raise SystemExit(f"unexpected DrawC flash hook bytes: {current_hook.hex(' ')}")

    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {bytes(CAVE_LEN), cave}:
        raise SystemExit(f"cave is not empty/known at 0x{CAVE_OFF:X}: {current_cave[:16].hex(' ')}")

    if args.revert:
        data[HOOK_OFF : HOOK_OFF + 8] = stock_hook
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    else:
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = cave
        data[HOOK_OFF : HOOK_OFF + 8] = patched_hook

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(bytes(data))}")
    print("player all-lights alternating double blink:", "reverted" if args.revert else "patched")
    print("controlled by existing player-arrest cheat: 800F7A00 0001")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
