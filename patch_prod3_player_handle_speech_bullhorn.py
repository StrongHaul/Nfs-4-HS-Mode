#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_handle_speech_bullhorn"
RUNTIME_BASE = 0x8000F800

# AIHigh_Player::HandleSpeech after Mobile__6SpeechP8Car_tObj:
#   lw    v1,0x4C(v0)
#   addu  a1,s0,zero
#   lh    a0,0x48(v1)
#   lw    v1,0x4C(v1)
#   jalr  v1
#   addu  a0,v0,a0
#
# Stock calls Catch(ticket). Some arrest/bust paths in PROD3 do not produce the
# police loudspeaker line the user expects. This hook adds Bullhorn() on the
# same MobileSpeaker, then falls through to the original Catch call.
HOOK_OFF = 0x535F8
RETURN_ADDR = 0x80062E14
STOCK = bytes.fromhex(
    "4C 00 43 8C"  # lw v1,0x4C(v0)
    "21 28 00 02"  # addu a1,s0,zero
)

CAVE_OFF = 0xFF300
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x100

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "a0": 4,
    "a1": 5,
    "t0": 8,
    "t1": 9,
    "s0": 16,
    "sp": 29,
    "ra": 31,
}


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
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


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jalr(rs: str) -> int:
    return ins_r(REG[rs], 0, REG["ra"], 0, 0x09)


def lh(rt: str, off: int, rs: str) -> int:
    return ins_i(0x21, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def nop() -> int:
    return 0


def make_hook() -> bytes:
    return pack([j(CAVE_ADDR), nop()])


def make_cave() -> bytes:
    words = [
        addiu("sp", "sp", -16),
        sw("ra", 12, "sp"),
        sw("v0", 8, "sp"),
        # MobileSpeaker::Bullhorn(): vtable this-adjust +0x38, method +0x3C.
        lw("v1", 0x004C, "v0"),
        nop(),
        lh("t0", 0x0038, "v1"),
        lw("t1", 0x003C, "v1"),
        nop(),
        jalr("t1"),
        addu("a0", "v0", "t0"),
        lw("v0", 8, "sp"),
        lw("ra", 12, "sp"),
        addiu("sp", "sp", 16),
        # Original Catch(ticket) call sequence from AIHigh_Player::HandleSpeech.
        lw("v1", 0x004C, "v0"),
        addu("a1", "s0", "zero"),
        lh("a0", 0x0048, "v1"),
        lw("v1", 0x004C, "v1"),
        nop(),
        jalr("v1"),
        addu("a0", "v0", "a0"),
        j(RETURN_ADDR),
        nop(),
    ]
    blob = pack(words)
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob + bytes(CAVE_LEN - len(blob))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    data = bytearray(exe.read_bytes())
    original = bytes(data)

    hook = make_hook()
    cave = make_cave()

    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {STOCK, hook}:
        raise SystemExit(
            f"unexpected HandleSpeech hook bytes at 0x{HOOK_OFF:X}: "
            f"{current_hook.hex(' ')}"
        )

    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {bytes(CAVE_LEN), cave}:
        raise SystemExit(f"HandleSpeech bullhorn cave is not empty/known at 0x{CAVE_OFF:X}")

    if args.revert:
        data[HOOK_OFF : HOOK_OFF + 8] = STOCK
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    else:
        data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = cave
        data[HOOK_OFF : HOOK_OFF + 8] = hook

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(exe)}")
    print("AIHigh_Player HandleSpeech bullhorn: {}".format("reverted" if args.revert else "enabled"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
