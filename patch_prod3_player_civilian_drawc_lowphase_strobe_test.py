#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_civilian_drawc_lowphase_strobe_test"
RUNTIME_BASE = 0x8000F800

# DrawC_NightHeadlight gate:
# if (R3DCar_InMenu || (carObj->speechInfo.speechSource & 2)) { flash tables... }
HOOK_OFF = 0xB0B34
CONTINUE_ADDR = RUNTIME_BASE + 0xB0B3C
FLASH_BLOCK_ADDR = RUNTIME_BASE + 0xB0B50

CAVE_OFF = 0x457F0
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0xB0
COUNTER_OFF = CAVE_OFF + CAVE_LEN - 4
COUNTER_ADDR = RUNTIME_BASE + COUNTER_OFF

PLAYER_CAR_OBJ_PTR_ADDR = 0x80110D0C

REG = {
    "zero": 0,
    "v0": 2,
    "a2": 6,
    "t0": 8,
    "t1": 9,
    "t2": 10,
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


def cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Original branch delay instruction.
        lui("a2", 0x8012),
        # Preserve stock menu behavior.
        bne("v0", "zero", "flash"),
        nop(),
        # Only player 1.
        lui("t0", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
        lw("t0", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t0"),
        nop(),
        bne("s2", "t0", "stock_check"),
        nop(),
        # Only civilian cars; player cop cars stay fully stock.
        lhu("t1", 0x08BC, "s2"),
        slti("t1", "t1", 0x16),
        beq("t1", "zero", "stock_check"),
        nop(),
        # Low-nibble-only phase for DrawC flash tables.  Do not set 0x80:
        # on civilians that high bit is interpreted as turn-signal state.
        lui("t0", hi(COUNTER_ADDR)),
        lw("t1", lo(COUNTER_ADDR), "t0"),
        nop(),
        addiu("t1", "t1", 1),
        andi("t1", "t1", 0x000F),
        sw("t1", lo(COUNTER_ADDR), "t0"),
        sh("t1", 0x08B8, "s2"),
        addiu("t2", "t1", 8),
        andi("t2", "t2", 0x000F),
        sh("t2", 0x08BA, "s2"),
        "flash",
        j(FLASH_BLOCK_ADDR),
        nop(),
        "stock_check",
        j(CONTINUE_ADDR),
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

    stock_hook = bytes.fromhex("06 00 40 14 12 80 06 3c")
    patched_hook = pack([j(CAVE_ADDR), nop()])
    blob = cave()

    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {stock_hook, patched_hook}:
        raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")

    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {bytes(CAVE_LEN), blob}:
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
    print("player civilian DrawC low-phase strobe test:", "reverted" if args.revert else "patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
