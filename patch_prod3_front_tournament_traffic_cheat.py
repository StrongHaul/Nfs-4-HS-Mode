#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


FRONT_GLOB = "PROD 3*/FRONT.BIN"
BACKUP_SUFFIX = ".orig_before_prod3_front_tournament_traffic_cheat"
RUNTIME_BASE = 0x80010000

# Front_InitTourneyTraffic in FRONT.BIN:
#   stock skips tournament traffic unless current tournament fTraffic != 0.
# Hook that branch so 80054B7C can force tournament traffic on.
ALLOW_HOOK_OFF = 0x18530
ALLOW_CONTINUE_ADDR = RUNTIME_BASE + 0x18538
ALLOW_SKIP_ADDR = RUNTIME_BASE + 0x185F0

# Stock sets max tournament traffic to 3. Keep that for normal Tournament, but
# cap HP Tournament to 1 traffic car so 3 racers + 4 cops + traffic stays at 9.
LIMIT_HOOK_OFF = 0x18548
LIMIT_CONTINUE_ADDR = RUNTIME_BASE + 0x1854C

CAVE_OFF = 0x43180
CAVE_LEN = 0x100
ENABLE_ADDR = 0x80054B7C
FRONTEND_GAME_MODE_ADDR = 0x801158BB

STOCK_ALLOW_HOOK = bytes.fromhex("2f 00 40 10 21 88 00 00")
STOCK_LIMIT_HOOK = bytes.fromhex("03 00 15 24 21 10 20 02")

REG = {
    "zero": 0,
    "v0": 2,
    "t0": 8,
    "t1": 9,
    "s5": 21,
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


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lbu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x24, REG[rs], REG[rt], off)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


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


def cave() -> tuple[bytes, int, int]:
    items: list[int | str | tuple[str, str, str, str]] = [
        "allow_entry",
        # Hook delay already executes stock: addu s1,zero,zero.
        # v0 contains tournament fTraffic. If stock says traffic is enabled,
        # continue normally without requiring the cheat.
        bne("v0", "zero", "allow"),
        nop(),
        lui("t0", hi(ENABLE_ADDR)),
        lhu("t0", lo(ENABLE_ADDR), "t0"),
        beq("t0", "zero", "skip"),
        nop(),
        "allow",
        j(ALLOW_CONTINUE_ADDR),
        nop(),
        "skip",
        j(ALLOW_SKIP_ADDR),
        nop(),
        "limit_entry",
        # Hook delay already executes stock: addiu s5,zero,3.
        # Only the cheat can reduce HP Tournament's traffic cap to 1.
        lui("t0", hi(ENABLE_ADDR)),
        lhu("t0", lo(ENABLE_ADDR), "t0"),
        beq("t0", "zero", "limit_done"),
        nop(),
        lui("t0", hi(FRONTEND_GAME_MODE_ADDR)),
        lbu("t0", lo(FRONTEND_GAME_MODE_ADDR), "t0"),
        addiu("t1", "zero", 1),
        bne("t0", "t1", "limit_done"),
        nop(),
        addiu("s5", "zero", 1),
        "limit_done",
        j(LIMIT_CONTINUE_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, runtime(CAVE_OFF))
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X} > 0x{CAVE_LEN:X}")

    # Compute label offsets for hook targets.
    pc = runtime(CAVE_OFF)
    labels: dict[str, int] = {}
    for item in items:
        if isinstance(item, str):
            labels[item] = pc
        else:
            pc += 4
    return blob.ljust(CAVE_LEN, b"\x00"), labels["allow_entry"], labels["limit_entry"]


def find_front() -> Path:
    hits = list(Path(".").glob(FRONT_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {FRONT_GLOB}, found {len(hits)}")
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: make 80054B7C create traffic in Tournament safely."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    front = find_front()
    original = front.read_bytes()
    data = bytearray(original)

    blob, allow_addr, limit_addr = cave()
    allow_hook = pack([j(allow_addr), 0x00008821])  # addu s1,zero,zero
    limit_hook = pack([j(limit_addr), addiu("s5", "zero", 3)])

    current_allow = bytes(data[ALLOW_HOOK_OFF : ALLOW_HOOK_OFF + 8])
    if current_allow not in {STOCK_ALLOW_HOOK, allow_hook}:
        raise SystemExit(
            f"unexpected allow hook bytes at 0x{ALLOW_HOOK_OFF:X}: {current_allow.hex(' ')}"
        )

    current_limit = bytes(data[LIMIT_HOOK_OFF : LIMIT_HOOK_OFF + 8])
    if current_limit not in {STOCK_LIMIT_HOOK, limit_hook}:
        raise SystemExit(
            f"unexpected limit hook bytes at 0x{LIMIT_HOOK_OFF:X}: {current_limit.hex(' ')}"
        )

    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {b"\x00" * CAVE_LEN, blob}:
        raise SystemExit(f"cave is not empty/known at 0x{CAVE_OFF:X}")

    if args.revert:
        data[ALLOW_HOOK_OFF : ALLOW_HOOK_OFF + 8] = STOCK_ALLOW_HOOK
        data[LIMIT_HOOK_OFF : LIMIT_HOOK_OFF + 8] = STOCK_LIMIT_HOOK
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = b"\x00" * CAVE_LEN
    else:
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = blob
        data[ALLOW_HOOK_OFF : ALLOW_HOOK_OFF + 8] = allow_hook
        data[LIMIT_HOOK_OFF : LIMIT_HOOK_OFF + 8] = limit_hook

    if bytes(data) != original:
        backup = front.with_name(front.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        front.write_bytes(data)

    print(("reverted" if args.revert else "patched"), front)
    print("Tournament + 80054B7C: force frontend traffic on")
    print("Tournament max traffic: normal=3, HP gameMode=1")
    print(f"md5 {hashlib.md5(data).hexdigest().upper()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
