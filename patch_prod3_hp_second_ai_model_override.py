#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_hp_second_ai_model_override"
RUNTIME_BASE = 0x8000F800

# Reuses the stable "second AI shares first carData" hook:
#   stock delay slot computes v0 = setupBase + slot * 0xB4
#   cave can replace v0 before storing Car_tObj+0x288.
HOOK_OFF = 0x7B8DC
RETURN_ADDR = 0x8008B0E4
STOCK = bytes.fromhex(
    "21 10 42 02"  # addu v0,s2,v0
    "88 02 02 ae"  # sw v0,0x288(s0)
)

CAVE_OFF = 0xE8024
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x80

SECOND_AI_SLOT = 2
FIRST_AI_CARDATA_OFF_FROM_SETUP_BASE = 0x488  # 0x3D4 + 1 * 0xB4

# Padding in both FRONT.BIN and NFS4.EXE in the current stable PROD3 layout.
# 0000 = default behavior, second AI shares first AI car.
# 00?? = force second AI car id.
SECOND_AI_MODEL_CHEAT_ADDR = 0x80054800


REG = {
    "zero": 0,
    "v0": 2,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "s0": 16,
    "s1": 17,
    "s2": 18,
    "s3": 19,
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


def addu(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x21)


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


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
            kind, rs, rt, target = item
            op = 0x04 if kind == "beq" else 0x05
            item = ins_i(op, REG[rs], REG[rt], (labels[target] - (pc + 4)) >> 2)
        words.append(item)
        pc += 4
    return pack(words)


def make_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Delay slot already computed stock v0. Only slot 2 is special.
        addiu("t0", "zero", SECOND_AI_SLOT),
        bne("s1", "t0", "store"),
        nop(),
        lui("t1", hi(SECOND_AI_MODEL_CHEAT_ADDR)),
        lhu("t2", lo(SECOND_AI_MODEL_CHEAT_ADDR), "t1"),
        beq("t2", "zero", "share_first"),
        nop(),
        # Use slot 2's own carData, but override car id before resources load.
        sw("t2", 0x0000, "v0"),
        beq("zero", "zero", "store"),
        nop(),
        "share_first",
        addiu("v0", "s3", FIRST_AI_CARDATA_OFF_FROM_SETUP_BASE),
        "store",
        sw("v0", 0x0288, "s0"),
        j(RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, CAVE_ADDR)
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob + bytes(CAVE_LEN - len(blob))


def apply(path: Path) -> None:
    data = bytearray(path.read_bytes())
    hook = pack([j(CAVE_ADDR), addu("v0", "s2", "v0")])
    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + len(STOCK)])
    if current_hook not in {STOCK, hook}:
        raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")

    cave = make_cave()
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_bytes(data)

    data[HOOK_OFF : HOOK_OFF + len(STOCK)] = hook
    data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = cave
    path.write_bytes(data)


def revert(path: Path) -> None:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if backup.exists():
        path.write_bytes(backup.read_bytes())
        return
    raise SystemExit(f"backup not found: {backup}")


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
    print("second AI model override: 80054800 00??, 0000 = same as first AI")
    print(f"md5 {md5(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
