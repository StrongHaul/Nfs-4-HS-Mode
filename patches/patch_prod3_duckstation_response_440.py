#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import struct
from pathlib import Path


BACKUP_SUFFIX = ".orig_before_response_440_prod3"

STEERING_RESPONSE = {
    "small_neg": (0x9C768, -0x240),
    "full_neg": (0x9C784, -0x440),
    "full_pos": (0x9C7A0, 0x440),
}


def prod3_exe() -> Path:
    hits = list(Path(".").glob("PROD 3*/NFS4.EXE"))
    if len(hits) != 1:
        raise SystemExit(f"expected one PROD 3*/NFS4.EXE, found {len(hits)}")
    return hits[0]


def addiu_v0(imm: int) -> bytes:
    return struct.pack("<I", (0x09 << 26) | (2 << 21) | (2 << 16) | (imm & 0xFFFF))


def main() -> int:
    exe = prod3_exe()
    original = exe.read_bytes()
    data = bytearray(original)

    for _, (off, imm) in STEERING_RESPONSE.items():
        data[off : off + 4] = addiu_v0(imm)

    if bytes(data) != original:
        backup = exe.with_name(exe.name + BACKUP_SUFFIX)
        if not backup.exists():
            backup.write_bytes(original)
        exe.write_bytes(data)

    final = exe.read_bytes()
    print(f"patched {exe}")
    print(f"md5 {hashlib.md5(final).hexdigest()}")
    for name, (off, _) in STEERING_RESPONSE.items():
        print(f"{name} 0x{off:06X}: {final[off:off+4].hex(' ')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
