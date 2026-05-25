#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_single_race_traffic_respawn_cap"
RUNTIME_BASE = 0x8000F800

# Roving traffic release check. Stock reads AITune_MaxTraffic:
#   lw v0,0(v0)
#   nop
# then compares current live traffic count against v0.
HOOK_OFF = 0x62890
RETURN_ADDR = RUNTIME_BASE + HOOK_OFF + 8

# Free space before the player cop light-color cave at 0x45400.
CAVE_OFF = 0x45380
CAVE_LEN = 0x80

ENABLE_ADDR = 0x80054B7C
GAMESETUP_DATA_ADDR = 0x801144A4
GAME_TYPE_OFF = 0x0000
SINGLE_RACE_GAME_TYPE = 0
HOT_PURSUIT_GAME_TYPE = 1
MIN_SINGLE_RACE_TRAFFIC_CAP = 5
MIN_HOT_PURSUIT_TRAFFIC_CAP = 2

REG = {
    "zero": 0,
    "v0": 2,
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


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


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


def cave(*, include_hot_pursuit: bool = True) -> bytes:
    if not include_hot_pursuit:
        items: list[int | str | tuple[str, str, str, str]] = [
            # Legacy SR-only version.
            lui("t0", hi(ENABLE_ADDR)),
            lhu("t1", lo(ENABLE_ADDR), "t0"),
            beq("t1", "zero", "finish"),
            nop(),
            lui("t0", hi(GAMESETUP_DATA_ADDR)),
            addiu("t0", "t0", lo(GAMESETUP_DATA_ADDR)),
            lw("t1", GAME_TYPE_OFF, "t0"),
            bne("t1", "zero", "finish"),
            nop(),
            slti("t1", "v0", MIN_SINGLE_RACE_TRAFFIC_CAP),
            beq("t1", "zero", "finish"),
            nop(),
            addiu("v0", "zero", MIN_SINGLE_RACE_TRAFFIC_CAP),
            "finish",
            j(RETURN_ADDR),
            nop(),
        ]
        blob = pack_labeled(items, runtime(CAVE_OFF))
        if len(blob) > CAVE_LEN:
            raise SystemExit(f"legacy cave too large: 0x{len(blob):X} > 0x{CAVE_LEN:X}")
        return blob.ljust(CAVE_LEN, b"\x00")

    items: list[int | str | tuple[str, str, str, str]] = [
        # Hook delay already executes stock: lw v0,0(v0).
        lui("t0", hi(ENABLE_ADDR)),
        lhu("t1", lo(ENABLE_ADDR), "t0"),
        beq("t1", "zero", "finish"),
        nop(),
        lui("t0", hi(GAMESETUP_DATA_ADDR)),
        addiu("t0", "t0", lo(GAMESETUP_DATA_ADDR)),
        lw("t1", GAME_TYPE_OFF, "t0"),
        beq("t1", "zero", "single_race"),
        nop(),
        *(
            [
                addiu("t1", "t1", -HOT_PURSUIT_GAME_TYPE),
                bne("t1", "zero", "finish"),
                nop(),
                # Hot Pursuit + enabled traffic cheat: let the second night
                # traffic car leave purgatory.
                slti("t1", "v0", MIN_HOT_PURSUIT_TRAFFIC_CAP),
                beq("t1", "zero", "finish"),
                nop(),
                addiu("v0", "zero", MIN_HOT_PURSUIT_TRAFFIC_CAP),
                beq("zero", "zero", "finish"),
                nop(),
            ]
            if include_hot_pursuit
            else [bne("t1", "zero", "finish"), nop()]
        ),
        "single_race",
        # Single Race + enabled Raceway/traffic cheat: let roving traffic keep
        # up to the normal day cap even on night/dusk variants.
        slti("t1", "v0", MIN_SINGLE_RACE_TRAFFIC_CAP),
        beq("t1", "zero", "finish"),
        nop(),
        addiu("v0", "zero", MIN_SINGLE_RACE_TRAFFIC_CAP),
        "finish",
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
        description="PROD3: raise Single Race traffic release cap when 80054B7C is enabled."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    stock_hook = pack([lw("v0", 0, "v0"), nop()])
    patched_hook = pack([j(runtime(CAVE_OFF)), lw("v0", 0, "v0")])
    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {stock_hook, patched_hook}:
        raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")

    blob = cave()
    previous_blob = cave(include_hot_pursuit=False)
    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {b"\x00" * CAVE_LEN, blob, previous_blob}:
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
    print("Single Race + 80054B7C: traffic release cap minimum = 5")
    print("Hot Pursuit + 80054B7C: traffic release cap minimum = 2")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
