#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_civilian_render_strobe_mask_test"
RUNTIME_BASE = 0x8000F800

# DrawC_NightHeadlight, just before RotMatrix.  At this point the game has
# already calculated the temporary head/tail-light masks for the current car.
HOOK_OFF = 0xB0D7C
RETURN_ADDR = RUNTIME_BASE + HOOK_OFF + 8

CAVE_OFF = 0x457F0
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0xF0
COUNTER_OFF = CAVE_OFF + CAVE_LEN - 4
COUNTER_ADDR = RUNTIME_BASE + COUNTER_OFF

PLAYER_CAR_OBJ_PTR_ADDR = 0x80110D0C

MASK_BASE_ADDR = 0x80120828
MASK_TAIL_A_OFF = 0x00
MASK_TAIL_B_OFF = 0x02
MASK_TAIL_EXTRA_OFF = 0x04
MASK_HEAD_OFF = 0x0A

REG = {
    "zero": 0,
    "v0": 2,
    "a0": 4,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "s0": 16,
    "s2": 18,  # carObj in DrawC_NightHeadlight
}


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


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


def sh(rt: str, off: int, rs: str) -> int:
    return ins_i(0x29, REG[rs], REG[rt], off)


def slti(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0A, REG[rs], REG[rt], imm)


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


def cave(force_clear_off_phase: bool = False) -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Original overwritten instructions.
        addiu("a0", "zero", 0),  # patched below manually to addiu a0,sp,24 is not helper-friendly
    ]
    # Replace the placeholder with raw addiu a0,sp,24; sp is reg 29.
    items[0] = ins_i(0x09, 29, REG["a0"], 24)
    items.extend(
        [
            lui("s0", 0x8012),
            # Only player 1.
            lui("t0", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
            lw("t0", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t0"),
            nop(),
            bne("s2", "t0", "done"),
            nop(),
            # Only civilian cars; cop cars keep their own beacon/headlight path.
            lhu("t1", 0x08BC, "s2"),
            slti("t1", "t1", 0x16),
            beq("t1", "zero", "done"),
            nop(),
            # Private frame counter.  No palCopy/control.lights touch, so no
            # turn signal side effects.
            lui("t0", hi(COUNTER_ADDR)),
            lw("t1", lo(COUNTER_ADDR), "t0"),
            nop(),
            addiu("t1", "t1", 1),
            andi("t1", "t1", 0x0F),
            sw("t1", lo(COUNTER_ADDR), "t0"),
            # 8 frames on / 8 frames off.  In the off phase we leave the
            # game's own masks alone by default; clearing shared masks can
            # interfere with visible police cars that use the same renderer.
            andi("t2", "t1", 0x08),
            beq("t2", "zero", "done"),
            nop(),
            # On phase: force both sides of the head/tail light masks.
            lui("t0", hi(MASK_BASE_ADDR)),
            addiu("t0", "t0", lo(MASK_BASE_ADDR)),
            addiu("t1", "zero", -0x7F7F),  # 0x8181
            sh("t1", MASK_HEAD_OFF, "t0"),
            addiu("t1", "zero", -0x7F80),  # 0x8080
            sh("t1", MASK_TAIL_A_OFF, "t0"),
            sh("t1", MASK_TAIL_B_OFF, "t0"),
            sh("t1", MASK_TAIL_EXTRA_OFF, "t0"),
            "done",
            j(RETURN_ADDR),
            nop(),
        ]
    )
    if force_clear_off_phase:
        # Kept only for recognizing/reverting the first unsafe test variant.
        raise NotImplementedError
    blob = pack_labeled(items, CAVE_ADDR)
    if len(blob) > CAVE_LEN - 4:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob + bytes(CAVE_LEN - len(blob))


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    stock_hook = bytes.fromhex("18 00 a4 27 12 80 10 3c")
    patched_hook = pack([j(CAVE_ADDR), nop()])
    blob = cave()

    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {stock_hook, patched_hook}:
        raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")

    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    known_ours_prefix = bytes.fromhex("18 00 a4 27 12 80 10 3c 11 80 08 3c")
    if current_cave not in {bytes(CAVE_LEN), blob} and not current_cave.startswith(known_ours_prefix):
        raise SystemExit(f"cave is not empty/known at 0x{CAVE_OFF:X}: {current_cave[:16].hex(' ')}")

    if args.revert:
        data[HOOK_OFF : HOOK_OFF + 8] = stock_hook
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    else:
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = blob
        data[HOOK_OFF : HOOK_OFF + 8] = patched_hook

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {hashlib.md5(bytes(data)).hexdigest().upper()}")
    print("player civilian render strobe mask test:", "reverted" if args.revert else "patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
