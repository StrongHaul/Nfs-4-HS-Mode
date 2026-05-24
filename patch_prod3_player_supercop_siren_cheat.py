#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


RUNTIME_BASE = 0x8000F800
DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_prod3_player_supercop_siren_cheat"

# Free zeroed area before the player-cop-livery cave at 0x45B00.
CAVE_OFF = 0x45A00
CAVE_LEN = 0x80
SIREN_ON_CAVE_OFF = CAVE_OFF
UPDATE_SIREN_CAVE_OFF = CAVE_OFF + 0x50

# Runtime cheat writes the immediate halfword in these two addiu instructions:
#   80055204 0000 + 80055258 0000 - force normal player siren/default
#   80055204 0001 + 80055258 0001 - use the super-cop siren mode

# PROD3 AudioClc_SoundPlayersCar callsites.
SOUND_PLAYER_SIREN_ON_HOOK_OFF = 0x66DD0
SOUND_PLAYER_UPDATE_SIREN_HOOK_OFF = 0x66DE4

SOUND_PLAYER_AFTER_SIREN_ON_ADDR = 0x800765DC
SOUND_PLAYER_AFTER_UPDATE_SIREN_ADDR = 0x800765F8
SIREN_ON_ADDR = 0x8007A280
UPDATE_SIREN_ADDR = 0x8007A3E4

EXPECTED_SIREN_ON_BYTES = bytes.fromhex(
    "60 02 45 8e"  # lw a1,0x260(s2)
    "a0 e8 01 0c"  # jal SirenOn
)

EXPECTED_UPDATE_SIREN_BYTES = bytes.fromhex(
    "60 02 42 8e"  # lw v0,0x260(s2)
    "20 00 a6 8f"  # lw a2,0x20(sp)
    "40 00 42 30"  # andi v0,v0,0x40
    "f9 e8 01 0c"  # jal UpdateSiren
    "10 00 a2 af"  # sw v0,0x10(sp)
)
EXPECTED_UPDATE_SIREN_VOLUME_BYTES = bytes.fromhex(
    "11 80 03 3c"  # lui v1,0x8011
    "c0 fb 63 24"  # addiu v1,v1,-0x440
)
PATCHED_UPDATE_SIREN_VOLUME_HOOK_BYTES = bytes.fromhex("a0 54 01 08 00 00 00 00")
STOCK_SUPERCOP_START_VOLUME_BYTES = bytes.fromhex("40 00 06 24")
PATCHED_SUPERCOP_START_VOLUME_BYTES = bytes.fromhex("7f 00 06 24")

WRONG_PATCHED_SIREN_ON_HOOK_BYTES = bytes.fromhex("80 d6 01 08 00 00 00 00")
WRONG_PATCHED_UPDATE_SIREN_HOOK_BYTES = bytes.fromhex("94 d6 01 08 00 00 00 00")
OLD_PATCHED_QUICK_SIREN_SAMPLE_BYTES = bytes.fromhex("a8 54 01 08 00 00 00 00")
EXPECTED_QUICK_SIREN_SAMPLE_BYTES = bytes.fromhex(
    "11 80 03 3c"  # lui v1,0x8011
    "b4 fa 63 24"  # addiu v1,v1,-0x54c
)
WRONG_PATCHED_QUICK_SIREN_SAMPLE_BYTES = bytes.fromhex("a8 d6 01 08 00 00 00 00")

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "a1": 5,
    "a2": 6,
    "a3": 7,
    "t0": 8,
    "s1": 17,
    "s2": 18,
    "sp": 29,
}


def runtime(off: int) -> int:
    return RUNTIME_BASE + off


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


def ins_r(rs: int, rt: int, rd: int, sh: int, fn: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (sh << 6) | fn


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def andi(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0C, REG[rs], REG[rt], imm)


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


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def sra(rd: str, rt: str, sh: int) -> int:
    return ins_r(0, REG[rt], REG[rd], sh, 0x03)


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
            if kind not in ("beq", "bne"):
                raise ValueError(kind)
            op = 0x04 if kind == "beq" else 0x05
            item = ins_i(op, REG[rs], REG[rt], (labels[target] - (pc + 4)) >> 2)
        words.append(item)
        pc += 4
    return pack(words)


def siren_on_cave() -> bytes:
    items: list[int | str] = [
        lw("a1", 0x0260, "s2"),
        addiu("a1", "zero", 0),  # Cheat patches this immediate to 1.
        jal(SIREN_ON_ADDR),
        nop(),
        j(SOUND_PLAYER_AFTER_SIREN_ON_ADDR),
        nop(),
    ]
    return pack_labeled(items, runtime(SIREN_ON_CAVE_OFF))


def update_siren_cave() -> bytes:
    items: list[int | str] = [
        lw("v0", 0x0260, "s2"),
        lw("a2", 0x20, "sp"),
        addiu("v0", "zero", 0),  # Cheat patches this immediate to 1.
        jal(UPDATE_SIREN_ADDR),
        sw("v0", 0x10, "sp"),
        j(SOUND_PLAYER_AFTER_UPDATE_SIREN_ADDR),
        nop(),
    ]
    return pack_labeled(items, runtime(UPDATE_SIREN_CAVE_OFF))


def build_cave() -> bytes:
    blob = bytearray(b"\x00" * CAVE_LEN)
    on = siren_on_cave()
    upd = update_siren_cave()
    blob[0 : len(on)] = on
    rel = UPDATE_SIREN_CAVE_OFF - CAVE_OFF
    blob[rel : rel + len(upd)] = upd
    return bytes(blob)


def hook_bytes(addr: int) -> bytes:
    return pack([j(addr), nop()])


def patched_siren_on_hook_bytes() -> bytes:
    return hook_bytes(runtime(SIREN_ON_CAVE_OFF))


def patched_update_siren_hook_bytes() -> bytes:
    return hook_bytes(runtime(UPDATE_SIREN_CAVE_OFF))


def patch(exe: Path) -> None:
    data = bytearray(exe.read_bytes())

    on_now = bytes(data[SOUND_PLAYER_SIREN_ON_HOOK_OFF : SOUND_PLAYER_SIREN_ON_HOOK_OFF + 8])
    if on_now not in (
        EXPECTED_SIREN_ON_BYTES,
        patched_siren_on_hook_bytes(),
        WRONG_PATCHED_SIREN_ON_HOOK_BYTES,
    ):
        raise SystemExit(
            f"unexpected SirenOn hook bytes at 0x{SOUND_PLAYER_SIREN_ON_HOOK_OFF:X}: {on_now.hex(' ')}"
        )

    upd_now = bytes(data[SOUND_PLAYER_UPDATE_SIREN_HOOK_OFF : SOUND_PLAYER_UPDATE_SIREN_HOOK_OFF + 20])
    if upd_now not in (
        EXPECTED_UPDATE_SIREN_BYTES,
        patched_update_siren_hook_bytes() + EXPECTED_UPDATE_SIREN_BYTES[8:],
        WRONG_PATCHED_UPDATE_SIREN_HOOK_BYTES + EXPECTED_UPDATE_SIREN_BYTES[8:],
    ):
        raise SystemExit(
            f"unexpected UpdateSiren hook bytes at 0x{SOUND_PLAYER_UPDATE_SIREN_HOOK_OFF:X}: {upd_now.hex(' ')}"
        )

    quick_now = bytes(data[0x6A9C4 : 0x6A9C4 + 8])
    if quick_now not in (
        EXPECTED_QUICK_SIREN_SAMPLE_BYTES,
        OLD_PATCHED_QUICK_SIREN_SAMPLE_BYTES,
        WRONG_PATCHED_QUICK_SIREN_SAMPLE_BYTES,
    ):
        raise SystemExit(
            f"unexpected quickSirenOn hook bytes at 0x6A9C4: {quick_now.hex(' ')}"
        )

    vol_now = bytes(data[0x6ACC4 : 0x6ACC4 + 8])
    if vol_now not in (EXPECTED_UPDATE_SIREN_VOLUME_BYTES, PATCHED_UPDATE_SIREN_VOLUME_HOOK_BYTES):
        raise SystemExit(
            f"unexpected UpdateSiren volume hook bytes at 0x6ACC4: {vol_now.hex(' ')}"
        )

    super_vol_now = bytes(data[0x6AA40 : 0x6AA40 + 4])
    if super_vol_now not in (STOCK_SUPERCOP_START_VOLUME_BYTES, PATCHED_SUPERCOP_START_VOLUME_BYTES):
        raise SystemExit(
            f"unexpected SuperCopSirenOn volume bytes at 0x6AA40: {super_vol_now.hex(' ')}"
        )

    backup = exe.with_name(exe.name + BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_bytes(data)

    data[CAVE_OFF : CAVE_OFF + 0x100] = b"\x00" * 0x100
    data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = build_cave()
    data[SOUND_PLAYER_SIREN_ON_HOOK_OFF : SOUND_PLAYER_SIREN_ON_HOOK_OFF + 8] = patched_siren_on_hook_bytes()
    data[SOUND_PLAYER_UPDATE_SIREN_HOOK_OFF : SOUND_PLAYER_UPDATE_SIREN_HOOK_OFF + 8] = patched_update_siren_hook_bytes()
    data[0x6ACC4 : 0x6ACC4 + 8] = EXPECTED_UPDATE_SIREN_VOLUME_BYTES
    data[0x6AA40 : 0x6AA40 + 4] = STOCK_SUPERCOP_START_VOLUME_BYTES
    data[0x6A9C4 : 0x6A9C4 + 8] = EXPECTED_QUICK_SIREN_SAMPLE_BYTES

    exe.write_bytes(data)
    print(f"patched: {exe}")
    print(f"md5: {hashlib.md5(data).hexdigest()}")
    print("cheat off:")
    print("80055204 0000")
    print("80055258 0000")
    print("cheat on:")
    print("80055204 0001")
    print("80055258 0001")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=None)
    args = parser.parse_args()
    exe = args.exe or next(Path.cwd().glob(DEFAULT_EXE_GLOB))
    patch(exe)


if __name__ == "__main__":
    main()
