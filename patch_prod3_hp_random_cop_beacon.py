#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

EXE_GLOB = "PROD 3*/NFS4.EXE"
RUNTIME_BASE = 0x8000F800
BACKUP_SUFFIX = ".orig_before_prod3_hp_random_cop_beacon"

# SetupBuildMatrices: replace the start of the stock camera-distance calculation.
# All stock active/speechSource/bodyPitch filtering has already run at this point.
HOOK_OFF = 0x6ECA8
STOCK = bytes.fromhex("a0 00 c5 8c 08 00 23 8e")
RETURN_DISTANCE = RUNTIME_BASE + HOOK_OFF + 8
SELECT_COMPARE = 0x8007E4F4

# The stock speechSource gate changes much more slowly than our selector.
# Keep it for the player, but let active AI cop-list entries reach selection.
FILTER_HOOK_OFF = 0x6EC8C
FILTER_STOCK = bytes.fromhex("1e 00 40 10 00 00 00 00")
FILTER_CONTINUE = 0x8007E494
FILTER_SKIP = 0x8007E508

# Free gap immediately before the stable 0x800F7B00 cheat/code area.
CAVE_OFF = 0xE8264
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x9C
FILTER_CAVE_ADDR = CAVE_ADDR + 0x70

GAME_TICKS_ADDR = 0x8011F368
HP_COP_COUNT = 4
FEATURE_GATE_DEFAULT = 0

REG = {
    "zero": 0, "v0": 2, "v1": 3, "a0": 4, "a1": 5, "a2": 6,
    "a3": 7, "t3": 11, "t5": 13, "t6": 14, "t7": 15, "s1": 17,
}


def i(op: int, rs: str, rt: str, imm: int) -> int:
    return (op << 26) | (REG[rs] << 21) | (REG[rt] << 16) | (imm & 0xFFFF)


def r(rs: str, rt: str, rd: str, sh: int, fn: int) -> int:
    return (REG[rs] << 21) | (REG[rt] << 16) | (REG[rd] << 11) | (sh << 6) | fn


def j(addr: int) -> int:
    return (0x02 << 26) | ((addr >> 2) & 0x03FFFFFF)


def branch(op: int, rs: str, rt: str, pc: int, target: int) -> int:
    return i(op, rs, rt, (target - (pc + 4)) >> 2)


def bgez(rs: str, pc: int, target: int) -> int:
    offset = ((target - (pc + 4)) >> 2) & 0xFFFF
    return (0x01 << 26) | (REG[rs] << 21) | (1 << 16) | offset


def cave() -> bytes:
    words: list[int] = []
    pc = CAVE_ADDR

    def emit(word: int) -> None:
        nonlocal pc
        words.append(word)
        pc += 4

    stock = CAVE_ADDR + 0x60
    emit(i(0x09, "zero", "t5", FEATURE_GATE_DEFAULT))
    emit(branch(0x05, "t3", "t5", pc, stock))
    emit(0)

    # Pick a new target slot about every 171 game ticks. Slot 0 is the player;
    # slots 1..4 are the AI cops. The stock loop still validates every object.
    emit(i(0x0F, "zero", "t5", (GAME_TICKS_ADDR + 0x8000) >> 16))
    emit(i(0x23, "t5", "t5", GAME_TICKS_ADDR & 0xFFFF))
    emit(0)  # PS1 load delay
    emit(r("zero", "t5", "t6", 1, 0x02))
    emit(r("t5", "t6", "t5", 0, 0x21))
    emit(r("zero", "t5", "t5", 8, 0x02))
    emit(r("zero", "t5", "t6", 13, 0x00))
    emit(r("t5", "t6", "t5", 0, 0x26))
    emit(r("zero", "t5", "t6", 17, 0x02))
    emit(r("t5", "t6", "t5", 0, 0x26))

    emit(i(0x0C, "t5", "t5", 0xFFFF))
    emit(r("zero", "t5", "t7", 2, 0x00))
    emit(r("t7", "t5", "t5", 0, 0x21))
    emit(r("zero", "t5", "t5", 16, 0x02))
    emit(i(0x09, "a3", "t6", 1))
    emit(r("t6", "t5", "a0", 0, 0x23))
    select = pc + 12
    emit((0x01 << 26) | (REG["a0"] << 21) | (1 << 16) | ((select - (pc + 4)) >> 2))
    emit(0)
    emit(i(0x09, "a0", "a0", HP_COP_COUNT + 1))
    emit(j(SELECT_COMPARE))
    emit(0)

    if pc != stock:
        raise SystemExit(f"unexpected stock label: 0x{pc:X} != 0x{stock:X}")
    emit(i(0x23, "a2", "a1", 0x00A0))
    emit(i(0x23, "s1", "v1", 0x0008))
    emit(j(RETURN_DISTANCE))
    emit(0)

    while pc < FILTER_CAVE_ADDR:
        emit(0)
    if pc != FILTER_CAVE_ADDR:
        raise SystemExit(f"unexpected filter cave address: 0x{pc:X}")

    # Outside four-cop HP, retain the complete stock speechSource gate.
    # In HP, a3=-1 is the player and keeps that gate, while a3>=0 is an
    # already active object from the dedicated AI cop list.
    stock_test = FILTER_CAVE_ADDR + 0x14
    allow = FILTER_CAVE_ADDR + 0x1C
    reject = FILTER_CAVE_ADDR + 0x24
    emit(i(0x09, "zero", "t5", FEATURE_GATE_DEFAULT))
    emit(branch(0x05, "t3", "t5", pc, stock_test))
    emit(0)
    emit(bgez("a3", pc, allow))
    emit(0)
    emit(branch(0x04, "v0", "zero", pc, reject))
    emit(0)
    emit(j(FILTER_CONTINUE))
    emit(0)
    emit(j(FILTER_SKIP))
    emit(0)

    blob = struct.pack("<" + "I" * len(words), *words)
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob.ljust(CAVE_LEN, b"\x00")


def find_exe() -> Path:
    hits = list(Path(".").glob(EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {EXE_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="PROD3: random held HP night cop beacon source")
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)
    hook = struct.pack("<II", j(CAVE_ADDR), 0)
    filter_hook = struct.pack("<II", j(FILTER_CAVE_ADDR), 0)
    blob = cave()

    current_hook = bytes(data[HOOK_OFF:HOOK_OFF + len(STOCK)])
    if current_hook not in {STOCK, hook}:
        raise SystemExit(f"unexpected hook: {current_hook.hex(' ')}")
    current_filter_hook = bytes(data[FILTER_HOOK_OFF:FILTER_HOOK_OFF + len(FILTER_STOCK)])
    if current_filter_hook not in {FILTER_STOCK, filter_hook}:
        raise SystemExit(f"unexpected filter hook: {current_filter_hook.hex(' ')}")
    current_cave = bytes(data[CAVE_OFF:CAVE_OFF + CAVE_LEN])
    if current_cave not in {bytes(CAVE_LEN), blob}:
        raise SystemExit("random beacon cave is not empty/known")

    if args.revert:
        data[HOOK_OFF:HOOK_OFF + len(STOCK)] = STOCK
        data[FILTER_HOOK_OFF:FILTER_HOOK_OFF + len(FILTER_STOCK)] = FILTER_STOCK
        data[CAVE_OFF:CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    else:
        data[CAVE_OFF:CAVE_OFF + CAVE_LEN] = blob
        data[HOOK_OFF:HOOK_OFF + len(STOCK)] = hook
        data[FILTER_HOOK_OFF:FILTER_HOOK_OFF + len(FILTER_STOCK)] = filter_hook
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)

    if bytes(data) != original:
        exe.write_bytes(data)
    print("reverted" if args.revert else "patched", exe)
    print("HP beacon source: cheat-gated fair pseudo-random slot, about 171 game ticks")
    print("cheat off/on: 800F7A64 0000/0004 and 800F7AD4 0000/0004")
    print("md5", hashlib.md5(data).hexdigest().upper())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
