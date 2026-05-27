#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_handle_speech_direct_arrest"
RUNTIME_BASE = 0x8000F800

# AIHigh_Player::HandleSpeech, after Mobile(Cars_gList[s1]) returns in v0:
#   lw    v1,0x4C(v0)
#   addu  a1,s0,zero
#
# Stock MobileSpeaker::Catch(s0) can be skipped by our safety guard or can
# return before producing speech when speaker state is incomplete. For now this
# hook forces the actual loudspeaker/bullhorn event for every player
# warning/ticket/arrest path, then runs the original virtual Catch call for
# stock side effects.
HOOK_OFF = 0x535F8
RETURN_ADDR = 0x80062E14
STOCK = bytes.fromhex(
    "4C 00 43 8C"  # lw v1,0x4C(v0)
    "21 28 00 02"  # addu a1,s0,zero
)

CAVE_OFF = 0xFF300
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x100

SPCHNFS_C_P_ARRESTED_ADDR = 0x800945D8
SPCHNFS_C_P_WARNING_ADDR = 0x8009462C
SPCHNFS_C_P_TICKET_ADDR = 0x80094680
SPCHNFS_C_P_BULLHORN_ADDR = 0x80094770
SPCH_PLAY_SPEECH_ADDR = 0x800E8230

REG = {
    "zero": 0,
    "v0": 2,
    "v1": 3,
    "a0": 4,
    "a1": 5,
    "t0": 8,
    "t1": 9,
    "s0": 16,
    "gp": 28,
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


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def addu(rd: str, rs: str, rt: str) -> int:
    return ins_r(REG[rs], REG[rt], REG[rd], 0, 0x21)


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jal(addr: int) -> int:
    return ins_j(0x03, addr)


def jalr(rs: str) -> int:
    return ins_r(REG[rs], 0, REG["ra"], 0, 0x09)


def lh(rt: str, off: int, rs: str) -> int:
    return ins_i(0x21, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def slti(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0A, REG[rs], REG[rt], imm)


def nop() -> int:
    return 0


def make_hook() -> bytes:
    return pack([j(CAVE_ADDR), nop()])


def make_cave(*, set_speaker_car: bool = True, mode: str = "bullhorn") -> bytes:
    if mode not in {"bullhorn", "catch_events"}:
        raise SystemExit(f"unknown mode: {mode}")

    items: list[int | str | tuple[str, str, str, str]] = [
        addiu("sp", "sp", -16),
        sw("ra", 12, "sp"),
        sw("v0", 8, "sp"),
        *(
            [
                lw("t1", 0x083C, "gp"),  # fgSpeech
                lw("t0", 0x0060, "v0"),  # MobileSpeaker::carObj
                nop(),
                sw("t0", 0x038C, "t1"),  # fgSpeech->fSpeakerCar
            ]
            if set_speaker_car
            else []
        ),
        *(
            [
                addiu("a0", "v0", 0x0050),
                jal(SPCHNFS_C_P_BULLHORN_ADDR),
                nop(),
            ]
            if mode == "bullhorn"
            else [
                sw("s0", 0x002C, "v0"),
                addiu("t0", "zero", 1),
                bne("s0", "t0", "not_arrested"),
                nop(),
                addiu("a0", "v0", 0x0050),
                jal(SPCHNFS_C_P_ARRESTED_ADDR),
                addiu("a1", "v0", 0x002C),
                beq("zero", "zero", "play"),
                nop(),
                "not_arrested",
                addiu("t0", "zero", 2),
                bne("s0", "t0", "ticket"),
                nop(),
                addiu("a0", "v0", 0x0050),
                jal(SPCHNFS_C_P_WARNING_ADDR),
                addiu("a1", "v0", 0x002C),
                beq("zero", "zero", "play"),
                nop(),
                "ticket",
                addiu("a0", "v0", 0x0050),
                jal(SPCHNFS_C_P_TICKET_ADDR),
                addiu("a1", "v0", 0x002C),
                "play",
            ]
        ),
        jal(SPCH_PLAY_SPEECH_ADDR),
        nop(),
        "stock",
        lw("v0", 8, "sp"),
        lw("ra", 12, "sp"),
        addiu("sp", "sp", 16),
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
    blob = pack_labeled(items, CAVE_ADDR)
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob + bytes(CAVE_LEN - len(blob))


def make_arrest_only_cave(*, set_speaker_car: bool = True) -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        addiu("sp", "sp", -16),
        sw("ra", 12, "sp"),
        sw("v0", 8, "sp"),
        slti("t0", "s0", 8),
        bne("t0", "zero", "stock"),
        nop(),
        *(
            [
                lw("t1", 0x083C, "gp"),
                lw("t0", 0x0060, "v0"),
                nop(),
                sw("t0", 0x038C, "t1"),
            ]
            if set_speaker_car
            else []
        ),
        addiu("t0", "zero", 1),
        sw("t0", 0x002C, "v0"),
        addiu("a0", "v0", 0x0050),
        jal(SPCHNFS_C_P_ARRESTED_ADDR),
        addiu("a1", "v0", 0x002C),
        jal(SPCH_PLAY_SPEECH_ADDR),
        nop(),
        "stock",
        lw("v0", 8, "sp"),
        lw("ra", 12, "sp"),
        addiu("sp", "sp", 16),
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
    blob = pack_labeled(items, CAVE_ADDR)
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"old cave too large: 0x{len(blob):X}")
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
    previous_no_speaker_cave = make_cave(set_speaker_car=False)
    previous_catch_events_cave = make_cave(mode="catch_events")
    previous_catch_events_no_speaker_cave = make_cave(set_speaker_car=False, mode="catch_events")
    previous_arrest_only_cave = make_arrest_only_cave()
    previous_arrest_only_no_speaker_cave = make_arrest_only_cave(set_speaker_car=False)

    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + 8])
    if current_hook not in {STOCK, hook}:
        raise SystemExit(f"unexpected HandleSpeech hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")

    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {
        bytes(CAVE_LEN),
        cave,
        previous_no_speaker_cave,
        previous_catch_events_cave,
        previous_catch_events_no_speaker_cave,
        previous_arrest_only_cave,
        previous_arrest_only_no_speaker_cave,
    }:
        raise SystemExit(f"HandleSpeech direct arrest cave is not empty/known at 0x{CAVE_OFF:X}")

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
    print("AIHigh_Player direct arrest speech:", "reverted" if args.revert else "enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
