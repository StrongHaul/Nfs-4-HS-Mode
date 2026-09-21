#!/usr/bin/env python3
"""Build a DuckStation cheat for civilian AI-cop body colors in HP."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path


TITLE = "Мои\\Расцветка гражданских ИИ-копов"
GAME_SETUP = 0x801144A4
CAR_DATA = GAME_SETUP + 0x3D4
CAR_STRIDE = 0xB4
HP_MODE = 0x801158BC
MODEL_COUNT = 0x16


def parse_colors(path: Path) -> tuple[dict[int, int], int]:
    data = path.read_bytes()
    if len(data) < 4 or (len(data) - 4) % 204 != 0:
        raise ValueError(f"unexpected car catalog size: {path}")
    if int.from_bytes(data[:4], "little") != (len(data) - 4) // 204:
        raise ValueError(f"unexpected car catalog header: {path}")

    selected: dict[int, int] = {}
    fallback_count = 0
    seen: set[int] = set()
    for offset in range(4, len(data), 204):
        model = data[offset]
        if model >= MODEL_COUNT:
            continue
        if model in seen:
            raise ValueError(f"duplicate model {model:02X} in {path}")
        seen.add(model)
        colors = [struct.unpack_from("<I", data, offset + 0x44 + 4 * i)[0] & 0xFFFFFF
                  for i in range(16)]
        count = min(16, data[offset + 0xAC] + data[offset + 0xAD])
        indices = list(dict.fromkeys(data[offset + 0xAF:offset + 0xAF + count]))
        indices = [index for index in indices if index < 16]

        def rgb(index: int) -> tuple[int, int, int]:
            color = colors[index]
            return ((color >> 16) & 255, (color >> 8) & 255, color & 255)

        light = [index for index in indices if min(rgb(index)) >= 180
                 and max(rgb(index)) - min(rgb(index)) <= 48]
        if light:
            selected[model] = max(light, key=lambda index: sum(rgb(index)))
            continue

        black = [index for index in indices if max(rgb(index)) <= 32]
        if not indices:
            raise ValueError(f"model {model:02X} has no selectable colors")
        selected[model] = min(black or indices, key=lambda index: sum(rgb(index)))
        fallback_count += 1
    if len(selected) != MODEL_COUNT:
        raise ValueError(f"incomplete civilian model catalog: {len(selected)}")
    return selected, fallback_count


def compare(kind: str, address: int, value: int) -> str:
    return f"{kind}{address & 0xFFFFFF:06X} {value:04X}"


def block(slot: int, model: int, color: int) -> list[str]:
    car = CAR_DATA + slot * CAR_STRIDE
    return [
        compare("D0", HP_MODE, 1),
        compare("E0", car, model),
        compare("80", car + 0x0C, color),
    ]


def make_section(colors: dict[int, int]) -> str:
    lines = [
        f"[{TITLE}]",
        "Description = Белый цвет гражданских ИИ-копов в HP; если белого нет, самый тёмный доступный цвет. Эксперимент для стандартного состава гонки.",
        "Type = Gameshark",
        "Activation = EndFrame",
    ]
    for slot in range(3, 7):  # HP: player, racers, then up to four cops
        for model, color in sorted(colors.items()):
            lines.extend(block(slot, model, color))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true", help="append the generated cheat to NFS 4.cht")
    parser.add_argument("--remove", action="store_true", help="remove the generated cheat")
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("cheats/NFS 4.cht"),
        help="cheat file to update",
    )
    args = parser.parse_args()
    executables = list(Path(".").glob("PROD 3*/NFS4.EXE"))
    if len(executables) != 1:
        raise SystemExit("expected one PROD3 directory")
    colors, fallback_count = parse_colors(executables[0].with_name("ZFECARS.CAR"))
    section = make_section(colors)
    print(f"civilian models: {len(colors)}, dark fallback: {fallback_count}")
    print(f"generated cheat lines: {len(section.splitlines())}")
    if not args.install and not args.remove:
        return

    path = args.file
    original = path.read_bytes()
    bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
    body = original[len(bom):].decode("utf-8")
    newline = "\r\n" if "\r\n" in body else "\n"
    header = f"[{TITLE}]"
    if header in body:
        if "\n[" in body[body.index(header) + len(header):]:
            raise SystemExit("cheat is not the final section; refusing to replace it")
        body = body[:body.index(header)]
    if args.remove:
        path.write_bytes(bom + (body.rstrip("\r\n") + newline).encode("utf-8"))
        print(f"removed from {path}")
        return
    updated = body.rstrip("\r\n") + newline * 2 + section.replace("\n", newline)
    path.write_bytes(bom + updated.encode("utf-8"))
    print(f"installed in {path}")


if __name__ == "__main__":
    main()
