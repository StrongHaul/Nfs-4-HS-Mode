#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path


DEFAULT_EXE_GLOB = "PROD 3*/NFS4.EXE"
BACKUP_SUFFIX = ".orig_before_prod3_create_speech_for_all_race_modes"
RUNTIME_BASE = 0x8000F800

# Nfs2_GameModuleStartUp, immediately after CopSpeak_StartUp().
#
# Stock creates fgSpeech only for the narrow Hot Pursuit setup. PROD3 can have
# cops/arrests in Single Race and other mixed race compositions, so the stock
# MobileSpeaker/SPCH event path can silently enqueue nothing because no Speech
# object and speech banks were created. Redirect the final "skip Speech init"
# jump back to the allocation path, preserving the existing earlier HP checks.
HOOK_OFF = 0x955C8
STOCK_SKIP_SPEECH_INIT = 0x0802937A  # j 0x800A4DE8
PATCH_CREATE_SPEECH = 0x08029374     # j 0x800A4DD0


def find_exe() -> Path:
    hits = list(Path(".").glob(DEFAULT_EXE_GLOB))
    if len(hits) != 1:
        raise SystemExit(f"expected one {DEFAULT_EXE_GLOB}, found {len(hits)}")
    return hits[0]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest().upper()


def read_u32(data: bytes | bytearray, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def write_u32(data: bytearray, off: int, value: int) -> None:
    struct.pack_into("<I", data, off, value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PROD3: create the Speech object for SR/mixed police race modes."
    )
    parser.add_argument("--revert", action="store_true")
    args = parser.parse_args()

    exe = find_exe()
    data = bytearray(exe.read_bytes())
    original = bytes(data)

    current = read_u32(data, HOOK_OFF)
    known = {STOCK_SKIP_SPEECH_INIT, PATCH_CREATE_SPEECH}
    if current not in known:
        raise SystemExit(
            f"unexpected word at 0x{HOOK_OFF:X} "
            f"(runtime 0x{RUNTIME_BASE + HOOK_OFF:08X}): 0x{current:08X}"
        )

    write_u32(data, HOOK_OFF, STOCK_SKIP_SPEECH_INIT if args.revert else PATCH_CREATE_SPEECH)

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    print(f"NFS4.EXE {md5(exe)}")
    print("Speech init for all race modes:", "stock" if args.revert else "enabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
