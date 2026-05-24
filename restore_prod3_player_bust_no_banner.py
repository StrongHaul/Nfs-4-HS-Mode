from pathlib import Path
import hashlib
import shutil


ROOT = Path(__file__).resolve().parent
PROD3_DIR = ROOT / "PROD 3 версия. DuckStation. Need for Speed - High Stakes (USA) — Мод Hypercycle"
EXE = PROD3_DIR / "NFS4.EXE"


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def put(buf: bytearray, off: int, data: bytes) -> None:
    buf[off:off + len(data)] = data


def nop_cave(buf: bytearray, off: int, size: int) -> None:
    put(buf, off, b"\x00" * size)


def main() -> None:
    if not EXE.exists():
        raise SystemExit(f"Missing {EXE}")

    before = md5(EXE)
    backup = EXE.with_name(f"NFS4.EXE.backup_before_restore_no_banner_{before}")
    if not backup.exists():
        shutil.copy2(EXE, backup)

    data = bytearray(EXE.read_bytes())

    # Restore stock instructions for failed banner/overlay experiments.
    put(data, 0x50BF0, bytes.fromhex(
        "60000224 640002AE 1280023C 68F3438C"
        "02000224 180002AE 680003AE"
    ))
    put(data, 0x50B94, bytes.fromhex(
        "0000028E 00000000 780240AC 180000AE"
        "7C0011AE 03810108 800000AE"
    ))
    put(data, 0x53590, bytes.fromhex("4469030C 01000524"))
    put(data, 0x53DAC, bytes.fromhex("0000228E 00000000"))

    # Clear the banner/speech caves so stale code cannot run accidentally.
    nop_cave(data, 0xFEB80, 0x180)
    nop_cave(data, 0xFED00, 0x100)
    nop_cave(data, 0xFEE00, 0x80)
    nop_cave(data, 0xFEE80, 0x80)

    # Stable player-bust candidate cave without the banner marker write.
    candidate = bytes.fromhex(
        "00000824 FFFF0825 0C000015 00000000"
        "1180083C 0C0D098D 00000000 07004916"
        "00000000 0000688E 00000000 03000911"
        "00000000 71700108 00000000 66700108"
        "00000000"
    )
    # Runtime 0x800F7A00, file offset 0xE8200 with PROD3 base 0x8000F800.
    put(data, 0xE8200, candidate + b"\x00" * (0x100 - len(candidate)))

    EXE.write_bytes(data)
    after = md5(EXE)
    print(f"backup: {backup.name}")
    print(f"before: {before}")
    print(f"after : {after}")
    print("Restored player bust without banner/overlay hooks.")


if __name__ == "__main__":
    main()
