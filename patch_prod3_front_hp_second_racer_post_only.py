#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


FRONT_GLOB = "PROD 3*/FRONT.BIN"
BACKUP_SUFFIX = ".orig_before_prod3_front_hp_second_racer_post_only"
RUNTIME_BASE = 0x80010000

POST_HOOK_OFF = 0x1A818
POST_RETURN_ADDR = RUNTIME_BASE + 0x1A820
POST_STOCK = bytes.fromhex(
    "14 80 02 3c"  # lui v0,0x8014
    "8c ef 43 8c"  # lw v1,-0x1074(v0)
)
POST_CAVE_OFF = 0x43100
POST_CAVE_ADDR = RUNTIME_BASE + POST_CAVE_OFF
POST_CAVE_LEN = 0x100

FRONTEND_RACE_TYPE_ADDR = 0x801158BC
AI_RACER_MODEL_CHEAT_ADDR = 0x80054B82
AI_RACER_MODEL_SCRATCH_ADDR = 0x80054B84

OPP_APPEND_CALL_OFF = 0x1AE7C
OPP_APPEND_CALL_RETURN_ADDR = RUNTIME_BASE + 0x1AE88
OPP_APPEND_CALL_STOCK = bytes.fromhex(
    "21 20 40 00"  # addu a0,v0,zero
    "dd a6 00 0c"  # jal Front_AppendOpponentData
    "10 00 a5 27"  # addiu a1,sp,0x10
)
OPP_APPEND_FUNC_ADDR = 0x80029B74
AI_MODEL_CAVE_OFF = 0x43200
AI_MODEL_CAVE_ADDR = RUNTIME_BASE + AI_MODEL_CAVE_OFF
AI_MODEL_CAVE_LEN = 0x100
ENABLE_UNSAFE_AI_MODEL_CHEAT = False

REG = {
    "zero": 0,
    "a0": 4,
    "a1": 5,
    "v0": 2,
    "v1": 3,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "t3": 11,
    "sp": 29,
}


def find_front() -> Path:
    matches = list(Path(".").glob(FRONT_GLOB))
    if len(matches) != 1:
        raise SystemExit(f"expected one {FRONT_GLOB}, found {len(matches)}")
    return matches[0]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest().upper()


def ins_i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def ins_j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jal(addr: int) -> int:
    return ins_j(0x03, addr)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lbu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x24, REG[rs], REG[rt], off)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def sb(rt: str, off: int, rs: str) -> int:
    return ins_i(0x28, REG[rs], REG[rt], off)


def sh(rt: str, off: int, rs: str) -> int:
    return ins_i(0x29, REG[rs], REG[rt], off)


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
            op = 0x05 if kind == "bne" else 0x04
            item = ins_i(op, REG[rs], REG[rt], (labels[target] - (pc + 4)) >> 2)
        words.append(item)
        pc += 4
    return pack(words)


def make_post_cave(*, duplicate_hp_one_traffic: bool = True) -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        addiu("t0", "sp", 0x10),
        lui("t1", hi(FRONTEND_RACE_TYPE_ADDR)),
        lbu("t2", lo(FRONTEND_RACE_TYPE_ADDR), "t1"),
        addiu("t3", "zero", 1),
        bne("t2", "t3", "stock"),
        nop(),
        lhu("t2", 0x1A0, "t0"),
        bne("t2", "t3", "maybe_already_two"),
        nop(),
        sw("zero", 0x1CC, "t0"),
        sw("zero", 0x1D0, "t0"),
        addiu("t2", "zero", 2),
        sb("t2", 0x1D4, "t0"),
        lw("t2", 0x1C4, "t0"),
        sw("t2", 0x1D8, "t0"),
        lbu("t2", 0x1C8, "t0"),
        sb("t2", 0x1DC, "t0"),
        lbu("t2", 0x1C9, "t0"),
        sb("t2", 0x1DD, "t0"),
        addiu("t2", "zero", 2),
        sh("t2", 0x1A0, "t0"),
        addiu("t2", "zero", 3),
        sb("t2", 0x1AC, "t0"),
        "maybe_already_two",
        *(
            [
                # HP night normally has exactly one traffic model. Duplicate
                # that model in FRONT so the game stream and model list are
                # consistent before NFS4.EXE sees it.
                lhu("t2", 0x244, "t0"),
                bne("t2", "t3", "traffic_cap_three"),
                nop(),
                lhu("t2", 0x246, "t0"),
                sh("t2", 0x248, "t0"),
                addiu("t2", "zero", 2),
                sh("t2", 0x244, "t0"),
            ]
            if duplicate_hp_one_traffic
            else []
        ),
        "traffic_cap_three",
        lhu("t2", 0x244, "t0"),
        addiu("t3", "zero", 3),
        bne("t2", "t3", "stock"),
        nop(),
        addiu("t2", "zero", 2),
        sh("t2", 0x244, "t0"),
        "stock",
        lui("v0", 0x8014),
        lw("v1", -0x1074, "v0"),
        j(POST_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, POST_CAVE_ADDR)
    if len(blob) > POST_CAVE_LEN:
        raise SystemExit(f"post cave too large: 0x{len(blob):X}")
    return blob + bytes(POST_CAVE_LEN - len(blob))


def make_ai_model_cave() -> bytes:
    # Hook around Front_AppendOpponentData. The stable second-racer hook has
    # already edited tFEStream before this point. If 80054B82 is non-zero, write
    # that value into each generated opponent record's sim/model field.
    items: list[int | str | tuple[str, str, str, str]] = [
        lui("t0", hi(AI_RACER_MODEL_SCRATCH_ADDR)),
        sw("v0", lo(AI_RACER_MODEL_SCRATCH_ADDR), "t0"),
        addiu("a0", "v0", 0),
        jal(OPP_APPEND_FUNC_ADDR),
        addiu("a1", "sp", 0x10),
        lui("t0", hi(AI_RACER_MODEL_CHEAT_ADDR)),
        lhu("t1", lo(AI_RACER_MODEL_CHEAT_ADDR), "t0"),
        beq("t1", "zero", "done"),
        nop(),
        lw("t2", lo(AI_RACER_MODEL_SCRATCH_ADDR), "t0"),
        addiu("t0", "sp", 0x10),
        lhu("t3", 0x1A0, "t0"),
        beq("t3", "zero", "done"),
        nop(),
        "loop",
        sw("t1", 0x14, "t2"),
        addiu("t2", "t2", 0xC0),
        addiu("t3", "t3", -1),
        bne("t3", "zero", "loop"),
        nop(),
        "done",
        j(OPP_APPEND_CALL_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, AI_MODEL_CAVE_ADDR)
    if len(blob) > AI_MODEL_CAVE_LEN:
        raise SystemExit(f"ai model cave too large: 0x{len(blob):X}")
    return blob + bytes(AI_MODEL_CAVE_LEN - len(blob))


def apply_patch(path: Path) -> None:
    data = bytearray(path.read_bytes())
    hook = pack([j(POST_CAVE_ADDR), nop()])
    current_hook = bytes(data[POST_HOOK_OFF : POST_HOOK_OFF + len(POST_STOCK)])
    if current_hook not in {POST_STOCK, hook}:
        raise SystemExit(f"unexpected hook bytes at 0x{POST_HOOK_OFF:X}: {current_hook.hex(' ')}")
    cave = make_post_cave()
    previous_cave = make_post_cave(duplicate_hp_one_traffic=False)
    current_cave = bytes(data[POST_CAVE_OFF : POST_CAVE_OFF + POST_CAVE_LEN])
    if current_cave not in {bytes(POST_CAVE_LEN), cave, previous_cave}:
        raise SystemExit(f"cave at 0x{POST_CAVE_OFF:X} is not empty/ours")
    if ENABLE_UNSAFE_AI_MODEL_CHEAT:
        model_hook = pack([j(AI_MODEL_CAVE_ADDR), nop(), nop()])
        current_model_hook = bytes(data[OPP_APPEND_CALL_OFF : OPP_APPEND_CALL_OFF + len(OPP_APPEND_CALL_STOCK)])
        if current_model_hook not in {OPP_APPEND_CALL_STOCK, model_hook}:
            raise SystemExit(
                f"unexpected opponent append hook bytes at 0x{OPP_APPEND_CALL_OFF:X}: "
                f"{current_model_hook.hex(' ')}"
            )
        model_cave = make_ai_model_cave()
        current_model_cave = bytes(data[AI_MODEL_CAVE_OFF : AI_MODEL_CAVE_OFF + AI_MODEL_CAVE_LEN])
        if current_model_cave not in {bytes(AI_MODEL_CAVE_LEN), model_cave}:
            raise SystemExit(f"ai model cave at 0x{AI_MODEL_CAVE_OFF:X} is not empty/ours")

    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_bytes(data)

    data[POST_HOOK_OFF : POST_HOOK_OFF + len(POST_STOCK)] = hook
    data[POST_CAVE_OFF : POST_CAVE_OFF + POST_CAVE_LEN] = cave
    if ENABLE_UNSAFE_AI_MODEL_CHEAT:
        data[OPP_APPEND_CALL_OFF : OPP_APPEND_CALL_OFF + len(OPP_APPEND_CALL_STOCK)] = model_hook
        data[AI_MODEL_CAVE_OFF : AI_MODEL_CAVE_OFF + AI_MODEL_CAVE_LEN] = model_cave
    else:
        data[OPP_APPEND_CALL_OFF : OPP_APPEND_CALL_OFF + len(OPP_APPEND_CALL_STOCK)] = OPP_APPEND_CALL_STOCK
        data[AI_MODEL_CAVE_OFF : AI_MODEL_CAVE_OFF + AI_MODEL_CAVE_LEN] = bytes(AI_MODEL_CAVE_LEN)
    path.write_bytes(data)


def revert_patch(path: Path) -> None:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if backup.exists():
        path.write_bytes(backup.read_bytes())
        return
    data = bytearray(path.read_bytes())
    data[POST_HOOK_OFF : POST_HOOK_OFF + len(POST_STOCK)] = POST_STOCK
    data[POST_CAVE_OFF : POST_CAVE_OFF + POST_CAVE_LEN] = bytes(POST_CAVE_LEN)
    data[OPP_APPEND_CALL_OFF : OPP_APPEND_CALL_OFF + len(OPP_APPEND_CALL_STOCK)] = OPP_APPEND_CALL_STOCK
    data[AI_MODEL_CAVE_OFF : AI_MODEL_CAVE_OFF + AI_MODEL_CAVE_LEN] = bytes(AI_MODEL_CAVE_LEN)
    path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    path = find_front()
    if args.revert:
        revert_patch(path)
        action = "reverted"
    else:
        apply_patch(path)
        action = "patched"

    print(f"{action} {path}")
    print("HP Duel: add second AI racer without AI model hook")
    print("HP night: duplicate one traffic model to make two FRONT traffic entries")
    print(f"md5 {md5(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
