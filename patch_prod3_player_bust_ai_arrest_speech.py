#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_bust_ai_arrest_speech"
RUNTIME_BASE = 0x8000F800

# AIHigh_BTC_Perp::HandlePullOver, after NotifyHumanCopsOfArrestHud(this):
#   addiu v0,zero,1
#   sw    v0,0x80(s0)   ; hudActivated_ = 1
#
# The player-arrests-AI patch avoids setting the global human-cop flag on the
# player car, because the stock HUD path casts highLevelAIObjs[player] as a
# BTC human cop and can hang. That also means no real cop speaker receives the
# arrest notification. This hook restores only the speech call for the player
# arrest path, without reviving the unsafe human-cop cast.
HOOK_OFF = 0x50B20
HOOK_ADDR = RUNTIME_BASE + HOOK_OFF
RETURN_ADDR = 0x80060328
STOCK = bytes.fromhex(
    "01 00 02 24"  # addiu v0,zero,1
    "80 00 02 AE"  # sw v0,0x80(s0)
)

CAVE_OFF = 0xFEF00
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x120

PLAYER_ARREST_CHEAT_FLAG_ADDR = 0x800F7A00
PLAYER_CAR_OBJ_PTR_ADDR = 0x80110D0C
SPEECH_MOBILE_ADDR = 0x8009785C

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "a0": 4,
    "a1": 5,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "t3": 11,
    "t4": 12,
    "t5": 13,
    "s0": 16,
    "sp": 29,
    "ra": 31,
}


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest().upper()


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_r(rs: int, rt: int, rd: int, sh: int, fn: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (sh << 6) | fn


def ins_j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


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


def jal(addr: int) -> int:
    return ins_j(0x03, addr)


def jalr(rs: str) -> int:
    return ins_r(REG[rs], 0, REG["ra"], 0, 0x09)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lh(rt: str, off: int, rs: str) -> int:
    return ins_i(0x21, REG[rs], REG[rt], off)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def nop() -> int:
    return 0


def hi(addr: int) -> int:
    return (addr >> 16) & 0xFFFF


def lo(addr: int) -> int:
    return addr & 0xFFFF


def make_hook() -> bytes:
    return pack([j(CAVE_ADDR), addiu("v0", "zero", 1)])


def make_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Hook delay slot already executed addiu v0,zero,1.
        sw("v0", 0x0080, "s0"),
        # Only the explicit player-arrest cheat path should synthesize speech.
        lui("t0", hi(PLAYER_ARREST_CHEAT_FLAG_ADDR)),
        lhu("t0", lo(PLAYER_ARREST_CHEAT_FLAG_ADDR), "t0"),
        addiu("t0", "t0", -1),
        bne("t0", "zero", "done"),
        nop(),
        lui("t0", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
        lw("t1", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t0"),
        nop(),
        beq("t1", "zero", "done"),
        nop(),
        lw("t2", 0x006C, "s0"),  # AIHigh_BasicPerp::lastArrestingCop_
        nop(),
        bne("t2", "t1", "done"),
        nop(),
        addiu("sp", "sp", -16),
        sw("ra", 12, "sp"),
        addu("a0", "t1", "zero"),
        jal(SPEECH_MOBILE_ADDR),
        nop(),
        beq("v0", "zero", "restore"),
        nop(),
        # Same virtual call shape as AIHigh_Player::HandleSpeech:
        # Mobile(playerCar)->Catch(8)
        lw("t3", 0x004C, "v0"),
        nop(),
        lh("t4", 0x0048, "t3"),
        lw("t5", 0x004C, "t3"),
        addiu("a1", "zero", 8),
        jalr("t5"),
        addu("a0", "v0", "t4"),
        "restore",
        lw("ra", 12, "sp"),
        addiu("sp", "sp", 16),
        "done",
        j(RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, CAVE_ADDR)
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"speech cave too large: 0x{len(blob):X}")
    return blob + bytes(CAVE_LEN - len(blob))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    data = bytearray(exe.read_bytes())
    original = bytes(data)

    hook = make_hook()
    cave = make_cave()

    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {STOCK, hook}:
        raise SystemExit(
            f"unexpected arrest speech hook bytes at 0x{HOOK_OFF:X}: "
            f"{current_hook.hex(' ')}"
        )

    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {bytes(CAVE_LEN), cave}:
        raise SystemExit(f"arrest speech cave is not empty/known at 0x{CAVE_OFF:X}")

    if args.revert:
        data[HOOK_OFF : HOOK_OFF + 8] = STOCK
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    else:
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = cave
        data[HOOK_OFF : HOOK_OFF + 8] = hook

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(exe)}")
    print(
        "player bust AI arrest speech: {}".format(
            "reverted" if args.revert else "enabled"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
