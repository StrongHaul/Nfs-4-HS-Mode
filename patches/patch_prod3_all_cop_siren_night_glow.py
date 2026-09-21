#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
RUNTIME_BASE = 0x8000F800

# Old first-person-only experiment hooks in DrawC_NightHeadlight.
NIGHT_START_HOOK_OFF = 0xAFEFC
NIGHT_ADDITIVE_HOOK_OFF = 0xAFFF8
NIGHT_EFFECT_HOOK_OFF = 0xB0004

# Failed all-view experiment in DrawC_PrimStart.  Keep the constants so the
# patch can cleanly remove it when present.
PRIM_HOOK_OFF = 0xB0308
PRIM_RETURN_ADDR = RUNTIME_BASE + 0xB0318

# Race-only callsite hook after DrawC_PrimStart. This avoids hooking the shared
# DrawC_PrimStart body, which is also used by the car-selection menu.
RACE_PRIM_POST_HOOK_OFF = 0xA37F0
RACE_PRIM_POST_RETURN_ADDR = RUNTIME_BASE + 0xA37F8
RACE_PRIM_POST_BRANCH_ADDR = RUNTIME_BASE + 0xA3BF8

# Pre-DrawC_PrimStart brightness hook. This changes the actual lighting
# strength passed into DrawC_PrimStart, unlike the later cache-color attempts
# which only recolored already prepared primitive data.
RACE_BRIGHTNESS_HOOK_OFF = 0xA37E0
RACE_BRIGHTNESS_RETURN_ADDR = RUNTIME_BASE + 0xA37E8
SIREN_GLOW_BRIGHTNESS = 0x80
SIREN_GLOW_RGB = 0x00484848

RACE_CAR_COLOR_HOOK_OFF = 0xA3780
RACE_CAR_COLOR_RETURN_ADDR = RUNTIME_BASE + 0xA3784

THIRD_PERSON_PRIM_CALL_HOOK_OFF = 0xA37E8
THIRD_PERSON_PRIM_CALL_RETURN_ADDR = RUNTIME_BASE + 0xA37F0
OLD_THIRD_PERSON_PRIM_CALL_HOOK_OFF = 0xA3CE8
DRAWC_PRIM_START_ADDR = 0x800BFAC8
NIGHT_NIGHT_CALC_ADDR = 0x800C6CA8
NIGHT_NIGHT_COP_CALC_ADDR = 0x800C6D48

# Disabled all-view cache-color experiment inside DrawC_PrimStart. Keep these
# constants so older builds with that hook can be cleaned up.
PRIM_COLOR_HOOK_OFF = 0xB11D4
PRIM_COLOR_RETURN_ADDR = RUNTIME_BASE + 0xB11DC
PRIM_COLOR_CAVE_OFF = 0x45900
PRIM_COLOR_CAVE_LEN = 0x100

# Free half of the current siren patch cave. The active siren patch uses
# 0x45A00..0x45A7F. Keep the enable word at the very end for GameShark.
CAVE_OFF = 0x45A80
CAVE_LEN = 0x80
EFFECT_CAVE_OFF = 0x45AA0
ENABLE_INSN_OFF = EFFECT_CAVE_OFF
ENABLE_ADDR = RUNTIME_BASE + ENABLE_INSN_OFF

NIGHT_RENDER_ADDR = 0x8014ED08
NIGHT_ADDITIVE_CALC_ADDR = 0x800DCDA4
DRAWC_SIMPLE_OR_MENU_RENDER_ADDR = 0x8014E608

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "a0": 4,
    "a1": 5,
    "a2": 6,
    "a3": 7,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "s1": 17,
    "s2": 18,
    "s3": 19,
    "s4": 20,
    "s5": 21,
    "s6": 22,
    "s7": 23,
    "sp": 29,
    "fp": 30,
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


def or_(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x25)


def addu(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x21)


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


def bltz(rs: str, target: str) -> tuple[str, str, str]:
    return ("bltz", rs, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jal(addr: int) -> int:
    return ins_j(0x03, addr)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def ori(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0D, REG[rs], REG[rt], imm)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def lbu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x24, REG[rs], REG[rt], off)


def lh(rt: str, off: int, rs: str) -> int:
    return ins_i(0x21, REG[rs], REG[rt], off)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def sltiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0B, REG[rs], REG[rt], imm)


def srl(rd: str, rt: str, sh: int) -> int:
    return ins_r(0, REG[rt], REG[rd], sh, 0x02)


def nop() -> int:
    return 0


def pack_labeled(
    items: list[int | str | tuple[str, str, str, str] | tuple[str, str, str]],
    base_pc: int,
) -> bytes:
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
            kind = item[0]
            if kind == "beq":
                _, rs, rt, target = item
                item = ins_i(0x04, REG[rs], REG[rt], (labels[target] - (pc + 4)) >> 2)
            elif kind == "bne":
                _, rs, rt, target = item
                item = ins_i(0x05, REG[rs], REG[rt], (labels[target] - (pc + 4)) >> 2)
            elif kind == "bltz":
                _, rs, target = item
                item = ins_i(0x01, REG[rs], 0, (labels[target] - (pc + 4)) >> 2)
            else:
                raise ValueError(kind)
        words.append(item)
        pc += 4
    return pack(words)


def hook(addr: int, delay: int) -> bytes:
    return pack([j(addr), delay])


def cave() -> bytes:
    # Entry hook for DrawC_NightHeadlight start. It preserves the car pointer
    # for the later effect hook and then resumes the stock prologue.
    start_items: list[int | str | tuple[str, str, str, str]] = [
        or_("a1", "a0", "zero"),
        sw("a0", 0x006C, "sp"),
        j(runtime(NIGHT_START_HOOK_OFF + 8)),
        nop(),
    ]
    start_blob = pack_labeled(start_items, runtime(CAVE_OFF))
    if len(start_blob) > (EFFECT_CAVE_OFF - CAVE_OFF):
        raise SystemExit(f"start cave too large: 0x{len(start_blob):X}")

    items: list[int | str | tuple[str, str, str, str]] = [
        # Cheat patches this immediate:
        #   800552A0 0000 - off
        #   800552A0 0001 - on
        addiu("t1", "zero", 0),
        beq("t1", "zero", "original"),
        lw("t0", 0x006C, "sp"),
        # Some camera/draw paths reach this hook without a valid car pointer in
        # the saved stack slot. DuckStation logs that as invalid 0xFE/0xFF reads.
        # Real car objects live in the 0x80xxxxxx range, so skip anything else.
        srl("t1", "t0", 24),
        addiu("t2", "zero", 0x80),
        bne("t1", "t2", "original"),
        nop(),
        # A car with active siren/flasher state has nonzero 0x08B4/0x08B6.
        lhu("t1", 0x08B4, "t0"),
        lhu("t2", 0x08B6, "t0"),
        or_("t1", "t1", "t2"),
        beq("t1", "zero", "original"),
        sw("zero", 0x0014, "sp"),
        # Fake a local light vector at zero distance and let the stock
        # additive night code brighten the current car color.
        sw("zero", 0x0018, "sp"),
        sw("zero", 0x001C, "sp"),
        addiu("a0", "sp", 0x0014),
        addiu("a1", "t0", 0x0880),
        jal(NIGHT_ADDITIVE_CALC_ADDR),
        nop(),
        "original",
        lui("v0", 0x8014),
        lbu("v0", 0xECC0, "v0"),
        j(runtime(NIGHT_EFFECT_HOOK_OFF + 8)),
        nop(),
    ]
    effect_blob = pack_labeled(items, runtime(EFFECT_CAVE_OFF))
    blob = start_blob.ljust(EFFECT_CAVE_OFF - CAVE_OFF, b"\x00") + effect_blob
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X} > 0x{CAVE_LEN:X}")
    return blob.ljust(CAVE_LEN, b"\x00")


def prim_color_cave(glow_mask: int = 0x00181818) -> bytes:
    items: list[int | str | tuple[str, str, str, str] | tuple[str, str, str]] = [
        # Hook delay already executes: sw v0,0x20(sp).
        lui("t0", (ENABLE_ADDR >> 16) & 0xFFFF),
        lhu("t1", ENABLE_ADDR & 0xFFFF, "t0"),
        beq("t1", "zero", "original_branch"),
        nop(),
        lui("t0", (NIGHT_RENDER_ADDR >> 16) & 0xFFFF),
        lw("t1", NIGHT_RENDER_ADDR & 0xFFFF, "t0"),
        beq("t1", "zero", "original_branch"),
        nop(),
        lhu("t1", 0x08B4, "s3"),
        lhu("t2", 0x08B6, "s3"),
        or_("t1", "t1", "t2"),
        beq("t1", "zero", "original_branch"),
        nop(),
        # External-view cache brightening for the race Draw_CarCache at s2.
        # Keep it neutral and subtle; stronger RGB bitmasks produce red/blue
        # PS1 color artifacts instead of the soft headlight-like wash.
        lui("t0", (glow_mask >> 16) & 0xFFFF),
        ori("t0", "t0", glow_mask & 0xFFFF),
        lw("t1", 0x0090, "s2"),
        or_("t1", "t1", "t0"),
        sw("t1", 0x0090, "s2"),
        lw("t1", 0x0094, "s2"),
        or_("t1", "t1", "t0"),
        sw("t1", 0x0094, "s2"),
        lw("t1", 0x0098, "s2"),
        or_("t1", "t1", "t0"),
        sw("t1", 0x0098, "s2"),
        "original_branch",
        bltz("v0", "skip_draw"),
        nop(),
        j(RACE_PRIM_POST_RETURN_ADDR),
        nop(),
        "skip_draw",
        j(RACE_PRIM_POST_BRANCH_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, runtime(PRIM_COLOR_CAVE_OFF))
    if len(blob) > PRIM_COLOR_CAVE_LEN:
        raise SystemExit(
            f"Prim color cave too large: 0x{len(blob):X} > 0x{PRIM_COLOR_CAVE_LEN:X}"
        )
    return blob.ljust(PRIM_COLOR_CAVE_LEN, b"\x00")


def third_person_additive_cave(return_addr: int = THIRD_PERSON_PRIM_CALL_RETURN_ADDR) -> bytes:
    items: list[int | str | tuple[str, str, str, str] | tuple[str, str, str]] = [
        # Hook delay already executes: sw v0,0x008C(s2).
        sw("ra", 0x000C, "sp"),
        sw("a0", 0x0010, "sp"),
        sw("a1", 0x0014, "sp"),
        sw("a2", 0x0018, "sp"),
        sw("a3", 0x001C, "sp"),
        lui("t0", (ENABLE_ADDR >> 16) & 0xFFFF),
        lhu("t1", ENABLE_ADDR & 0xFFFF, "t0"),
        beq("t1", "zero", "call_prim"),
        nop(),
        lui("t0", (NIGHT_RENDER_ADDR >> 16) & 0xFFFF),
        lw("t1", NIGHT_RENDER_ADDR & 0xFFFF, "t0"),
        beq("t1", "zero", "call_prim"),
        nop(),
        lw("t0", 0x0014, "sp"),
        lhu("t1", 0x08B4, "t0"),
        lhu("t2", 0x08B6, "t0"),
        or_("t1", "t1", "t2"),
        beq("t1", "zero", "call_prim"),
        nop(),
        sw("zero", 0x0000, "sp"),
        sw("zero", 0x0004, "sp"),
        sw("zero", 0x0008, "sp"),
        addiu("a0", "sp", 0x0000),
        addiu("a1", "t0", 0x0880),
        jal(NIGHT_ADDITIVE_CALC_ADDR),
        nop(),
        "call_prim",
        lw("a0", 0x0010, "sp"),
        lw("a1", 0x0014, "sp"),
        lw("a2", 0x0018, "sp"),
        lw("a3", 0x001C, "sp"),
        jal(DRAWC_PRIM_START_ADDR),
        nop(),
        lw("ra", 0x000C, "sp"),
        j(return_addr),
        nop(),
    ]
    blob = pack_labeled(items, runtime(PRIM_COLOR_CAVE_OFF))
    if len(blob) > PRIM_COLOR_CAVE_LEN:
        raise SystemExit(
            f"Third-person additive cave too large: 0x{len(blob):X} > 0x{PRIM_COLOR_CAVE_LEN:X}"
        )
    return blob.ljust(PRIM_COLOR_CAVE_LEN, b"\x00")


def race_post_cop_calc_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str] | tuple[str, str, str]] = [
        # Hook delay already executes: sw v0,0x0020(sp).
        sw("ra", 0x000C, "sp"),
        sw("v0", 0x0010, "sp"),
        lui("t0", (ENABLE_ADDR >> 16) & 0xFFFF),
        lhu("t1", ENABLE_ADDR & 0xFFFF, "t0"),
        beq("t1", "zero", "original_branch"),
        nop(),
        lui("t0", (NIGHT_RENDER_ADDR >> 16) & 0xFFFF),
        lw("t1", NIGHT_RENDER_ADDR & 0xFFFF, "t0"),
        beq("t1", "zero", "original_branch"),
        nop(),
        lhu("t1", 0x08B4, "s3"),
        lhu("t2", 0x08B6, "s3"),
        or_("t1", "t1", "t2"),
        beq("t1", "zero", "original_branch"),
        nop(),
        sw("zero", 0x0014, "sp"),
        sw("zero", 0x0018, "sp"),
        sw("zero", 0x001C, "sp"),
        addiu("a0", "sp", 0x0014),
        addiu("a1", "s2", 0x0090),
        jal(NIGHT_NIGHT_COP_CALC_ADDR),
        or_("a2", "s2", "zero"),
        addiu("a0", "sp", 0x0014),
        addiu("a1", "s2", 0x0092),
        jal(NIGHT_NIGHT_COP_CALC_ADDR),
        or_("a2", "s2", "zero"),
        addiu("a0", "sp", 0x0014),
        addiu("a1", "s2", 0x0094),
        jal(NIGHT_NIGHT_COP_CALC_ADDR),
        or_("a2", "s2", "zero"),
        addiu("a0", "sp", 0x0014),
        addiu("a1", "s2", 0x0096),
        jal(NIGHT_NIGHT_COP_CALC_ADDR),
        or_("a2", "s2", "zero"),
        addiu("a0", "sp", 0x0014),
        addiu("a1", "s2", 0x0098),
        jal(NIGHT_NIGHT_COP_CALC_ADDR),
        or_("a2", "s2", "zero"),
        addiu("a0", "sp", 0x0014),
        addiu("a1", "s2", 0x009A),
        jal(NIGHT_NIGHT_COP_CALC_ADDR),
        or_("a2", "s2", "zero"),
        "original_branch",
        lw("v0", 0x0010, "sp"),
        lw("ra", 0x000C, "sp"),
        bltz("v0", "skip_draw"),
        nop(),
        j(RACE_PRIM_POST_RETURN_ADDR),
        nop(),
        "skip_draw",
        j(RACE_PRIM_POST_BRANCH_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, runtime(PRIM_COLOR_CAVE_OFF))
    if len(blob) > PRIM_COLOR_CAVE_LEN:
        raise SystemExit(
            f"Race post cop-calc cave too large: 0x{len(blob):X} > 0x{PRIM_COLOR_CAVE_LEN:X}"
        )
    return blob.ljust(PRIM_COLOR_CAVE_LEN, b"\x00")


def race_post_night_calc_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str] | tuple[str, str, str]] = [
        # Hook delay already executes: sw v0,0x0020(sp).
        sw("ra", 0x000C, "sp"),
        sw("v0", 0x0010, "sp"),
        lui("t0", (ENABLE_ADDR >> 16) & 0xFFFF),
        lhu("t1", ENABLE_ADDR & 0xFFFF, "t0"),
        beq("t1", "zero", "original_branch"),
        nop(),
        lui("t0", (NIGHT_RENDER_ADDR >> 16) & 0xFFFF),
        lw("t1", NIGHT_RENDER_ADDR & 0xFFFF, "t0"),
        beq("t1", "zero", "original_branch"),
        nop(),
        lhu("t1", 0x08B4, "s3"),
        lhu("t2", 0x08B6, "s3"),
        or_("t1", "t1", "t2"),
        beq("t1", "zero", "original_branch"),
        nop(),
        # Neutral night-table lighting, not cop red/blue light tables.
        sw("zero", 0x0014, "sp"),
        sw("zero", 0x0018, "sp"),
        sw("zero", 0x001C, "sp"),
        addiu("a0", "sp", 0x0014),
        jal(NIGHT_NIGHT_CALC_ADDR),
        addiu("a1", "s2", 0x0090),
        addiu("a0", "sp", 0x0014),
        jal(NIGHT_NIGHT_CALC_ADDR),
        addiu("a1", "s2", 0x0092),
        addiu("a0", "sp", 0x0014),
        jal(NIGHT_NIGHT_CALC_ADDR),
        addiu("a1", "s2", 0x0094),
        addiu("a0", "sp", 0x0014),
        jal(NIGHT_NIGHT_CALC_ADDR),
        addiu("a1", "s2", 0x0096),
        addiu("a0", "sp", 0x0014),
        jal(NIGHT_NIGHT_CALC_ADDR),
        addiu("a1", "s2", 0x0098),
        addiu("a0", "sp", 0x0014),
        jal(NIGHT_NIGHT_CALC_ADDR),
        addiu("a1", "s2", 0x009A),
        "original_branch",
        lw("v0", 0x0010, "sp"),
        lw("ra", 0x000C, "sp"),
        bltz("v0", "skip_draw"),
        nop(),
        j(RACE_PRIM_POST_RETURN_ADDR),
        nop(),
        "skip_draw",
        j(RACE_PRIM_POST_BRANCH_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, runtime(PRIM_COLOR_CAVE_OFF))
    if len(blob) > PRIM_COLOR_CAVE_LEN:
        raise SystemExit(
            f"Race post night-calc cave too large: 0x{len(blob):X} > 0x{PRIM_COLOR_CAVE_LEN:X}"
        )
    return blob.ljust(PRIM_COLOR_CAVE_LEN, b"\x00")


def race_pre_brightness_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str] | tuple[str, str, str]] = [
        # Hook delay already executes the stock: addu a2,s6,zero.
        lui("t0", (ENABLE_ADDR >> 16) & 0xFFFF),
        lhu("t1", ENABLE_ADDR & 0xFFFF, "t0"),
        beq("t1", "zero", "original"),
        nop(),
        lui("t0", (NIGHT_RENDER_ADDR >> 16) & 0xFFFF),
        lw("t1", NIGHT_RENDER_ADDR & 0xFFFF, "t0"),
        beq("t1", "zero", "original"),
        nop(),
        lhu("t1", 0x08B4, "s3"),
        lhu("t2", 0x08B6, "s3"),
        or_("t1", "t1", "t2"),
        beq("t1", "zero", "original"),
        nop(),
        # This is the real DrawC_PrimStart lighting argument. Keep s6 and a2
        # aligned because nearby code treats s6 as the current car brightness.
        addiu("s6", "zero", SIREN_GLOW_BRIGHTNESS),
        addu("a2", "s6", "zero"),
        "original",
        lui("a3", 0x1F80),
        j(RACE_BRIGHTNESS_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, runtime(PRIM_COLOR_CAVE_OFF))
    if len(blob) > PRIM_COLOR_CAVE_LEN:
        raise SystemExit(
            f"Race pre-brightness cave too large: 0x{len(blob):X} > 0x{PRIM_COLOR_CAVE_LEN:X}"
        )
    return blob.ljust(PRIM_COLOR_CAVE_LEN, b"\x00")


def race_pre_car_color_cave(glow_rgb: int = SIREN_GLOW_RGB) -> bytes:
    items: list[int | str | tuple[str, str, str, str] | tuple[str, str, str]] = [
        # Hook delay already executes the stock: lw v0,0x0880(s3).
        lui("t0", (ENABLE_ADDR >> 16) & 0xFFFF),
        lhu("t1", ENABLE_ADDR & 0xFFFF, "t0"),
        beq("t1", "zero", "original"),
        nop(),
        lui("t0", (NIGHT_RENDER_ADDR >> 16) & 0xFFFF),
        lw("t1", NIGHT_RENDER_ADDR & 0xFFFF, "t0"),
        beq("t1", "zero", "original"),
        nop(),
        lhu("t1", 0x08B4, "s3"),
        lhu("t2", 0x08B6, "s3"),
        or_("t1", "t1", "t2"),
        beq("t1", "zero", "original"),
        nop(),
        # External renderer derives the car body brightness from car+0x880
        # immediately after this hook. Raise that source color itself.
        lui("v0", (glow_rgb >> 16) & 0xFFFF),
        ori("v0", "v0", glow_rgb & 0xFFFF),
        sw("v0", 0x0880, "s3"),
        "original",
        j(RACE_CAR_COLOR_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, runtime(PRIM_COLOR_CAVE_OFF))
    if len(blob) > PRIM_COLOR_CAVE_LEN:
        raise SystemExit(
            f"Race pre-car-color cave too large: 0x{len(blob):X} > 0x{PRIM_COLOR_CAVE_LEN:X}"
        )
    return blob.ljust(PRIM_COLOR_CAVE_LEN, b"\x00")


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="PROD3: optional all-view siren night glow cheat.")
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    stock_night_start = pack([
        addiu("sp", "sp", -128),
        ins_r(REG["a0"], REG["zero"], REG["a1"], 0, 0x21),  # addu a1,a0,zero
        lui("v1", 0x8012),
        lui("v0", 0x8011),
    ])
    patched_night_start = pack([j(runtime(CAVE_OFF)), addiu("sp", "sp", -128)]) + stock_night_start[8:]
    current_night_start = bytes(data[NIGHT_START_HOOK_OFF : NIGHT_START_HOOK_OFF + len(stock_night_start)])
    if current_night_start not in [stock_night_start, patched_night_start]:
        raise SystemExit(f"unexpected NightHeadlight start hook: {current_night_start.hex(' ')}")

    stock_night_effect = pack([lui("v0", 0x8014), lbu("v0", 0xECC0, "v0")])
    patched_night_effect = pack([j(runtime(EFFECT_CAVE_OFF)), nop()])
    current_night_effect = bytes(data[NIGHT_EFFECT_HOOK_OFF : NIGHT_EFFECT_HOOK_OFF + 8])
    if current_night_effect not in [stock_night_effect, patched_night_effect]:
        raise SystemExit(f"unexpected NightHeadlight effect hook: {current_night_effect.hex(' ')}")

    stock_night_additive = pack([lw("a1", 0x0068, "sp"), jal(NIGHT_ADDITIVE_CALC_ADDR), nop()])
    patched_night_additive = pack([j(runtime(EFFECT_CAVE_OFF)), lw("a1", 0x0068, "sp"), nop()])
    current_night_additive = bytes(
        data[NIGHT_ADDITIVE_HOOK_OFF : NIGHT_ADDITIVE_HOOK_OFF + 12]
    )
    if current_night_additive not in [stock_night_additive, patched_night_additive]:
        raise SystemExit(f"unexpected NightHeadlight additive hook: {current_night_additive.hex(' ')}")

    stock_prim = pack([lh("s1", 0x08BC, "s2"), addiu("t0", "t0", 0x07B8)])
    patched_prim = hook(runtime(CAVE_OFF), lh("s1", 0x08BC, "s2"))
    current_prim = bytes(data[PRIM_HOOK_OFF : PRIM_HOOK_OFF + 8])
    if current_prim not in [stock_prim, patched_prim]:
        raise SystemExit(f"unexpected PrimStart hook: {current_prim.hex(' ')}")

    stock_prim_color = pack([lw("v0", 0x0864, "s2"), lw("ra", 0x0044, "sp")])
    patched_prim_color = hook(runtime(PRIM_COLOR_CAVE_OFF), lw("v0", 0x0864, "s2"))
    current_prim_color = bytes(data[PRIM_COLOR_HOOK_OFF : PRIM_COLOR_HOOK_OFF + 8])
    if current_prim_color not in [stock_prim_color, patched_prim_color]:
        raise SystemExit(f"unexpected PrimStart color hook: {current_prim_color.hex(' ')}")

    stock_race_prim_post = pack([
        ins_i(0x01, REG["v0"], 0, (RACE_PRIM_POST_BRANCH_ADDR - (runtime(RACE_PRIM_POST_HOOK_OFF) + 4)) >> 2),
        sw("v0", 0x0020, "sp"),
    ])
    patched_race_prim_post = hook(runtime(PRIM_COLOR_CAVE_OFF), sw("v0", 0x0020, "sp"))
    current_race_prim_post = bytes(data[RACE_PRIM_POST_HOOK_OFF : RACE_PRIM_POST_HOOK_OFF + 8])
    if current_race_prim_post not in [stock_race_prim_post, patched_race_prim_post]:
        raise SystemExit(f"unexpected race PrimStart post hook: {current_race_prim_post.hex(' ')}")

    stock_race_brightness = pack([addu("a2", "s6", "zero"), lui("a3", 0x1F80)])
    patched_race_brightness = hook(runtime(PRIM_COLOR_CAVE_OFF), addu("a2", "s6", "zero"))
    current_race_brightness = bytes(
        data[RACE_BRIGHTNESS_HOOK_OFF : RACE_BRIGHTNESS_HOOK_OFF + 8]
    )
    if current_race_brightness not in [stock_race_brightness, patched_race_brightness]:
        raise SystemExit(f"unexpected race brightness hook: {current_race_brightness.hex(' ')}")

    stock_race_car_color = pack([lw("v0", 0x0880, "s3"), ori("a0", "a0", 0x5556)])
    patched_race_car_color = hook(runtime(PRIM_COLOR_CAVE_OFF), lw("v0", 0x0880, "s3"))
    current_race_car_color = bytes(
        data[RACE_CAR_COLOR_HOOK_OFF : RACE_CAR_COLOR_HOOK_OFF + 8]
    )
    if current_race_car_color not in [stock_race_car_color, patched_race_car_color]:
        raise SystemExit(f"unexpected race car-color hook: {current_race_car_color.hex(' ')}")

    stock_third_person_prim_call = pack([jal(DRAWC_PRIM_START_ADDR), sw("v0", 0x008C, "s2")])
    patched_third_person_prim_call = hook(runtime(PRIM_COLOR_CAVE_OFF), sw("v0", 0x008C, "s2"))
    current_third_person_prim_call = bytes(
        data[THIRD_PERSON_PRIM_CALL_HOOK_OFF : THIRD_PERSON_PRIM_CALL_HOOK_OFF + 8]
    )
    if current_third_person_prim_call not in [
        stock_third_person_prim_call,
        patched_third_person_prim_call,
    ]:
        raise SystemExit(
            f"unexpected third-person PrimStart call hook: {current_third_person_prim_call.hex(' ')}"
        )

    old_stock_third_person_prim_call = pack([jal(DRAWC_PRIM_START_ADDR), lui("a3", 0x1F80)])
    old_patched_third_person_prim_call = hook(runtime(PRIM_COLOR_CAVE_OFF), lui("a3", 0x1F80))
    current_old_third_person_prim_call = bytes(
        data[OLD_THIRD_PERSON_PRIM_CALL_HOOK_OFF : OLD_THIRD_PERSON_PRIM_CALL_HOOK_OFF + 8]
    )
    if current_old_third_person_prim_call not in [
        old_stock_third_person_prim_call,
        old_patched_third_person_prim_call,
    ]:
        raise SystemExit(
            "unexpected old third-person PrimStart call hook: "
            f"{current_old_third_person_prim_call.hex(' ')}"
        )

    new_cave = cave()
    new_prim_color_cave = race_pre_car_color_cave()
    old_505050_car_color_cave = race_pre_car_color_cave(0x00505050)
    old_softer_car_color_cave = race_pre_car_color_cave(0x00606060)
    old_soft_car_color_cave = race_pre_car_color_cave(0x00707070)
    old_medium_car_color_cave = race_pre_car_color_cave(0x00A0A0A0)
    old_strong_car_color_cave = race_pre_car_color_cave(0x00C0C0C0)
    old_no_third_person_cave = b"\x00" * PRIM_COLOR_CAVE_LEN
    old_brightness_cave = race_pre_brightness_cave()
    old_night_calc_cave = race_post_night_calc_cave()
    old_cop_calc_cave = race_post_cop_calc_cave()
    old_first_call_additive_cave = third_person_additive_cave()
    old_second_call_additive_cave = third_person_additive_cave(
        RUNTIME_BASE + OLD_THIRD_PERSON_PRIM_CALL_HOOK_OFF + 8
    )
    old_soft_cache_cave = prim_color_cave(0x00181818)
    old_strong_prim_color_cave = prim_color_cave(0x00404040)
    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in [b"\x00" * CAVE_LEN, new_cave]:
        # This area is reserved for this feature and previous failed variants.
        # Be conservative about hook bytes, but allow replacing our own old cave.
        if current_night_start == stock_night_start and current_night_effect == stock_night_effect and current_prim == stock_prim:
            raise SystemExit(f"cave is not empty at 0x{CAVE_OFF:X}")

    # Always remove the failed all-view PrimStart experiment.
    data[PRIM_HOOK_OFF : PRIM_HOOK_OFF + 8] = stock_prim

    current_prim_color_cave = bytes(
        data[PRIM_COLOR_CAVE_OFF : PRIM_COLOR_CAVE_OFF + PRIM_COLOR_CAVE_LEN]
    )
    if current_prim_color_cave not in [
        b"\x00" * PRIM_COLOR_CAVE_LEN,
        new_prim_color_cave,
        old_505050_car_color_cave,
        old_softer_car_color_cave,
        old_soft_car_color_cave,
        old_medium_car_color_cave,
        old_strong_car_color_cave,
        old_no_third_person_cave,
        old_brightness_cave,
        old_night_calc_cave,
        old_first_call_additive_cave,
        old_second_call_additive_cave,
        old_cop_calc_cave,
        old_soft_cache_cave,
        old_strong_prim_color_cave,
    ]:
        raise SystemExit(f"Prim color cave is not empty/known at 0x{PRIM_COLOR_CAVE_OFF:X}")

    if current_cave not in [b"\x00" * CAVE_LEN, new_cave]:
        # Continue only if one of this feature's hooks is active; otherwise it
        # might be unrelated data.
        if current_night_start == stock_night_start and current_night_effect == stock_night_effect and current_prim == stock_prim:
            raise SystemExit(f"cave is not empty/known at 0x{CAVE_OFF:X}")

    if args.revert:
        data[NIGHT_START_HOOK_OFF : NIGHT_START_HOOK_OFF + len(stock_night_start)] = stock_night_start
        data[NIGHT_ADDITIVE_HOOK_OFF : NIGHT_ADDITIVE_HOOK_OFF + 12] = stock_night_additive
        data[NIGHT_EFFECT_HOOK_OFF : NIGHT_EFFECT_HOOK_OFF + 8] = stock_night_effect
        data[PRIM_HOOK_OFF : PRIM_HOOK_OFF + 8] = stock_prim
        data[PRIM_COLOR_HOOK_OFF : PRIM_COLOR_HOOK_OFF + 8] = stock_prim_color
        data[RACE_PRIM_POST_HOOK_OFF : RACE_PRIM_POST_HOOK_OFF + 8] = stock_race_prim_post
        data[RACE_BRIGHTNESS_HOOK_OFF : RACE_BRIGHTNESS_HOOK_OFF + 8] = stock_race_brightness
        data[RACE_CAR_COLOR_HOOK_OFF : RACE_CAR_COLOR_HOOK_OFF + 8] = stock_race_car_color
        data[THIRD_PERSON_PRIM_CALL_HOOK_OFF : THIRD_PERSON_PRIM_CALL_HOOK_OFF + 8] = (
            stock_third_person_prim_call
        )
        data[OLD_THIRD_PERSON_PRIM_CALL_HOOK_OFF : OLD_THIRD_PERSON_PRIM_CALL_HOOK_OFF + 8] = (
            old_stock_third_person_prim_call
        )
        data[PRIM_COLOR_CAVE_OFF : PRIM_COLOR_CAVE_OFF + PRIM_COLOR_CAVE_LEN] = (
            b"\x00" * PRIM_COLOR_CAVE_LEN
        )
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = b"\x00" * CAVE_LEN
    else:
        data[NIGHT_START_HOOK_OFF : NIGHT_START_HOOK_OFF + len(stock_night_start)] = patched_night_start
        data[NIGHT_ADDITIVE_HOOK_OFF : NIGHT_ADDITIVE_HOOK_OFF + 12] = stock_night_additive
        data[NIGHT_EFFECT_HOOK_OFF : NIGHT_EFFECT_HOOK_OFF + 8] = patched_night_effect
        # Keep the external-view experiment disabled by default. DrawC_PrimStart
        # also runs during car selection, and the menu guard was not reliable
        # enough there. This still removes it if a previous build installed it.
        data[PRIM_COLOR_HOOK_OFF : PRIM_COLOR_HOOK_OFF + 8] = stock_prim_color
        data[RACE_PRIM_POST_HOOK_OFF : RACE_PRIM_POST_HOOK_OFF + 8] = stock_race_prim_post
        data[RACE_BRIGHTNESS_HOOK_OFF : RACE_BRIGHTNESS_HOOK_OFF + 8] = stock_race_brightness
        data[RACE_CAR_COLOR_HOOK_OFF : RACE_CAR_COLOR_HOOK_OFF + 8] = patched_race_car_color
        data[THIRD_PERSON_PRIM_CALL_HOOK_OFF : THIRD_PERSON_PRIM_CALL_HOOK_OFF + 8] = (
            stock_third_person_prim_call
        )
        data[OLD_THIRD_PERSON_PRIM_CALL_HOOK_OFF : OLD_THIRD_PERSON_PRIM_CALL_HOOK_OFF + 8] = (
            old_stock_third_person_prim_call
        )
        data[PRIM_COLOR_CAVE_OFF : PRIM_COLOR_CAVE_OFF + PRIM_COLOR_CAVE_LEN] = (
            b"\x00" * PRIM_COLOR_CAVE_LEN
        )
        data[PRIM_COLOR_CAVE_OFF : PRIM_COLOR_CAVE_OFF + PRIM_COLOR_CAVE_LEN] = (
            new_prim_color_cave
        )
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = b"\x00" * CAVE_LEN
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = new_cave

    if bytes(data) != original:
        exe.write_bytes(data)

    cheat = 0x80000000 | (ENABLE_ADDR & 0x1FFFFF)
    print(("reverted" if args.revert else "patched"), exe)
    if not args.revert:
        print(f"GameShark: {cheat:08X} 0000 off, {cheat:08X} 0001 on")
    print(f"md5 {hashlib.md5(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
