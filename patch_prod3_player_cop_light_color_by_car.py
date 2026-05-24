#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_cop_light_color_by_car"
RUNTIME_BASE = 0x8000F800

# PROD3 Night_SetCopColor, after car id is loaded into v0 and before the
# country slot in a1 is used to index Night_gCopCountryLightTbl.
HOOK_OFF = 0xCCC44
RETURN_ADDR = RUNTIME_BASE + HOOK_OFF + 8

# Free zeroed area between the old HP traffic test cave and the stable HP cave.
CAVE_OFF = 0x45400
CAVE_LEN = 0x100

PLAYER_CAR_DATA_ADDR = 0x80114878
PLAYER_COP_LIVERY_MODE_ADDR = 0x800553F4

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "a0": 4,
    "a1": 5,
    "t0": 8,
    "t1": 9,
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


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


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


def old_porsche_always_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Hook delay already executes stock: lw a1,0x00A0(a0).
        lui("t0", hi(PLAYER_COP_LIVERY_MODE_ADDR)),
        lhu("t1", lo(PLAYER_COP_LIVERY_MODE_ADDR), "t0"),
        beq("t1", "zero", "finish"),
        nop(),
        lui("t0", hi(PLAYER_CAR_DATA_ADDR)),
        addiu("t0", "t0", lo(PLAYER_CAR_DATA_ADDR)),
        bne("a0", "t0", "finish"),
        nop(),
        addiu("t1", "zero", 0x1A),
        bne("v0", "t1", "finish"),
        nop(),
        addiu("a1", "zero", 2),  # Porsche 911 Cop -> German blue
        "finish",
        addu("v0", "v0", "v1"),
        j(RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, runtime(CAVE_OFF))
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X} > 0x{CAVE_LEN:X}")
    return blob.ljust(CAVE_LEN, b"\x00")


def cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Hook delay already executes stock: lw a1,0x00A0(a0).
        # If player cop-livery mode is off, keep stock light color behavior.
        lui("t0", hi(PLAYER_COP_LIVERY_MODE_ADDR)),
        lhu("t1", lo(PLAYER_COP_LIVERY_MODE_ADDR), "t0"),
        beq("t1", "zero", "finish"),
        nop(),
        # Only player 1 carData gets the livery fallback light override.
        lui("t0", hi(PLAYER_CAR_DATA_ADDR)),
        addiu("t0", "t0", lo(PLAYER_CAR_DATA_ADDR)),
        bne("a0", "t0", "finish"),
        nop(),
        # Porsche 911 Cop on US/Canada tracks visually falls back to the
        # German/blue ZZZP993 livery. Other country slots keep their own color:
        # France remains red, UK/Germany remain blue.
        addiu("t1", "zero", 0x1A),
        bne("v0", "t1", "finish"),
        nop(),
        addiu("t1", "zero", 4),
        bne("a1", "t1", "finish"),
        nop(),
        addiu("a1", "zero", 2),  # US/Canada fallback -> German blue
        "finish",
        addu("v0", "v0", "v1"),
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
        description="PROD3: make player cop beacon light color follow player cop car model."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    stock_hook = pack([lw("a1", 0x00A0, "a0"), addu("v0", "v0", "v1")])
    patched_hook = pack([j(runtime(CAVE_OFF)), lw("a1", 0x00A0, "a0")])
    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {stock_hook, patched_hook}:
        raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")

    blob = cave()
    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {b"\x00" * CAVE_LEN, blob, old_porsche_always_cave()}:
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
    print("player-only cop light fallback: Porsche 911 Cop uses German/blue light")
    print("active only when 800553F4 is nonzero")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
