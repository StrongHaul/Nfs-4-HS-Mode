#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_single_race_traffic_respawn_cap"
RUNTIME_BASE = 0x8000F800

# Roving traffic release check. Stock reads an AITune release interval:
#   lw v0,0(v0)
#   nop
# then compares elapsed frames since the last traffic release against v0.
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
TOURNAMENT_GAME_TYPE = 2
BOOSTED_SINGLE_RACE_RELEASE_INTERVAL = 1
BOOSTED_HOT_PURSUIT_RELEASE_INTERVAL = 1
BOOSTED_TOURNAMENT_RELEASE_INTERVAL = 1
LEGACY_SINGLE_RACE_RELEASE_INTERVAL = 5
LEGACY_HOT_PURSUIT_RELEASE_INTERVAL = 2
LEGACY_TOURNAMENT_RELEASE_INTERVAL = 2

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


def cap_interval_items(interval: int) -> list[int | str | tuple[str, str, str, str]]:
    return [
        # If the stock interval is already <= interval, keep it. Otherwise cap
        # it down to the requested value.
        slti("t1", "v0", interval + 1),
        bne("t1", "zero", "finish"),
        nop(),
        addiu("v0", "zero", interval),
    ]


def old_min_interval_items(interval: int) -> list[int | str | tuple[str, str, str, str]]:
    return [
        # Old broken behavior: this raised very small intervals but left large
        # stock intervals unchanged.
        slti("t1", "v0", interval),
        beq("t1", "zero", "finish"),
        nop(),
        addiu("v0", "zero", interval),
    ]


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


def cave(
    *,
    include_hot_pursuit: bool = True,
    include_tournament: bool = True,
    single_race_interval: int = BOOSTED_SINGLE_RACE_RELEASE_INTERVAL,
    hot_pursuit_interval: int = BOOSTED_HOT_PURSUIT_RELEASE_INTERVAL,
    tournament_interval: int = BOOSTED_TOURNAMENT_RELEASE_INTERVAL,
    use_old_min_logic: bool = False,
) -> bytes:
    interval_items = old_min_interval_items if use_old_min_logic else cap_interval_items
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
            *interval_items(single_race_interval),
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
                *(
                    [
                        # After subtracting HP's raceType, HP is 0 and Tournament is 1.
                        # Keep every other mode on the stock release interval.
                        slti("t1", "t1", TOURNAMENT_GAME_TYPE),
                        beq("t1", "zero", "finish"),
                    ]
                    if include_tournament
                    else [bne("t1", "zero", "finish")]
                ),
                nop(),
                # HP + enabled traffic cheat: let the second night traffic car
                # leave purgatory. Tournament uses the same compact density boost
                # without changing carData composition.
                *interval_items(hot_pursuit_interval),
                beq("zero", "zero", "finish"),
                nop(),
            ]
            if include_hot_pursuit
            else [bne("t1", "zero", "finish"), nop()]
        ),
        "single_race",
        # Single Race + enabled Raceway/traffic cheat: heavily shorten the
        # roving traffic release interval, so replacement traffic appears much
        # sooner after the live count drops.
        *interval_items(single_race_interval),
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
        description="PROD3: shorten traffic release interval when 80054B7C is enabled."
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
    broken_one_frame_blob = cave(use_old_min_logic=True)
    legacy_full_blob = cave(
        single_race_interval=LEGACY_SINGLE_RACE_RELEASE_INTERVAL,
        hot_pursuit_interval=LEGACY_HOT_PURSUIT_RELEASE_INTERVAL,
        tournament_interval=LEGACY_TOURNAMENT_RELEASE_INTERVAL,
        use_old_min_logic=True,
    )
    previous_blob = cave(include_hot_pursuit=False, use_old_min_logic=True)
    previous_hp_blob = cave(include_tournament=False, use_old_min_logic=True)
    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {
        b"\x00" * CAVE_LEN,
        blob,
        broken_one_frame_blob,
        legacy_full_blob,
        previous_blob,
        previous_hp_blob,
    }:
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
    print("Single Race + 80054B7C: traffic release interval <= 1 frame")
    print("Hot Pursuit + 80054B7C: traffic release interval <= 1 frame")
    print("Tournament + 80054B7C: traffic release interval <= 1 frame")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
