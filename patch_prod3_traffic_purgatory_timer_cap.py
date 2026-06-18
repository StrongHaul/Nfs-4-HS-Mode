#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_traffic_purgatory_timer_cap"
RUNTIME_BASE = 0x8000F800

# AIState_Purgatory ctor, immediately after:
#   srl   v0,v1,16
#   lw    v1,0(s1)       ; v1 = carObj
#   addiu v0,v0,1        ; randomized wait timer
#   sw    v0,0x58C(v1)   ; carObj->desiredLatPos / purgatory timer
HOOK_OFF = 0x62658
RETURN_ADDR = RUNTIME_BASE + HOOK_OFF + 8

# Free zeroed space between the player light-color cave at 0x45400 and the
# stable traffic/Raceway cave at 0x45600.
CAVE_OFF = 0x45480
CAVE_LEN = 0x80

ENABLE_ADDR = 0x80054B7C
TRAFFIC_FLAG = 0x0010
CAR_FLAGS_OFF = 0x0260
PURGATORY_TIMER_OFF = 0x058C
BOOSTED_TIMER_CAP = 4

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "t0": 8,
}


def runtime(off: int) -> int:
    return RUNTIME_BASE + off


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
        # Hook delay slot already ran stock: addiu v0,v0,1.
        lui("t0", hi(ENABLE_ADDR)),
        lhu("t0", lo(ENABLE_ADDR), "t0"),
        beq("t0", "zero", "store"),
        nop(),
        lw("t0", CAR_FLAGS_OFF, "v1"),
        andi("t0", "t0", TRAFFIC_FLAG),
        beq("t0", "zero", "store"),
        nop(),
        slti("t0", "v0", BOOSTED_TIMER_CAP + 1),
        bne("t0", "zero", "store"),
        nop(),
        addiu("v0", "zero", BOOSTED_TIMER_CAP),
        "store",
        sw("v0", PURGATORY_TIMER_OFF, "v1"),
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
        description="PROD3: cap traffic purgatory timer when 80054B7C is enabled."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    stock_hook = pack([addiu("v0", "v0", 1), sw("v0", PURGATORY_TIMER_OFF, "v1")])
    patched_hook = pack([j(runtime(CAVE_OFF)), addiu("v0", "v0", 1)])
    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {stock_hook, patched_hook}:
        raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")

    blob = cave()
    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {b"\x00" * CAVE_LEN, blob}:
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
    print(f"80054B7C traffic purgatory timer cap: {BOOSTED_TIMER_CAP}")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
