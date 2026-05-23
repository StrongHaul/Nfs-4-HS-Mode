#!/usr/bin/env python3
from __future__ import annotations

import argparse
import struct
from pathlib import Path


REG = [
    "zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
    "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
    "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
    "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra",
]


def sx16(x: int) -> int:
    return x - 0x10000 if x & 0x8000 else x


def decode(w: int, pc: int) -> str:
    op = w >> 26
    rs = (w >> 21) & 31
    rt = (w >> 16) & 31
    rd = (w >> 11) & 31
    sh = (w >> 6) & 31
    fn = w & 63
    imm = w & 0xFFFF
    simm = sx16(imm)
    target = ((pc + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
    if w == 0:
        return "nop"
    if op == 0:
        r = REG
        names = {
            0x00: f"sll {r[rd]},{r[rt]},{sh}",
            0x02: f"srl {r[rd]},{r[rt]},{sh}",
            0x03: f"sra {r[rd]},{r[rt]},{sh}",
            0x08: f"jr {r[rs]}",
            0x09: f"jalr {r[rd]},{r[rs]}",
            0x10: f"mfhi {r[rd]}",
            0x12: f"mflo {r[rd]}",
            0x18: f"mult {r[rs]},{r[rt]}",
            0x19: f"multu {r[rs]},{r[rt]}",
            0x1A: f"div {r[rs]},{r[rt]}",
            0x20: f"add {r[rd]},{r[rs]},{r[rt]}",
            0x21: f"addu {r[rd]},{r[rs]},{r[rt]}",
            0x22: f"sub {r[rd]},{r[rs]},{r[rt]}",
            0x23: f"subu {r[rd]},{r[rs]},{r[rt]}",
            0x24: f"and {r[rd]},{r[rs]},{r[rt]}",
            0x25: f"or {r[rd]},{r[rs]},{r[rt]}",
            0x26: f"xor {r[rd]},{r[rs]},{r[rt]}",
            0x27: f"nor {r[rd]},{r[rs]},{r[rt]}",
            0x2A: f"slt {r[rd]},{r[rs]},{r[rt]}",
            0x2B: f"sltu {r[rd]},{r[rs]},{r[rt]}",
        }
        return names.get(fn, f"special fn=0x{fn:X} w=0x{w:08X}")
    r = REG
    if op == 0x02:
        return f"j 0x{target:08X}"
    if op == 0x03:
        return f"jal 0x{target:08X}"
    if op == 0x04:
        return f"beq {r[rs]},{r[rt]},0x{pc+4+(simm<<2):08X}"
    if op == 0x05:
        return f"bne {r[rs]},{r[rt]},0x{pc+4+(simm<<2):08X}"
    if op == 0x06:
        return f"blez {r[rs]},0x{pc+4+(simm<<2):08X}"
    if op == 0x07:
        return f"bgtz {r[rs]},0x{pc+4+(simm<<2):08X}"
    names = {
        0x08: "addi", 0x09: "addiu", 0x0A: "slti", 0x0B: "sltiu",
        0x0C: "andi", 0x0D: "ori", 0x0E: "xori",
    }
    if op in names:
        val = imm if op in (0x0C, 0x0D, 0x0E) else simm
        return f"{names[op]} {r[rt]},{r[rs]},{val}"
    if op == 0x0F:
        return f"lui {r[rt]},0x{imm:04X}"
    mem = {
        0x20: "lb", 0x21: "lh", 0x23: "lw", 0x24: "lbu", 0x25: "lhu",
        0x28: "sb", 0x29: "sh", 0x2B: "sw",
    }
    if op in mem:
        return f"{mem[op]} {r[rt]},{simm}({r[rs]})"
    return f"op=0x{op:X} w=0x{w:08X}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--base", type=lambda x: int(x, 0), default=0x8000F800)
    ap.add_argument("--off", type=lambda x: int(x, 0), required=True)
    ap.add_argument("--count", type=lambda x: int(x, 0), default=0x100)
    args = ap.parse_args()
    data = args.path.read_bytes()
    for off in range(args.off, args.off + args.count, 4):
        if off + 4 > len(data):
            break
        w = struct.unpack_from("<I", data, off)[0]
        pc = args.base + off
        print(f"{pc:08X} {off:06X} {w:08X}  {decode(w, pc)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
