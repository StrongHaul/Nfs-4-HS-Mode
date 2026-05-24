#!/usr/bin/env python3
from __future__ import annotations

import argparse
import struct
from pathlib import Path


BACKUP_SUFFIX = ".orig_opponent_racers_prod2"
DEFAULT_EXE_GLOB = "PROD 2*/NFS4.EXE"
RUNTIME_BASE = 0x8000F800

MASS_HOOK_OFF = 0x92F48
MASS_CAVE_OFF = 0x45C00
MASS_CAVE_LEN = 0x70
OLD_MASS_CAVE_OFF = 0x4627C
OLD_CD_CAVE_OFF = 0xE8024
MASS_RETURN_ADDR = 0x800A2750
OPPONENT_MARK_HOOK_OFF = 0x54AFC
LOD_DETAIL_OFF = 0xA0508
AIRACE_LIST_LOW = 0x0D30
AIRACE_COUNT_LOW = 0xDAF8


REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "a0": 4,
    "a1": 5,
    "a2": 6,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "s0": 16,
    "s4": 20,
    "sp": 29,
    "ra": 31,
}


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_r(rs: int, rt: int, rd: int, sh: int, fn: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (sh << 6) | fn


def ins_j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def sb(rt: str, off: int, rs: str) -> int:
    return ins_i(0x28, REG[rs], REG[rt], off)


def sh(rt: str, off: int, rs: str) -> int:
    return ins_i(0x29, REG[rs], REG[rt], off)


def andi(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0C, REG[rs], REG[rt], imm)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def beq(rs: str, rt: str, pc: int, target: int) -> int:
    return ins_i(0x04, REG[rs], REG[rt], (target - (pc + 4)) >> 2)


def bne(rs: str, rt: str, pc: int, target: int) -> int:
    return ins_i(0x05, REG[rs], REG[rt], (target - (pc + 4)) >> 2)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jal(addr: int) -> int:
    return ins_j(0x03, addr)


def nop() -> int:
    return 0


def jr(reg: str) -> int:
    return ins_r(REG[reg], 0, 0, 0, 0x08)


def sll(rd: str, rt: str, shamt: int) -> int:
    return ins_r(0, REG[rt], REG[rd], shamt, 0x00)


def addu(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x21)


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def runtime(off: int) -> int:
    return RUNTIME_BASE + off


def mass_cave() -> bytes:
    pc = runtime(MASS_CAVE_OFF)
    loop = pc + 0x1C
    normal = pc + 0x34
    heavy = pc + 0x3C
    words = [
        sw("a2", 0x00B8, "s0"),
        lui("t0", 0x8011),
        addiu("t0", "t0", AIRACE_LIST_LOW),
        lui("t1", 0x8014),
        lw("t1", AIRACE_COUNT_LOW, "t1"),
        beq("t1", "zero", pc + 0x14, normal),
        nop(),
        lw("t2", 0x0000, "t0"),
        addiu("t0", "t0", 4),
        beq("t2", "s0", pc + 0x24, heavy),
        addiu("t1", "t1", -1),
        bne("t1", "zero", pc + 0x2C, loop),
        nop(),
        j(MASS_RETURN_ADDR),
        nop(),
        sll("t0", "a2", 5),
        sll("t1", "a2", 2),
        addu("t0", "t0", "t1"),
        addu("t0", "t0", "a2"),
        ins_r(0, REG["t0"], REG["t0"], 4, 0x03),  # sra t0,t0,4 -> x37/16 ~= x2.3
        sw("t0", 0x00B8, "s0"),
        j(MASS_RETURN_ADDR),
        nop(),
    ]
    return pack(words).ljust(MASS_CAVE_LEN, b"\x00")


def old_bss_mass_cave() -> bytes:
    pc = runtime(0x12F86C)
    ret = pc + 0x44
    words = [
        sw("a2", 0x00B8, "s0"),
        lw("t0", 0x0570, "s0"),
        nop(),
        andi("t0", "t0", 0x0004),
        bne("t0", "zero", pc + 0x10, ret),
        nop(),
        lw("t0", 0x0260, "s0"),
        nop(),
        andi("t1", "t0", 0x0004),
        bne("t1", "zero", pc + 0x24, ret),
        nop(),
        andi("t1", "t0", 0x0400),
        bne("t1", "zero", pc + 0x30, ret),
        nop(),
        sll("t0", "a2", 2),
        addu("t0", "t0", "a2"),
        sw("t0", 0x00B8, "s0"),
        jr("ra"),
        nop(),
    ]
    return pack(words)


def find_default_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def patch_at(data: bytearray, off: int, old_options: list[bytes], new: bytes, name: str, apply: bool) -> None:
    actual = bytes(data[off : off + len(new)])
    if actual == new:
        print(f"{name}: already patched at 0x{off:X}")
        return
    if actual not in old_options:
        expected = " or ".join(x.hex(" ") for x in old_options)
        raise SystemExit(f"{name}: unexpected bytes at 0x{off:X}: {actual.hex(' ')}; expected {expected}")
    print(f"{name}: patch 0x{off:X}: {actual.hex(' ')} -> {new.hex(' ')}")
    if apply:
        data[off : off + len(new)] = new


def apply_patch(path: Path, apply: bool, high_lod: bool) -> None:
    original = path.read_bytes()
    data = bytearray(original)

    mass_hook = pack([j(runtime(MASS_CAVE_OFF))])
    mass_blob = mass_cave()
    old_mass_blob = old_bss_mass_cave()

    patch_at(
        data,
        MASS_HOOK_OFF,
        [
            bytes.fromhex("b8 00 06 ae"),  # sw a2,0x00B8(s0)
            pack([jal(runtime(MASS_CAVE_OFF))]),
            pack([j(runtime(OLD_MASS_CAVE_OFF))]),
            pack([j(runtime(OLD_CD_CAVE_OFF))]),
            mass_hook,
            pack([jal(runtime(0x12F86C))]),
        ],
        mass_hook,
        "opponent racer Newton mass hook",
        apply,
    )

    lod_target = bytes.fromhex("c0 08 84 a6") if high_lod else bytes.fromhex("b2 08 84 a2")
    patch_at(
        data,
        OPPONENT_MARK_HOOK_OFF,
        [
            bytes.fromhex("b0 00 40 ac b4 00 40 ac"),
            pack([jal(runtime(MASS_CAVE_OFF)), nop()]),
        ],
        bytes.fromhex("b0 00 40 ac b4 00 40 ac"),
        "restore AIHigh_Opponent constructor",
        apply,
    )

    patch_at(
        data,
        LOD_DETAIL_OFF,
        [
            bytes.fromhex("b2 08 84 a2"),  # sb a0,0x08B2(s4)
            bytes.fromhex("c0 08 84 a6"),  # sh a0,0x08C0(s4), unsafe for full AI grids
        ],
        lod_target,
        "opponent racer LOD mode",
        apply,
    )

    patch_at(
        data,
        MASS_CAVE_OFF,
        [
            b"\x00" * len(mass_blob),
            mass_blob,
            bytes.fromhex(
                "f4 ff bd 27 00 00 a8 af 04 00 a9 af 08 00 aa af b8 00 06 ae"
                " 11 80 08 3c 30 0d 08 25 14 80 09 3c f8 da 29 8d 07 00 20 11"
                " 00 00 00 00 00 00 0a 8d 04 00 08 25 08 00 50 11 ff ff 29 25"
                " fb ff 20 15 00 00 00 00 08 00 aa 8f 04 00 a9 8f 00 00 a8 8f"
                " d4 89 02 08 0c 00 bd 27 80 40 06 00 21 40 06 01 b8 00 08 ae"
                " 11 55 01 08 00 00 00 00 00 00 00 00"
            ),
            bytes.fromhex(
                "f4 ff bd 27 00 00 a8 af 04 00 a9 af 08 00 aa af b8 00 06 ae"
                " 11 80 08 3c 30 0d 08 25 14 80 09 3c f8 da 29 8d 07 00 20 11"
                " 00 00 00 00 00 00 0a 8d 04 00 08 25 08 00 50 11 ff ff 29 25"
                " fb ff 20 15 00 00 00 00 08 00 aa 8f 04 00 a9 8f 00 00 a8 8f"
                " d4 89 02 08 0c 00 bd 27 80 40 06 00 21 40 06 01 43 40 08 00"
                " b8 00 08 ae 11 55 01 08 00 00 00 00"
            ),
            bytes.fromhex(
                "f8 ff bd 27 00 00 a8 af 04 00 a9 af b8 00 06 ae 60 02 08 8e"
                " 00 00 00 00 00 10 09 31 04 00 20 11 00 00 00 00 80 40 06 00"
                " 21 40 06 01 b8 00 08 ae 04 00 a9 8f 00 00 a8 8f 08 00 e0 03"
                " 08 00 bd 27"
            ),
            bytes.fromhex(
                "b0 00 40 ac b4 00 40 ac 00 00 48 8c 00 00 00 00 60 02 09 8d"
                " 00 00 00 00 00 10 29 35 60 02 09 ad 08 00 e0 03 00 00 00 00"
            ).ljust(len(mass_blob), b"\x00"),
        ],
        mass_blob,
        "opponent racer AIRace-list x2.3 mass cave",
        apply,
    )
    patch_at(
        data,
        OLD_MASS_CAVE_OFF,
        [
            b"\x00" * 0x48,
            bytes.fromhex(
                "f8 ff bd 27 00 00 a8 af 04 00 a9 af b8 00 06 ae 60 02 08 8e"
                " 00 00 00 00 00 10 09 31 04 00 20 11 00 00 00 00 80 40 06 00"
                " 21 40 06 01 b8 00 08 ae 04 00 a9 8f 00 00 a8 8f d4 89 02 08"
                " 08 00 bd 27"
            ),
            bytes.fromhex(
                "f8 ff bd 27 00 00 a8 af 04 00 a9 af b8 00 06 ae 60 02 08 8e"
                " 00 00 00 00 00 10 09 31 04 00 20 11 00 00 00 00 80 40 06 00"
                " 21 40 06 01 b8 00 08 ae 04 00 a9 8f 00 00 a8 8f d4 89 02 08"
                " 08 00 bd 27 08 00 e0 03 08 00 bd 27"
            ),
            bytes.fromhex(
                "f8 ff bd 27 00 00 a8 af 04 00 a9 af b8 00 06 ae 60 02 08 8e"
                " 00 00 00 00 00 10 09 31 04 00 20 11 00 00 00 00 80 40 06 00"
                " 21 40 06 01 b8 00 08 ae 04 00 a9 8f 00 00 a8 8f 08 00 e0 03"
                " 08 00 bd 27"
            ),
        ],
        b"\x00" * 0x48,
        "clear old local mass cave",
        apply,
    )
    patch_at(
        data,
        OLD_CD_CAVE_OFF,
        [
            b"\x00" * len(mass_blob),
            mass_blob,
            bytes.fromhex(
                "f4 ff bd 27 00 00 a8 af 04 00 a9 af 08 00 aa af b8 00 06 ae"
                " 11 80 08 3c 30 0d 08 25 14 80 09 3c f8 da 29 8d 07 00 20 11"
                " 00 00 00 00 00 00 0a 8d 04 00 08 25 08 00 50 11 ff ff 29 25"
                " fb ff 20 15 00 00 00 00 08 00 aa 8f 04 00 a9 8f 00 00 a8 8f"
                " d4 89 02 08 0c 00 bd 27 80 40 06 00 21 40 06 01 b8 00 08 ae"
                " 11 55 01 08 00 00 00 00"
            ),
            bytes.fromhex(
                "f4 ff bd 27 00 00 a8 af 04 00 a9 af 08 00 aa af b8 00 06 ae"
                " 11 80 08 3c 30 0d 08 25 14 80 09 3c f8 da 29 8d 07 00 20 11"
                " 00 00 00 00 00 00 0a 8d 04 00 08 25 08 00 50 11 ff ff 29 25"
                " fb ff 20 15 00 00 00 00 08 00 aa 8f 04 00 a9 8f 00 00 a8 8f"
                " d4 89 02 08 0c 00 bd 27 80 40 06 00 21 40 06 01 b8 00 08 ae"
                " 11 55 01 08 00 00 00 00 00 00 00 00"
            ),
            bytes.fromhex(
                "b0 00 40 ac b4 00 40 ac 00 00 48 8c 00 00 00 00 60 02 09 8d"
                " 00 00 00 00 00 10 29 35 60 02 09 ad 08 00 e0 03 00 00 00 00"
            ).ljust(len(mass_blob), b"\x00"),
            bytes.fromhex(
                "f4 ff bd 27 00 00 a8 af 04 00 a9 af 08 00 aa af b8 00 06 ae"
                " 11 80 08 3c 30 0d 08 25 14 80 09 3c f8 da 29 8d 07 00 20 11"
                " 00 00 00 00 00 00 0a 8d 04 00 08 25 08 00 50 11 ff ff 29 25"
                " fb ff 20 15 00 00 00 00 08 00 aa 8f 04 00 a9 8f 00 00 a8 8f"
                " d4 89 02 08 0c 00 bd 27 80 40 06 00 21 40 06 01 b8 00 08 ae"
                " 1a de 03 08 00 00 00 00"
            ),
        ],
        b"\x00" * len(mass_blob),
        "clear old CD-area cave",
        apply,
    )
    patch_at(
        data,
        0x12F86C,
        [b"\x00" * len(old_mass_blob), old_mass_blob],
        b"\x00" * len(old_mass_blob),
        "clear unsafe old BSS mass cave",
        apply,
    )
    patch_at(
        data,
        0x12F8C0,
        [b"\x00" * 0x4C],
        b"\x00" * 0x4C,
        "clear unsafe old BSS LOD cave",
        apply,
    )

    if apply:
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        path.write_bytes(data)
        print(f"done: patched {path}")
    else:
        print("dry run only; pass --apply to write changes")


def restore(path: Path) -> None:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        raise SystemExit(f"backup not found: {backup}")
    path.write_bytes(backup.read_bytes())
    print(f"restored {path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patch PROD2 NFS4.EXE: x2.3 Newton collision mass for racer bots only."
    )
    parser.add_argument("--exe", type=Path, help="Path to PROD2 NFS4.EXE")
    parser.add_argument("--apply", action="store_true", help="Write patched EXE")
    parser.add_argument("--restore", action="store_true", help="Restore backup")
    parser.add_argument(
        "--high-lod",
        action="store_true",
        help="Experimental: force the second AI LOD path to high-poly. Can crash from memory pressure.",
    )
    args = parser.parse_args()

    path = args.exe or find_default_exe()
    if args.restore:
        restore(path)
    else:
        apply_patch(path, args.apply, args.high_lod)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
