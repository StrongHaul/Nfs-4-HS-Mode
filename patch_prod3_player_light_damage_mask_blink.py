#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_light_damage_mask_blink"
RUNTIME_BASE = 0x8000F800

# DrawC_PrimStart, immediately after the R3DCar_InMenu damage-block gate and
# before the stock damage[] checks start OR-ing DrawC_gOverlay/SHORT_8011f50a.
# This lets us use the game's own damaged-light masks instead of clearing final
# draw masks later.
HOOK_OFF = 0xB04F8
HOOK_ADDR = RUNTIME_BASE + HOOK_OFF
RETURN_ADDR = HOOK_ADDR + 8

CAVE_OFF = 0x45000
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x180

PLAYER_CAR_OBJ_PTR_ADDR = 0x80110D0C
PLAYER_STROBE_COUNTER_ADDR = 0x800550FC
LIGHT_DAMAGE_MASK_BASE_ADDR = 0x801207F8

REG = {
    "zero": 0,
    "v1": 3,
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


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


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


def done() -> list[int]:
    return [
        lw("t0", 0, "sp"),
        lw("t1", 4, "sp"),
        lw("t2", 8, "sp"),
        lw("t3", 12, "sp"),
        addiu("sp", "sp", 16),
        lw("v1", 0x0218, "s2"),
        j(RETURN_ADDR),
        nop(),
    ]


def make_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        addiu("sp", "sp", -16),
        sw("t0", 0, "sp"),
        sw("t1", 4, "sp"),
        sw("t2", 8, "sp"),
        sw("t3", 12, "sp"),
        # Player car only. Menu rendering never reaches this hook because the
        # original R3DCar_InMenu branch skips the whole damage block.
        lui("t0", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
        lw("t1", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t0"),
        nop(),
        bne("s2", "t1", "done"),
        nop(),
        # Civilian player model slots only. Police player models keep stock behavior.
        lhu("t1", 0x08BC, "s2"),
        slti("t1", "t1", 0x16),
        beq("t1", "zero", "done"),
        nop(),
        # phase = (counter / 8) & 7. The same counter drives the already stable
        # alternating turn/strobe rhythm.
        lui("t2", hi(PLAYER_STROBE_COUNTER_ADDR)),
        lw("t2", lo(PLAYER_STROBE_COUNTER_ADDR), "t2"),
        nop(),
        srl("t2", "t2", 3),
        andi("t2", "t2", 0x0007),
        lui("t0", hi(LIGHT_DAMAGE_MASK_BASE_ADDR)),
        addiu("t0", "t0", lo(LIGHT_DAMAGE_MASK_BASE_ADDR)),
        slti("t3", "t2", 2),
        bne("t3", "zero", "left_on"),
        nop(),
        addiu("t3", "t2", -3),
        sltiu("t3", "t3", 2),
        bne("t3", "zero", "right_on"),
        nop(),
        # Off gap: mark both light sides as damaged/off.
        lhu("t1", 0x00, "t0"),
        ori("t1", "t1", 0x0101),
        sh("t1", 0x00, "t0"),
        lhu("t1", 0x02, "t0"),
        ori("t1", "t1", 0x0101),
        sh("t1", 0x02, "t0"),
        beq("zero", "zero", "done"),
        nop(),
        "left_on",
        # Left visible: suppress right front/rear/reverse using stock damage bits.
        lhu("t1", 0x00, "t0"),
        ori("t1", "t1", 0x0100),
        sh("t1", 0x00, "t0"),
        lhu("t1", 0x02, "t0"),
        ori("t1", "t1", 0x0100),
        sh("t1", 0x02, "t0"),
        beq("zero", "zero", "done"),
        nop(),
        "right_on",
        # Right visible: suppress left front/rear/reverse using stock damage bits.
        lhu("t1", 0x00, "t0"),
        ori("t1", "t1", 0x0001),
        sh("t1", 0x00, "t0"),
        lhu("t1", 0x02, "t0"),
        ori("t1", "t1", 0x0001),
        sh("t1", 0x02, "t0"),
        "done",
        *done(),
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
        description="PROD3: blink player lights by feeding stock damaged-light masks."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    stock_hook = pack([lw("v1", 0x0218, "s2"), nop()])
    patched_hook = pack([j(CAVE_ADDR), nop()])
    cave = make_cave()

    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {stock_hook, patched_hook}:
        raise SystemExit(f"unexpected DrawC damage hook bytes: {current_hook.hex(' ')}")

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
    print("player damaged-light mask blink:", "reverted" if args.revert else "patched")
    print("no cheat gate; stock damage masks choose which side is hidden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
