#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_player_can_bust_ai_racers"
RUNTIME_BASE = 0x8000F800

# AIHigh_BasicPerp::CheckIfCaught candidate-car test:
#   stock checks carFlags & 0x20 for normal cops, or carFlags & 0x200 for
#   human cops. We add a special player-controlled path without globally setting
#   the human-cop flag, because the HUD notify path casts highLevelAIObjs[player]
#   to AIHigh_BTC_HumanCop.
CANDIDATE_HOOK_OFF = 0x4C990
CANDIDATE_RETURN_STOCK = RUNTIME_BASE + 0x4C998
CANDIDATE_RETURN_ACCEPT = RUNTIME_BASE + 0x4C9C4
CANDIDATE_STOCK = bytes.fromhex(
    "60 02 42 8E"  # lw v0,0x0260(s2)
    "00 00 00 00"  # nop
)

# AIHigh_BTC_Perp::CheckForControlsPressed entry. Stock requires
# Cars_gHumanRaceCarList[0]->carFlags & 0x200 before checking controls; we let
# player controls complete the arrest without needing that global flag.
CONTROLS_HOOK_OFF = 0x509A8
CONTROLS_RETURN_STOCK = RUNTIME_BASE + 0x509B4
CONTROLS_STOCK = bytes.fromhex(
    "11 80 02 3C"  # lui v0,0x8011
    "0C 0D 43 8C"  # lw v1,0x0D0C(v0)
)

CANDIDATE_CAVE_OFF = 0xE8200
CANDIDATE_CAVE_ADDR = RUNTIME_BASE + CANDIDATE_CAVE_OFF
CANDIDATE_CAVE_LEN = 0x100
CONTROLS_CAVE_OFF = 0xE8300
CONTROLS_CAVE_ADDR = RUNTIME_BASE + CONTROLS_CAVE_OFF
CONTROLS_CAVE_LEN = 0x100
CRIME_GUARD_HOOK_OFF = 0x4C7E8
CRIME_GUARD_CAVE_OFF = 0xE8480
CRIME_GUARD_CAVE_ADDR = RUNTIME_BASE + CRIME_GUARD_CAVE_OFF
CRIME_GUARD_CAVE_LEN = 0x80
CRIME_GUARD_CONTINUE_ADDR = 0x8005BFF8
CRIME_GUARD_RETURN_ZERO_ADDR = 0x8005C538
CRIME_GUARD_STOCK = bytes.fromhex(
    "78 00 62 8E"  # lw v0,0x78(s3)
    "00 00 00 00"  # nop
)
NO_COPS_GUARD_HOOK_OFF = 0x53ADC
NO_COPS_GUARD_CAVE_OFF = 0xE8400
NO_COPS_GUARD_CAVE_ADDR = RUNTIME_BASE + NO_COPS_GUARD_CAVE_OFF
NO_COPS_GUARD_CAVE_LEN = 0x80
NO_COPS_GUARD_CONTINUE_ADDR = 0x800632E4
NO_COPS_GUARD_RETURN_ADDR = 0x8006343C
NO_COPS_GUARD_STOCK = bytes.fromhex(
    "57 00 40 10"  # beq v0,zero,0x8006343c
    "00 00 00 00"  # nop
)
PLAYER_CAR_OBJ_PTR_ADDR = 0x80110D0C
HUD_BUSTED_OVERLAY_ON_ADDR = 0x800DA218
HUD_BTC_UPDATE_ADDR = 0x800DA1B4
HUD_BUSTED_OVERLAY_OFF_ADDR = 0x800DA3D0
PERP_OVERLAY_ON_0_ADDR = 0x8013F140
PERP_OVERLAY_MESSAGE_0_ADDR = 0x8013F148
PLAYER_BUST_PERP_MARKER_ADDR = 0x8010E6F0

PULLOVER_START_HOOK_OFF = 0x50BF0
PULLOVER_START_RETURN_ADDR = 0x8006040C
PULLOVER_START_CAVE_OFF = 0xFEB80
PULLOVER_START_CAVE_ADDR = RUNTIME_BASE + PULLOVER_START_CAVE_OFF
PULLOVER_START_CAVE_LEN = 0x180
PULLOVER_START_STOCK_PREFIX = bytes.fromhex(
    "60 00 02 24"  # addiu v0,zero,0x60
    "64 00 02 AE"  # sw v0,0x64(s0)
)
PULLOVER_START_STOCK_FULL = bytes.fromhex(
    "60 00 02 24"  # addiu v0,zero,0x60
    "64 00 02 AE"  # sw v0,0x64(s0)
    "12 80 02 3C"  # lui v0,0x8012
    "68 F3 43 8C"  # lw v1,-0x0C98(v0)
    "02 00 02 24"  # addiu v0,zero,2
    "18 00 02 AE"  # sw v0,0x18(s0)
    "68 00 03 AE"  # sw v1,0x68(s0)
)

PULLOVER_COMPLETE_HOOK_OFF = 0x50B94
PULLOVER_COMPLETE_RETURN_ADDR = 0x8006040C
PULLOVER_COMPLETE_CAVE_OFF = 0xFED00
PULLOVER_COMPLETE_CAVE_ADDR = RUNTIME_BASE + PULLOVER_COMPLETE_CAVE_OFF
PULLOVER_COMPLETE_CAVE_LEN = 0x100
PULLOVER_COMPLETE_STOCK_PREFIX = bytes.fromhex(
    "00 00 02 8E"  # lw v0,0(s0)
    "00 00 00 00"  # nop
)
PULLOVER_COMPLETE_STOCK_FULL = bytes.fromhex(
    "00 00 02 8E"  # lw v0,0(s0)
    "00 00 00 00"  # nop
    "78 02 40 AC"  # sw zero,0x278(v0)
    "18 00 00 AE"  # sw zero,0x18(s0)
    "7C 00 11 AE"  # sw s1,0x7C(s0)
    "03 81 01 08"  # j 0x8006040C
    "80 00 00 AE"  # sw zero,0x80(s0)
)

PLAYER_SPEECH_BUST_HOOK_OFF = 0x53590
PLAYER_SPEECH_BUST_RETURN_ADDR = 0x80062D98
PLAYER_SPEECH_BUST_CAVE_OFF = 0xFEE00
PLAYER_SPEECH_BUST_CAVE_ADDR = RUNTIME_BASE + PLAYER_SPEECH_BUST_CAVE_OFF
PLAYER_SPEECH_BUST_CAVE_LEN = 0x80
PLAYER_SPEECH_BUST_STOCK = bytes.fromhex(
    "44 69 03 0C"  # jal Hud_Perp_OverlayOn__Fii
    "01 00 05 24"  # addiu a1,zero,1
)

PLAYER_COMPLETE_HOOK_OFF = 0x53DAC
PLAYER_COMPLETE_RETURN_ADDR = 0x800635B4
PLAYER_COMPLETE_CAVE_OFF = 0xFEE80
PLAYER_COMPLETE_CAVE_ADDR = RUNTIME_BASE + PLAYER_COMPLETE_CAVE_OFF
PLAYER_COMPLETE_CAVE_LEN = 0x80
PLAYER_COMPLETE_STOCK = bytes.fromhex(
    "00 00 22 8E"  # lw v0,0(s1)
    "00 00 00 00"  # nop
)

REG = {
    "zero": 0,
    "a0": 4,
    "a1": 5,
    "a2": 6,
    "a3": 7,
    "v0": 2,
    "v1": 3,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "s0": 16,
    "s1": 17,
    "s2": 18,
    "s3": 19,
    "fp": 30,
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


def addiu(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x09, REG[rs], REG[rt], imm)


def andi(rt: str, rs: str, imm: int) -> int:
    return ins_i(0x0C, REG[rs], REG[rt], imm)


def beq(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("beq", rs, rt, target)


def bne(rs: str, rt: str, target: str) -> tuple[str, str, str, str]:
    return ("bne", rs, rt, target)


def j(addr: int) -> int:
    return ins_j(0x02, addr)


def jal(addr: int) -> int:
    return ins_j(0x03, addr)


def jr(rs: str) -> int:
    return ins_r(REG[rs], 0, 0, 0, 0x08)


def lui(rt: str, imm: int) -> int:
    return ins_i(0x0F, 0, REG[rt], imm)


def lbu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x24, REG[rs], REG[rt], off)


def lhu(rt: str, off: int, rs: str) -> int:
    return ins_i(0x25, REG[rs], REG[rt], off)


def lw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x23, REG[rs], REG[rt], off)


def sw(rt: str, off: int, rs: str) -> int:
    return ins_i(0x2B, REG[rs], REG[rt], off)


def nop() -> int:
    return 0


def hi(addr: int) -> int:
    return (addr >> 16) & 0xFFFF


def hi_signed(addr: int) -> int:
    return ((addr + 0x8000) >> 16) & 0xFFFF


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


def old_player_cop_id_check_items(
    success_label: str, fail_label: str
) -> list[int | str | tuple[str, str, str, str]]:
    # Previous version limited the feature to BMW/Porsche/Diablo cop cars.
    # Keep this only so the script can recognize and replace that old cave.
    player_car_data_addr = 0x80114878
    return [
        lui("t0", hi(player_car_data_addr)),
        lbu("t1", lo(player_car_data_addr), "t0"),
        addiu("t0", "zero", 0x18),
        beq("t1", "t0", success_label),
        nop(),
        addiu("t0", "zero", 0x1A),
        beq("t1", "t0", success_label),
        nop(),
        addiu("t0", "zero", 0x1B),
        bne("t1", "t0", fail_label),
        nop(),
    ]


def make_candidate_cave(
    *, default_enabled: bool, require_cop_id: bool, set_perp_marker: bool = True
) -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # 800F7A00 0001 enables this player-arrest candidate override.
        addiu("t0", "zero", 1 if default_enabled else 0),
        addiu("t0", "t0", -1),
        bne("t0", "zero", "stock"),
        nop(),
        lui("t0", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
        lw("t1", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t0"),
        nop(),
        bne("s2", "t1", "stock"),
        nop(),
        # Do not let the player car arrest itself. In Single Race the optional
        # crime guard lets player/opponent AIHigh_Player objects reach this
        # check, so the checked perp may be the player too.
        lw("t0", 0x0000, "s3"),
        nop(),
        beq("t0", "t1", "stock"),
        nop(),
        *(old_player_cop_id_check_items("accept", "stock") if require_cop_id else []),
        "accept",
        *(
            [
                lui("t0", hi_signed(PLAYER_BUST_PERP_MARKER_ADDR)),
                sw("s3", lo(PLAYER_BUST_PERP_MARKER_ADDR), "t0"),
            ]
            if set_perp_marker
            else []
        ),
        # Skip stock cop-flag and speechSource checks, but keep the later
        # active/flight/speed/distance checks for a real arrest window.
        j(CANDIDATE_RETURN_ACCEPT),
        nop(),
        "stock",
        j(CANDIDATE_RETURN_STOCK),
        nop(),
    ]
    blob = pack_labeled(items, CANDIDATE_CAVE_ADDR)
    if len(blob) > CANDIDATE_CAVE_LEN:
        raise SystemExit(f"candidate cave too large: 0x{len(blob):X}")
    return blob + bytes(CANDIDATE_CAVE_LEN - len(blob))


def make_controls_cave(
    *,
    default_enabled: bool,
    require_cop_id: bool,
    hud_signal: str = "none",
    flag_at_start: bool = True,
) -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # 800F7B00 0001 enables this player-arrest control override.
        addiu("t0", "zero", 1 if default_enabled else 0),
        addiu("t0", "t0", -1),
        bne("t0", "zero", "stock"),
        nop(),
        # Hook delay slot already executes stock: lui v0,0x8011.
        lw("v1", 0x0D0C, "v0"),
    ]
    if not flag_at_start:
        # Legacy layout used during earlier experiments: the stock lw came
        # first, so the printed 800F7B00 code did not actually touch the flag.
        items = [
            lw("v1", 0x0D0C, "v0"),
            addiu("t0", "zero", 1 if default_enabled else 0),
            addiu("t0", "t0", -1),
            bne("t0", "zero", "stock"),
            nop(),
        ]

    items += [
        beq("v1", "zero", "stock"),
        nop(),
        *(old_player_cop_id_check_items("check_controls", "stock") if require_cop_id else []),
        "check_controls",
        lhu("t0", 0x043C, "v1"),
        nop(),
        bne("t0", "zero", "return_one"),
        addiu("v1", "v1", 0x043C),
        lbu("t0", 0x0009, "v1"),
        addiu("t1", "zero", 1),
        beq("t0", "t1", "return_one"),
        nop(),
        "stock",
        *( [lw("v1", 0x0D0C, "v0")] if flag_at_start else [] ),
        j(CONTROLS_RETURN_STOCK),
        nop(),
        "return_one",
        *(
            [
                # Show the same caught overlay used by the real HumanCop HUD
                # path. s3 is the current AIHigh_BTC_Perp/BasicPerp object;
                # +0 holds carObj, carObj+0x288 is carInfo, +0x5C is driver.
                addiu("sp", "sp", -8),
                sw("ra", 4, "sp"),
                lw("t0", 0x0000, "s3"),
                nop(),
                lw("t0", 0x0288, "t0"),
                addiu("a0", "zero", 0),
                addiu("a2", "zero", 1),
                addiu("a3", "zero", 0),
                jal(HUD_BUSTED_OVERLAY_ON_ADDR),
                addiu("a1", "t0", 0x005C),
                lw("ra", 4, "sp"),
                addiu("sp", "sp", 8),
            ]
            if hud_signal == "busted_overlay"
            else []
        ),
        *(
            [
                # Legacy no-op visual test that used the wingman HUD channel.
                addiu("sp", "sp", -8),
                sw("ra", 4, "sp"),
                addiu("a0", "zero", 0),
                addiu("a1", "zero", 8),
                jal(0x800D6B8C),
                nop(),
                lw("ra", 4, "sp"),
                addiu("sp", "sp", 8),
            ]
            if hud_signal == "wingman"
            else []
        ),
        jr("ra"),
        addiu("v0", "zero", 1),
    ]
    blob = pack_labeled(items, CONTROLS_CAVE_ADDR)
    if len(blob) > CONTROLS_CAVE_LEN:
        raise SystemExit(f"controls cave too large: 0x{len(blob):X}")
    return blob + bytes(CONTROLS_CAVE_LEN - len(blob))


def player_arrest_gate_items(
    success_label: str, fail_label: str, *, gate: str = "marker"
) -> list[int | str | tuple[str, str, str, str]]:
    if gate == "last_arresting_cop":
        return [
            lui("t0", hi(CANDIDATE_CAVE_ADDR)),
            lhu("t0", lo(CANDIDATE_CAVE_ADDR), "t0"),
            addiu("t0", "t0", -1),
            bne("t0", "zero", fail_label),
            nop(),
            lw("t0", 0x006C, "s0"),  # lastArrestingCop_
            lui("t1", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
            lw("t1", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t1"),
            nop(),
            bne("t0", "t1", fail_label),
            nop(),
            success_label,
        ]
    return [
        lui("t0", hi(CANDIDATE_CAVE_ADDR)),
        lhu("t0", lo(CANDIDATE_CAVE_ADDR), "t0"),
        addiu("t0", "t0", -1),
        bne("t0", "zero", fail_label),
        nop(),
        lui("t0", hi_signed(PLAYER_BUST_PERP_MARKER_ADDR)),
        lw("t1", lo(PLAYER_BUST_PERP_MARKER_ADDR), "t0"),
        nop(),
        bne("s0", "t1", fail_label),
        nop(),
        success_label,
    ]


def make_pullover_start_cave(*, mode: str = "perp_overlay", gate: str = "marker") -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Hook delay slot already executes stock: addiu v0,zero,0x60.
        sw("v0", 0x0064, "s0"),
        lui("v0", 0x8012),
        lw("v1", -0x0C98, "v0"),
        addiu("v0", "zero", 2),
        sw("v0", 0x0018, "s0"),
        sw("v1", 0x0068, "s0"),
        *player_arrest_gate_items("show_banner", "done", gate=gate),
        *(
            [
                lui(
                    "t0",
                    hi_signed(PERP_OVERLAY_ON_0_ADDR)
                    if mode in {"perp_overlay", "perp_overlay_hud_route", "perp_overlay_no_hud_route"}
                    else hi(PERP_OVERLAY_ON_0_ADDR),
                ),
                addiu("t1", "zero", 1),
                sw("t1", lo(PERP_OVERLAY_ON_0_ADDR), "t0"),
                # Message 1 reuses the stock "busted/arrest" short banner text.
                sw("t1", lo(PERP_OVERLAY_MESSAGE_0_ADDR), "t0"),
                *([sw("t1", 0x18FC, "gp")] if mode == "perp_overlay_hud_route" else []),
            ]
            if mode in {
                "perp_overlay",
                "perp_overlay_hud_route",
                "perp_overlay_no_hud_route",
                "perp_overlay_wrong_hi",
            }
            else []
        ),
        *(
            [
                addiu("sp", "sp", -8),
                sw("ra", 4, "sp"),
                lw("t0", 0x0000, "s0"),
                nop(),
                lw("t0", 0x0288, "t0"),
                nop(),
                addiu("a0", "t0", 0x005C),
                addiu("a1", "zero", 0),
                jal(HUD_BTC_UPDATE_ADDR),
                addiu("a2", "zero", 1),
                lw("t0", 0x0000, "s0"),
                nop(),
                lw("t0", 0x0288, "t0"),
                addiu("a0", "zero", 0),
                addiu("a2", "zero", 1),
                addiu("a3", "zero", 0),
                jal(HUD_BUSTED_OVERLAY_ON_ADDR),
                addiu("a1", "t0", 0x005C),
                lw("ra", 4, "sp"),
                addiu("sp", "sp", 8),
            ]
            if mode == "btc_overlay"
            else []
        ),
        "done",
        j(PULLOVER_START_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, PULLOVER_START_CAVE_ADDR)
    if len(blob) > PULLOVER_START_CAVE_LEN:
        raise SystemExit(f"pullover start cave too large: 0x{len(blob):X}")
    return blob + bytes(PULLOVER_START_CAVE_LEN - len(blob))


def make_pullover_complete_cave(
    *, mode: str = "perp_overlay", gate: str = "marker", clear_marker: bool = True
) -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        *player_arrest_gate_items("hide_banner", "original", gate=gate),
        *(
            [
                lui(
                    "t0",
                    hi_signed(PERP_OVERLAY_ON_0_ADDR)
                    if mode in {"perp_overlay", "perp_overlay_hud_route", "perp_overlay_no_hud_route"}
                    else hi(PERP_OVERLAY_ON_0_ADDR),
                ),
                sw("zero", lo(PERP_OVERLAY_ON_0_ADDR), "t0"),
                *([sw("zero", 0x18FC, "gp")] if mode == "perp_overlay_hud_route" else []),
                *(
                    [
                        lui("t0", hi_signed(PLAYER_BUST_PERP_MARKER_ADDR)),
                        sw("zero", lo(PLAYER_BUST_PERP_MARKER_ADDR), "t0"),
                    ]
                    if clear_marker
                    else []
                ),
            ]
            if mode in {
                "perp_overlay",
                "perp_overlay_hud_route",
                "perp_overlay_no_hud_route",
                "perp_overlay_wrong_hi",
            }
            else []
        ),
        *(
            [
                addiu("sp", "sp", -8),
                sw("ra", 4, "sp"),
                jal(HUD_BUSTED_OVERLAY_OFF_ADDR),
                nop(),
                sw("zero", 0x18FC, "gp"),
                lw("ra", 4, "sp"),
                addiu("sp", "sp", 8),
            ]
            if mode == "btc_overlay"
            else []
        ),
        "original",
        lw("v0", 0x0000, "s0"),
        nop(),
        sw("zero", 0x0278, "v0"),
        sw("zero", 0x0018, "s0"),
        sw("s1", 0x007C, "s0"),
        j(PULLOVER_COMPLETE_RETURN_ADDR),
        sw("zero", 0x0080, "s0"),
    ]
    blob = pack_labeled(items, PULLOVER_COMPLETE_CAVE_ADDR)
    if len(blob) > PULLOVER_COMPLETE_CAVE_LEN:
        raise SystemExit(f"pullover complete cave too large: 0x{len(blob):X}")
    return blob + bytes(PULLOVER_COMPLETE_CAVE_LEN - len(blob))


def make_player_speech_bust_cave(*, mode: str = "marker_overlay") -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Hook delay slot already set a1=1 (PULLOVER_BUST message).
        lui("t0", hi_signed(PLAYER_BUST_PERP_MARKER_ADDR)),
        lw("t1", lo(PLAYER_BUST_PERP_MARKER_ADDR), "t0"),
        nop(),
        bne("s0", "t1", "stock"),
        nop(),
        *(
            [
                lui("t0", hi_signed(PERP_OVERLAY_ON_0_ADDR)),
                addiu("t1", "zero", 1),
                sw("t1", lo(PERP_OVERLAY_ON_0_ADDR), "t0"),
                sw("t1", lo(PERP_OVERLAY_MESSAGE_0_ADDR), "t0"),
                *([sw("t1", 0x18FC, "gp")] if mode == "marker_overlay_hud_route" else []),
            ]
            if mode in {"marker_overlay", "marker_overlay_hud_route"}
            else []
        ),
        j(PLAYER_SPEECH_BUST_RETURN_ADDR),
        nop(),
        "stock",
        addiu("sp", "sp", -8),
        sw("ra", 4, "sp"),
        jal(0x800DA510),
        nop(),
        lw("ra", 4, "sp"),
        addiu("sp", "sp", 8),
        j(PLAYER_SPEECH_BUST_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, PLAYER_SPEECH_BUST_CAVE_ADDR)
    if len(blob) > PLAYER_SPEECH_BUST_CAVE_LEN:
        raise SystemExit(f"player speech bust cave too large: 0x{len(blob):X}")
    return blob + bytes(PLAYER_SPEECH_BUST_CAVE_LEN - len(blob))


def make_player_complete_cave(*, mode: str = "marker_overlay") -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Hook delay slot already executed stock: lw v0,0(s1).
        lui("t0", hi_signed(PLAYER_BUST_PERP_MARKER_ADDR)),
        lw("t1", lo(PLAYER_BUST_PERP_MARKER_ADDR), "t0"),
        nop(),
        bne("s1", "t1", "done"),
        nop(),
        *(
            [
                lui("t0", hi_signed(PERP_OVERLAY_ON_0_ADDR)),
                sw("zero", lo(PERP_OVERLAY_ON_0_ADDR), "t0"),
                *([sw("zero", 0x18FC, "gp")] if mode == "marker_overlay_hud_route" else []),
                lui("t0", hi_signed(PLAYER_BUST_PERP_MARKER_ADDR)),
                sw("zero", lo(PLAYER_BUST_PERP_MARKER_ADDR), "t0"),
            ]
            if mode in {"marker_overlay", "marker_overlay_hud_route"}
            else []
        ),
        "done",
        j(PLAYER_COMPLETE_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, PLAYER_COMPLETE_CAVE_ADDR)
    if len(blob) > PLAYER_COMPLETE_CAVE_LEN:
        raise SystemExit(f"player complete cave too large: 0x{len(blob):X}")
    return blob + bytes(PLAYER_COMPLETE_CAVE_LEN - len(blob))


def make_no_cops_guard_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Original condition: no cop cars means HandleCops returns immediately.
        # For Single Race, let the existing player-arrest cheat provide the
        # "human cop" source even when there are no AI cop cars in the race.
        bne("v0", "zero", "continue"),
        nop(),
        lui("t0", hi(CANDIDATE_CAVE_ADDR)),
        lhu("t0", lo(CANDIDATE_CAVE_ADDR), "t0"),
        nop(),
        beq("t0", "zero", "return"),
        nop(),
        "continue",
        j(NO_COPS_GUARD_CONTINUE_ADDR),
        nop(),
        "return",
        j(NO_COPS_GUARD_RETURN_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, NO_COPS_GUARD_CAVE_ADDR)
    if len(blob) > NO_COPS_GUARD_CAVE_LEN:
        raise SystemExit(f"no-cops guard cave too large: 0x{len(blob):X}")
    return blob + bytes(NO_COPS_GUARD_CAVE_LEN - len(blob))


def make_crime_guard_cave() -> bytes:
    items: list[int | str | tuple[str, str, str, str]] = [
        # Hook delay slot already executes stock: lw v0,0x78(s3).
        lui("t0", hi(CANDIDATE_CAVE_ADDR)),
        lhu("t0", lo(CANDIDATE_CAVE_ADDR), "t0"),
        nop(),
        beq("t0", "zero", "stock"),
        nop(),
        # While the optional player-arrest cheat is active, the player car is
        # never a valid perp. This prevents AI cops from busting the player when
        # the Single Race crime bypass is enabled for AI racers.
        lui("t1", hi(PLAYER_CAR_OBJ_PTR_ADDR)),
        lw("t1", lo(PLAYER_CAR_OBJ_PTR_ADDR), "t1"),
        lw("t2", 0x0000, "s3"),
        nop(),
        beq("t2", "t1", "return_zero"),
        nop(),
        # If the optional player-arrest cheat is on, let Single Race AI racers
        # pass the crime_ != CRIME_NONE gate and use the normal caught tests.
        j(CRIME_GUARD_CONTINUE_ADDR),
        lui("v0", 0x8011),
        "stock",
        bne("v0", "zero", "continue"),
        nop(),
        j(CRIME_GUARD_RETURN_ZERO_ADDR),
        nop(),
        "continue",
        j(CRIME_GUARD_CONTINUE_ADDR),
        lui("v0", 0x8011),
        "return_zero",
        j(CRIME_GUARD_RETURN_ZERO_ADDR),
        nop(),
    ]
    blob = pack_labeled(items, CRIME_GUARD_CAVE_ADDR)
    if len(blob) > CRIME_GUARD_CAVE_LEN:
        raise SystemExit(f"crime guard cave too large: 0x{len(blob):X}")
    return blob + bytes(CRIME_GUARD_CAVE_LEN - len(blob))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: optional cheat lets player bust AI racers in Hot Pursuit and Single Race."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    candidate_hook = pack([j(CANDIDATE_CAVE_ADDR), lw("v0", 0x0260, "s2")])
    controls_hook = pack([j(CONTROLS_CAVE_ADDR), lui("v0", 0x8011)])
    crime_guard_hook = pack([j(CRIME_GUARD_CAVE_ADDR), lw("v0", 0x0078, "s3")])
    no_cops_guard_hook = pack([j(NO_COPS_GUARD_CAVE_ADDR), nop()])
    candidate_cave = make_candidate_cave(
        default_enabled=False, require_cop_id=False, set_perp_marker=False
    )
    controls_cave = make_controls_cave(
        default_enabled=False, require_cop_id=False, hud_signal="none"
    )
    previous_controls_cave = make_controls_cave(
        default_enabled=False, require_cop_id=False, hud_signal="none", flag_at_start=False
    )
    previous_controls_cave_hud_wrong_flag = make_controls_cave(
        default_enabled=False,
        require_cop_id=False,
        hud_signal="busted_overlay",
        flag_at_start=False,
    )
    previous_controls_cave_busted = make_controls_cave(
        default_enabled=False, require_cop_id=False, hud_signal="busted_overlay"
    )
    previous_controls_cave_wingman = make_controls_cave(
        default_enabled=False, require_cop_id=False, hud_signal="wingman"
    )
    previous_controls_cave_wingman_wrong_flag = make_controls_cave(
        default_enabled=False, require_cop_id=False, hud_signal="wingman", flag_at_start=False
    )
    crime_guard_cave = make_crime_guard_cave()
    previous_crime_guard_cave = bytes.fromhex(
        "06 00 40 14 00 00 00 00 0f 80 08 3c 00 7a 08 95"
        "00 00 00 00 03 00 00 11 00 00 00 00 fe 6f 01 08"
        "11 80 02 3c 4e 71 01 08 00 00 00 00"
    ) + bytes(CRIME_GUARD_CAVE_LEN - 0x2C)
    no_cops_guard_cave = make_no_cops_guard_cave()
    pullover_start_hook = pack([j(PULLOVER_START_CAVE_ADDR), addiu("v0", "zero", 0x60)])
    pullover_start_cave = make_pullover_start_cave()
    previous_pullover_start_cave_hud_route = make_pullover_start_cave(
        mode="perp_overlay_hud_route"
    )
    previous_pullover_start_cave_last_gate = make_pullover_start_cave(
        gate="last_arresting_cop"
    )
    previous_pullover_start_cave_no_hud_route = make_pullover_start_cave(
        mode="perp_overlay_no_hud_route"
    )
    previous_pullover_start_cave_no_hud_route_last_gate = make_pullover_start_cave(
        mode="perp_overlay_no_hud_route", gate="last_arresting_cop"
    )
    previous_pullover_start_cave_wrong_hi = make_pullover_start_cave(mode="perp_overlay_wrong_hi")
    previous_pullover_start_cave_btc = make_pullover_start_cave(mode="btc_overlay")
    pullover_complete_hook = pack([j(PULLOVER_COMPLETE_CAVE_ADDR), nop()])
    pullover_complete_cave = make_pullover_complete_cave()
    previous_pullover_complete_cave_hud_route = make_pullover_complete_cave(
        mode="perp_overlay_hud_route"
    )
    previous_pullover_complete_cave_last_gate = make_pullover_complete_cave(
        gate="last_arresting_cop"
    )
    previous_pullover_complete_cave_last_gate_no_marker_clear = make_pullover_complete_cave(
        gate="last_arresting_cop", clear_marker=False
    )
    previous_pullover_complete_cave_no_hud_route = make_pullover_complete_cave(
        mode="perp_overlay_no_hud_route"
    )
    previous_pullover_complete_cave_no_hud_route_last_gate = make_pullover_complete_cave(
        mode="perp_overlay_no_hud_route", gate="last_arresting_cop"
    )
    previous_pullover_complete_cave_wrong_hi = make_pullover_complete_cave(
        mode="perp_overlay_wrong_hi"
    )
    previous_pullover_complete_cave_btc = make_pullover_complete_cave(mode="btc_overlay")
    player_speech_bust_hook = pack([j(PLAYER_SPEECH_BUST_CAVE_ADDR), addiu("a1", "zero", 1)])
    player_speech_bust_cave = make_player_speech_bust_cave()
    previous_player_speech_bust_cave_hud_route = make_player_speech_bust_cave(
        mode="marker_overlay_hud_route"
    )
    player_complete_hook = pack([j(PLAYER_COMPLETE_CAVE_ADDR), lw("v0", 0x0000, "s1")])
    player_complete_cave = make_player_complete_cave()
    previous_player_complete_cave_hud_route = make_player_complete_cave(
        mode="marker_overlay_hud_route"
    )
    old_candidate_cave = make_candidate_cave(default_enabled=True, require_cop_id=True)
    old_candidate_cave_no_marker = make_candidate_cave(
        default_enabled=True, require_cop_id=True, set_perp_marker=False
    )
    old_controls_cave = make_controls_cave(default_enabled=True, require_cop_id=True)
    previous_candidate_cave_no_marker = make_candidate_cave(
        default_enabled=False, require_cop_id=False, set_perp_marker=False
    )
    previous_candidate_cave = bytes.fromhex(
        "00 00 08 24 ff ff 08 25 08 00 00 15 00 00 00 00"
        "11 80 08 3c 0c 0d 09 8d 00 00 00 00 03 00 49 16"
        "00 00 00 00 71 70 01 08 00 00 00 00 66 70 01 08"
        "00 00 00 00"
    ) + bytes(CANDIDATE_CAVE_LEN - 0x34)

    current_candidate_hook = bytes(data[CANDIDATE_HOOK_OFF : CANDIDATE_HOOK_OFF + 8])
    if current_candidate_hook not in {CANDIDATE_STOCK, candidate_hook}:
        raise SystemExit(
            f"unexpected candidate hook bytes at 0x{CANDIDATE_HOOK_OFF:X}: "
            f"{current_candidate_hook.hex(' ')}"
        )

    current_controls_hook = bytes(data[CONTROLS_HOOK_OFF : CONTROLS_HOOK_OFF + 8])
    if current_controls_hook not in {CONTROLS_STOCK, controls_hook}:
        raise SystemExit(
            f"unexpected controls hook bytes at 0x{CONTROLS_HOOK_OFF:X}: "
            f"{current_controls_hook.hex(' ')}"
        )

    current_crime_guard_hook = bytes(data[CRIME_GUARD_HOOK_OFF : CRIME_GUARD_HOOK_OFF + 8])
    if current_crime_guard_hook not in {CRIME_GUARD_STOCK, crime_guard_hook}:
        raise SystemExit(
            f"unexpected crime guard hook bytes at 0x{CRIME_GUARD_HOOK_OFF:X}: "
            f"{current_crime_guard_hook.hex(' ')}"
        )

    current_candidate_cave = bytes(data[CANDIDATE_CAVE_OFF : CANDIDATE_CAVE_OFF + CANDIDATE_CAVE_LEN])
    if current_candidate_cave not in {
        bytes(CANDIDATE_CAVE_LEN),
        candidate_cave,
        previous_candidate_cave_no_marker,
        old_candidate_cave,
        old_candidate_cave_no_marker,
        previous_candidate_cave,
    }:
        raise SystemExit(f"candidate cave is not empty/known at 0x{CANDIDATE_CAVE_OFF:X}")

    current_controls_cave = bytes(data[CONTROLS_CAVE_OFF : CONTROLS_CAVE_OFF + CONTROLS_CAVE_LEN])
    if current_controls_cave not in {
        bytes(CONTROLS_CAVE_LEN),
        controls_cave,
        previous_controls_cave,
        previous_controls_cave_busted,
        previous_controls_cave_hud_wrong_flag,
        previous_controls_cave_wingman,
        previous_controls_cave_wingman_wrong_flag,
        old_controls_cave,
    }:
        raise SystemExit(f"controls cave is not empty/known at 0x{CONTROLS_CAVE_OFF:X}")

    current_crime_guard_cave = bytes(data[CRIME_GUARD_CAVE_OFF : CRIME_GUARD_CAVE_OFF + CRIME_GUARD_CAVE_LEN])
    if current_crime_guard_cave not in {
        bytes(CRIME_GUARD_CAVE_LEN),
        crime_guard_cave,
        previous_crime_guard_cave,
    }:
        raise SystemExit(f"crime guard cave is not empty/known at 0x{CRIME_GUARD_CAVE_OFF:X}")

    current_no_cops_guard_hook = bytes(data[NO_COPS_GUARD_HOOK_OFF : NO_COPS_GUARD_HOOK_OFF + 8])
    if current_no_cops_guard_hook not in {NO_COPS_GUARD_STOCK, no_cops_guard_hook}:
        raise SystemExit(
            f"unexpected no-cops guard hook bytes at 0x{NO_COPS_GUARD_HOOK_OFF:X}: "
            f"{current_no_cops_guard_hook.hex(' ')}"
        )

    current_no_cops_guard_cave = bytes(
        data[NO_COPS_GUARD_CAVE_OFF : NO_COPS_GUARD_CAVE_OFF + NO_COPS_GUARD_CAVE_LEN]
    )
    if current_no_cops_guard_cave not in {bytes(NO_COPS_GUARD_CAVE_LEN), no_cops_guard_cave}:
        raise SystemExit(f"no-cops guard cave is not empty/known at 0x{NO_COPS_GUARD_CAVE_OFF:X}")

    current_player_speech_bust_hook = bytes(
        data[PLAYER_SPEECH_BUST_HOOK_OFF : PLAYER_SPEECH_BUST_HOOK_OFF + 8]
    )
    if current_player_speech_bust_hook not in {PLAYER_SPEECH_BUST_STOCK, player_speech_bust_hook}:
        raise SystemExit(
            f"unexpected player speech bust hook bytes at 0x{PLAYER_SPEECH_BUST_HOOK_OFF:X}: "
            f"{current_player_speech_bust_hook.hex(' ')}"
        )
    current_player_speech_bust_cave = bytes(
        data[PLAYER_SPEECH_BUST_CAVE_OFF : PLAYER_SPEECH_BUST_CAVE_OFF + PLAYER_SPEECH_BUST_CAVE_LEN]
    )
    if current_player_speech_bust_cave not in {
        bytes(PLAYER_SPEECH_BUST_CAVE_LEN),
        player_speech_bust_cave,
        previous_player_speech_bust_cave_hud_route,
    }:
        raise SystemExit(
            f"player speech bust cave is not empty/known at 0x{PLAYER_SPEECH_BUST_CAVE_OFF:X}"
        )

    current_player_complete_hook = bytes(
        data[PLAYER_COMPLETE_HOOK_OFF : PLAYER_COMPLETE_HOOK_OFF + 8]
    )
    if current_player_complete_hook not in {PLAYER_COMPLETE_STOCK, player_complete_hook}:
        raise SystemExit(
            f"unexpected player complete hook bytes at 0x{PLAYER_COMPLETE_HOOK_OFF:X}: "
            f"{current_player_complete_hook.hex(' ')}"
        )
    current_player_complete_cave = bytes(
        data[PLAYER_COMPLETE_CAVE_OFF : PLAYER_COMPLETE_CAVE_OFF + PLAYER_COMPLETE_CAVE_LEN]
    )
    if current_player_complete_cave not in {
        bytes(PLAYER_COMPLETE_CAVE_LEN),
        player_complete_cave,
        previous_player_complete_cave_hud_route,
    }:
        raise SystemExit(
            f"player complete cave is not empty/known at 0x{PLAYER_COMPLETE_CAVE_OFF:X}"
        )

    current_pullover_start_hook = bytes(
        data[PULLOVER_START_HOOK_OFF : PULLOVER_START_HOOK_OFF + 8]
    )
    if current_pullover_start_hook not in {PULLOVER_START_STOCK_PREFIX, pullover_start_hook}:
        raise SystemExit(
            f"unexpected pullover start hook bytes at 0x{PULLOVER_START_HOOK_OFF:X}: "
            f"{current_pullover_start_hook.hex(' ')}"
        )

    current_pullover_start_cave = bytes(
        data[PULLOVER_START_CAVE_OFF : PULLOVER_START_CAVE_OFF + PULLOVER_START_CAVE_LEN]
    )
    if current_pullover_start_cave not in {
        bytes(PULLOVER_START_CAVE_LEN),
        pullover_start_cave,
        previous_pullover_start_cave_hud_route,
        previous_pullover_start_cave_last_gate,
        previous_pullover_start_cave_no_hud_route,
        previous_pullover_start_cave_no_hud_route_last_gate,
        previous_pullover_start_cave_wrong_hi,
        previous_pullover_start_cave_btc,
    }:
        raise SystemExit(f"pullover start cave is not empty/known at 0x{PULLOVER_START_CAVE_OFF:X}")

    current_pullover_complete_hook = bytes(
        data[PULLOVER_COMPLETE_HOOK_OFF : PULLOVER_COMPLETE_HOOK_OFF + 8]
    )
    if current_pullover_complete_hook not in {
        PULLOVER_COMPLETE_STOCK_PREFIX,
        pullover_complete_hook,
    }:
        raise SystemExit(
            f"unexpected pullover complete hook bytes at 0x{PULLOVER_COMPLETE_HOOK_OFF:X}: "
            f"{current_pullover_complete_hook.hex(' ')}"
        )

    current_pullover_complete_cave = bytes(
        data[PULLOVER_COMPLETE_CAVE_OFF : PULLOVER_COMPLETE_CAVE_OFF + PULLOVER_COMPLETE_CAVE_LEN]
    )
    if current_pullover_complete_cave not in {
        bytes(PULLOVER_COMPLETE_CAVE_LEN),
        pullover_complete_cave,
        previous_pullover_complete_cave_hud_route,
        previous_pullover_complete_cave_last_gate,
        previous_pullover_complete_cave_last_gate_no_marker_clear,
        previous_pullover_complete_cave_no_hud_route,
        previous_pullover_complete_cave_no_hud_route_last_gate,
        previous_pullover_complete_cave_wrong_hi,
        previous_pullover_complete_cave_btc,
    }:
        raise SystemExit(
            f"pullover complete cave is not empty/known at 0x{PULLOVER_COMPLETE_CAVE_OFF:X}"
        )

    if args.revert:
        data[CANDIDATE_HOOK_OFF : CANDIDATE_HOOK_OFF + 8] = CANDIDATE_STOCK
        data[CONTROLS_HOOK_OFF : CONTROLS_HOOK_OFF + 8] = CONTROLS_STOCK
        data[CRIME_GUARD_HOOK_OFF : CRIME_GUARD_HOOK_OFF + 8] = CRIME_GUARD_STOCK
        data[CANDIDATE_CAVE_OFF : CANDIDATE_CAVE_OFF + CANDIDATE_CAVE_LEN] = bytes(CANDIDATE_CAVE_LEN)
        data[CONTROLS_CAVE_OFF : CONTROLS_CAVE_OFF + CONTROLS_CAVE_LEN] = bytes(CONTROLS_CAVE_LEN)
        data[CRIME_GUARD_CAVE_OFF : CRIME_GUARD_CAVE_OFF + CRIME_GUARD_CAVE_LEN] = bytes(
            CRIME_GUARD_CAVE_LEN
        )
        data[NO_COPS_GUARD_HOOK_OFF : NO_COPS_GUARD_HOOK_OFF + 8] = NO_COPS_GUARD_STOCK
        data[NO_COPS_GUARD_CAVE_OFF : NO_COPS_GUARD_CAVE_OFF + NO_COPS_GUARD_CAVE_LEN] = bytes(
            NO_COPS_GUARD_CAVE_LEN
        )
        data[PULLOVER_START_HOOK_OFF : PULLOVER_START_HOOK_OFF + len(PULLOVER_START_STOCK_FULL)] = (
            PULLOVER_START_STOCK_FULL
        )
        data[PULLOVER_START_CAVE_OFF : PULLOVER_START_CAVE_OFF + PULLOVER_START_CAVE_LEN] = bytes(
            PULLOVER_START_CAVE_LEN
        )
        data[
            PULLOVER_COMPLETE_HOOK_OFF : PULLOVER_COMPLETE_HOOK_OFF + len(PULLOVER_COMPLETE_STOCK_FULL)
        ] = PULLOVER_COMPLETE_STOCK_FULL
        data[
            PULLOVER_COMPLETE_CAVE_OFF : PULLOVER_COMPLETE_CAVE_OFF + PULLOVER_COMPLETE_CAVE_LEN
        ] = bytes(PULLOVER_COMPLETE_CAVE_LEN)
        data[PLAYER_SPEECH_BUST_HOOK_OFF : PLAYER_SPEECH_BUST_HOOK_OFF + 8] = (
            PLAYER_SPEECH_BUST_STOCK
        )
        data[
            PLAYER_SPEECH_BUST_CAVE_OFF : PLAYER_SPEECH_BUST_CAVE_OFF + PLAYER_SPEECH_BUST_CAVE_LEN
        ] = bytes(PLAYER_SPEECH_BUST_CAVE_LEN)
        data[PLAYER_COMPLETE_HOOK_OFF : PLAYER_COMPLETE_HOOK_OFF + 8] = PLAYER_COMPLETE_STOCK
        data[PLAYER_COMPLETE_CAVE_OFF : PLAYER_COMPLETE_CAVE_OFF + PLAYER_COMPLETE_CAVE_LEN] = bytes(
            PLAYER_COMPLETE_CAVE_LEN
        )
    else:
        data[CANDIDATE_CAVE_OFF : CANDIDATE_CAVE_OFF + CANDIDATE_CAVE_LEN] = candidate_cave
        data[CONTROLS_CAVE_OFF : CONTROLS_CAVE_OFF + CONTROLS_CAVE_LEN] = controls_cave
        data[CRIME_GUARD_CAVE_OFF : CRIME_GUARD_CAVE_OFF + CRIME_GUARD_CAVE_LEN] = crime_guard_cave
        data[NO_COPS_GUARD_CAVE_OFF : NO_COPS_GUARD_CAVE_OFF + NO_COPS_GUARD_CAVE_LEN] = no_cops_guard_cave
        data[PULLOVER_START_HOOK_OFF : PULLOVER_START_HOOK_OFF + len(PULLOVER_START_STOCK_FULL)] = (
            PULLOVER_START_STOCK_FULL
        )
        data[PULLOVER_START_CAVE_OFF : PULLOVER_START_CAVE_OFF + PULLOVER_START_CAVE_LEN] = bytes(
            PULLOVER_START_CAVE_LEN
        )
        data[
            PULLOVER_COMPLETE_HOOK_OFF : PULLOVER_COMPLETE_HOOK_OFF + len(PULLOVER_COMPLETE_STOCK_FULL)
        ] = PULLOVER_COMPLETE_STOCK_FULL
        data[
            PULLOVER_COMPLETE_CAVE_OFF : PULLOVER_COMPLETE_CAVE_OFF + PULLOVER_COMPLETE_CAVE_LEN
        ] = bytes(PULLOVER_COMPLETE_CAVE_LEN)
        data[PLAYER_SPEECH_BUST_HOOK_OFF : PLAYER_SPEECH_BUST_HOOK_OFF + 8] = (
            PLAYER_SPEECH_BUST_STOCK
        )
        data[
            PLAYER_SPEECH_BUST_CAVE_OFF : PLAYER_SPEECH_BUST_CAVE_OFF + PLAYER_SPEECH_BUST_CAVE_LEN
        ] = bytes(PLAYER_SPEECH_BUST_CAVE_LEN)
        data[PLAYER_COMPLETE_HOOK_OFF : PLAYER_COMPLETE_HOOK_OFF + 8] = PLAYER_COMPLETE_STOCK
        data[PLAYER_COMPLETE_CAVE_OFF : PLAYER_COMPLETE_CAVE_OFF + PLAYER_COMPLETE_CAVE_LEN] = bytes(
            PLAYER_COMPLETE_CAVE_LEN
        )
        data[CANDIDATE_HOOK_OFF : CANDIDATE_HOOK_OFF + 8] = candidate_hook
        data[CONTROLS_HOOK_OFF : CONTROLS_HOOK_OFF + 8] = controls_hook
        data[CRIME_GUARD_HOOK_OFF : CRIME_GUARD_HOOK_OFF + 8] = crime_guard_hook
        data[NO_COPS_GUARD_HOOK_OFF : NO_COPS_GUARD_HOOK_OFF + 8] = no_cops_guard_hook

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(exe)}")
    print("player bust AI racers: {}".format("reverted" if args.revert else "cheat-controlled, default off"))
    print("off codes:")
    print("  800F7A00 0000")
    print("  800F7B00 0000")
    print("optional on codes:")
    print("  800F7A00 0001")
    print("  800F7B00 0001")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
