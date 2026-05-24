#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import struct
from pathlib import Path


RUNTIME_BASE = 0x8000F800
EXE_GLOB = "PROD 3*/NFS4.EXE"

CONTROLS_CAVE_OFF = 0xE8300
CONTROLS_CAVE_ADDR = RUNTIME_BASE + CONTROLS_CAVE_OFF
CONTROLS_CAVE_LEN = 0x100
CONTROLS_CAVE_PREFIX = bytes.fromhex("0C 0D 43 8C 00 00 08 24")

HUD_BRANCH_OFF = 0xC9774
HUD_BRANCH_STOCK = bytes.fromhex(
    "AA 00 40 10"  # beq v0,zero,0x800d9220
    "00 00 00 00"  # nop
)
HUD_BRANCH_CAVE_OFF = 0xFEB80
HUD_BRANCH_CAVE_ADDR = RUNTIME_BASE + HUD_BRANCH_CAVE_OFF
HUD_BRANCH_CAVE_LEN = 0x80
HUD_RENDER_OVERLAY_ADDR = 0x800D8F7C
HUD_SKIP_OVERLAY_ADDR = 0x800D9220

BANNER_TIMER_OFF = 0xFF200
BANNER_TIMER_ADDR = RUNTIME_BASE + BANNER_TIMER_OFF
BANNER_TIMER_LEN = 4
BANNER_TICKS = 0x90
PERP_OVERLAY_MESSAGE0_ADDR = 0x8013F148

CONTROLS_RETURN_STOCK = RUNTIME_BASE + 0x509B4

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "a0": 4,
    "a1": 5,
    "a2": 6,
    "t0": 8,
    "t1": 9,
    "ra": 31,
}


def exe_path() -> Path:
    hits = list(Path(".").glob(EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest().upper()


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


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jr(rs: str) -> int:
    return ins_r(REG[rs], 0, 0, 0, 0x08)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lbu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x24, REG[rs], REG[rt], off)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def nop() -> int:
    return 0


def hi(addr: int) -> int:
    return ((addr + 0x8000) >> 16) & 0xFFFF


def lo(addr: int) -> int:
    return addr & 0xFFFF


def pack_labeled(items: list[int | str | tuple[str, str, str, str]], base: int) -> bytes:
    labels: dict[str, int] = {}
    pc = base
    for item in items:
        if isinstance(item, str):
            labels[item] = pc
        else:
            pc += 4
    out: list[int] = []
    pc = base
    for item in items:
        if isinstance(item, str):
            continue
        if isinstance(item, tuple):
            kind, rs, rt, target = item
            op = 0x04 if kind == "beq" else 0x05
            item = ins_i(op, REG[rs], REG[rt], (labels[target] - (pc + 4)) >> 2)
        out.append(item)
        pc += 4
    return pack(out)


def make_controls_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        lw("v1", 0x0D0C, "v0"),
        addiu("t0", "zero", 0),
        addiu("t0", "t0", -1),
        bne("t0", "zero", "stock"),
        nop(),
        beq("v1", "zero", "stock"),
        nop(),
        lhu("t0", 0x043C, "v1"),
        nop(),
        bne("t0", "zero", "show_banner"),
        addiu("v1", "v1", 0x043C),
        lbu("t0", 0x0009, "v1"),
        addiu("t1", "zero", 1),
        beq("t0", "t1", "show_banner"),
        nop(),
        "stock",
        j(CONTROLS_RETURN_STOCK),
        nop(),
        "show_banner",
        lui("t0", hi(BANNER_TIMER_ADDR)),
        addiu("t1", "zero", BANNER_TICKS),
        sw("t1", lo(BANNER_TIMER_ADDR), "t0"),
        lui("t0", hi(PERP_OVERLAY_MESSAGE0_ADDR)),
        addiu("t1", "zero", 1),
        sw("t1", lo(PERP_OVERLAY_MESSAGE0_ADDR), "t0"),
        jr("ra"),
        addiu("v0", "zero", 1),
    ]
    blob = pack_labeled(items, CONTROLS_CAVE_ADDR)
    if len(blob) > CONTROLS_CAVE_LEN:
        raise SystemExit(f"controls cave too large: 0x{len(blob):X}")
    return blob + bytes(CONTROLS_CAVE_LEN - len(blob))


def make_hud_branch_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        bne("v0", "zero", "render"),
        nop(),
        bne("t1", "zero", "skip"),
        nop(),
        lui("v1", hi(BANNER_TIMER_ADDR)),
        lw("v0", lo(BANNER_TIMER_ADDR), "v1"),
        nop(),
        beq("v0", "zero", "skip"),
        nop(),
        addiu("v0", "v0", -1),
        sw("v0", lo(BANNER_TIMER_ADDR), "v1"),
        "render",
        j(HUD_RENDER_OVERLAY_ADDR),
        nop(),
        "skip",
        j(HUD_SKIP_OVERLAY_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, HUD_BRANCH_CAVE_ADDR)
    if len(blob) > HUD_BRANCH_CAVE_LEN:
        raise SystemExit(f"HUD branch cave too large: 0x{len(blob):X}")
    return blob + bytes(HUD_BRANCH_CAVE_LEN - len(blob))


def main() -> int:
    path = exe_path()
    data = bytearray(path.read_bytes())

    controls_cave = make_controls_cave()
    hud_branch_hook = pack([j(HUD_BRANCH_CAVE_ADDR), nop()])
    hud_branch_cave = make_hud_branch_cave()

    current_controls = bytes(data[CONTROLS_CAVE_OFF : CONTROLS_CAVE_OFF + 8])
    if current_controls != CONTROLS_CAVE_PREFIX:
        raise SystemExit(f"unexpected controls cave prefix: {current_controls.hex(' ')}")

    current_hud_branch = bytes(data[HUD_BRANCH_OFF : HUD_BRANCH_OFF + 8])
    if current_hud_branch not in {HUD_BRANCH_STOCK, hud_branch_hook}:
        raise SystemExit(f"unexpected HUD branch bytes: {current_hud_branch.hex(' ')}")

    current_hud_cave = bytes(data[HUD_BRANCH_CAVE_OFF : HUD_BRANCH_CAVE_OFF + HUD_BRANCH_CAVE_LEN])
    if current_hud_cave not in {bytes(HUD_BRANCH_CAVE_LEN), hud_branch_cave}:
        raise SystemExit(f"HUD branch cave is not empty/known at 0x{HUD_BRANCH_CAVE_OFF:X}")

    if bytes(data[BANNER_TIMER_OFF : BANNER_TIMER_OFF + BANNER_TIMER_LEN]) != bytes(BANNER_TIMER_LEN):
        raise SystemExit(f"banner timer storage is not empty at 0x{BANNER_TIMER_OFF:X}")

    data[CONTROLS_CAVE_OFF : CONTROLS_CAVE_OFF + CONTROLS_CAVE_LEN] = controls_cave
    data[HUD_BRANCH_CAVE_OFF : HUD_BRANCH_CAVE_OFF + HUD_BRANCH_CAVE_LEN] = hud_branch_cave
    data[HUD_BRANCH_OFF : HUD_BRANCH_OFF + 8] = hud_branch_hook
    data[BANNER_TIMER_OFF : BANNER_TIMER_OFF + BANNER_TIMER_LEN] = bytes(BANNER_TIMER_LEN)
    path.write_bytes(data)

    print(f"NFS4.EXE {md5(path)}")
    print("player bust custom banner: enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
