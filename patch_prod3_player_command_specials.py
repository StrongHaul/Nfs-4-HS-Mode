#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_command_specials"
RUNTIME_BASE = 0x8000F800

# The civilian player command that normally feeds turn-signal state is mirrored
# in car+0x446. For player civilian special signals, use that byte as the
# on/off state for custom blinking lights and siren audio.
COMMAND_BYTE_OFF = 0x446
PLAYER_CAR_PTR_ADDR = 0x80110D0C

STROBE_GATE_OFF = 0x45948
OBJECT_GATE_OFF = 0x4597C
DRAW_GATE_OFF = 0x459B0
GATE_LEN = 0x34

STROBE_COUNTER_LOAD_RETURN_ADDR = 0x8005501C
STROBE_SKIP_ADDR = 0x800550F4
OBJECT_COUNTER_LOAD_RETURN_ADDR = 0x800F7B84
OBJECT_STOCK_ADDR = 0x800F7BD4
DRAW_COUNTER_LOAD_RETURN_ADDR = 0x800F7874
DRAW_STOCK_ADDR = 0x800F78AC

SIREN_TYPE_HOOK_OFF = 0x066D54
SIREN_BIT_HOOK_OFF = 0x066D68
SIREN_TYPE_CAVE_OFF = 0x45444
SIREN_BIT_CAVE_OFF = 0x45484

SIREN_TYPE_ALLOW_ADDR = 0x8007655C
SIREN_TYPE_SKIP_ADDR = 0x8007663C
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


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def lbu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x24, REG[rs], REG[rt], off)


def slti(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0A, REG[rs], REG[rt], imm)


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


def make_light_gate(*, car_reg: str, disabled_addr: int, return_addr: int) -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        lbu("t1", COMMAND_BYTE_OFF, car_reg),
        beq("t1", "zero", "disabled"),
        nop(),
        lui("t0", 0x8005),
        lw("t1", 0x50FC, "t0"),
        j(return_addr),
        nop(),
        "disabled",
        j(disabled_addr),
        nop(),
    ]
    return padded(pack_labeled(items, 0), GATE_LEN)


def make_siren_type_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        bne("v0", "zero", "allow"),
        nop(),
        lui("t0", (PLAYER_CAR_PTR_ADDR >> 16) & 0xFFFF),
        lw("t0", PLAYER_CAR_PTR_ADDR & 0xFFFF, "t0"),
        bne("s2", "t0", "skip"),
        nop(),
        lbu("t0", COMMAND_BYTE_OFF, "s2"),
        beq("t0", "zero", "skip"),
        nop(),
        "allow",
        j(SIREN_TYPE_ALLOW_ADDR),
        nop(),
        "skip",
        j(SIREN_TYPE_SKIP_ADDR),
        nop(),
    ]
    return pack_labeled(items, runtime(SIREN_TYPE_CAVE_OFF))


def make_siren_bit_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        bne("v0", "zero", "allow"),
        nop(),
        lui("t0", (PLAYER_CAR_PTR_ADDR >> 16) & 0xFFFF),
        lw("t0", PLAYER_CAR_PTR_ADDR & 0xFFFF, "t0"),
        bne("s2", "t0", "skip"),
        nop(),
        lbu("t0", COMMAND_BYTE_OFF, "s2"),
        beq("t0", "zero", "skip"),
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
    return pack_labeled(items, runtime(SIREN_BIT_CAVE_OFF))


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

    strobe_old = bytes(data[STROBE_GATE_OFF : STROBE_GATE_OFF + GATE_LEN])
    object_old = bytes(data[OBJECT_GATE_OFF : OBJECT_GATE_OFF + GATE_LEN])
    draw_old = bytes(data[DRAW_GATE_OFF : DRAW_GATE_OFF + GATE_LEN])

    strobe_gate = make_light_gate(
        car_reg="s5",
        disabled_addr=STROBE_SKIP_ADDR,
        return_addr=STROBE_COUNTER_LOAD_RETURN_ADDR,
    )
    object_gate = make_light_gate(
        car_reg="s5",
        disabled_addr=OBJECT_STOCK_ADDR,
        return_addr=OBJECT_COUNTER_LOAD_RETURN_ADDR,
    )
    draw_gate = make_light_gate(
        car_reg="s2",
        disabled_addr=DRAW_STOCK_ADDR,
        return_addr=DRAW_COUNTER_LOAD_RETURN_ADDR,
    )

    known_light_gate_prefixes = {
        bytes.fromhex("00 00 09 24"),
        bytes.fromhex("49 04 a9 92"),
        bytes.fromhex("49 04 49 92"),
    }
    for name, old in (("strobe", strobe_old), ("object", object_old), ("draw", draw_old)):
        if old[:4] not in known_light_gate_prefixes:
            raise SystemExit(f"unexpected {name} light gate bytes: {old[:16].hex(' ')}")

    type_hook = bytes(data[SIREN_TYPE_HOOK_OFF : SIREN_TYPE_HOOK_OFF + 8])
    bit_hook = bytes(data[SIREN_BIT_HOOK_OFF : SIREN_BIT_HOOK_OFF + 8])
    type_patch = hook_bytes(SIREN_TYPE_CAVE_OFF)
    bit_patch = hook_bytes(SIREN_BIT_CAVE_OFF)
    if type_hook not in (EXPECTED_SIREN_TYPE_HOOK, type_patch):
        raise SystemExit(f"unexpected siren type hook bytes: {type_hook.hex(' ')}")
    if bit_hook not in (EXPECTED_SIREN_BIT_HOOK, bit_patch):
        raise SystemExit(f"unexpected siren bit hook bytes: {bit_hook.hex(' ')}")

    type_cave = make_siren_type_cave()
    bit_cave = make_siren_bit_cave()
    cave_start = SIREN_TYPE_CAVE_OFF
    cave_end = SIREN_BIT_CAVE_OFF + len(bit_cave)
    cave_now = bytes(data[cave_start:cave_end])
    expected_installed = bytearray(cave_end - cave_start)
    expected_installed[0 : len(type_cave)] = type_cave
    bit_rel = SIREN_BIT_CAVE_OFF - cave_start
    expected_installed[bit_rel : bit_rel + len(bit_cave)] = bit_cave
    if cave_now not in (bytes(cave_end - cave_start), bytes(expected_installed)):
        raise SystemExit(f"unexpected command special cave bytes: {cave_now[:16].hex(' ')}")

    if revert:
        # Revert only the command-control layer. The previous code-immediate
        # light gates are restored as default-off.
        from patch_prod3_player_civilian_blink_cheat_gate import make_gate
        from patch_prod3_player_civilian_blink_cheat_gate import padded as pad_gate

        data[STROBE_GATE_OFF : STROBE_GATE_OFF + GATE_LEN] = pad_gate(
            make_gate(runtime(STROBE_GATE_OFF), disabled_addr=STROBE_SKIP_ADDR, return_addr=STROBE_COUNTER_LOAD_RETURN_ADDR),
            GATE_LEN,
        )
        data[OBJECT_GATE_OFF : OBJECT_GATE_OFF + GATE_LEN] = pad_gate(
            make_gate(runtime(OBJECT_GATE_OFF), disabled_addr=OBJECT_STOCK_ADDR, return_addr=OBJECT_COUNTER_LOAD_RETURN_ADDR),
            GATE_LEN,
        )
        data[DRAW_GATE_OFF : DRAW_GATE_OFF + GATE_LEN] = pad_gate(
            make_gate(runtime(DRAW_GATE_OFF), disabled_addr=DRAW_STOCK_ADDR, return_addr=DRAW_COUNTER_LOAD_RETURN_ADDR),
            GATE_LEN,
        )
        data[SIREN_TYPE_HOOK_OFF : SIREN_TYPE_HOOK_OFF + 8] = EXPECTED_SIREN_TYPE_HOOK
        data[SIREN_BIT_HOOK_OFF : SIREN_BIT_HOOK_OFF + 8] = EXPECTED_SIREN_BIT_HOOK
        data[cave_start:cave_end] = bytes(cave_end - cave_start)
    else:
        data[STROBE_GATE_OFF : STROBE_GATE_OFF + GATE_LEN] = strobe_gate
        data[OBJECT_GATE_OFF : OBJECT_GATE_OFF + GATE_LEN] = object_gate
        data[DRAW_GATE_OFF : DRAW_GATE_OFF + GATE_LEN] = draw_gate
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
    print("player civilian command specials:", "reverted" if revert else "patched")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: make the civilian player light/siren command control custom specials."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()
    patch(find_exe(), revert=args.revert)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
