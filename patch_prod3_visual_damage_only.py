#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_visual_damage_only"

# Keep Newton_AddDamageZone untouched so render damage, smoke, lights, stats, and
# repair bills can still see the accumulated damage array. These patches only
# neutralize places where the damage array weakens car behavior.

AISPEEDS_DAMAGE_FACTOR_OFF = 0x05F898
AISPEEDS_DAMAGE_FACTOR_LEN = 0x10

AIPHYSIC_REAR_DAMAGE_FACTOR_OFF = 0x05CA70
AIPHYSIC_REAR_DAMAGE_FACTOR_LEN = 0x0C

PHYSICS_DAMAGE_READ_PATCHES = {
    # Physics_CalculateCarAcceleration: engine sputter chance from damage[1]+damage[5].
    0x09BF10: ("a0", "8e24021c", "lw a0,0x021C(s1)"),
    0x09BF14: ("v1", "8e23022c", "lw v1,0x022C(s1)"),
    # Physics main handling: front damage reduces steering.
    0x09DA54: ("v0", "8ea20218", "lw v0,0x0218(s5)"),
    0x09DA58: ("v1", "8ea3021c", "lw v1,0x021C(s5)"),
    0x09DA64: ("v1", "8ea30220", "lw v1,0x0220(s5)"),
    0x09DA68: ("a0", "8ea4023c", "lw a0,0x023C(s5)"),
    # Brake/center damage reduces braking.
    0x09DC84: ("v1", "8ea3023c", "lw v1,0x023C(s5)"),
    # Rear damage changes rear grip/weight transfer.
    0x09DD8C: ("v0", "8ea20228", "lw v0,0x0228(s5)"),
    0x09DD90: ("v1", "8ea3022c", "lw v1,0x022C(s5)"),
    0x09DD9C: ("v1", "8ea30230", "lw v1,0x0230(s5)"),
    0x09DDA0: ("a0", "8ea4023c", "lw a0,0x023C(s5)"),
}

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "a0": 4,
    "ra": 31,
}


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_r(rs: int, rt: int, rd: int, sh: int, fn: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (sh << 6) | fn


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def addu(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x21)


def jr(rs: str) -> int:
    return ins_r(REG[rs], 0, 0, 0, 0x08)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def nop() -> int:
    return 0


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: keep car damage visual-only by neutralizing damage physics factors."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    aispeeds_stock = bytes.fromhex("e8 ff bd 27 10 00 b0 af 21 80 80 00 14 00 bf af")
    aispeeds_patch = pack(
        [
            lui("v0", 0x0001),      # no-damage factor = 0x10000
            sw("v0", 0x0778, "a0"), # keep carObj->damageMult consistent
            jr("ra"),
            nop(),
        ]
    )

    rear_factor_stock = bytes.fromhex("e8 ff bd 27 10 00 bf af 28 02 83 8c")
    rear_factor_patch = pack(
        [
            addu("v0", "zero", "zero"), # no rear damage factor = 0
            jr("ra"),
            nop(),
        ]
    )

    current = bytes(data[AISPEEDS_DAMAGE_FACTOR_OFF : AISPEEDS_DAMAGE_FACTOR_OFF + AISPEEDS_DAMAGE_FACTOR_LEN])
    if current not in {aispeeds_stock, aispeeds_patch}:
        raise SystemExit(
            f"unexpected AISpeeds damage factor bytes: {current.hex(' ')}"
        )

    current = bytes(data[AIPHYSIC_REAR_DAMAGE_FACTOR_OFF : AIPHYSIC_REAR_DAMAGE_FACTOR_OFF + AIPHYSIC_REAR_DAMAGE_FACTOR_LEN])
    if current not in {rear_factor_stock, rear_factor_patch}:
        raise SystemExit(
            f"unexpected AIPhysic rear damage factor bytes: {current.hex(' ')}"
        )

    zero_reg_patches = {
        off: pack([addu(reg, "zero", "zero")])
        for off, (reg, _, _) in PHYSICS_DAMAGE_READ_PATCHES.items()
    }
    stock_read_patches = {
        off: bytes.fromhex(stock_hex)
        for off, (_, stock_hex, _) in PHYSICS_DAMAGE_READ_PATCHES.items()
    }
    for off, (_, _, label) in PHYSICS_DAMAGE_READ_PATCHES.items():
        current = bytes(data[off : off + 4])
        stock = stock_read_patches[off]
        patched = zero_reg_patches[off]
        if current not in {stock, patched}:
            raise SystemExit(f"unexpected bytes at 0x{off:X} for {label}: {current.hex(' ')}")

    if args.revert:
        data[AISPEEDS_DAMAGE_FACTOR_OFF : AISPEEDS_DAMAGE_FACTOR_OFF + AISPEEDS_DAMAGE_FACTOR_LEN] = aispeeds_stock
        data[AIPHYSIC_REAR_DAMAGE_FACTOR_OFF : AIPHYSIC_REAR_DAMAGE_FACTOR_OFF + AIPHYSIC_REAR_DAMAGE_FACTOR_LEN] = rear_factor_stock
        for off, stock in stock_read_patches.items():
            data[off : off + 4] = stock
    else:
        data[AISPEEDS_DAMAGE_FACTOR_OFF : AISPEEDS_DAMAGE_FACTOR_OFF + AISPEEDS_DAMAGE_FACTOR_LEN] = aispeeds_patch
        data[AIPHYSIC_REAR_DAMAGE_FACTOR_OFF : AIPHYSIC_REAR_DAMAGE_FACTOR_OFF + AIPHYSIC_REAR_DAMAGE_FACTOR_LEN] = rear_factor_patch
        for off, patched in zero_reg_patches.items():
            data[off : off + 4] = patched

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(bytes(data))}")
    print("visual damage only:", "reverted" if args.revert else "patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
