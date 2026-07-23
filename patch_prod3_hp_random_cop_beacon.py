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
EXT_CAVE_OFF = 0x45500
EXT_CAVE_ADDR = RUNTIME_BASE + EXT_CAVE_OFF
EXT_CAVE_LEN = 0x100
OLD_EXT_CAVE_OFF = 0xFF300
OLD_EXT_CAVE_ADDR = RUNTIME_BASE + OLD_EXT_CAVE_OFF
PAIR_LOOKUP_ADDR = CAVE_ADDR + 0x14
PAIR_COMPARE_ADDR = CAVE_ADDR + 0x4C
PAIR_LOOKUP_RETURN_ADDR = EXT_CAVE_ADDR + 0x80

GAME_TICKS_ADDR = 0x8011F368
HP_COP_COUNT = 4
FEATURE_GATE_DEFAULT = 0

REG = {
    "zero": 0, "v0": 2, "v1": 3, "a0": 4, "a1": 5, "a2": 6, "t0": 8,
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


def cave(*, variant: str = "multi") -> bytes:
    words: list[int] = []
    pc = CAVE_ADDR

    def emit(word: int) -> None:
        nonlocal pc
        words.append(word)
        pc += 4

    stock = CAVE_ADDR + 0x60
    if variant in {"multi", "multi_v3", "multi_far"}:
        # Keep the GameShark-controlled immediate at the historical address.
        emit(i(0x09, "zero", "t7", FEATURE_GATE_DEFAULT))
        emit(branch(0x04, "t7", "zero", pc, stock))
        emit(0)
        emit(j(OLD_EXT_CAVE_ADDR if variant == "multi_far" else EXT_CAVE_ADDR))
        emit(0)
        if variant == "multi":
            # Pair-mode pointer lookup: slot 0 is the player, 1..4 are AI cops.
            emit(branch(0x04, "t5", "zero", pc, CAVE_ADDR + 0x38))
            emit(r("zero", "t5", "a0", 2, 0x00))
            emit(i(0x09, "a0", "a0", -4))
            emit(i(0x0F, "zero", "v0", 0x8011))
            emit(i(0x09, "v0", "v0", 0x0D78))
            emit(r("v0", "a0", "a0", 0, 0x21))
            emit(i(0x23, "a0", "a0", 0))
            emit(j(PAIR_LOOKUP_RETURN_ADDR))
            emit(0)
            emit(i(0x0F, "zero", "a0", 0x8011))
            emit(i(0x09, "a0", "a0", 0x0CA0))
            emit(i(0x23, "a0", "a0", 0))
            emit(j(PAIR_LOOKUP_RETURN_ADDR))
            emit(0)
            emit(i(0x09, "a3", "t6", 1))
            emit(r("t6", "t5", "a0", 0, 0x26))
            emit(j(SELECT_COMPARE))
            emit(0)
            emit(0)
        else:
            while pc < stock:
                emit(0)
    elif variant == "multi_v2":        # Mode 1 holds one source for about 4-5 seconds. Mode 2 rapidly and
        # deterministically time-multiplexes the four AI cop sources because
        # the stock renderer exposes only one environmental beacon light.
        emit(i(0x09, "zero", "t7", FEATURE_GATE_DEFAULT))
        emit(branch(0x04, "t7", "zero", pc, stock))
        emit(i(0x0F, "zero", "t5", (GAME_TICKS_ADDR + 0x8000) >> 16))
        emit(i(0x23, "t5", "t5", GAME_TICKS_ADDR & 0xFFFF))
        emit(i(0x09, "zero", "t6", 2))
        held = CAVE_ADDR + 0x2C
        emit(branch(0x05, "t7", "t6", pc, held))
        emit(0)

        # Fast mode: slots 1..4 only, so an inactive player-cop slot cannot
        # create a blank pulse in the all-AI-cops option.
        emit(i(0x0C, "t5", "t5", 3))
        emit(i(0x09, "t5", "t5", 1))
        common = CAVE_ADDR + 0x50
        emit(j(common))
        emit(0)

        # Held mode: division-free, stable pseudo-random slot 0..4.
        emit(r("zero", "t5", "t6", 1, 0x02))
        emit(r("t5", "t6", "t5", 0, 0x21))
        emit(r("zero", "t5", "t5", 8, 0x02))
        emit(r("zero", "t5", "t6", 13, 0x00))
        emit(r("t5", "t6", "t5", 0, 0x26))
        emit(i(0x0C, "t5", "t5", 0xFFFF))
        emit(r("zero", "t5", "t6", 2, 0x00))
        emit(r("t6", "t5", "t5", 0, 0x21))
        emit(r("zero", "t5", "t5", 16, 0x02))

        # Exact slot match: zero wins the stock minimum-distance comparison;
        # all later non-matching slots are nonzero and cannot replace it.
        emit(i(0x09, "a3", "t6", 1))
        emit(r("t6", "t5", "a0", 0, 0x26))
        emit(j(SELECT_COMPARE))
        emit(0)
    elif variant == "multi_v1":        # 0=stock, 1=held switching, 2=all active AI cops.
        emit(i(0x09, "zero", "t5", FEATURE_GATE_DEFAULT))
        emit(branch(0x04, "t5", "zero", pc, stock))
        emit(i(0x09, "zero", "t6", 2))
        emit(branch(0x04, "t5", "t6", pc, stock))
        emit(0)

        # Proven division-free selector for player + four AI cop slots.
        emit(i(0x0F, "zero", "t5", (GAME_TICKS_ADDR + 0x8000) >> 16))
        emit(i(0x23, "t5", "t5", GAME_TICKS_ADDR & 0xFFFF))
        emit(0)
        emit(r("zero", "t5", "t6", 1, 0x02))
        emit(r("t5", "t6", "t5", 0, 0x21))
        emit(r("zero", "t5", "t5", 8, 0x02))
        emit(r("zero", "t5", "t6", 13, 0x00))
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
    elif variant == "dynamic":
        # Previous experimental variable-count selector, retained for upgrade.
        emit(i(0x09, "zero", "t5", FEATURE_GATE_DEFAULT))
        emit(branch(0x04, "t5", "zero", pc, stock))
        emit(i(0x09, "zero", "t7", HP_COP_COUNT))
        emit(branch(0x04, "t7", "zero", pc, stock))
        emit(0)
        emit(i(0x0F, "zero", "t5", (GAME_TICKS_ADDR + 0x8000) >> 16))
        emit(i(0x23, "t5", "t5", GAME_TICKS_ADDR & 0xFFFF))
        emit(0)
        emit(r("zero", "t5", "t6", 1, 0x02))
        emit(r("t5", "t6", "t5", 0, 0x21))
        emit(r("zero", "t5", "t6", 13, 0x00))
        emit(r("t5", "t6", "t5", 0, 0x26))
        emit(r("zero", "t5", "t6", 17, 0x02))
        emit(r("t5", "t6", "t5", 0, 0x26))
        emit(i(0x09, "t7", "t7", 1))
        emit(r("t5", "t7", "zero", 0, 0x1B))
        emit(r("zero", "zero", "t5", 0, 0x10))
        emit(i(0x09, "a3", "t6", 1))
        emit(r("t6", "t5", "a0", 0, 0x23))
        select = pc + 12
        emit((0x01 << 26) | (REG["a0"] << 21) | (1 << 16) | ((select - (pc + 4)) >> 2))
        emit(0)
        emit(r("a0", "t7", "a0", 0, 0x21))
        emit(j(SELECT_COMPARE))
        emit(0)
    elif variant == "legacy":
        emit(i(0x09, "zero", "t5", FEATURE_GATE_DEFAULT))
        emit(branch(0x05, "t3", "t5", pc, stock))
        emit(0)
        emit(i(0x0F, "zero", "t5", (GAME_TICKS_ADDR + 0x8000) >> 16))
        emit(i(0x23, "t5", "t5", GAME_TICKS_ADDR & 0xFFFF))
        emit(0)
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
    else:
        raise ValueError(f"unknown cave variant: {variant}")

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

    stock_test = FILTER_CAVE_ADDR + 0x14
    allow = FILTER_CAVE_ADDR + 0x1C
    reject = FILTER_CAVE_ADDR + 0x24
    emit(i(0x09, "zero", "t5", FEATURE_GATE_DEFAULT))
    if variant == "legacy":
        emit(branch(0x05, "t3", "t5", pc, stock_test))
    else:
        emit(branch(0x04, "t5", "zero", pc, stock_test))
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

def extended_cave_v1(*, scratch: str = "v1") -> bytes:
    words: list[int] = []
    labels: dict[str, int] = {}
    fixups: list[tuple[int, int, int, str, str, str]] = []
    pc = EXT_CAVE_ADDR

    def emit(word: int) -> None:
        nonlocal pc
        words.append(word)
        pc += 4

    def label(name: str) -> None:
        labels[name] = pc

    def emit_branch(op: int, rs: str, rt: str, target: str) -> None:
        fixups.append((len(words), pc, op, rs, rt, target))
        emit(0)

    emit(i(0x0F, "zero", "t5", (GAME_TICKS_ADDR + 0x8000) >> 16))
    emit(i(0x23, "t5", scratch, GAME_TICKS_ADDR & 0xFFFF))
    emit(0)
    emit(i(0x09, "zero", "t6", 2))
    emit_branch(0x04, "t7", "t6", "fast")
    emit(r(scratch, "zero", "t5", 0, 0x21))

    # Stable held hash used by both single-source and pair modes.
    emit(r("zero", "t5", "t6", 1, 0x02))
    emit(r("t5", "t6", "t5", 0, 0x21))
    emit(r("zero", "t5", "t5", 8, 0x02))
    emit(r("zero", "t5", "t6", 13, 0x00))
    emit(r("t5", "t6", "t5", 0, 0x26))
    emit(i(0x0C, "t5", "t5", 0xFFFF))
    emit(r("zero", "t5", "t6", 2, 0x00))
    emit(r("t6", "t5", "t5", 0, 0x21))
    emit(r("zero", "t5", "t5", 16, 0x02))
    emit(i(0x09, "zero", "t6", 3))
    emit_branch(0x05, "t7", "t6", "compare")
    emit(0)

    # Mode 3: choose one of four AI pairs for a held interval, then alternate
    # rapidly inside that pair. Slot pairs are 1-2, 2-3, 3-4, and 4-1.
    emit(i(0x0C, "t5", "t5", 3))
    emit(i(0x09, "t5", "t5", 1))
    emit(i(0x0C, scratch, scratch, 1))
    emit(r("t5", scratch, "t5", 0, 0x21))
    emit(i(0x0B, "t5", "t6", 5))
    emit_branch(0x05, "t6", "zero", "compare")
    emit(0)
    emit(i(0x09, "t5", "t5", -4))
    emit_branch(0x04, "zero", "zero", "compare")
    emit(0)

    label("fast")
    emit(i(0x0C, scratch, "t5", 3))
    emit(i(0x09, "t5", "t5", 1))

    label("compare")
    emit(i(0x09, "a3", "t6", 1))
    emit(r("t6", "t5", "a0", 0, 0x26))
    emit(j(SELECT_COMPARE))
    emit(0)

    for index, branch_pc, op, rs, rt, target in fixups:
        words[index] = branch(op, rs, rt, branch_pc, labels[target])

    blob = struct.pack("<" + "I" * len(words), *words)
    if len(blob) > EXT_CAVE_LEN:
        raise SystemExit(f"extended cave too large: 0x{len(blob):X}")
    return blob.ljust(EXT_CAVE_LEN, b"\x00")

def extended_cave_v2() -> bytes:
    words: list[int] = []
    labels: dict[str, int] = {}
    fixups: list[tuple[int, int, int, str, str, str]] = []
    pc = EXT_CAVE_ADDR

    def emit(word: int) -> None:
        nonlocal pc
        words.append(word)
        pc += 4

    def label(name: str) -> None:
        labels[name] = pc

    def emit_branch(op: int, rs: str, rt: str, target: str) -> None:
        fixups.append((len(words), pc, op, rs, rt, target))
        emit(0)

    emit(i(0x0F, "zero", "t5", (GAME_TICKS_ADDR + 0x8000) >> 16))
    emit(i(0x23, "t5", "v1", GAME_TICKS_ADDR & 0xFFFF))
    emit(0)
    emit(i(0x09, "zero", "t6", 2))
    emit_branch(0x04, "t7", "t6", "fast")
    emit(r("v1", "zero", "t5", 0, 0x21))

    # Held pseudo-random value shared by single-source and pair modes.
    emit(r("zero", "t5", "t6", 1, 0x02))
    emit(r("t5", "t6", "t5", 0, 0x21))
    emit(r("zero", "t5", "t5", 8, 0x02))
    emit(r("zero", "t5", "t6", 13, 0x00))
    emit(r("t5", "t6", "t5", 0, 0x26))
    emit(i(0x0C, "t5", "t5", 0xFFFF))
    emit(r("zero", "t5", "t6", 2, 0x00))
    emit(r("t6", "t5", "t5", 0, 0x21))
    emit(r("zero", "t5", "t5", 16, 0x02))
    emit(i(0x09, "zero", "t6", 3))
    emit_branch(0x04, "t7", "t6", "pair")
    emit(0)
    emit(j(EXT_CAVE_ADDR + 0xE8))
    emit(0)

    label("fast")
    emit(i(0x0C, "v1", "t5", 3))
    emit(i(0x09, "t5", "t5", 1))
    emit(j(EXT_CAVE_ADDR + 0xE8))
    emit(0)

    label("pair")
    # Random circular start, then choose eligible member 0 or 1 by tick phase.
    emit(i(0x0C, "t5", "t5", 3))
    emit(i(0x0C, "v1", "t6", 1))
    emit(i(0x0F, "zero", "v0", 0x8011))
    emit(i(0x09, "v0", "v0", 0x0D78))
    emit(i(0x09, "zero", "a1", 4))
    emit(i(0x09, "zero", "t7", 0))

    label("scan")
    emit(r("zero", "t5", "a0", 2, 0x00))
    emit(r("v0", "a0", "a0", 0, 0x21))
    emit(i(0x23, "a0", "a0", 0))
    emit(0)
    emit_branch(0x04, "a0", "zero", "next")
    emit(0)
    emit(i(0x24, "a0", "v1", 0x0091))
    emit(0)
    emit_branch(0x04, "v1", "zero", "next")
    emit(0)
    emit(i(0x25, "a0", "v1", 0x087E))
    emit(0)
    emit(i(0x0C, "v1", "v1", 4))
    emit_branch(0x05, "v1", "zero", "next")
    emit(0)
    emit_branch(0x04, "t6", "zero", "found")
    emit(0)
    emit(i(0x09, "t6", "t6", -1))
    emit(i(0x09, "t5", "t7", 1))

    label("next")
    emit(i(0x09, "t5", "t5", 1))
    emit(i(0x0C, "t5", "t5", 3))
    emit(i(0x09, "a1", "a1", -1))
    emit_branch(0x05, "a1", "zero", "scan")
    emit(0)
    emit(r("t7", "zero", "t5", 0, 0x21))
    emit_branch(0x04, "zero", "zero", "compare")
    emit(0)

    label("found")
    emit(i(0x09, "t5", "t5", 1))

    label("compare")
    emit(i(0x09, "a3", "t6", 1))
    emit(r("t6", "t5", "a0", 0, 0x26))
    emit(j(SELECT_COMPARE))
    emit(0)

    if labels["compare"] != EXT_CAVE_ADDR + 0xE8:
        raise SystemExit(f"unexpected compare address: 0x{labels['compare']:X}")
    for index, branch_pc, op, rs, rt, target in fixups:
        words[index] = branch(op, rs, rt, branch_pc, labels[target])

    blob = struct.pack("<" + "I" * len(words), *words)
    if len(blob) > EXT_CAVE_LEN:
        raise SystemExit(f"extended cave too large: 0x{len(blob):X}")
    return blob.ljust(EXT_CAVE_LEN, b"\x00")

def extended_cave() -> bytes:
    words: list[int] = []
    labels: dict[str, int] = {}
    fixups: list[tuple[int, int, int, str, str, str]] = []
    pc = EXT_CAVE_ADDR

    def emit(word: int) -> None:
        nonlocal pc
        words.append(word)
        pc += 4

    def label(name: str) -> None:
        labels[name] = pc

    def emit_branch(op: int, rs: str, rt: str, target: str) -> None:
        fixups.append((len(words), pc, op, rs, rt, target))
        emit(0)

    emit(i(0x0F, "zero", "t5", (GAME_TICKS_ADDR + 0x8000) >> 16))
    emit(i(0x23, "t5", "v1", GAME_TICKS_ADDR & 0xFFFF))
    emit(0)
    emit(i(0x09, "zero", "t6", 2))
    emit_branch(0x04, "t7", "t6", "fast")
    emit(r("v1", "zero", "t5", 0, 0x21))

    emit(r("zero", "t5", "t6", 1, 0x02))
    emit(r("t5", "t6", "t5", 0, 0x21))
    emit(r("zero", "t5", "t5", 8, 0x02))
    emit(r("zero", "t5", "t6", 13, 0x00))
    emit(r("t5", "t6", "t5", 0, 0x26))
    emit(i(0x0C, "t5", "t5", 0xFFFF))
    emit(r("zero", "t5", "t6", 2, 0x00))
    emit(r("t6", "t5", "t5", 0, 0x21))
    emit(r("zero", "t5", "t5", 16, 0x02))
    emit(i(0x09, "zero", "t6", 3))
    emit_branch(0x04, "t7", "t6", "pair")
    emit(0)
    emit(j(PAIR_COMPARE_ADDR))
    emit(0)

    label("fast")
    emit(i(0x0C, "v1", "t5", 3))
    emit(i(0x09, "t5", "t5", 1))
    emit(j(PAIR_COMPARE_ADDR))
    emit(0)

    label("pair")
    # Slot 0 is the player; slots 1..4 are AI cops.
    emit(i(0x0C, "v1", "t6", 1))
    emit(i(0x09, "zero", "a1", 5))
    emit(i(0x09, "zero", "t7", 0))

    label("scan")
    emit(j(PAIR_LOOKUP_ADDR))
    emit(0)
    while pc < PAIR_LOOKUP_RETURN_ADDR:
        emit(0)
    if pc != PAIR_LOOKUP_RETURN_ADDR:
        raise SystemExit(f"unexpected lookup return: 0x{pc:X}")
    emit(0)
    emit_branch(0x04, "a0", "zero", "next")
    emit(0)
    emit(i(0x24, "a0", "v1", 0x0091))
    emit(0)
    emit_branch(0x04, "v1", "zero", "next")
    emit(0)
    emit(i(0x25, "a0", "v1", 0x087E))
    emit(0)
    emit(i(0x0C, "v1", "v1", 4))
    emit_branch(0x05, "v1", "zero", "next")
    emit(0)
    emit_branch(0x04, "t6", "zero", "found")
    emit(0)
    emit(i(0x09, "t6", "t6", -1))
    emit(i(0x09, "t5", "t7", 1))

    label("next")
    emit(i(0x09, "t5", "t5", 1))
    emit(i(0x0B, "t5", "v1", 5))
    emit_branch(0x05, "v1", "zero", "count")
    emit(0)
    emit(r("zero", "zero", "t5", 0, 0x21))
    label("count")
    emit(i(0x09, "a1", "a1", -1))
    emit_branch(0x05, "a1", "zero", "scan")
    emit(0)
    emit(r("t7", "zero", "t5", 0, 0x21))
    emit(j(PAIR_COMPARE_ADDR))
    emit(0)

    label("found")
    emit(i(0x09, "t5", "t5", 1))
    emit(j(PAIR_COMPARE_ADDR))
    emit(0)

    if pc > EXT_CAVE_ADDR + EXT_CAVE_LEN:
        raise SystemExit(f"extended cave too large: 0x{pc - EXT_CAVE_ADDR:X}")
    for index, branch_pc, op, rs, rt, target in fixups:
        words[index] = branch(op, rs, rt, branch_pc, labels[target])
    blob = struct.pack("<" + "I" * len(words), *words)
    return blob.ljust(EXT_CAVE_LEN, b"\x00")

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
    ext_blob = extended_cave()
    previous_pair_ai_blob = extended_cave_v2()
    previous_t0_ext_blob = extended_cave_v1(scratch="t0")
    previous_v1_ext_blob = extended_cave_v1(scratch="v1")
    previous_multi_v3_blob = cave(variant="multi_v3")
    previous_multi_far_blob = cave(variant="multi_far")
    previous_multi_v2_blob = cave(variant="multi_v2")
    previous_multi_blob = cave(variant="multi_v1")
    previous_dynamic_blob = cave(variant="dynamic")
    previous_blob = cave(variant="legacy")

    current_hook = bytes(data[HOOK_OFF:HOOK_OFF + len(STOCK)])
    if current_hook not in {STOCK, hook}:
        raise SystemExit(f"unexpected hook: {current_hook.hex(' ')}")
    current_filter_hook = bytes(data[FILTER_HOOK_OFF:FILTER_HOOK_OFF + len(FILTER_STOCK)])
    if current_filter_hook not in {FILTER_STOCK, filter_hook}:
        raise SystemExit(f"unexpected filter hook: {current_filter_hook.hex(' ')}")
    current_cave = bytes(data[CAVE_OFF:CAVE_OFF + CAVE_LEN])
    if current_cave not in {
        bytes(CAVE_LEN),
        blob,
        previous_multi_v3_blob,
        previous_multi_far_blob,
        previous_multi_v2_blob,
        previous_multi_blob,
        previous_dynamic_blob,
        previous_blob,
    }:
        raise SystemExit("random beacon cave is not empty/known")

    current_ext_cave = bytes(data[EXT_CAVE_OFF:EXT_CAVE_OFF + EXT_CAVE_LEN])
    if current_ext_cave not in {bytes(EXT_CAVE_LEN), ext_blob, previous_pair_ai_blob, previous_t0_ext_blob, previous_v1_ext_blob}:
        raise SystemExit("extended beacon cave is not empty/known")
    old_ext_cave = bytes(data[OLD_EXT_CAVE_OFF:OLD_EXT_CAVE_OFF + EXT_CAVE_LEN])
    if old_ext_cave not in {bytes(EXT_CAVE_LEN), ext_blob, previous_pair_ai_blob, previous_t0_ext_blob, previous_v1_ext_blob}:
        raise SystemExit("old extended beacon cave is not empty/known")

    if args.revert:
        data[HOOK_OFF:HOOK_OFF + len(STOCK)] = STOCK
        data[FILTER_HOOK_OFF:FILTER_HOOK_OFF + len(FILTER_STOCK)] = FILTER_STOCK
        data[CAVE_OFF:CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
        data[EXT_CAVE_OFF:EXT_CAVE_OFF + EXT_CAVE_LEN] = bytes(EXT_CAVE_LEN)
        data[OLD_EXT_CAVE_OFF:OLD_EXT_CAVE_OFF + EXT_CAVE_LEN] = bytes(EXT_CAVE_LEN)
    else:
        data[CAVE_OFF:CAVE_OFF + CAVE_LEN] = blob
        data[EXT_CAVE_OFF:EXT_CAVE_OFF + EXT_CAVE_LEN] = ext_blob
        data[OLD_EXT_CAVE_OFF:OLD_EXT_CAVE_OFF + EXT_CAVE_LEN] = bytes(EXT_CAVE_LEN)
        data[HOOK_OFF:HOOK_OFF + len(STOCK)] = hook
        data[FILTER_HOOK_OFF:FILTER_HOOK_OFF + len(FILTER_STOCK)] = filter_hook
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)

    if bytes(data) != original:
        exe.write_bytes(data)
    print("reverted" if args.revert else "patched", exe)
    print("HP beacon source: cheat-gated fair pseudo-random slot, about 171 game ticks")
    print("mode: 800F7A64 and 800F7AD4 = 0000/0001/0002/0003")
    print("md5", hashlib.md5(data).hexdigest().upper())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
