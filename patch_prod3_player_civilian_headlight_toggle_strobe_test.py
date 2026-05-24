#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_civilian_headlight_toggle_strobe_test"
RUNTIME_BASE = 0x8000F800

# R3DCar_InsertCarFacetII, after stock cop-palCopy handling and before the
# normal palCopy animation increment.
HOOK_OFF = 0xA126C
RETURN_ADDR = RUNTIME_BASE + HOOK_OFF + 8

CAVE_OFF = 0x457F0
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x110
COUNTER_OFF = CAVE_OFF + CAVE_LEN - 4
COUNTER_ADDR = RUNTIME_BASE + COUNTER_OFF

PLAYER_CAR_OBJ_PTR_ADDR = 0x80110D0C
TURN_HEADLIGHT_ON_ADDR = 0x800B078C
TURN_HEADLIGHT_OFF_ADDR = 0x800B07EC

REG = {
    "zero": 0,
    "v0": 2,
    "a0": 4,
    "a1": 5,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "s5": 21,  # carObj
    "s7": 23,  # car type
    "sp": 29,
    "ra": 31,
    "gp": 28,
}


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


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def lbu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x24, REG[rs], REG[rt], off)


def ori(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0D, REG[rs], REG[rt], imm)


def sh(rt: str, off: int, rs: str) -> int:
    return ins_i(0x29, REG[rs], REG[rt], off)


def sb(rt: str, off: int, rs: str) -> int:
    return ins_i(0x28, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def slti(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0A, REG[rs], REG[rt], imm)


def sltiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0B, REG[rs], REG[rt], imm)


def srl(rd: str, rt: str, sh: int) -> int:
    return ins_r(0, REG[rt], REG[rd], sh, 0x02)


def sll(rd: str, rt: str, sh: int) -> int:
    return ins_r(0, REG[rt], REG[rd], sh, 0x00)


def addu(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x21)


def or_(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x25)


def subu(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x23)


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


def cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Original overwritten instruction.
        lw("v0", 0x0E50, "gp"),
        # Only player 1.
        lui("t0", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
        lw("t0", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t0"),
        nop(),
        bne("s5", "t0", "done"),
        nop(),
        # Only civilian cars; leave player cop cars stock.
        slti("t0", "s7", 0x16),
        beq("t0", "zero", "done"),
        nop(),
        # Private 0..15 counter.
        lui("t0", hi(COUNTER_ADDR)),
        lw("t1", lo(COUNTER_ADDR), "t0"),
        nop(),
        addiu("t1", "t1", 1),
        andi("t1", "t1", 0x003F),
        sw("t1", lo(COUNTER_ADDR), "t0"),
        andi("t2", "t1", 0x0008),
        # Preserve caller return address while calling the stock light helpers.
        addiu("sp", "sp", -16),
        sw("ra", 12, "sp"),
        bne("t2", "zero", "lights_on"),
        nop(),
        # Off phase.
        jal(TURN_HEADLIGHT_OFF_ADDR),
        addiu("a0", "s5", 0),
        # Delay slot cannot set a1 here; set it before call via branch target style.
        "after_off_call",
        lw("ra", 12, "sp"),
        addiu("sp", "sp", 16),
        lw("v0", 0x0E50, "gp"),
        j(RETURN_ADDR),
        nop(),
        "lights_on",
        jal(TURN_HEADLIGHT_ON_ADDR),
        addiu("a0", "s5", 0),
        lw("ra", 12, "sp"),
        addiu("sp", "sp", 16),
        lw("v0", 0x0E50, "gp"),
        j(RETURN_ADDR),
        nop(),
        "done",
        lw("v0", 0x0E50, "gp"),
        j(RETURN_ADDR),
        nop(),
    ]
    # Patch the two call delay slots cannot carry a1, so insert a1 setup by
    # replacing the previous nops? Simpler: the helper reads a1; set it before
    # each jal by using the jal delay for a0 and rely on a1 from prior code is
    # unsafe.  Keep this function compact by post-patching below.
    blob = bytearray(pack_labeled(items, CAVE_ADDR))
    words = list(struct.unpack("<" + "I" * (len(blob) // 4), blob))
    # Locate jal words and insert addiu a1,zero,1 immediately before them by
    # rebuilding with explicit setup if this compact version is not acceptable.
    # The above comment is left as a guard; rebuild explicitly instead.
    items = [
        lw("v0", 0x0E50, "gp"),
        lui("t0", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
        lw("t0", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t0"),
        nop(),
        bne("s5", "t0", "done"),
        nop(),
        slti("t0", "s7", 0x16),
        beq("t0", "zero", "done"),
        nop(),
        lui("t0", hi(COUNTER_ADDR)),
        lw("t1", lo(COUNTER_ADDR), "t0"),
        nop(),
        addiu("t1", "t1", 2),
        andi("t1", "t1", 0x03FF),
        sw("t1", lo(COUNTER_ADDR), "t0"),
        # Raw bit 6 selects the turn-signal side within the same 16-phase
        # cycle: clear = left double-blink, set = right double-blink.
        andi("t0", "t1", 0x0040),
        # Counter / 8, then use an 8-phase double-blink pattern which repeats
        # once for each side inside the 16-phase cycle.
        # phase 0-1 on, 2 off, 3-4 on, 5-7 pause.
        srl("t1", "t1", 3),
        andi("t1", "t1", 0x0007),
        slti("t2", "t1", 2),
        addiu("sp", "sp", -16),
        sw("ra", 12, "sp"),
        bne("t2", "zero", "lights_on"),
        nop(),
        addiu("t2", "t1", -3),
        sltiu("t2", "t2", 2),
        bne("t2", "zero", "lights_on"),
        nop(),
        lbu("t2", 0x0447, "s5"),
        andi("t2", "t2", 0x00E7),
        sb("t2", 0x0447, "s5"),
        sh("zero", 0x08B8, "s5"),
        sh("zero", 0x08BA, "s5"),
        addiu("a0", "s5", 0),
        jal(TURN_HEADLIGHT_OFF_ADDR),
        addiu("a1", "zero", 1),
        beq("zero", "zero", "after_light_call"),
        nop(),
        "lights_on",
        srl("t0", "t0", 2),
        bne("t0", "zero", "turn_bit_ready"),
        nop(),
        addiu("t0", "zero", 8),
        "turn_bit_ready",
        lbu("t2", 0x0447, "s5"),
        andi("t2", "t2", 0x00E7),
        or_("t2", "t2", "t0"),
        sb("t2", 0x0447, "s5"),
        srl("t0", "t0", 3),
        addiu("t0", "t0", -1),
        beq("t0", "zero", "left_pal"),
        nop(),
        lhu("t2", 0x08BA, "s5"),
        ori("t2", "t2", 0x88),
        sh("t2", 0x08BA, "s5"),
        beq("zero", "zero", "pal_done"),
        nop(),
        "left_pal",
        lhu("t2", 0x08B8, "s5"),
        ori("t2", "t2", 0x80),
        sh("t2", 0x08B8, "s5"),
        "pal_done",
        addiu("a0", "s5", 0),
        jal(TURN_HEADLIGHT_ON_ADDR),
        addiu("a1", "zero", 1),
        "after_light_call",
        lw("ra", 12, "sp"),
        addiu("sp", "sp", 16),
        lw("v0", 0x0E50, "gp"),
        j(RETURN_ADDR),
        nop(),
        "done",
        j(RETURN_ADDR),
        nop(),
    ]
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

    stock_hook = pack([lw("v0", 0x0E50, "gp"), nop()])
    patched_hook = pack([j(CAVE_ADDR), nop()])
    blob = cave()

    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    old_far_hook = pack([j(RUNTIME_BASE + 0xFEB80), nop()])
    if current_hook not in {stock_hook, patched_hook, old_far_hook}:
        raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")

    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    known_ours_prefix = bytes.fromhex("50 0e 82 8f 11 80 08 3c 0c 0d 08 8d")
    if current_cave not in {bytes(CAVE_LEN), blob} and not current_cave.startswith(known_ours_prefix):
        raise SystemExit(f"cave is not empty/known at 0x{CAVE_OFF:X}: {current_cave[:16].hex(' ')}")

    if args.revert:
        data[HOOK_OFF : HOOK_OFF + 8] = stock_hook
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
        data[0xFEB80 : 0xFEB80 + 0x180] = bytes(0x180)
    else:
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = blob
        data[0xFEB80 : 0xFEB80 + 0x180] = bytes(0x180)
        data[HOOK_OFF : HOOK_OFF + 8] = patched_hook

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {hashlib.md5(bytes(data)).hexdigest().upper()}")
    print("player civilian headlight toggle strobe test:", "reverted" if args.revert else "patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
