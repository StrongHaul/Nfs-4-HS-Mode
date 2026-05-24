#!/usr/bin/env python3
from __future__ import annotations

import argparse
import struct
from pathlib import Path


BACKUP_SUFFIX = ".orig_player_physics_prod"

# Retail/PROD SLUS-00826 NFS4.EXE.  The offsets below are verified by
# signatures copied from the Feb 23, 1999 prototype/debug build.
#
# This patch intentionally avoids the QDA/CAR front-end data path: on this PS1
# build those edits did not affect live driving physics for the player.  The
# stable levers here are:
#   1. Physics_CalculateDerivedCarSpecs real mass + massInv calculation
#   2. road grip / grip-loss tables in the executable data segment
#   3. Physics_GetTorque return value
#
# The "police" mode keeps the tuned heavy-car collision mass, but uses softer
# torque/grip so the car stays controllable instead of feeling glued down.

PROD_EXE = Path(
    "PROD версия. Need For Speed IV - High Stakes [SLUS-00826][RUS][RGRStudio]"
) / "NFS4.EXE"

DERIVED_FUNC_SIG = bytes.fromhex(
    "e0 ff bd 27 14 00 b1 af 21 88 80 00 1c 00 bf af"
    " 18 00 b2 af 10 00 b0 af 64 04 24 8e 00 00 00 00"
    " f0 00 83 8c"
)
MASS_BLOCK_ORIGINAL = bytes.fromhex(
    # lui v0,0x0001; div v0,v1; bne v1,zero,+2; nop; break
    "01 00 02 3c 1a 00 43 00 02 00 60 14 00 00 00 00 0d 00 07 00"
)
MASS_BLOCK_OLD_MASSINV_PATCHES = [
    # Previous script versions changed only the massInv numerator.
    bytes.fromhex("00 c0 02 34 1a 00 43 00 02 00 60 14 00 00 00 00 0d 00 07 00"),
    bytes.fromhex("00 80 02 34 1a 00 43 00 02 00 60 14 00 00 00 00 0d 00 07 00"),
    bytes.fromhex("00 40 02 34 1a 00 43 00 02 00 60 14 00 00 00 00 0d 00 07 00"),
]
MASS_BLOCK_PATCHES = {
    # sll v1,v1,N; sw v1,0x00F0(a0); lui v0,0x0001; div v0,v1; nop
    "mild": bytes.fromhex("40 18 03 00 f0 00 83 ac 01 00 02 3c 1a 00 43 00 00 00 00 00"),
    "normal": bytes.fromhex("40 18 03 00 f0 00 83 ac 01 00 02 3c 1a 00 43 00 00 00 00 00"),
    "strong": bytes.fromhex("80 18 03 00 f0 00 83 ac 01 00 02 3c 1a 00 43 00 00 00 00 00"),
    "police": MASS_BLOCK_ORIGINAL,
}

GET_TORQUE_SIG = bytes.fromhex(
    "29 00 a6 28 02 00 c0 14 21 10 a0 00 28 00 02 24"
    " 04 00 40 18 21 18 00 00 02 00 c0 10 28 00 03 24"
    " 21 18 a0 00 64 04 82 8c 80 18 03 00 21 10 43 00"
    " 4c 00 42 8c 08 00 e0 03"
)
TORQUE_DELAY_ORIGINAL = bytes.fromhex("00 00 00 00")
TORQUE_PATCHES = {
    "mild": bytes.fromhex("00 00 00 00"),
    "normal": bytes.fromhex("00 00 00 00"),
    "strong": bytes.fromhex("40 10 02 00"),  # sll v0,v0,1
    "police": bytes.fromhex("40 10 02 00"),  # sll v0,v0,1
}
TORQUE_DELAY_OLD_PATCHES = [
    bytes.fromhex("40 10 02 00"),  # earlier police mode: x2 torque
    bytes.fromhex("00 10 42 24"),  # earlier soft boost: +0x1000
    bytes.fromhex("00 18 42 24"),  # earlier soft boost: +0x1800
    bytes.fromhex("00 40 42 24"),  # bad soft boost: breaks speedometer/gears
]

TORQUE_TABLE_MULT_SIG = bytes.fromhex(
    # Physics_CalculateDerivedCarSpecs scales all torque-table points with
    # fixed_mul(value, 0x12666). This is safer than touching Physics_GetTorque's
    # return delay slot because gear/speed display logic still sees sane data.
    "01 00 05 3c 64 04 22 8e 80 80 12 00 21 10 50 00"
    " 4c 00 44 8c c5 93 03 0c"
)
TORQUE_TABLE_MULT_SIG_PATCHED = bytes.fromhex(
    "02 00 05 3c 64 04 22 8e 80 80 12 00 21 10 50 00"
    " 4c 00 44 8c c5 93 03 0c"
)
TORQUE_TABLE_MULT_PATCHES = {
    "normal": bytes.fromhex("66 26 a5 34"),  # ori a1,a1,0x2666 -> 0x12666
    "strong": bytes.fromhex("33 33 a5 34"),  # 0x13333
    "police": bytes.fromhex("00 80 a5 34"),  # 0x18000 (with lui a1,0x0002 below)
}
TORQUE_TABLE_MULT_OLD_PATCHES = [
    bytes.fromhex("00 00 a5 34"),  # previous police value: 0x20000
    bytes.fromhex("00 40 a5 34"),  # previous police value: 0x14000
]
TORQUE_TABLE_LUI_PATCHES = {
    "normal": bytes.fromhex("01 00 05 3c"),
    "police": bytes.fromhex("02 00 05 3c"),
}

POWER_SPEED_CAP_PREFIX = bytes.fromhex(
    # In the power/drive-force function after Physics_GetTorque.
    "07 00 80 10 98 01 42 ae"
)
POWER_SPEED_CAP_PATCHES = {
    "normal_hi": bytes.fromhex("13 00 02 3c"),  # 0x13FFFF
    "police_hi": bytes.fromhex("18 00 02 3c"),  # 0x18FFFF
    "lo": bytes.fromhex("ff ff 42 34"),
}

HANDBRAKE_DRIFT_PREFIX = bytes.fromhex(
    # Physics_Real: when the brake/handbrake input byte is active and the
    # forward drive force is positive, the game boosts that force before the
    # tire/yaw integration.  Raising this one step makes handbrake entries
    # break loose more visibly without lowering normal road grip.
    "dc 44 42 8c 00 00 00 00 80 00 42 30 08 00 40 10"
    " 00 00 00 00 06 00 60 18 00 00 00 00 46 04 a2 92"
    " 00 00 00 00"
    " 02 00 40 10"
)
HANDBRAKE_DRIFT_ORIGINAL = bytes.fromhex("80 10 03 00")  # sll v0,v1,2 (x4)
HANDBRAKE_DRIFT_OLD_X8_PATCH = bytes.fromhex("c0 10 03 00")  # previous experiment: x8
HANDBRAKE_DRIFT_PATCH = HANDBRAKE_DRIFT_ORIGINAL

TIRE_SLIP_ENVELOPE_PREFIX = bytes.fromhex(
    # Physics_CalcTireForces clamp around the lateral tire-force/slip envelope.
    # Raising the clamp gives the body more room to yaw/slide before the tire
    # model snaps it back.  This is a bigger handling change than road grip.
    "35 00 40 10 00 00 00 00 ec b2 02 08 21 18 c0 00"
    " 02 00 01 06 21 18 00 02 23 18 03 00"
)
TIRE_SLIP_ENVELOPE_ORIGINAL_A1 = bytes.fromhex("00 80 05 34")  # ori a1,zero,0x8000
TIRE_SLIP_ENVELOPE_ORIGINAL_A0 = bytes.fromhex("00 80 04 34")  # ori a0,zero,0x8000
TIRE_SLIP_ENVELOPE_OLD_C000_A1 = bytes.fromhex("00 c0 05 34")  # previous drift experiment
TIRE_SLIP_ENVELOPE_OLD_C000_A0 = bytes.fromhex("00 c0 04 34")  # previous drift experiment
TIRE_SLIP_ENVELOPE_PATCH_A1 = TIRE_SLIP_ENVELOPE_ORIGINAL_A1
TIRE_SLIP_ENVELOPE_PATCH_A0 = TIRE_SLIP_ENVELOPE_ORIGINAL_A0

VISUAL_WHEEL_STEER_PATCHES = [
    # R3DCar visual steering reads.  These feed steering angle into car/wheel
    # render transforms; replacing them with zero keeps the wheels visually
    # straight while the physics still uses the real steering fields.
    (0xA1790, bytes.fromhex("50 04 b0 8e"), bytes.fromhex("21 80 00 00"), "visual wheel steer main"),
    (0xA1F84, bytes.fromhex("50 04 a2 8e"), bytes.fromhex("21 10 00 00"), "visual wheel steer part A"),
    (0xA1FFC, bytes.fromhex("50 04 b0 8e"), bytes.fromhex("21 80 00 00"), "visual wheel steer part B"),
]

STEERING_CONTROL_SCALE_PREFIX = bytes.fromhex(
    # abs(car->0x450) << 9 -> steeringControl. Raise to << 10.
    "50 04 22 8e 11 80 04 3c 02 00 41 04 00 00 00 00 23 10 02 00"
)
STEERING_CONTROL_SCALE_PATCHES = {
    "normal": bytes.fromhex("40 12 02 00"),  # sll v0,v0,9
    "police": bytes.fromhex("80 12 02 00"),  # sll v0,v0,10
}

STEERING_RATIO_USE_PREFIX = bytes.fromhex(
    # Physics uses gp+0x0DAC steering ratio/control after Physics_UpdateSuspension.
    "ac 0d 82 8f"
)
STEERING_RATIO_USE_NOP = bytes.fromhex("00 00 00 00")
STEERING_RATIO_USE_PATCH = bytes.fromhex("40 10 02 00")  # sll v0,v0,1
STEERING_RATIO_USE_OLD_SOFT_PATCH = bytes.fromhex("00 10 42 24")  # addiu v0,v0,0x1000
STEERING_RATIO_USE_OLD_MEDIUM_PATCH = bytes.fromhex("00 18 42 24")  # addiu v0,v0,0x1800
STEERING_RATIO_USE_OLD_STRONG_PATCH = bytes.fromhex("00 28 42 24")  # addiu v0,v0,0x2800
STEERING_RATIO_USE_SOFT_PATCH = bytes.fromhex("00 40 42 24")  # addiu v0,v0,0x4000
STEERING_RATIO_USE_POLICE = STEERING_RATIO_USE_SOFT_PATCH

STEERING_RATE_PREFIXES = [
    # Physics_CalculateDerivedCarSpecs bumps Car_tSpecs + 0x110 for steering
    # smoothing. Doubling the loaded value before the existing +1 makes the
    # ramp-to-desired steering much more direct without touching gear logic.
    bytes.fromhex("64 04 23 8e 00 00 00 00 10 01 62 8c"),
    bytes.fromhex("64 04 23 8e 00 00 00 00 10 01 62 8c 00 00 00 00 01 00 42 24"),
]
STEERING_RATE_NOP = bytes.fromhex("00 00 00 00")
STEERING_RATE_PATCH = bytes.fromhex("40 10 02 00")  # sll v0,v0,1

NEWTON_CAR_MASS_SIG = bytes.fromhex(
    # Normal car branch before Newton_InitBaseNewtonObj:
    # lw v0,0x0464(s0); nop; lw v0,0(v0); nop; bgez v0,+2; nop; addiu v0,0x7f; sra a2,v0,7
    "64 04 02 8e 00 00 00 00 00 00 42 8c 00 00 00 00"
    " 02 00 41 04 00 00 00 00 7f 00 42 24 c3 31 02 00"
)
NEWTON_CAR_MASS_ORIGINAL = bytes.fromhex(
    "64 04 02 8e 00 00 00 00 00 00 42 8c 00 00 00 00"
    " 02 00 41 04 00 00 00 00 7f 00 42 24 c3 31 02 00"
)
NEWTON_CAR_MASS_BAD_PATCHES = [
    bytes.fromhex(
        "11 00 06 3c 99 27 02 08 00 00 00 00 00 00 00 00"
        " 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
    ),
    bytes.fromhex(
        "19 00 06 3c 99 27 02 08 00 00 00 00 00 00 00 00"
        " 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
    ),
    bytes.fromhex(
        "20 00 06 3c 99 27 02 08 00 00 00 00 00 00 00 00"
        " 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
    ),
]
NEWTON_CAR_MASS_PATCHES = {
    # Earlier versions of this script forced this branch to a large constant.
    # That made map loading hang on hardware/emulator, so keep the original
    # branch and use safer cheat-flag/impulse tuning instead.
    "mild": NEWTON_CAR_MASS_ORIGINAL,
    "normal": NEWTON_CAR_MASS_ORIGINAL,
    "strong": NEWTON_CAR_MASS_ORIGINAL,
    "police": NEWTON_CAR_MASS_ORIGINAL,
}

ROAD_ORIGINAL = [
    0x11999,
    0x10CCC,
    0x10000,
    0x0F333,
    0x0E666,
    0x0D999,
    0x0CCCC,
    0x0C000,
    0x0B333,
    0x08000,
]
REVERSE_ORIGINAL = [
    0x0E8F5,
    0x0F333,
    0x10000,
    0x10D91,
    0x11C28,
    0x12D0E,
    0x14000,
    0x1547A,
    0x16E14,
    0x20000,
]
GRIP_LOSS_ORIGINAL = [0x20, 0x08, 0x08]
GRIP_LOSS_WET_ORIGINAL = [0x10, 0x06, 0x04]

GRIP_MULT = {
    "mild": 1.10,
    "normal": 1.18,
    "strong": 1.28,
    "police": 1.20,
}
LEGACY_GRIP_MULT = [1.40, 1.20, 1.08, 0.95]
GRIP_LOSS_PATCHES = {
    "mild": ([0x18, 0x06, 0x06], [0x0C, 0x05, 0x04]),
    "normal": ([0x14, 0x04, 0x04], [0x0A, 0x04, 0x03]),
    "strong": ([0x10, 0x03, 0x03], [0x08, 0x03, 0x02]),
    "police": ([0x14, 0x04, 0x04], [0x0A, 0x04, 0x03]),
}
LEGACY_GRIP_LOSS_PATCHES = [
    ([0x0C, 0x02, 0x02], [0x06, 0x02, 0x01]),
]

PEC_HEAVY_FLAG_OFF = 0x801144DC - 0x80010000 + 0x800
PEC_HEAVY_FLAG_PATCHES = {
    # 0x0002 enables the real Newton collision-mass cheat. 0x0008 raises the
    # RS control desired-position cap, making the car turn in a little harder.
    "mild": 0x0002,
    "normal": 0x0002,
    "strong": 0x000A,
    "police": 0x000A,
}

HEAVY_CHEAT_MASS_PREFIX = bytes.fromhex(
    # lw v0,0x44DC(v0); nop; andi v0,0x0002; beqz; nop;
    # lw v0,0x0260(s0); nop; andi v0,0x0004; beqz
    "dc 44 42 8c 00 00 00 00 02 00 42 30 08 00 40 10"
    " 00 00 00 00 60 02 02 8e 00 00 00 00 04 00 42 30"
    " 03 00 40 10"
)
HEAVY_CHEAT_MULT_PATCHES = {
    # These replace stock x5: sll v0,a2,2; addu v0,v0,a2.
    "1.5": bytes.fromhex("43 10 06 00 21 10 46 00"),  # sra v0,a2,1; addu v0,v0,a2
    2: bytes.fromhex("40 10 06 00 00 00 00 00"),  # sll v0,a2,1; nop
    3: bytes.fromhex("40 10 06 00 21 10 46 00"),  # sll v0,a2,1; addu v0,v0,a2
    4: bytes.fromhex("80 10 06 00 00 00 00 00"),  # sll v0,a2,2; nop
    5: bytes.fromhex("80 10 06 00 21 10 46 00"),  # stock PEC heavy car
}

TURN_CAP_PREFIX = bytes.fromhex(
    # In Physics_CalculateRSControlDesiredPosition, flag 0x0008 selects the
    # raised steering/RS desired-position cap.
    "08 00 42 30 07 00 40 10 21 18 64 00"
)
TURN_CAP_PATCHES = {
    "normal": bytes.fromhex("03 00 02 3c"),
    "strong": bytes.fromhex("04 00 02 3c"),
    "very_strong": bytes.fromhex("05 00 02 3c"),
}
TURN_CAP_STORE_PATCHES = {
    "normal": bytes.fromhex("03 00 03 3c"),
    "strong": bytes.fromhex("04 00 03 3c"),
    "very_strong": bytes.fromhex("05 00 03 3c"),
}

STEERING_STEP_PREFIX = bytes.fromhex(
    # Physics_CalculateRSControlDesiredPosition steering response steps.
    # Stock/current branch uses -0x64, -0xC8, +0xC8.
    "c9 00 62 2a 68 04 22 8e 21 a0 00 00"
)
STEERING_STEP_PATCHES = {
    "normal": {
        "small_neg": bytes.fromhex("9c ff 42 24"),  # addiu v0,v0,-0x64
        "full_neg": bytes.fromhex("38 ff 42 24"),  # addiu v0,v0,-0xC8
        "full_pos": bytes.fromhex("c8 00 42 24"),  # addiu v0,v0,+0xC8
    },
    "strong": {
        "small_neg": bytes.fromhex("60 ff 42 24"),  # addiu v0,v0,-0xA0
        "full_neg": bytes.fromhex("c0 fe 42 24"),  # addiu v0,v0,-0x140
        "full_pos": bytes.fromhex("40 01 42 24"),  # addiu v0,v0,+0x140
    },
}

HUMAN_STEER_INPUT_PATCHES = {
    "normal": bytes.fromhex("80 10 02 00"),  # sll v0,v0,2
    "strong": bytes.fromhex("c0 10 02 00"),  # sll v0,v0,3
}
HUMAN_STEER_INPUT_PATTERNS = [
    # Replay/scripted input branch: addiu v1,3; sra v0,v1,2; sll v0,v0,N.
    bytes.fromhex("03 00 63 24 83 10 03 00"),
    # Live controller branches: addiu v0,3; sra v0,v0,2; sll v0,v0,N.
    bytes.fromhex("03 00 42 24 83 10 02 00"),
]
CONTROL_HUMAN_SIG = bytes.fromhex(
    "12 80 02 3c 68 f3 42 8c e8 ff bd 27 10 00 b0 af"
    " 21 80 80 00 03 00 42 30"
)


def pack_i32(values: list[int]) -> bytes:
    return struct.pack("<" + "i" * len(values), *values)


def grip_values(mode_or_mult: str | float) -> tuple[list[int], list[int]]:
    mult = GRIP_MULT[mode_or_mult] if isinstance(mode_or_mult, str) else mode_or_mult
    road = [max(1, round(v * mult)) for v in ROAD_ORIGINAL]
    reverse = [round((0x10000 * 0x10000) / v) for v in road]
    return road, reverse


def find_one(data: bytes, needle: bytes, name: str) -> int:
    positions: list[int] = []
    start = 0
    while True:
        pos = data.find(needle, start)
        if pos < 0:
            break
        positions.append(pos)
        start = pos + 1
    if len(positions) != 1:
        raise SystemExit(f"{name}: expected 1 hit, found {len(positions)}: {[hex(p) for p in positions]}")
    return positions[0]


def find_one_of(data: bytes, needles: list[bytes], name: str) -> int:
    hits: list[int] = []
    for needle in needles:
        start = 0
        while True:
            pos = data.find(needle, start)
            if pos < 0:
                break
            hits.append(pos)
            start = pos + 1
    hits = sorted(set(hits))
    if len(hits) != 1:
        raise SystemExit(f"{name}: expected 1 hit, found {len(hits)}: {[hex(p) for p in hits]}")
    return hits[0]


def find_all(data: bytes, needle: bytes) -> list[int]:
    hits: list[int] = []
    start = 0
    while True:
        pos = data.find(needle, start)
        if pos < 0:
            return hits
        hits.append(pos)
        start = pos + 1


def patch_at(data: bytearray, off: int, old_options: list[bytes], new: bytes, name: str, apply: bool) -> None:
    size = len(new)
    actual = bytes(data[off : off + size])
    if actual == new:
        print(f"{name}: already patched at 0x{off:X}")
        return
    if actual not in old_options:
        expected = " or ".join(x.hex(" ") for x in old_options)
        raise SystemExit(
            f"{name}: unexpected bytes at 0x{off:X}: {actual.hex(' ')}; expected {expected}"
        )
    print(f"{name}: patch 0x{off:X}: {actual.hex(' ')} -> {new.hex(' ')}")
    if apply:
        data[off : off + size] = new


def patch_u16(data: bytearray, off: int, allowed: list[int], new: int, name: str, apply: bool) -> None:
    actual = struct.unpack_from("<H", data, off)[0]
    if actual == new:
        print(f"{name}: already patched at 0x{off:X}: 0x{new:04X}")
        return
    if actual not in allowed:
        raise SystemExit(
            f"{name}: unexpected halfword at 0x{off:X}: 0x{actual:04X}; "
            f"expected one of {[hex(x) for x in allowed]}"
        )
    print(f"{name}: patch 0x{off:X}: 0x{actual:04X} -> 0x{new:04X}")
    if apply:
        struct.pack_into("<H", data, off, new)


def apply_patch(path: Path, mode: str, heavy_mult: int, apply: bool) -> None:
    original = path.read_bytes()
    data = bytearray(original)

    derived_off = find_one(data, DERIVED_FUNC_SIG, "Physics_CalculateDerivedCarSpecs signature")
    mass_block_off = derived_off + 0x24
    patch_at(
        data,
        mass_block_off,
        [MASS_BLOCK_ORIGINAL, *MASS_BLOCK_OLD_MASSINV_PATCHES, *MASS_BLOCK_PATCHES.values()],
        MASS_BLOCK_PATCHES[mode],
        "heavier full-physics car real mass",
        apply,
    )

    torque_off = find_one(data, GET_TORQUE_SIG, "Physics_GetTorque signature") + len(GET_TORQUE_SIG)
    patch_at(
        data,
        torque_off,
        [TORQUE_DELAY_ORIGINAL, *TORQUE_DELAY_OLD_PATCHES, *TORQUE_PATCHES.values()],
        TORQUE_PATCHES[mode],
        "engine torque tweak",
        apply,
    )

    torque_table_sig_off = find_one_of(
        data,
        [TORQUE_TABLE_MULT_SIG, TORQUE_TABLE_MULT_SIG_PATCHED],
        "derived torque-table multiplier",
    )
    patch_at(
        data,
        torque_table_sig_off,
        list(TORQUE_TABLE_LUI_PATCHES.values()),
        TORQUE_TABLE_LUI_PATCHES["police" if mode == "police" else "normal"],
        "derived torque-table multiplier high half",
        apply,
    )
    torque_table_off = torque_table_sig_off + len(TORQUE_TABLE_MULT_SIG)
    patch_at(
        data,
        torque_table_off,
        [*TORQUE_TABLE_MULT_PATCHES.values(), *TORQUE_TABLE_MULT_OLD_PATCHES],
        TORQUE_TABLE_MULT_PATCHES["police" if mode == "police" else "normal"],
        "derived torque-table multiplier",
        apply,
    )

    power_cap_off = find_one(data, POWER_SPEED_CAP_PREFIX, "power speed cap") + len(POWER_SPEED_CAP_PREFIX)
    patch_at(
        data,
        power_cap_off,
        [POWER_SPEED_CAP_PATCHES["normal_hi"], POWER_SPEED_CAP_PATCHES["police_hi"]],
        POWER_SPEED_CAP_PATCHES["police_hi" if mode == "police" else "normal_hi"],
        "power speed cap high half",
        apply,
    )
    patch_at(
        data,
        power_cap_off + 0x08,
        [POWER_SPEED_CAP_PATCHES["lo"]],
        POWER_SPEED_CAP_PATCHES["lo"],
        "power speed cap low half",
        apply,
    )

    handbrake_drift_off = find_one(data, HANDBRAKE_DRIFT_PREFIX, "handbrake drift force") + len(
        HANDBRAKE_DRIFT_PREFIX
    )
    patch_at(
        data,
        handbrake_drift_off,
        [HANDBRAKE_DRIFT_ORIGINAL, HANDBRAKE_DRIFT_OLD_X8_PATCH, HANDBRAKE_DRIFT_PATCH],
        HANDBRAKE_DRIFT_PATCH if mode == "police" else HANDBRAKE_DRIFT_ORIGINAL,
        "handbrake drift force",
        apply,
    )

    tire_slip_off = find_one(data, TIRE_SLIP_ENVELOPE_PREFIX, "tire slip envelope")
    patch_at(
        data,
        tire_slip_off + len(TIRE_SLIP_ENVELOPE_PREFIX),
        [
            TIRE_SLIP_ENVELOPE_ORIGINAL_A1,
            TIRE_SLIP_ENVELOPE_OLD_C000_A1,
            TIRE_SLIP_ENVELOPE_PATCH_A1,
        ],
        TIRE_SLIP_ENVELOPE_PATCH_A1 if mode == "police" else TIRE_SLIP_ENVELOPE_ORIGINAL_A1,
        "tire slip envelope front",
        apply,
    )
    patch_at(
        data,
        tire_slip_off + len(TIRE_SLIP_ENVELOPE_PREFIX) + 0x38,
        [
            TIRE_SLIP_ENVELOPE_ORIGINAL_A0,
            TIRE_SLIP_ENVELOPE_OLD_C000_A0,
            TIRE_SLIP_ENVELOPE_PATCH_A0,
        ],
        TIRE_SLIP_ENVELOPE_PATCH_A0 if mode == "police" else TIRE_SLIP_ENVELOPE_ORIGINAL_A0,
        "tire slip envelope rear",
        apply,
    )

    for visual_off, visual_original, visual_patch, visual_name in VISUAL_WHEEL_STEER_PATCHES:
        patch_at(
            data,
            visual_off,
            [visual_original, visual_patch],
            visual_patch if mode == "police" else visual_original,
            visual_name,
            apply,
        )

    steering_rate_hits = sorted(set(find_all(data, STEERING_RATE_PREFIXES[0])))
    if len(steering_rate_hits) != 2:
        raise SystemExit(
            f"steering smoothing rate: expected 2 hits, found {len(steering_rate_hits)}: "
            f"{[hex(p) for p in steering_rate_hits]}"
        )
    for index, steering_rate_off in enumerate(steering_rate_hits, start=1):
        patch_at(
            data,
            steering_rate_off + len(STEERING_RATE_PREFIXES[0]),
            [STEERING_RATE_NOP, STEERING_RATE_PATCH],
            STEERING_RATE_PATCH if mode == "police" else STEERING_RATE_NOP,
            f"steering smoothing rate x2 #{index}",
            apply,
        )

    steering_control_off = find_one(data, STEERING_CONTROL_SCALE_PREFIX, "steering control scale")
    patch_at(
        data,
        steering_control_off + len(STEERING_CONTROL_SCALE_PREFIX),
        list(STEERING_CONTROL_SCALE_PATCHES.values()),
        STEERING_CONTROL_SCALE_PATCHES["police" if mode == "police" else "normal"],
        "steering control scale",
        apply,
    )

    steering_ratio_off = find_one(data, STEERING_RATIO_USE_PREFIX, "steering ratio use") + len(
        STEERING_RATIO_USE_PREFIX
    )
    patch_at(
        data,
        steering_ratio_off,
        [
            STEERING_RATIO_USE_NOP,
            STEERING_RATIO_USE_PATCH,
            STEERING_RATIO_USE_OLD_SOFT_PATCH,
            STEERING_RATIO_USE_OLD_MEDIUM_PATCH,
            STEERING_RATIO_USE_OLD_STRONG_PATCH,
            STEERING_RATIO_USE_SOFT_PATCH,
        ],
        STEERING_RATIO_USE_POLICE if mode == "police" else STEERING_RATIO_USE_NOP,
        "steering ratio use",
        apply,
    )

    newton_mass_off = find_one_of(
        data,
        [NEWTON_CAR_MASS_ORIGINAL, *NEWTON_CAR_MASS_BAD_PATCHES, *NEWTON_CAR_MASS_PATCHES.values()],
        "car Newton mass init branch",
    )
    patch_at(
        data,
        newton_mass_off,
        [NEWTON_CAR_MASS_ORIGINAL, *NEWTON_CAR_MASS_BAD_PATCHES, *NEWTON_CAR_MASS_PATCHES.values()],
        NEWTON_CAR_MASS_PATCHES[mode],
        "regular car Newton collision mass",
        apply,
    )

    patch_u16(
        data,
        PEC_HEAVY_FLAG_OFF,
        [0x0000, 0x0001, 0x0002, 0x000A],
        PEC_HEAVY_FLAG_PATCHES[mode],
        "PEC heavy/turning physics flag",
        apply,
    )

    heavy_cheat_off = find_one(data, HEAVY_CHEAT_MASS_PREFIX, "PEC heavy-car mass branch")
    heavy_cheat_mult_off = heavy_cheat_off + len(HEAVY_CHEAT_MASS_PREFIX)
    patch_at(
        data,
        heavy_cheat_mult_off,
        list(HEAVY_CHEAT_MULT_PATCHES.values()),
        HEAVY_CHEAT_MULT_PATCHES[heavy_mult],
        f"PEC heavy-car Newton mass multiplier x{heavy_mult}",
        apply,
    )

    turn_cap_off = find_one(data, TURN_CAP_PREFIX, "raised steering cap branch")
    turn_cap_mode = "very_strong" if mode == "police" else "normal"
    patch_at(
        data,
        turn_cap_off + len(TURN_CAP_PREFIX),
        [*TURN_CAP_PATCHES.values()],
        TURN_CAP_PATCHES[turn_cap_mode],
        "raised steering cap compare",
        apply,
    )
    patch_at(
        data,
        turn_cap_off + len(TURN_CAP_PREFIX) + 0x14,
        [*TURN_CAP_STORE_PATCHES.values()],
        TURN_CAP_STORE_PATCHES[turn_cap_mode],
        "raised steering cap value",
        apply,
    )

    steering_step_off = find_one(data, STEERING_STEP_PREFIX, "steering response step branch")
    steering_step_options = [
        patch[name]
        for patch in STEERING_STEP_PATCHES.values()
        for name in ("small_neg", "full_neg", "full_pos")
    ]
    steering_steps = STEERING_STEP_PATCHES["strong" if mode == "police" else "normal"]
    patch_at(
        data,
        steering_step_off + len(STEERING_STEP_PREFIX),
        steering_step_options,
        steering_steps["small_neg"],
        "steering response small negative step",
        apply,
    )
    patch_at(
        data,
        steering_step_off + 0x28,
        steering_step_options,
        steering_steps["full_neg"],
        "steering response full negative step",
        apply,
    )
    patch_at(
        data,
        steering_step_off + 0x44,
        steering_step_options,
        steering_steps["full_pos"],
        "steering response full positive step",
        apply,
    )

    control_human_off = find_one(data, CONTROL_HUMAN_SIG, "Control_Human signature")
    control_human = data[control_human_off : control_human_off + 0x180]
    steer_input_hits: list[int] = []
    for pattern in HUMAN_STEER_INPUT_PATTERNS:
        for hit in find_all(control_human, pattern):
            steer_input_hits.append(control_human_off + hit + len(pattern))
    steer_input_hits = sorted(set(steer_input_hits))
    if len(steer_input_hits) != 3:
        raise SystemExit(
            f"human steering input scale: expected 3 hits, found {len(steer_input_hits)}: "
            f"{[hex(p) for p in steer_input_hits]}"
        )
    steer_input_patch = HUMAN_STEER_INPUT_PATCHES["strong" if mode == "police" else "normal"]
    for index, steer_input_off in enumerate(steer_input_hits, start=1):
        patch_at(
            data,
            steer_input_off,
            list(HUMAN_STEER_INPUT_PATCHES.values()),
            steer_input_patch,
            f"human steering input scale #{index}",
            apply,
        )

    road_original = pack_i32(ROAD_ORIGINAL)
    reverse_original = pack_i32(REVERSE_ORIGINAL)
    grip_original = pack_i32(GRIP_LOSS_ORIGINAL)
    grip_wet_original = pack_i32(GRIP_LOSS_WET_ORIGINAL)

    road_new, reverse_new = grip_values(mode)
    grip_new, grip_wet_new = GRIP_LOSS_PATCHES[mode]

    all_road = [road_original]
    all_reverse = [reverse_original]
    all_grip = [grip_original]
    all_grip_wet = [grip_wet_original]
    for patch_mode in GRIP_MULT:
        road_patch, reverse_patch = grip_values(patch_mode)
        grip_patch, grip_wet_patch = GRIP_LOSS_PATCHES[patch_mode]
        all_road.append(pack_i32(road_patch))
        all_reverse.append(pack_i32(reverse_patch))
        all_grip.append(pack_i32(grip_patch))
        all_grip_wet.append(pack_i32(grip_wet_patch))
    for legacy_mult in LEGACY_GRIP_MULT:
        road_patch, reverse_patch = grip_values(legacy_mult)
        all_road.append(pack_i32(road_patch))
        all_reverse.append(pack_i32(reverse_patch))
    for grip_patch, grip_wet_patch in LEGACY_GRIP_LOSS_PATCHES:
        all_grip.append(pack_i32(grip_patch))
        all_grip_wet.append(pack_i32(grip_wet_patch))

    road_off = find_one_of(data, all_road, "road grip table")
    reverse_off = find_one_of(data, all_reverse, "reverse road grip table")
    grip_off = find_one_of(data, all_grip, "grip loss table")
    grip_wet_off = find_one_of(data, all_grip_wet, "wet grip loss table")

    patch_at(data, road_off, all_road, pack_i32(road_new), "road grip", apply)
    patch_at(
        data,
        reverse_off,
        all_reverse,
        pack_i32(reverse_new),
        "reverse road grip",
        apply,
    )
    patch_at(data, grip_off, all_grip, pack_i32(grip_new), "grip loss", apply)
    patch_at(
        data,
        grip_wet_off,
        all_grip_wet,
        pack_i32(grip_wet_new),
        "wet grip loss",
        apply,
    )

    if apply:
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        path.write_bytes(data)
        print(f"done: patched PROD physics mode={mode}, heavy_mult=x{heavy_mult}")
    else:
        print("dry run only; pass --apply to write changes")


def restore(path: Path) -> None:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        raise SystemExit(f"backup not found: {backup.name}")
    path.write_bytes(backup.read_bytes())
    print(f"restored {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch PROD NFS4.EXE handling/heaviness physics.")
    parser.add_argument("--exe", default=str(PROD_EXE), help="Path to PROD NFS4.EXE")
    parser.add_argument("--mode", choices=sorted(MASS_BLOCK_PATCHES), default="police")
    parser.add_argument(
        "--heavy-mult",
        choices=sorted(str(x) for x in HEAVY_CHEAT_MULT_PATCHES),
        default="3",
        help="Newton collision-mass multiplier for the built-in PEC heavy-car flag",
    )
    parser.add_argument("--apply", action="store_true", help="Write patched EXE")
    parser.add_argument("--restore", action="store_true", help="Restore .orig_player_physics_prod backup")
    args = parser.parse_args()

    path = Path(args.exe)
    if args.restore:
        restore(path)
    else:
        heavy_mult = "1.5" if args.heavy_mult == "1.5" else int(args.heavy_mult)
        apply_patch(path, args.mode, heavy_mult, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
