#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_reverse_lights_object_blink"
RUNTIME_BASE = 0x8000F800

# R3DCar_InsertCarFacet, object visibility switch, case 0x11:
#   lbu v0,0x0442(s5)          ; carObj->control.gear
#   beq v0,zero,visible
#
# The previous DrawC hook could only affect the reverse-light mask after this
# object was already accepted. This hook controls the actual white reverse-light
# object visibility, so it can blink even when the car is not reversing.
HOOK_OFF = 0xA1974
HOOK_ADDR = RUNTIME_BASE + HOOK_OFF

VISIBLE_ADDR = 0x800B126C
HIDDEN_ADDR = 0x800B1264
GEAR_NONZERO_ADDR = 0x800B1184

# Keep this outside any executed delay slots of the 0x800F7A00/0x800F7B00
# cheat-controlled player-arrest caves. 0xE8240 is the delay slot after the
# candidate cave's final jump, and 0xFF200 proved unsafe for this hook.
OBJECT_CAVE_OFF = 0xE8350
OBJECT_CAVE_ADDR = RUNTIME_BASE + OBJECT_CAVE_OFF
OBJECT_CAVE_LEN = 0xB0

LEGACY_OBJECT_CAVE_OFF = 0xE8240
LEGACY_OBJECT_CAVE_ADDR = RUNTIME_BASE + LEGACY_OBJECT_CAVE_OFF
LEGACY_OBJECT_CAVE_LEN = 0xC0
FAR_OBJECT_CAVE_OFF = 0xFF200
FAR_OBJECT_CAVE_ADDR = RUNTIME_BASE + FAR_OBJECT_CAVE_OFF
FAR_OBJECT_CAVE_LEN = 0xC0

DRAW_CAVE_OFF = 0xE803C
DRAW_CAVE_ADDR = RUNTIME_BASE + DRAW_CAVE_OFF
DRAW_CAVE_LEN = 0xC0

DRAW_HOOK_OFF = 0xB0778
DRAW_ON_RETURN_ADDR = RUNTIME_BASE + 0xB0788
DRAW_SKIP_REVERSE_ADDR = RUNTIME_BASE + 0xB07CC

PLAYER_CAR_OBJ_PTR_ADDR = 0x80110D0C

# Reuse the private counter from the already-working player civilian double
# blink hook, so the reverse objects follow the same on/off cadence.
PLAYER_STROBE_COUNTER_ADDR = 0x800550FC

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "t0": 8,
    "t1": 9,
    "s2": 18,
    "s4": 20,
    "s5": 21,
    "s7": 23,
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


def lbu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x24, REG[rs], REG[rt], off)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def ori(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0D, REG[rs], REG[rt], imm)


def slti(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0A, REG[rs], REG[rt], imm)


def sltiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0B, REG[rs], REG[rt], imm)


def srl(rd: str, rt: str, sh: int) -> int:
    return ins_r(0, REG[rt], REG[rd], sh, 0x02)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


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


def make_object_cave(base_addr: int = OBJECT_CAVE_ADDR) -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Hook delay slot already loaded the stock gear byte into v0.
        addiu("sp", "sp", -8),
        sw("t0", 0, "sp"),
        sw("t1", 4, "sp"),
        # Only the player's car gets the always-blink reverse-light object.
        lui("t0", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
        lw("t0", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t0"),
        nop(),
        bne("s5", "t0", "stock"),
        nop(),
        # Leave police car types on the original gear-based behavior.
        slti("t0", "s7", 0x16),
        beq("t0", "zero", "stock"),
        nop(),
        lui("t0", hi(PLAYER_STROBE_COUNTER_ADDR)),
        lw("t1", lo(PLAYER_STROBE_COUNTER_ADDR), "t0"),
        nop(),
        # phase = (counter / 8) & 7
        # on: 0,1 then 3,4. off: 2 and 5,6,7.
        srl("t1", "t1", 3),
        andi("t1", "t1", 0x0007),
        slti("t0", "t1", 2),
        bne("t0", "zero", "visible"),
        nop(),
        addiu("t0", "t1", -3),
        sltiu("t0", "t0", 2),
        bne("t0", "zero", "visible"),
        nop(),
        "hidden",
        lw("t0", 0, "sp"),
        lw("t1", 4, "sp"),
        addiu("sp", "sp", 8),
        j(HIDDEN_ADDR),
        nop(),
        "visible",
        lw("t0", 0, "sp"),
        lw("t1", 4, "sp"),
        addiu("sp", "sp", 8),
        j(VISIBLE_ADDR),
        addiu("v1", "s4", -6),
        "stock",
        lw("t0", 0, "sp"),
        lw("t1", 4, "sp"),
        addiu("sp", "sp", 8),
        bne("v0", "zero", "stock_gear_nonzero"),
        nop(),
        j(VISIBLE_ADDR),
        addiu("v1", "s4", -6),
        "stock_gear_nonzero",
        j(GEAR_NONZERO_ADDR),
        addiu("v1", "s4", -6),
    ]
    blob = pack_labeled(items, base_addr)
    if len(blob) > OBJECT_CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob + bytes(OBJECT_CAVE_LEN - len(blob))


def make_draw_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Hook delay slot already loaded the stock gear byte into v0.
        # Affect civilian models only. Police cars and copbots keep the
        # original reverse-gear condition.
        lhu("t1", 0x08BC, "s2"),
        slti("t1", "t1", 0x16),
        beq("t1", "zero", "stock"),
        nop(),
        lui("t0", hi(PLAYER_STROBE_COUNTER_ADDR)),
        lw("t1", lo(PLAYER_STROBE_COUNTER_ADDR), "t0"),
        nop(),
        srl("t1", "t1", 3),
        andi("t1", "t1", 0x0007),
        slti("t0", "t1", 2),
        bne("t0", "zero", "white_mask_on"),
        nop(),
        addiu("t0", "t1", -3),
        sltiu("t0", "t0", 2),
        bne("t0", "zero", "white_mask_on"),
        nop(),
        j(DRAW_SKIP_REVERSE_ADDR),
        nop(),
        "white_mask_on",
        j(DRAW_ON_RETURN_ADDR),
        lui("v0", 0x8012),
        "stock",
        bne("v0", "zero", "stock_gear_nonzero"),
        nop(),
        j(DRAW_ON_RETURN_ADDR),
        lui("v0", 0x8012),
        "stock_gear_nonzero",
        j(DRAW_SKIP_REVERSE_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, DRAW_CAVE_ADDR)
    if len(blob) > DRAW_CAVE_LEN:
        raise SystemExit(f"draw cave too large: 0x{len(blob):X}")
    return blob + bytes(DRAW_CAVE_LEN - len(blob))


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="PROD3: blink player reverse-light objects.")
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    object_stock_hook = pack([lbu("v0", 0x0442, "s5"), nop()])
    object_patched_hook = pack([j(OBJECT_CAVE_ADDR), lbu("v0", 0x0442, "s5")])
    object_legacy_hook = pack([j(LEGACY_OBJECT_CAVE_ADDR), lbu("v0", 0x0442, "s5")])
    object_far_hook = pack([j(FAR_OBJECT_CAVE_ADDR), lbu("v0", 0x0442, "s5")])
    object_cave = make_object_cave()
    object_legacy_cave = make_object_cave(LEGACY_OBJECT_CAVE_ADDR) + bytes(
        LEGACY_OBJECT_CAVE_LEN - OBJECT_CAVE_LEN
    )
    object_far_cave = make_object_cave(FAR_OBJECT_CAVE_ADDR) + bytes(
        FAR_OBJECT_CAVE_LEN - OBJECT_CAVE_LEN
    )

    draw_stock_hook = pack([lbu("v0", 0x0442, "s2"), nop()])
    draw_patched_hook = pack([j(DRAW_CAVE_ADDR), lbu("v0", 0x0442, "s2")])
    draw_cave = make_draw_cave()

    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {
        object_stock_hook,
        object_patched_hook,
        object_legacy_hook,
        object_far_hook,
    }:
        raise SystemExit(f"unexpected reverse-light hook bytes: {current_hook.hex(' ')}")

    current_cave = bytes(data[OBJECT_CAVE_OFF : OBJECT_CAVE_OFF + OBJECT_CAVE_LEN])
    if current_cave not in {bytes(OBJECT_CAVE_LEN), object_cave}:
        raise SystemExit(
            f"object cave is not empty/known at 0x{OBJECT_CAVE_OFF:X}: {current_cave[:16].hex(' ')}"
        )

    current_legacy_cave = bytes(
        data[LEGACY_OBJECT_CAVE_OFF : LEGACY_OBJECT_CAVE_OFF + LEGACY_OBJECT_CAVE_LEN]
    )
    if current_legacy_cave not in {bytes(LEGACY_OBJECT_CAVE_LEN), object_legacy_cave}:
        raise SystemExit(
            f"legacy object cave is not empty/known at 0x{LEGACY_OBJECT_CAVE_OFF:X}: "
            f"{current_legacy_cave[:16].hex(' ')}"
        )

    current_far_cave = bytes(data[FAR_OBJECT_CAVE_OFF : FAR_OBJECT_CAVE_OFF + FAR_OBJECT_CAVE_LEN])
    if current_far_cave not in {bytes(FAR_OBJECT_CAVE_LEN), object_far_cave}:
        raise SystemExit(
            f"far object cave is not empty/known at 0x{FAR_OBJECT_CAVE_OFF:X}: "
            f"{current_far_cave[:16].hex(' ')}"
        )

    current_draw_hook = bytes(data[DRAW_HOOK_OFF : DRAW_HOOK_OFF + 8])
    if current_draw_hook not in {draw_stock_hook, draw_patched_hook}:
        raise SystemExit(f"unexpected DrawC reverse mask hook: {current_draw_hook.hex(' ')}")

    current_draw_cave = bytes(data[DRAW_CAVE_OFF : DRAW_CAVE_OFF + DRAW_CAVE_LEN])
    if current_draw_cave not in {bytes(DRAW_CAVE_LEN), draw_cave}:
        raise SystemExit(
            f"DrawC cave is not empty/known at 0x{DRAW_CAVE_OFF:X}: {current_draw_cave[:16].hex(' ')}"
        )

    if args.revert:
        data[HOOK_OFF : HOOK_OFF + 8] = object_stock_hook
        data[OBJECT_CAVE_OFF : OBJECT_CAVE_OFF + OBJECT_CAVE_LEN] = bytes(OBJECT_CAVE_LEN)
        data[LEGACY_OBJECT_CAVE_OFF : LEGACY_OBJECT_CAVE_OFF + LEGACY_OBJECT_CAVE_LEN] = bytes(
            LEGACY_OBJECT_CAVE_LEN
        )
        data[FAR_OBJECT_CAVE_OFF : FAR_OBJECT_CAVE_OFF + FAR_OBJECT_CAVE_LEN] = bytes(
            FAR_OBJECT_CAVE_LEN
        )
        data[DRAW_HOOK_OFF : DRAW_HOOK_OFF + 8] = draw_stock_hook
        data[DRAW_CAVE_OFF : DRAW_CAVE_OFF + DRAW_CAVE_LEN] = bytes(DRAW_CAVE_LEN)
    else:
        data[OBJECT_CAVE_OFF : OBJECT_CAVE_OFF + OBJECT_CAVE_LEN] = object_cave
        data[LEGACY_OBJECT_CAVE_OFF : LEGACY_OBJECT_CAVE_OFF + LEGACY_OBJECT_CAVE_LEN] = bytes(
            LEGACY_OBJECT_CAVE_LEN
        )
        data[FAR_OBJECT_CAVE_OFF : FAR_OBJECT_CAVE_OFF + FAR_OBJECT_CAVE_LEN] = bytes(
            FAR_OBJECT_CAVE_LEN
        )
        data[HOOK_OFF : HOOK_OFF + 8] = object_patched_hook
        data[DRAW_CAVE_OFF : DRAW_CAVE_OFF + DRAW_CAVE_LEN] = draw_cave
        data[DRAW_HOOK_OFF : DRAW_HOOK_OFF + 8] = draw_patched_hook

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {hashlib.md5(bytes(data)).hexdigest().upper()}")
    print("reverse light object blink:", "reverted" if args.revert else "patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
