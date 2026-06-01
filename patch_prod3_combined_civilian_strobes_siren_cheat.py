#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_combined_civilian_strobes_siren_cheat"
RUNTIME_BASE = 0x8000F800

CHEAT_FLAG_ADDR = 0x8011F208

SIREN_TYPE_HOOK_OFF = 0x066D54
SIREN_BIT_HOOK_OFF = 0x066D68
SIREN_TYPE_CAVE_OFF = 0x45444
SIREN_BIT_CAVE_OFF = 0x45484

SIREN_TYPE_ALLOW_ADDR = 0x8007655C
SIREN_TYPE_SKIP_ADDR = 0x8007663C
SIREN_OFF_PATH_ADDR = 0x8007660C
SIREN_BIT_ALLOW_ADDR = 0x80076570
SIREN_BIT_SKIP_ADDR = 0x80076600

EXPECTED_SIREN_TYPE_HOOK = bytes.fromhex("39 00 40 10 00 00 00 00")
EXPECTED_SIREN_BIT_HOOK = bytes.fromhex("25 00 40 10 24 13 82 2a")

REG = {
    "zero": 0,
    "v0": 2,
    "t0": 8,
    "t1": 9,
    "s2": 18,
    "s4": 20,
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


def sltiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0B, REG[rs], REG[rt], imm)


def nop() -> int:
    return 0


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


def padded(blob: bytes, size: int) -> bytes:
    if len(blob) > size:
        raise SystemExit(f"blob too large: 0x{len(blob):X} > 0x{size:X}")
    return blob + bytes(size - len(blob))


def read_cheat_flag() -> list[int]:
    return [
        # 0x8011F208 is addressed as 0x80120000 - 0x0DF8.
        lui("t0", ((CHEAT_FLAG_ADDR + 0x8000) >> 16) & 0xFFFF),
        lhu("t1", CHEAT_FLAG_ADDR & 0xFFFF, "t0"),
        andi("t1", "t1", 1),
    ]


def car_type_is_police() -> list[int | str | tuple[str, str, str, str]]:
    return [
        lw("t1", 0x288, "s2"),
        lw("t1", 0, "t1"),
        addiu("t1", "t1", -0x16),
        sltiu("t1", "t1", 6),
    ]


def make_siren_type_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        bne("v0", "zero", "allow"),
        nop(),
        *read_cheat_flag(),
        bne("t1", "zero", "allow"),
        nop(),
        "force_off",
        j(SIREN_OFF_PATH_ADDR),
        nop(),
        "allow",
        j(SIREN_TYPE_ALLOW_ADDR),
        nop(),
    ]
    return padded(pack_labeled(items, runtime(SIREN_TYPE_CAVE_OFF)), 0x40)


def make_siren_bit_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        bne("v0", "zero", "allow"),
        nop(),
        *read_cheat_flag(),
        beq("t1", "zero", "skip"),
        nop(),
        *car_type_is_police(),
        bne("t1", "zero", "skip"),
        nop(),
        "allow",
        slti("v0", "s4", 4900),
        j(SIREN_BIT_ALLOW_ADDR),
        nop(),
        "skip",
        slti("v0", "s4", 4900),
        j(SIREN_BIT_SKIP_ADDR),
        nop(),
    ]
    return padded(pack_labeled(items, runtime(SIREN_BIT_CAVE_OFF)), 0x60)


def hook_bytes(cave_off: int) -> bytes:
    return pack([j(runtime(cave_off)), nop()])


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest().upper()


def patch(exe: Path, *, revert: bool = False) -> None:
    original = exe.read_bytes()
    data = bytearray(original)

    type_patch = hook_bytes(SIREN_TYPE_CAVE_OFF)
    bit_patch = hook_bytes(SIREN_BIT_CAVE_OFF)

    type_now = bytes(data[SIREN_TYPE_HOOK_OFF : SIREN_TYPE_HOOK_OFF + 8])
    bit_now = bytes(data[SIREN_BIT_HOOK_OFF : SIREN_BIT_HOOK_OFF + 8])
    if type_now not in (EXPECTED_SIREN_TYPE_HOOK, type_patch):
        raise SystemExit(f"unexpected siren type hook bytes: {type_now.hex(' ')}")
    if bit_now not in (EXPECTED_SIREN_BIT_HOOK, bit_patch):
        raise SystemExit(f"unexpected siren bit hook bytes: {bit_now.hex(' ')}")

    cave_start = SIREN_TYPE_CAVE_OFF
    cave_end = SIREN_BIT_CAVE_OFF + 0x60
    cave_now = bytes(data[cave_start:cave_end])
    expected = bytearray(cave_end - cave_start)
    type_cave = make_siren_type_cave()
    bit_cave = make_siren_bit_cave()
    expected[0 : len(type_cave)] = type_cave
    bit_rel = SIREN_BIT_CAVE_OFF - cave_start
    expected[bit_rel : bit_rel + len(bit_cave)] = bit_cave
    if (
        cave_now not in (bytes(cave_end - cave_start), bytes(expected))
        and cave_now[:4] not in (bytes(4), expected[:4])
    ):
        raise SystemExit(f"unexpected siren cave bytes: {cave_now[:16].hex(' ')}")

    if revert:
        data[SIREN_TYPE_HOOK_OFF : SIREN_TYPE_HOOK_OFF + 8] = EXPECTED_SIREN_TYPE_HOOK
        data[SIREN_BIT_HOOK_OFF : SIREN_BIT_HOOK_OFF + 8] = EXPECTED_SIREN_BIT_HOOK
        data[cave_start:cave_end] = bytes(cave_end - cave_start)
    else:
        data[SIREN_TYPE_HOOK_OFF : SIREN_TYPE_HOOK_OFF + 8] = type_patch
        data[SIREN_BIT_HOOK_OFF : SIREN_BIT_HOOK_OFF + 8] = bit_patch
        data[cave_start:cave_end] = bytes(cave_end - cave_start)
        data[SIREN_TYPE_CAVE_OFF : SIREN_TYPE_CAVE_OFF + len(type_cave)] = type_cave
        data[SIREN_BIT_CAVE_OFF : SIREN_BIT_CAVE_OFF + len(bit_cave)] = bit_cave

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(bytes(data))}")
    print("combined civilian strobes/siren cheat hook:", "reverted" if revert else "patched")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: built-in siren gate for the combined civilian strobes/siren cheat."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()
    patch(find_exe(), revert=args.revert)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
