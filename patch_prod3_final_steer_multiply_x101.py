#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import struct
from pathlib import Path


BACKUP_SUFFIX = ".orig_before_final_steer_x101_prod3"
RUNTIME_BASE = 0x8000F800

HOOK_OFF = 0x9DD50
CAVE_OFF = 0x45D00
CAVE_LEN = 0x58
RETURN_ADDR = RUNTIME_BASE + 0x9DD58

RATIO_ADD_OFF = 0x9DD3C
DUCK_SAFE_NOP = bytes.fromhex("00 00 00 00")
ORIGINAL_HOOK = bytes.fromhex("18 00 82 00 12 88 00 00")
HOOK = struct.pack("<II", (0x02 << 26) | (((RUNTIME_BASE + CAVE_OFF) >> 2) & 0x03FFFFFF), 0)

REG = {
    "zero": 0,
    "v0": 2,
    "a0": 4,
    "t0": 8,
    "s1": 17,
}


def prod3_exe() -> Path:
    hits = list(Path(".").glob("PROD 3*/NFS4.EXE"))
    if len(hits) != 1:
        raise SystemExit(f"expected one PROD 3*/NFS4.EXE, found {len(hits)}")
    return hits[0]


def ins_r(rs: str, rt: str, rd: str, sh: int, fn: int) -> int:
    return (REG[rs] << 21) | (REG[rt] << 16) | (REG[rd] << 11) | (sh << 6) | fn


def ins_j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def nop() -> int:
    return 0


def mult(rs: str, rt: str) -> int:
    return (REG[rs] << 21) | (REG[rt] << 16) | 0x18


def mflo(rd: str) -> int:
    return (REG[rd] << 11) | 0x12


def sra(rd: str, rt: str, sh: int) -> int:
    return ins_r("zero", rt, rd, sh, 0x03)


def addu(rd: str, rs: str, rt: str) -> int:
    return ins_r(rs, rt, rd, 0, 0x21)


def x101_cave() -> bytes:
    # x1 + 1/128 + 1/512 = x1.009765625, close to requested x1.01.
    words = [
        mult("a0", "v0"),
        mflo("s1"),
        sra("v0", "s1", 7),
        sra("t0", "s1", 9),
        addu("v0", "v0", "t0"),
        addu("s1", "s1", "v0"),
        j(RETURN_ADDR),
        nop(),
    ]
    cave = pack(words)
    if len(cave) > CAVE_LEN:
        raise SystemExit(f"cave too large: {len(cave)} > {CAVE_LEN}")
    return cave.ljust(CAVE_LEN, b"\x00")


def main() -> int:
    exe = prod3_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    actual_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if actual_hook not in (ORIGINAL_HOOK, HOOK):
        raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {actual_hook.hex(' ')}")

    backup = exe.with_name(exe.name + BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_bytes(original)

    data[RATIO_ADD_OFF : RATIO_ADD_OFF + 4] = DUCK_SAFE_NOP
    cave = x101_cave()
    data[CAVE_OFF : CAVE_OFF + len(cave)] = cave
    data[HOOK_OFF : HOOK_OFF + 8] = HOOK

    exe.write_bytes(data)
    final = exe.read_bytes()
    print(f"patched {exe}")
    print(f"backup {backup}")
    print("final steering multiply x1.009765625")
    print(f"md5 {hashlib.md5(final).hexdigest()}")
    print(f"hook 0x{HOOK_OFF:06X}: {final[HOOK_OFF:HOOK_OFF+8].hex(' ')}")
    print(f"cave 0x{CAVE_OFF:06X}: {final[CAVE_OFF:CAVE_OFF+32].hex(' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
