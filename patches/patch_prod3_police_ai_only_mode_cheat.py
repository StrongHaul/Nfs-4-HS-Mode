#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_police_ai_only_mode_cheat"
RUNTIME_BASE = 0x8000F800

# AIHigh_BasicPerp::CheckForCrimes entry.
CRIME_HOOK_OFF = 0x4C4F0
CRIME_HOOK_ADDR = RUNTIME_BASE + CRIME_HOOK_OFF
CRIME_RETURN_ADDR = CRIME_HOOK_ADDR + 8
CRIME_STOCK = bytes.fromhex(
    "E0 FF BD 27"  # addiu sp,sp,-0x20
    "14 00 B1 AF"  # sw s1,0x14(sp)
)

# AIHigh_Cop::CheckForNeedyPlayers entry.
NEEDY_HOOK_OFF = 0x56394
NEEDY_RETURN_ADDR = 0x80065B9C
NEEDY_STOCK_PREFIX = bytes.fromhex(
    "FF FF 07 24"  # addiu a3,zero,-1
    "21 30 00 00"  # addu a2,zero,zero
    "14 80 08 3C"  # lui t0,0x8014
)
NEEDY_HARDCODED_PATCH = bytes.fromhex(
    "FF FF 02 24"  # addiu v0,zero,-1
    "08 00 E0 03"  # jr ra
    "00 00 00 00"  # nop
)

# Padding after the current stable second-AI hook.
CRIME_CAVE_OFF = 0xE8100
CRIME_CAVE_ADDR = RUNTIME_BASE + CRIME_CAVE_OFF
CRIME_CAVE_LEN = 0x80
NEEDY_CAVE_OFF = 0xE8180
NEEDY_CAVE_ADDR = RUNTIME_BASE + NEEDY_CAVE_OFF
NEEDY_CAVE_LEN = 0x80

# Runtime cheat edits the immediate halfword in the first instruction of both
# police caves, just like the working super-cop siren cheat. Reading arbitrary
# scratch addresses was unreliable in DuckStation/PEC, while patching executed
# addiu immediates is known-good.
CRIME_MODE_CHEAT_ADDR = CRIME_CAVE_ADDR
NEEDY_MODE_CHEAT_ADDR = NEEDY_CAVE_ADDR

REG = {
    "zero": 0,
    "v0": 2,
    "a0": 4,
    "a2": 6,
    "a3": 7,
    "t0": 8,
    "sp": 29,
    "s1": 17,
    "ra": 31,
}


def find_exe() -> Path:
    hits = list(Path(".").glob(EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {EXE_GLOB}, found {len(hits)}")
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


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def addu(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x21)


def andi(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0C, REG[rs], REG[rt], imm)


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jr(rs: str) -> int:
    return ins_r(REG[rs], 0, 0, 0, 0x08)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


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
            _, rs, rt, target = item
            item = ins_i(0x04, REG[rs], REG[rt], (labels[target] - (pc + 4)) >> 2)
        words.append(item)
        pc += 4
    return pack(words)


def make_crime_cave() -> bytes:
    # a0 = AIHigh_BasicPerp*
    # *(a0 + 0) = Car_tObj*
    #
    # 800F7900 0001: for human cars, clear crime_ and return immediately;
    #                for AI cars, execute stock prologue and continue.
    # Any other value, including 0000/0002, is stock. This avoids accidental
    # AI-only mode if the scratch halfword contains unrelated non-zero data.
    items: list[int | str | tuple[str, str, str, str]] = [
        addiu("v0", "zero", 0),
        addiu("v0", "v0", -1),
        beq("v0", "zero", "ai_only"),
        nop(),
        beq("zero", "zero", "stock"),
        nop(),
        "ai_only",
        lw("v0", 0x0000, "a0"),
        nop(),
        lw("v0", 0x0260, "v0"),
        nop(),
        andi("v0", "v0", 0x0004),
        beq("v0", "zero", "stock"),
        nop(),
        sw("zero", 0x0078, "a0"),
        jr("ra"),
        nop(),
        "stock",
        addiu("sp", "sp", -0x20),
        sw("s1", 0x0014, "sp"),
        j(CRIME_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, CRIME_CAVE_ADDR)
    if len(blob) > CRIME_CAVE_LEN:
        raise SystemExit(f"crime cave too large: 0x{len(blob):X}")
    return blob + bytes(CRIME_CAVE_LEN - len(blob))


def make_needy_cave() -> bytes:
    # 800F7980 0001: return -1, so the human player is not treated as a
    # nearby/fast needy target while cops are chasing AI racers.
    # Any other value, including 0000/0002, is stock.
    items: list[int | str | tuple[str, str, str, str]] = [
        addiu("t0", "zero", 0),
        addiu("t0", "t0", -1),
        beq("t0", "zero", "ai_only"),
        nop(),
        beq("zero", "zero", "stock"),
        nop(),
        "ai_only",
        jr("ra"),
        addiu("v0", "zero", -1),
        "stock",
        addiu("a3", "zero", -1),
        addu("a2", "zero", "zero"),
        j(NEEDY_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, NEEDY_CAVE_ADDR)
    if len(blob) > NEEDY_CAVE_LEN:
        raise SystemExit(f"needy cave too large: 0x{len(blob):X}")
    return blob + bytes(NEEDY_CAVE_LEN - len(blob))


def apply(path: Path) -> None:
    data = bytearray(path.read_bytes())

    crime_hook = pack([j(CRIME_CAVE_ADDR), nop()])
    current_crime = bytes(data[CRIME_HOOK_OFF : CRIME_HOOK_OFF + len(CRIME_STOCK)])
    if current_crime not in {CRIME_STOCK, crime_hook}:
        raise SystemExit(
            f"unexpected CheckForCrimes hook bytes at 0x{CRIME_HOOK_OFF:X}: "
            f"{current_crime.hex(' ')}"
        )

    needy_hook = pack([j(NEEDY_CAVE_ADDR), nop()]) + NEEDY_STOCK_PREFIX[8:12]
    current_needy = bytes(data[NEEDY_HOOK_OFF : NEEDY_HOOK_OFF + len(NEEDY_STOCK_PREFIX)])
    if current_needy not in {NEEDY_STOCK_PREFIX, NEEDY_HARDCODED_PATCH, needy_hook}:
        raise SystemExit(
            f"unexpected CheckForNeedyPlayers bytes at 0x{NEEDY_HOOK_OFF:X}: "
            f"{current_needy.hex(' ')}"
        )

    crime_cave = make_crime_cave()
    needy_cave = make_needy_cave()

    current_crime_cave = bytes(data[CRIME_CAVE_OFF : CRIME_CAVE_OFF + CRIME_CAVE_LEN])
    known_old_crime_cave = current_crime_cave[:4] in {
        bytes.fromhex("00 00 82 8c"),  # hardcoded AI-only cave
        bytes.fromhex("05 80 02 3c"),  # old conditional cave at 80054804
    }
    if current_crime_cave not in {bytes(CRIME_CAVE_LEN), crime_cave} and not known_old_crime_cave:
        raise SystemExit(f"crime cave is not empty/known at 0x{CRIME_CAVE_OFF:X}")

    current_needy_cave = bytes(data[NEEDY_CAVE_OFF : NEEDY_CAVE_OFF + NEEDY_CAVE_LEN])
    known_old_needy_cave = current_needy_cave[:4] == bytes.fromhex("05 80 08 3c")
    if current_needy_cave not in {bytes(NEEDY_CAVE_LEN), needy_cave} and not known_old_needy_cave:
        raise SystemExit(f"needy cave is not empty/known at 0x{NEEDY_CAVE_OFF:X}")

    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_bytes(data)

    data[CRIME_HOOK_OFF : CRIME_HOOK_OFF + len(CRIME_STOCK)] = crime_hook
    data[CRIME_CAVE_OFF : CRIME_CAVE_OFF + CRIME_CAVE_LEN] = crime_cave
    data[NEEDY_HOOK_OFF : NEEDY_HOOK_OFF + len(NEEDY_STOCK_PREFIX)] = needy_hook
    data[NEEDY_CAVE_OFF : NEEDY_CAVE_OFF + NEEDY_CAVE_LEN] = needy_cave
    path.write_bytes(data)


def revert(path: Path) -> None:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        raise SystemExit(f"backup not found: {backup}")
    path.write_bytes(backup.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    path = args.exe or find_exe()
    if args.revert:
        revert(path)
        action = "reverted"
    else:
        apply(path)
        action = "patched"

    print(f"{action} {path}")
    print("police target mode:")
    print("  stock/all racers:")
    print(f"    {0x80000000 | (CRIME_MODE_CHEAT_ADDR & 0x1FFFFF):08X} 0000")
    print(f"    {0x80000000 | (NEEDY_MODE_CHEAT_ADDR & 0x1FFFFF):08X} 0000")
    print("  AI racers only:")
    print(f"    {0x80000000 | (CRIME_MODE_CHEAT_ADDR & 0x1FFFFF):08X} 0001")
    print(f"    {0x80000000 | (NEEDY_MODE_CHEAT_ADDR & 0x1FFFFF):08X} 0001")
    print(f"md5 {md5(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
