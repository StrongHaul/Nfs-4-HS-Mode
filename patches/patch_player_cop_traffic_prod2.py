#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


BACKUP_SUFFIX = ".orig_player_cop_traffic"

ROOT = Path(__file__).resolve().parent
PROD2_EXE = next(ROOT.glob("PROD 2*/NFS4.EXE"))

# Debug build symbol:
#   8013C55C AIHigh_CopGameType
#
# The same initialized data block is found in PROD 2 at file offset 0x12E04C.
# The first word is the cop-game type. Stock initializes it to 0.
AIHIGH_COP_GAME_TYPE_OFF = 0x12E04C
AIHIGH_COP_GAME_TYPE_ORIGINAL = bytes.fromhex("00 00 00 00")
AIHIGH_COP_GAME_TYPE_PLAYER_COP = bytes.fromhex("01 00 00 00")
AIHIGH_COP_GAME_TYPE_PLAYER_COP_ALT = bytes.fromhex("04 00 00 00")

AIHIGH_COP_GAME_TYPE_READ_PATCHES = [
    (0x4E080, bytes.fromhex("14 80 02 3c 4c d8 42 8c"), bytes.fromhex("04 00 02 24 00 00 00 00"), "AIHigh_CopGameType read v0 #1"),
    (0x4E454, bytes.fromhex("14 80 02 3c 4c d8 42 8c"), bytes.fromhex("04 00 02 24 00 00 00 00"), "AIHigh_CopGameType read v0 #2"),
    (0x4E0F8, bytes.fromhex("14 80 03 3c 4c d8 63 8c"), bytes.fromhex("04 00 03 24 00 00 00 00"), "AIHigh_CopGameType read v1 #1"),
    (0x4E48C, bytes.fromhex("14 80 03 3c 4c d8 63 8c"), bytes.fromhex("04 00 03 24 00 00 00 00"), "AIHigh_CopGameType read v1 #2"),
    (0x4E738, bytes.fromhex("14 80 03 3c 4c d8 63 8c"), bytes.fromhex("04 00 03 24 00 00 00 00"), "AIHigh_CopGameType read v1 #3"),
    (0x4E8C8, bytes.fromhex("14 80 03 3c 4c d8 63 8c"), bytes.fromhex("04 00 03 24 00 00 00 00"), "AIHigh_CopGameType read v1 #4"),
    (0x4F14C, bytes.fromhex("14 80 03 3c 4c d8 63 8c"), bytes.fromhex("04 00 03 24 00 00 00 00"), "AIHigh_CopGameType read v1 #5"),
    (0x4E688, bytes.fromhex("14 80 04 3c 4c d8 84 8c"), bytes.fromhex("04 00 04 24 00 00 00 00"), "AIHigh_CopGameType read a0 #1"),
]

# Broad experiment: traffic's CheckForCops filters candidate cars with
# car->0x570 & 0x0004.  Force that test true so we can confirm this is the
# "traffic yields to cops" path before narrowing it to player-only.
TRAFFIC_TREATS_CARS_AS_COPS_PATCHES = [
    (
        0x56CF4,
        bytes.fromhex("04 00 42 30"),  # andi v0,v0,0x0004
        bytes.fromhex("04 00 02 24"),  # addiu v0,zero,0x0004
        "traffic CheckForCops cop-flag filter",
    ),
]

TRAFFIC_NEVER_SKIPS_COP_CANDIDATE_PATCHES = [
    (
        0x56CF4,
        bytes.fromhex("04 00 42 30"),  # andi v0,v0,0x0004
        bytes.fromhex("21 10 00 00"),  # addu v0,zero,zero
        "traffic CheckForCops never skip candidate",
    ),
]

# Narrow experiment: traffic already finds a candidate car, but then rejects the
# mapped AI object when obj->0x58 is non-zero. Police bots appear to pass this;
# the player likely does not. Ignore this one gate and keep the rest of CopCheck
# intact.
COPCHECK_IGNORE_OBJECT_STATE_PATCHES = [
    (
        0x56E08,
        bytes.fromhex("13 00 40 14"),  # bne v0,zero,+0x13
        bytes.fromhex("00 00 00 00"),  # nop
        "traffic CopCheck ignore AI object +0x58 gate",
    ),
]

# Better-targeted obj+0x58 experiment: keep CopCheck's distance tests intact,
# but always take the successful return path once a non-traffic candidate has
# been selected. Nopping the branch made cops invalid too; this forces the
# original "return s0" branch instead.
COPCHECK_ACCEPT_SELECTED_CANDIDATE_PATCHES = [
    (
        0x56E08,
        bytes.fromhex("13 00 40 14"),  # bne v0,zero,+0x13
        bytes.fromhex("13 00 00 10"),  # beq zero,zero,+0x13
        "CopCheck accept selected non-traffic candidate",
    ),
]

# In Single Race there are no cops, so CopCheck returns before it even calls
# CheckForCops. After we broaden CheckForCops to scan non-traffic cars, this
# mode gate must be bypassed or Single Race can never use the same yield path.
COPCHECK_IGNORE_NO_COPS_GATE_PATCHES = [
    (
        0x56D84,
        bytes.fromhex("32 00 40 10"),  # beq v0,zero,return_0
        bytes.fromhex("00 00 00 00"),  # nop
        "CopCheck ignore global no-cops gate",
    ),
]

# Experimental: piggyback on an existing car-status write in AI physics and add
# the cop bit (0x0004) alongside the stock 0x0010 flag. This is narrower than
# patching traffic logic directly, but it may still only affect the cars that
# pass through this physics branch.
PLAYER_COP_FLAG_IN_PHYSICS_PATCHES = [
    (
        0x5B730,
        bytes.fromhex("10 00 42 34"),  # ori v0,v0,0x0010
        bytes.fromhex("14 00 42 34"),  # ori v0,v0,0x0014
        "physics status write adds cop bit",
    ),
]

# Experimental: traffic already picks the nearest non-traffic car in
# CheckForCops, but CopCheck applies extra range/state filters that seem tuned
# for cops only. Remove those gates so traffic can react to any nearby
# non-traffic AI object (player, racers, cops).
ANY_NONTRAFFIC_YIELD_PATCHES = [
    (
        0x56DBC,
        bytes.fromhex("16 00 40 14"),  # bne v0,zero,+0x16
        bytes.fromhex("00 00 00 00"),  # nop
        "CopCheck ignore near-range gate",
    ),
    (
        0x56DD4,
        bytes.fromhex("10 00 40 14"),  # bne v0,zero,+0x10
        bytes.fromhex("00 00 00 00"),  # nop
        "CopCheck ignore distance gate",
    ),
    (
        0x56E08,
        bytes.fromhex("13 00 40 14"),  # bne v0,zero,+0x13
        bytes.fromhex("00 00 00 00"),  # nop
        "CopCheck ignore AI object state gate",
    ),
]

# Narrower experiment than rewriting CopCheck: let one HighExecute_Traffic path
# continue even when CopCheck returns 0. The downstream code still has its own
# stack flag and threshold checks, so this may broaden reactions without
# disabling traffic behavior globally.
HIGH_TRAFFIC_EARLY_EXIT_PATCHES = [
    (
        0x5729C,
        bytes.fromhex("9b 00 40 10"),  # beq v0,zero,+0x9b
        bytes.fromhex("00 00 00 00"),  # nop
        "HighExecute_Traffic path A ignore CopCheck early exit",
    ),
]

# Scan every car instead of only Cars_gTrafficCarList. The existing
# car->0x570 & 0x0004 filter still skips traffic cars, so this should let
# CheckForCops pick player/racers/cops as non-traffic candidates.
CHECKFORCOPS_SCAN_ALL_CARS_PATCHES = [
    (
        0x56CC8,
        bytes.fromhex("78 0d 51 24"),  # addiu s1,v0,Cars_gTrafficCarList
        bytes.fromhex("c4 0c 51 24"),  # addiu s1,v0,Cars_gList
        "CheckForCops scan Cars_gList",
    ),
    (
        0x56CD0,
        bytes.fromhex("00 db 42 8c"),  # lw v0,Cars_gNumTrafficCars
        bytes.fromhex("ec da 42 8c"),  # lw v0,Cars_gNumCars
        "CheckForCops use Cars_gNumCars",
    ),
]

# Dangerous experiment, kept only so it can be reverted cleanly if a build still
# has it: routing state 1 through state 2 makes traffic spawn at the start line
# and stop moving, so do not use this as the Single Race solution.
SINGLE_RACE_STATE1_COPCHECK_PATCHES = [
    (
        0x4619C,
        bytes.fromhex("d4 67 06 80"),  # state 1 -> 0x800667D4
        bytes.fromhex("e0 69 06 80"),  # state 1 -> 0x800669E0
        "HighExecute_Traffic state 1 uses CopCheck path",
    ),
]

# Single Race / normal roving traffic uses its own nearby-car scan instead of
# AIHigh_Traffic::CopCheck. Debug symbols show this scan walks Cars_gSortedList
# (not Cars_gList) using the sorted-position index at car+0x25C.  Try the
# adjacent Cars_gTotalSortedList so it can see non-traffic cars while preserving
# road-order scanning.
ROVING_TRAFFIC_SCAN_ALL_CARS_PATCHES = [
    (
        0x62E00,
        bytes.fromhex("5c 02 43 8c"),  # lw v1,car->sorted index
        bytes.fromhex("54 02 43 8c"),  # lw v1,car->global car index
        "RovingTraffic forward TotalSortedList starts from global index",
    ),
    (
        0x62E10,
        bytes.fromhex("c0 0d 42 24"),  # addiu v0,v0,Cars_gSortedList
        bytes.fromhex("e4 0d 42 24"),  # addiu v0,v0,Cars_gTotalSortedList
        "RovingTraffic forward scan Cars_gTotalSortedList",
    ),
    (
        0x62E7C,
        bytes.fromhex("5c 02 43 8c"),  # lw v1,car->sorted index
        bytes.fromhex("54 02 43 8c"),  # lw v1,car->global car index
        "RovingTraffic backward TotalSortedList starts from global index",
    ),
    (
        0x62E8C,
        bytes.fromhex("c0 0d 42 24"),  # addiu v0,v0,Cars_gSortedList
        bytes.fromhex("e4 0d 42 24"),  # addiu v0,v0,Cars_gTotalSortedList
        "RovingTraffic backward scan Cars_gTotalSortedList",
    ),
]

# RovingTraffic::CheckIfCarIsNearbyAndStop rejects a candidate when byte
# candidate+0x91 is zero.  Player/racer cars in Single Race may not carry the
# same traffic-live marker, so let the function continue to the real distance
# checks instead of skipping immediately.
ROVING_TRAFFIC_IGNORE_CANDIDATE_91_PATCHES = [
    (
        0x629CC,
        bytes.fromhex("54 00 40 10"),  # beq v0,zero,skip_candidate
        bytes.fromhex("00 00 00 00"),  # nop
        "RovingTraffic do not skip candidate when +0x91 is zero",
    ),
]

# Cleanup for earlier failed RovingTraffic experiments: keep the sorted-list
# index/count that the debug build shows this function expects.
ROVING_TRAFFIC_RESTORE_SORTED_SCAN_PATCHES = [
    (
        0x62E00,
        bytes.fromhex("54 02 43 8c"),
        bytes.fromhex("5c 02 43 8c"),
        "RovingTraffic restore forward sorted index",
    ),
    (
        0x62E24,
        bytes.fromhex("ec da 42 8c"),
        bytes.fromhex("e8 da 42 8c"),
        "RovingTraffic restore sorted scan count",
    ),
    (
        0x62E7C,
        bytes.fromhex("54 02 43 8c"),
        bytes.fromhex("5c 02 43 8c"),
        "RovingTraffic restore backward sorted index",
    ),
]

# Exhaustive diagnostic: when CheckIfCarIsNearbyAndStop decides a candidate is
# not relevant, keep scanning instead of stopping the roving-traffic search.
# This is useful if player/racer cars are not adjacent in the sorted list.
ROVING_TRAFFIC_CONTINUE_ON_MISS_PATCHES = [
    (
        0x62A10,
        bytes.fromhex("45 00 40 14"),  # bne v0,zero,return_status_0
        bytes.fromhex("43 00 40 14"),  # bne v0,zero,return_status_2
        "RovingTraffic continue when candidate is too far by spline",
    ),
    (
        0x62B28,
        bytes.fromhex("00 00 60 ae"),  # sw zero,0(s3)
        bytes.fromhex("00 00 62 ae"),  # sw v0,0(s3), v0 is 2 via branch delay
        "RovingTraffic continue on generic miss",
    ),
]


def patch_at(data: bytearray, off: int, old_options: list[bytes], new: bytes, name: str, apply: bool) -> None:
    actual = bytes(data[off : off + len(new)])
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
        data[off : off + len(new)] = new


def run(
    path: Path,
    apply: bool,
    revert: bool,
    value: int | None,
    force_reads: bool,
    broad_traffic: bool,
    never_skip: bool,
    ignore_obj_state: bool,
    accept_selected_candidate: bool,
    ignore_no_cops_gate: bool,
    physics_cop_bit: bool,
    any_nontraffic_yield: bool,
    traffic_early_exit: bool,
    scan_all_cars: bool,
    single_race_state1_copcheck: bool,
    roving_scan_all_cars: bool,
    roving_ignore_candidate_91: bool,
    roving_continue_on_miss: bool,
) -> None:
    original = path.read_bytes()
    data = bytearray(original)

    new_value = AIHIGH_COP_GAME_TYPE_ORIGINAL
    if not revert and value is not None:
        if value == 1:
            new_value = AIHIGH_COP_GAME_TYPE_PLAYER_COP
        elif value == 4:
            new_value = AIHIGH_COP_GAME_TYPE_PLAYER_COP_ALT
        else:
            raise SystemExit("unsupported --value; use 1 or 4")

    patch_at(
        data,
        AIHIGH_COP_GAME_TYPE_OFF,
        [AIHIGH_COP_GAME_TYPE_ORIGINAL, AIHIGH_COP_GAME_TYPE_PLAYER_COP, AIHIGH_COP_GAME_TYPE_PLAYER_COP_ALT],
        new_value,
        "AIHigh_CopGameType initial value",
        apply,
    )

    for off, original_read, forced_read, name in AIHIGH_COP_GAME_TYPE_READ_PATCHES:
        patch_at(
            data,
            off,
            [original_read, forced_read],
            original_read if revert or not force_reads else forced_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in TRAFFIC_TREATS_CARS_AS_COPS_PATCHES:
        patch_at(
            data,
            off,
            [original_read, forced_read, TRAFFIC_NEVER_SKIPS_COP_CANDIDATE_PATCHES[0][2]],
            original_read if revert or not broad_traffic else forced_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in TRAFFIC_NEVER_SKIPS_COP_CANDIDATE_PATCHES:
        patch_at(
            data,
            off,
            [original_read, forced_read, TRAFFIC_TREATS_CARS_AS_COPS_PATCHES[0][2]],
            original_read if revert or not never_skip else forced_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in COPCHECK_IGNORE_OBJECT_STATE_PATCHES:
        patch_at(
            data,
            off,
            [original_read, forced_read, COPCHECK_ACCEPT_SELECTED_CANDIDATE_PATCHES[0][2]],
            original_read if revert or not ignore_obj_state else forced_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in PLAYER_COP_FLAG_IN_PHYSICS_PATCHES:
        patch_at(
            data,
            off,
            [original_read, forced_read],
            original_read if revert or not physics_cop_bit else forced_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in COPCHECK_IGNORE_NO_COPS_GATE_PATCHES:
        patch_at(
            data,
            off,
            [original_read, forced_read],
            original_read if revert or not ignore_no_cops_gate else forced_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in ANY_NONTRAFFIC_YIELD_PATCHES:
        old_options = [original_read, forced_read]
        if off == COPCHECK_ACCEPT_SELECTED_CANDIDATE_PATCHES[0][0]:
            old_options.append(COPCHECK_ACCEPT_SELECTED_CANDIDATE_PATCHES[0][2])
        patch_at(
            data,
            off,
            old_options,
            original_read if revert or not any_nontraffic_yield else forced_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in COPCHECK_ACCEPT_SELECTED_CANDIDATE_PATCHES:
        patch_at(
            data,
            off,
            [original_read, forced_read, COPCHECK_IGNORE_OBJECT_STATE_PATCHES[0][2]],
            original_read if revert or not accept_selected_candidate else forced_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in CHECKFORCOPS_SCAN_ALL_CARS_PATCHES:
        patch_at(
            data,
            off,
            [original_read, forced_read],
            original_read if revert or not scan_all_cars else forced_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in HIGH_TRAFFIC_EARLY_EXIT_PATCHES:
        patch_at(
            data,
            off,
            [original_read, forced_read],
            original_read if revert or not traffic_early_exit else forced_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in SINGLE_RACE_STATE1_COPCHECK_PATCHES:
        patch_at(
            data,
            off,
            [original_read, forced_read],
            original_read if revert or not single_race_state1_copcheck else forced_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in ROVING_TRAFFIC_SCAN_ALL_CARS_PATCHES:
        old_options = [original_read, forced_read]
        # Earlier failed experiments changed these sites to Cars_gList and also
        # changed the sorted index/count loads. Accept those bytes so this
        # script can move old test builds back to the current experiment.
        if off in (0x62E10, 0x62E8C):
            old_options.append(bytes.fromhex("c4 0c 42 24"))
        patch_at(
            data,
            off,
            old_options,
            original_read if revert or not roving_scan_all_cars else forced_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in ROVING_TRAFFIC_IGNORE_CANDIDATE_91_PATCHES:
        patch_at(
            data,
            off,
            [original_read, forced_read],
            original_read if revert or not roving_ignore_candidate_91 else forced_read,
            name,
            apply,
        )

    restore_sorted_scan = revert or not roving_scan_all_cars
    for off, wrong_read, restored_read, name in ROVING_TRAFFIC_RESTORE_SORTED_SCAN_PATCHES:
        patch_at(
            data,
            off,
            [wrong_read, restored_read],
            restored_read if restore_sorted_scan else wrong_read,
            name,
            apply,
        )

    for off, original_read, forced_read, name in ROVING_TRAFFIC_CONTINUE_ON_MISS_PATCHES:
        patch_at(
            data,
            off,
            [original_read, forced_read],
            original_read if revert or not roving_continue_on_miss else forced_read,
            name,
            apply,
        )

    if apply and bytes(data) != original:
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
            print(f"backup: {backup.name}")
        path.write_bytes(data)
        print("done")
    elif not apply:
        print("dry-run only; pass --apply to write")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, default=PROD2_EXE)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--revert", action="store_true")
    parser.add_argument("--value", type=int, choices=[1, 4])
    parser.add_argument("--force-reads", action="store_true")
    parser.add_argument("--broad-traffic-cop-filter", action="store_true")
    parser.add_argument("--never-skip-traffic-cop-candidate", action="store_true")
    parser.add_argument("--ignore-copcheck-object-state", action="store_true")
    parser.add_argument("--accept-selected-candidate", action="store_true")
    parser.add_argument("--ignore-no-cops-gate", action="store_true")
    parser.add_argument("--physics-cop-bit", action="store_true")
    parser.add_argument("--any-nontraffic-yield", action="store_true")
    parser.add_argument("--traffic-early-exit", action="store_true")
    parser.add_argument("--scan-all-cars", action="store_true")
    parser.add_argument("--single-race-state1-copcheck", action="store_true")
    parser.add_argument("--roving-scan-all-cars", action="store_true")
    parser.add_argument("--roving-ignore-candidate-91", action="store_true")
    parser.add_argument("--roving-continue-on-miss", action="store_true")
    args = parser.parse_args()

    run(
        args.exe,
        args.apply,
        args.revert,
        args.value,
        args.force_reads,
        args.broad_traffic_cop_filter,
        args.never_skip_traffic_cop_candidate,
        args.ignore_copcheck_object_state,
        args.accept_selected_candidate,
        args.ignore_no_cops_gate,
        args.physics_cop_bit,
        args.any_nontraffic_yield,
        args.traffic_early_exit,
        args.scan_all_cars,
        args.single_race_state1_copcheck,
        args.roving_scan_all_cars,
        args.roving_ignore_candidate_91,
        args.roving_continue_on_miss,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
