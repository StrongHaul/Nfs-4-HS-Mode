#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_civilian_blink_cheat_gate"
RUNTIME_BASE = 0x8000F800

# The gate is controlled by three code-immediate halfwords. Default file value
# is zero, so the civilian blink feature is off. DuckStation changes only the
# low 16-bit immediate in each addiu instruction:
#   80055148 000?
#   8005517C 000?
#   800551B0 000?
LEGACY_BLINK_CHEAT_ADDRS = [0x80054B78, 0x800551F8]

# Existing working player civilian strobe/blink cave.
STROBE_HOOK_OFF = 0x45814
STROBE_HOOK_ADDR = RUNTIME_BASE + STROBE_HOOK_OFF
STROBE_GATE_OFF = 0x45948
STROBE_GATE_ADDR = RUNTIME_BASE + STROBE_GATE_OFF
STROBE_GATE_LEN = 0x34
STROBE_COUNTER_LOAD_RETURN_ADDR = 0x8005501C
STROBE_SKIP_ADDR = 0x800550F4

# Existing reverse-light object cave.
OBJECT_HOOK_OFF = 0xE837C
OBJECT_HOOK_ADDR = RUNTIME_BASE + OBJECT_HOOK_OFF
OBJECT_GATE_OFF = 0x4597C
OBJECT_GATE_ADDR = RUNTIME_BASE + OBJECT_GATE_OFF
OBJECT_GATE_LEN = 0x34
OBJECT_COUNTER_LOAD_RETURN_ADDR = 0x800F7B84
OBJECT_STOCK_ADDR = 0x800F7BD4

# Existing reverse-light DrawC mask cave.
DRAW_HOOK_OFF = 0xE806C
DRAW_HOOK_ADDR = RUNTIME_BASE + DRAW_HOOK_OFF
DRAW_GATE_OFF = 0x459B0
DRAW_GATE_ADDR = RUNTIME_BASE + DRAW_GATE_OFF
DRAW_GATE_LEN = 0x34
DRAW_COUNTER_LOAD_RETURN_ADDR = 0x800F7874
DRAW_STOCK_ADDR = 0x800F78AC

REG = {
    "zero": 0,
    "t0": 8,
    "t1": 9,
}


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


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


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


def make_gate(base_addr: int, *, disabled_addr: int, return_addr: int) -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        addiu("t1", "zero", 0),
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
    blob = pack_labeled(items, base_addr)
    if len(blob) > STROBE_GATE_LEN:
        raise SystemExit(f"gate too large: 0x{len(blob):X}")
    return blob


def make_legacy_gate(base_addr: int, *, disabled_addr: int, return_addr: int, cheat_addr: int) -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        lui("t0", hi(cheat_addr)),
        lhu("t1", lo(cheat_addr), "t0"),
        addiu("t1", "t1", -1),
        bne("t1", "zero", "disabled"),
        nop(),
        lui("t0", 0x8005),
        lw("t1", 0x50FC, "t0"),
        j(return_addr),
        nop(),
        "disabled",
        j(disabled_addr),
        nop(),
    ]
    blob = pack_labeled(items, base_addr)
    if len(blob) > STROBE_GATE_LEN:
        raise SystemExit(f"legacy gate too large: 0x{len(blob):X}")
    return blob


def padded(blob: bytes, size: int) -> bytes:
    if len(blob) > size:
        raise SystemExit(f"blob too large: 0x{len(blob):X} > 0x{size:X}")
    return blob + bytes(size - len(blob))


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: gate ordinary-player blinking light feature behind code-immediate cheat."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    strobe_stock = pack([lui("t0", 0x8005), lw("t1", 0x50FC, "t0")])
    object_stock = pack([lui("t0", 0x8005), lw("t1", 0x50FC, "t0")])
    draw_stock = pack([lui("t0", 0x8005), lw("t1", 0x50FC, "t0")])

    strobe_patch = pack([j(STROBE_GATE_ADDR), nop()])
    object_patch = pack([j(OBJECT_GATE_ADDR), nop()])
    draw_patch = pack([j(DRAW_GATE_ADDR), nop()])

    strobe_gate = padded(
        make_gate(
            STROBE_GATE_ADDR,
            disabled_addr=STROBE_SKIP_ADDR,
            return_addr=STROBE_COUNTER_LOAD_RETURN_ADDR,
        ),
        STROBE_GATE_LEN,
    )
    object_gate = padded(
        make_gate(
            OBJECT_GATE_ADDR,
            disabled_addr=OBJECT_STOCK_ADDR,
            return_addr=OBJECT_COUNTER_LOAD_RETURN_ADDR,
        ),
        OBJECT_GATE_LEN,
    )
    draw_gate = padded(
        make_gate(
            DRAW_GATE_ADDR,
            disabled_addr=DRAW_STOCK_ADDR,
            return_addr=DRAW_COUNTER_LOAD_RETURN_ADDR,
        ),
        DRAW_GATE_LEN,
    )
    legacy_strobe_gates = [
        padded(
            make_legacy_gate(
                STROBE_GATE_ADDR,
                disabled_addr=STROBE_SKIP_ADDR,
                return_addr=STROBE_COUNTER_LOAD_RETURN_ADDR,
                cheat_addr=addr,
            ),
            STROBE_GATE_LEN,
        )
        for addr in LEGACY_BLINK_CHEAT_ADDRS
    ]
    legacy_object_gates = [
        padded(
            make_legacy_gate(
                OBJECT_GATE_ADDR,
                disabled_addr=OBJECT_STOCK_ADDR,
                return_addr=OBJECT_COUNTER_LOAD_RETURN_ADDR,
                cheat_addr=addr,
            ),
            OBJECT_GATE_LEN,
        )
        for addr in LEGACY_BLINK_CHEAT_ADDRS
    ]
    legacy_draw_gates = [
        padded(
            make_legacy_gate(
                DRAW_GATE_ADDR,
                disabled_addr=DRAW_STOCK_ADDR,
                return_addr=DRAW_COUNTER_LOAD_RETURN_ADDR,
                cheat_addr=addr,
            ),
            DRAW_GATE_LEN,
        )
        for addr in LEGACY_BLINK_CHEAT_ADDRS
    ]

    checks = [
        (STROBE_HOOK_OFF, strobe_stock, strobe_patch, "strobe hook"),
        (OBJECT_HOOK_OFF, object_stock, object_patch, "object hook"),
        (DRAW_HOOK_OFF, draw_stock, draw_patch, "draw hook"),
    ]
    for off, stock, patched, name in checks:
        current = bytes(data[off : off + 8])
        if current not in {stock, patched}:
            raise SystemExit(f"unexpected {name} bytes at 0x{off:X}: {current.hex(' ')}")

    caves = [
        (STROBE_GATE_OFF, STROBE_GATE_LEN, strobe_gate, legacy_strobe_gates, "strobe gate"),
        (OBJECT_GATE_OFF, OBJECT_GATE_LEN, object_gate, legacy_object_gates, "object gate"),
        (DRAW_GATE_OFF, DRAW_GATE_LEN, draw_gate, legacy_draw_gates, "draw gate"),
    ]
    for off, size, blob, legacy_blobs, name in caves:
        current = bytes(data[off : off + size])
        if current not in {bytes(size), blob, *legacy_blobs}:
            raise SystemExit(f"{name} is not empty/known at 0x{off:X}: {current[:16].hex(' ')}")

    # Leave BLINK_CHEAT_ADDR as zero in the file for default-off behavior.
    if args.revert:
        data[STROBE_HOOK_OFF : STROBE_HOOK_OFF + 8] = strobe_stock
        data[OBJECT_HOOK_OFF : OBJECT_HOOK_OFF + 8] = object_stock
        data[DRAW_HOOK_OFF : DRAW_HOOK_OFF + 8] = draw_stock
        for off, size, _, _, _ in caves:
            data[off : off + size] = bytes(size)
    else:
        data[STROBE_GATE_OFF : STROBE_GATE_OFF + STROBE_GATE_LEN] = strobe_gate
        data[OBJECT_GATE_OFF : OBJECT_GATE_OFF + OBJECT_GATE_LEN] = object_gate
        data[DRAW_GATE_OFF : DRAW_GATE_OFF + DRAW_GATE_LEN] = draw_gate
        data[STROBE_HOOK_OFF : STROBE_HOOK_OFF + 8] = strobe_patch
        data[OBJECT_HOOK_OFF : OBJECT_HOOK_OFF + 8] = object_patch
        data[DRAW_HOOK_OFF : DRAW_HOOK_OFF + 8] = draw_patch

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(bytes(data))}")
    print("player civilian blink feature gate:", "reverted" if args.revert else "patched")
    print("enable:")
    print("  80055148 0001")
    print("  8005517C 0001")
    print("  800551B0 0001")
    print("disable:")
    print("  80055148 0000")
    print("  8005517C 0000")
    print("  800551B0 0000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
