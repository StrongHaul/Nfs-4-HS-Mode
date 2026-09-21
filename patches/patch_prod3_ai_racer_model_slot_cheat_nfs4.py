#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_ai_racer_model_slot_cheat_nfs4"
RUNTIME_BASE = 0x8000F800

# Nfs2_GameModuleStartUp, immediately after GameSetup_StartUp(stream).
# Stock code calls Replay_InitReplay here; Replay_Init then mirrors
# data_801144A4 -> data_80118424, so editing primary setup slots here should
# keep the backup/replay copy consistent.
HOOK_OFF = 0x95558
RETURN_ADDR = 0x800A4D60
REPLAY_INIT_ADDR = 0x800B4A74
STOCK = bytes.fromhex(
    "9d d2 02 0c"  # jal 0x800B4A74
    "00 00 00 00"  # nop
)

CAVE_OFF = 0xE8024
CAVE_ADDR = RUNTIME_BASE + CAVE_OFF
CAVE_LEN = 0x80

AI_MODEL_CHEAT_ADDR = 0x80054B82

# Race setup car id field (+0x104) for slots 1 and 2.
AI1_CAR_ID_ADDR = 0x8011492C
AI2_CAR_ID_ADDR = 0x801149E0

REG = {
    "zero": 0,
    "t0": 8,
    "t1": 9,
    "t2": 10,
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


def ins_j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


def pack(words: list[int]) -> bytes:
    return struct.pack("<" + "I" * len(words), *words)


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jal(addr: int) -> int:
    return ins_j(0x03, addr)


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
        lui("t0", hi(AI_MODEL_CHEAT_ADDR)),
        lhu("t1", lo(AI_MODEL_CHEAT_ADDR), "t0"),
        beq("t1", "zero", "call_replay"),
        nop(),
        # Keep this deliberately narrow for the current HP 2-racer experiment.
        # Future multi-racer states can extend the same pattern to more slots.
        lui("t2", hi(AI1_CAR_ID_ADDR)),
        sw("t1", lo(AI1_CAR_ID_ADDR), "t2"),
        lui("t2", hi(AI2_CAR_ID_ADDR)),
        sw("t1", lo(AI2_CAR_ID_ADDR), "t2"),
        "call_replay",
        jal(REPLAY_INIT_ADDR),
        nop(),
        j(RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, CAVE_ADDR)
    if len(blob) > CAVE_LEN:
        raise SystemExit(f"cave too large: 0x{len(blob):X}")
    return blob + bytes(CAVE_LEN - len(blob))


def apply(path: Path) -> None:
    data = bytearray(path.read_bytes())
    hook = pack([j(CAVE_ADDR), nop()])
    current_hook = bytes(data[HOOK_OFF : HOOK_OFF + len(STOCK)])
    if current_hook not in {STOCK, hook}:
        raise SystemExit(f"unexpected hook bytes at 0x{HOOK_OFF:X}: {current_hook.hex(' ')}")

    cave = make_cave()
    current_cave = bytes(data[CAVE_OFF : CAVE_OFF + CAVE_LEN])
    if current_cave not in {bytes(CAVE_LEN), cave}:
        raise SystemExit(f"cave at 0x{CAVE_OFF:X} is not empty/ours")

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
    data = bytearray(path.read_bytes())
    data[HOOK_OFF : HOOK_OFF + len(STOCK)] = STOCK
    data[CAVE_OFF : CAVE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    path.write_bytes(data)


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
    print("AI racer slot model cheat: 80054B82 00??, 0000 = off")
    print(f"md5 {md5(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
