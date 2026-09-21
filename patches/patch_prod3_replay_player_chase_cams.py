#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
RUNTIME_BASE = 0x8000F800

# Current PROD3 addresses, not the stale debug-symbol addresses from NFS4.H.
REPLAY_CAMERA_LIST_ADDR = 0x801182C0
REPLAY_CAMERA_LIST_OFF = REPLAY_CAMERA_LIST_ADDR - RUNTIME_BASE

# Use the game's own camera-switch function for replay camera cycling. This
# avoids custom executable caves and lets Camera_NextMode read the same
# GameSetup_gData.carInfo[player].Camera[] values used during the race.
REPLAY_LIST_NON_TRACK = [2, 2, 2, 2, 2, 2, 2, 2, 2]

# Failed prototype cleanup: old debug-symbol table location.
OLD_UNUSED_TABLE_ADDR = 0x80117008
OLD_UNUSED_TABLE_OFF = OLD_UNUSED_TABLE_ADDR - RUNTIME_BASE
OLD_UNUSED_RESTORE = [(3, 0), (4, 0)]

# Replay camera switch path:
#   800B6108/610C originally calculate/load mode from ReplayCameraList.
#   800B6120/6124/6128 repeat that load to store Replay_ReplayCamera.cameraMode.
HOOK_SETMODE_OFF = 0x0A6908
HOOK_STOREMODE_OFF = 0x0A6920
HOOK_SETMODE_STOCK = bytes.fromhex("21 10 56 00 00 00 45 8C")
HOOK_STOREMODE_STOCK = bytes.fromhex("80 10 02 00 21 10 56 00 00 00 42 8C")
CALL_SETMODE_OFF = 0x0A6910
CALL_SETMODE_STOCK = bytes.fromhex("0B 18 02 0C")
CAMERA_NEXTMODE_ADDR = 0x80086240

CAVE_SETMODE_OFF = 0x0FEC00
CAVE_STOREMODE_OFF = 0x0FEC60
CAVE_SETMODE_ADDR = RUNTIME_BASE + CAVE_SETMODE_OFF
CAVE_STOREMODE_ADDR = RUNTIME_BASE + CAVE_STOREMODE_OFF
CAVE_LEN = 0x60
OLD_BAD_CAVE_SETMODE_OFF = 0x0FF000
OLD_BAD_CAVE_STOREMODE_OFF = 0x0FF060
OLD_BAD_CAVE_SETMODE_ADDR = RUNTIME_BASE + OLD_BAD_CAVE_SETMODE_OFF
OLD_BAD_CAVE_STOREMODE_ADDR = RUNTIME_BASE + OLD_BAD_CAVE_STOREMODE_OFF

# GameSetup_gData is at 0x801144A4 in current PROD3. carInfo[0].Camera[1] is
# base + 0x3D4 + 0xA8 = 0x80114920. Add player * sizeof(GameSetup_tCarData).
PLAYER_CAMERA2_ADDR = 0x80114920
CARINFO_SIZE = 0xB4


REG = {
    "zero": 0,
    "v0": 2,
    "a1": 5,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "t3": 11,
    "t4": 12,
    "s0": 16,
    "s1": 17,
    "s5": 21,
    "ra": 31,
}


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest().upper()


def r(fn: int, rs: int, rt: int, rd: int, sh: int = 0) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (sh << 6) | fn


def i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def j(op: int, addr: int) -> int:
    return (op << 26) | ((addr >> 2) & 0x03FFFFFF)


def addu(rd: str, rs: str, rt: str) -> int:
    return r(0x21, REG[rs], REG[rt], REG[rd])


def sll(rd: str, rt: str, sh: int) -> int:
    return r(0x00, 0, REG[rt], REG[rd], sh)


def jr(rs: str) -> int:
    return r(0x08, REG[rs], 0, 0)


def lw(rt: str, imm: int, rs: str) -> int:
    return i(0x23, REG[rs], REG[rt], imm)


def lhu(rt: str, imm: int, rs: str) -> int:
    return i(0x25, REG[rs], REG[rt], imm)


def lui(rt: str, imm: int) -> int:
    return i(0x0F, 0, REG[rt], imm)


def addiu(rt: str, rs: str, imm: int) -> int:
    return i(0x09, REG[rs], REG[rt], imm)


def andi(rt: str, rs: str, imm: int) -> int:
    return i(0x0C, REG[rs], REG[rt], imm)


def beq(rs: str, rt: str, pc: int, target: int) -> int:
    offset = (target - (pc + 4)) >> 2
    return i(0x04, REG[rs], REG[rt], offset)


def jal(addr: int) -> int:
    return j(0x03, addr)


def words_blob(words: list[int]) -> bytes:
    return b"".join(struct.pack("<I", word) for word in words)


def dynamic_camera_loader(*, dest: str, base_addr: int, post_incremented_player: bool) -> bytes:
    cam2_hi = PLAYER_CAMERA2_ADDR >> 16
    cam2_lo = PLAYER_CAMERA2_ADDR & 0xFFFF
    use_cam2_pc = base_addr + 0x48
    player_seed = addiu("t4", "s0", -1) if post_incremented_player else addu("t4", "s0", "zero")
    words = [
        lw("t0", 12, "s5"),           # current Replay_ReplayInterface.camera
        andi("t0", "t0", 1),         # even slots -> gameplay camera 2, odd -> camera 3
        lui("t1", cam2_hi),
        addiu("t1", "t1", cam2_lo),  # &GameSetup_gData.carInfo[0].Camera[1]
        player_seed,
        sll("t2", "t4", 7),          # player * 0x80
        sll("t3", "t4", 5),          # player * 0x20
        addu("t2", "t2", "t3"),
        sll("t3", "t4", 4),          # player * 0x10
        addu("t2", "t2", "t3"),
        sll("t3", "t4", 2),          # player * 0x04 => total 0xB4
        addu("t2", "t2", "t3"),
        addu("t1", "t1", "t2"),
        beq("t0", "zero", base_addr + 0x34, use_cam2_pc),
        0,
        lhu(dest, 4, "t1"),           # Camera[2], user-facing gameplay camera 3
        jr("ra"),
        0,
        lhu(dest, 0, "t1"),           # Camera[1], user-facing gameplay camera 2
        jr("ra"),
        0,
    ]
    blob = words_blob(words)
    return blob + bytes(CAVE_LEN - len(blob))


def verify_or_already_hooked(data: bytes) -> None:
    hook1 = bytes(data[HOOK_SETMODE_OFF : HOOK_SETMODE_OFF + 8])
    hook1_patch = words_blob([jal(CAVE_SETMODE_ADDR), 0])
    hook1_old_bad_patch = words_blob([jal(OLD_BAD_CAVE_SETMODE_ADDR), 0])
    if hook1 not in (HOOK_SETMODE_STOCK, hook1_patch, hook1_old_bad_patch):
        raise SystemExit(f"unexpected bytes at set-mode hook: {hook1.hex(' ')}")

    hook2 = bytes(data[HOOK_STOREMODE_OFF : HOOK_STOREMODE_OFF + 12])
    hook2_patch = words_blob([jal(CAVE_STOREMODE_ADDR), 0, 0])
    hook2_old_bad_patch = words_blob([jal(OLD_BAD_CAVE_STOREMODE_ADDR), 0, 0])
    if hook2 not in (HOOK_STOREMODE_STOCK, hook2_patch, hook2_old_bad_patch):
        raise SystemExit(f"unexpected bytes at store-mode hook: {hook2.hex(' ')}")

    call = bytes(data[CALL_SETMODE_OFF : CALL_SETMODE_OFF + 4])
    call_next = words_blob([jal(CAMERA_NEXTMODE_ADDR)])
    if call not in (CALL_SETMODE_STOCK, call_next):
        raise SystemExit(f"unexpected camera call bytes: {call.hex(' ')}")


def main() -> int:
    exe = find_exe()
    data = bytearray(exe.read_bytes())
    verify_or_already_hooked(data)

    print(f"before MD5 {md5(data)}")

    for index, restore_mode in OLD_UNUSED_RESTORE:
        off = OLD_UNUSED_TABLE_OFF + index * 4
        old_mode = struct.unpack_from("<i", data, off)[0]
        if old_mode in (2, 3):
            struct.pack_into("<i", data, off, restore_mode)
            print(f"cleanup unused old table[{index}]: {old_mode} -> {restore_mode}")

    for index, mode in enumerate(REPLAY_LIST_NON_TRACK):
        off = REPLAY_CAMERA_LIST_OFF + index * 4
        old_mode = struct.unpack_from("<i", data, off)[0]
        if old_mode != mode:
            struct.pack_into("<i", data, off, mode)
            print(f"ReplayCameraList[{index + 1}]: {old_mode} -> {mode}")

    data[CAVE_SETMODE_OFF : CAVE_SETMODE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    data[CAVE_STOREMODE_OFF : CAVE_STOREMODE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    data[OLD_BAD_CAVE_SETMODE_OFF : OLD_BAD_CAVE_SETMODE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    data[OLD_BAD_CAVE_STOREMODE_OFF : OLD_BAD_CAVE_STOREMODE_OFF + CAVE_LEN] = bytes(CAVE_LEN)
    data[HOOK_SETMODE_OFF : HOOK_SETMODE_OFF + 8] = HOOK_SETMODE_STOCK
    data[CALL_SETMODE_OFF : CALL_SETMODE_OFF + 4] = words_blob([jal(CAMERA_NEXTMODE_ADDR)])
    data[HOOK_STOREMODE_OFF : HOOK_STOREMODE_OFF + 12] = words_blob([
        lhu("v0", 0x70, "s1"),  # Replay_ReplayCamera.cameraMode = Camera_gInfo.mode
        0,
        0,
    ])

    exe.write_bytes(data)
    print(f"after  MD5 {md5(data)}")
    print("Replay camera switching now calls Camera_NextMode and stores Camera_gInfo.mode.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
