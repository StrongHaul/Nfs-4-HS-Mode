#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
RUNTIME_BASE = 0x8000F800

HOOK_OFF = 0x09B1A0
HOOK_ADDR = RUNTIME_BASE + HOOK_OFF
HOOK_STOCK = bytes.fromhex("e0 ff bd 27 14 00 b1 af")

CAVE_OFF = 0x108B00
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
FLAG_ADDR = CAVE_ADDR + 4
RETURN_ADDR = HOOK_ADDR + 8
STATE_OFF = CAVE_OFF + 0x6F00
STATE_ADDR = RUNTIME_BASE + STATE_OFF

# Default-off implementation. The EXE contains only a tiny switchable RAM
# patcher. With FLAG_ADDR immediate == 0 it restores stock code; with 1 it
# disables only the physics/AI damage penalties. Newton_AddDamageZone is not
# touched, so visual damage remains available.
PATCH_BLOCKS = [
    (
        0x05F898,
        "AISpeeds damage factor",
        bytes.fromhex("e8 ff bd 27 10 00 b0 af 21 80 80 00 14 00 bf af"),
        bytes.fromhex("01 00 02 3c 78 07 82 ac 08 00 e0 03 00 00 00 00"),
    ),
    (
        0x05CA70,
        "AIPhysic rear damage factor",
        bytes.fromhex("e8 ff bd 27 10 00 bf af 28 02 83 8c"),
        bytes.fromhex("21 10 00 00 08 00 e0 03 00 00 00 00"),
    ),
    (0x09BF10, "engine sputter damage[1]", bytes.fromhex("1c 02 24 8e"), bytes.fromhex("21 20 00 00")),
    (0x09BF14, "engine sputter damage[5]", bytes.fromhex("2c 02 23 8e"), bytes.fromhex("21 18 00 00")),
    (0x09DA54, "front steering damage[0]", bytes.fromhex("18 02 a2 8e"), bytes.fromhex("21 10 00 00")),
    (0x09DA58, "front steering damage[1]", bytes.fromhex("1c 02 a3 8e"), bytes.fromhex("21 18 00 00")),
    (0x09DA64, "front steering damage[2]", bytes.fromhex("20 02 a3 8e"), bytes.fromhex("21 18 00 00")),
    (0x09DA68, "front steering damage[9]", bytes.fromhex("3c 02 a4 8e"), bytes.fromhex("21 20 00 00")),
    (0x09DC84, "brake damage[9]", bytes.fromhex("3c 02 a3 8e"), bytes.fromhex("21 18 00 00")),
    (0x09DD8C, "rear grip damage[4]", bytes.fromhex("28 02 a2 8e"), bytes.fromhex("21 10 00 00")),
    (0x09DD90, "rear grip damage[5]", bytes.fromhex("2c 02 a3 8e"), bytes.fromhex("21 18 00 00")),
    (0x09DD9C, "rear grip damage[6]", bytes.fromhex("30 02 a3 8e"), bytes.fromhex("21 18 00 00")),
    (0x09DDA0, "rear grip damage[9]", bytes.fromhex("3c 02 a4 8e"), bytes.fromhex("21 20 00 00")),
]


REG = {
    "zero": 0,
    "sp": 29,
    "s1": 17,
    "t0": 8,
    "t1": 9,
}


def itype(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def jtype(op: int, target: int) -> int:
    return (op << 26) | ((target >> 2) & 0x03FFFFFF)


def nop() -> int:
    return 0


def lui(rt: int, imm: int) -> int:
    return itype(0x0F, 0, rt, imm)


def ori(rt: int, rs: int, imm: int) -> int:
    return itype(0x0D, rs, rt, imm)


def addiu(rt: int, rs: int, imm: int) -> int:
    return itype(0x09, rs, rt, imm)


def sw(rt: int, imm: int, rs: int) -> int:
    return itype(0x2B, rs, rt, imm)


def lhu(rt: int, imm: int, rs: int) -> int:
    return itype(0x25, rs, rt, imm)


def sh(rt: int, imm: int, rs: int) -> int:
    return itype(0x29, rs, rt, imm)


def beq(rs: int, rt: int, offset_words: int) -> int:
    return itype(0x04, rs, rt, offset_words)


def bne(rs: int, rt: int, offset_words: int) -> int:
    return itype(0x05, rs, rt, offset_words)


def jump(target: int) -> int:
    return jtype(0x02, target)


def load_imm(rt: int, value: int) -> list[int]:
    upper = (value >> 16) & 0xFFFF
    lower = value & 0xFFFF
    if upper == 0:
        return [ori(rt, REG["zero"], lower)]
    return [lui(rt, upper), ori(rt, rt, lower)]


def load_addr(rt: int, addr: int) -> list[int]:
    return [lui(rt, (addr >> 16) & 0xFFFF), ori(rt, rt, addr & 0xFFFF)]


def write_word(addr: int, value: int) -> list[int]:
    return [
        *load_addr(REG["t0"], addr),
        *load_imm(REG["t1"], value),
        sw(REG["t1"], 0, REG["t0"]),
    ]


def block_words(*, patched: bool) -> list[tuple[int, int]]:
    words: list[tuple[int, int]] = []
    for off, _, stock, patch in PATCH_BLOCKS:
        blob = patch if patched else stock
        if len(blob) % 4:
            raise ValueError("patch blocks must be word-aligned")
        for i in range(0, len(blob), 4):
            words.append((RUNTIME_BASE + off + i, struct.unpack_from("<I", blob, i)[0]))
    return words


def build_patcher_cave() -> bytes:
    code: list[int] = []
    code.append(sw(REG["s1"], 0x14, REG["sp"]))  # original hook instruction
    flag_index = len(code)
    code.append(addiu(REG["t1"], REG["zero"], 0))
    code.extend(load_addr(REG["t0"], STATE_ADDR))
    code.append(lhu(REG["t0"], 0, REG["t0"]))
    same_state_branch_index = len(code)
    code.append(0)
    code.append(nop())
    code.extend(load_addr(REG["t0"], STATE_ADDR))
    code.append(sh(REG["t1"], 0, REG["t0"]))
    branch_index = len(code)
    code.append(0)
    code.append(nop())

    for addr, value in block_words(patched=False):
        code.extend(write_word(addr, value))
    return_index = len(code)
    code.extend([jump(RETURN_ADDR), nop()])

    on_index = len(code)
    for addr, value in block_words(patched=True):
        code.extend(write_word(addr, value))
    code.extend([jump(RETURN_ADDR), nop()])

    branch_pc = CAVE_ADDR + branch_index * 4
    on_addr = CAVE_ADDR + on_index * 4
    code[branch_index] = bne(REG["t1"], REG["zero"], (on_addr - (branch_pc + 4)) // 4)
    same_state_branch_pc = CAVE_ADDR + same_state_branch_index * 4
    return_addr = CAVE_ADDR + return_index * 4
    code[same_state_branch_index] = beq(
        REG["t0"],
        REG["t1"],
        (return_addr - (same_state_branch_pc + 4)) // 4,
    )

    assert CAVE_ADDR + flag_index * 4 == FLAG_ADDR
    return b"".join(struct.pack("<I", word) for word in code)


def build_hook() -> bytes:
    return struct.pack("<II", jump(CAVE_ADDR), addiu(REG["sp"], REG["sp"], -32))


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest().upper()


def verify_patch_targets(data: bytes) -> None:
    for off, name, stock, patch in PATCH_BLOCKS:
        current = bytes(data[off : off + len(stock)])
        if current in (stock, patch):
            continue
        raise SystemExit(f"unexpected bytes for {name} at 0x{off:X}: {current.hex(' ')}")


def apply_patch(exe: Path, *, revert: bool = False) -> None:
    data = bytearray(exe.read_bytes())
    cave = build_patcher_cave()
    if len(cave) > 0x6F00:
        raise SystemExit(f"cave is unexpectedly large: 0x{len(cave):X}")

    verify_patch_targets(data)
    if revert:
        if data[HOOK_OFF : HOOK_OFF + 8] != build_hook():
            raise SystemExit("visual damage toggle hook is not installed")
        data[HOOK_OFF : HOOK_OFF + 8] = HOOK_STOCK
        data[CAVE_OFF : CAVE_OFF + len(cave)] = b"\x00" * len(cave)
        data[STATE_OFF : STATE_OFF + 4] = b"\x00" * 4
    else:
        current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
        if current_hook not in (HOOK_STOCK, build_hook()):
            raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")
        data[HOOK_OFF : HOOK_OFF + 8] = build_hook()
        data[CAVE_OFF : CAVE_OFF + len(cave)] = cave
        data[STATE_OFF : STATE_OFF + 4] = b"\x00" * 4

    exe.write_bytes(data)
    print(f"NFS4.EXE {md5(data)}")
    print("visual damage only toggle is", "removed" if revert else "installed")
    if not revert:
        print(f"cheat flag: {FLAG_ADDR:08X} 000?")


def print_cheat_section() -> None:
    print("[Мои\\Damage только визуальный]")
    print("Type = Gameshark")
    print("Activation = EndFrame")
    print("Option = Выкл:0")
    print("Option = Вкл:1")
    print(f"{FLAG_ADDR:08X} 000?")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: install a 0/1 Gameshark toggle for visual-only car damage."
    )
    parser.add_argument("--revert", action="store_true")
    parser.add_argument("--cheat-section", action="store_true")
    args = parser.parse_args()

    if args.cheat_section:
        print_cheat_section()
        return 0

    exe = find_exe()
    apply_patch(exe, revert=args.revert)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
