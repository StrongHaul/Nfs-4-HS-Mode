# Reverse-engineering reference context

This workspace contains the active PROD3 modification, generated pseudocode
for its binaries, and a matching decomp of the original game. Treat reference
material as read-only unless the user explicitly asks to update it.

## Source priority

1. `PROD3_STABLE_CONTEXT.md` describes the currently accepted mod state.
2. The current PROD3 `NFS4.EXE`, `FRONT.BIN`, generated disassembly, hashes,
   and observed DuckStation behavior are the source of truth for patches.
3. `references/PROD3-pseudocode/` contains generated pseudocode for the
   current PROD3 and debug binaries and helps locate modified code.
4. `references/NFSHS-PSX-decomp/` is the matching decomp and has high
   confidence for functions reported as 100% matched, but targets a different
   executable build. It is tracked as a Git submodule and treated as read-only
   reference material during PROD3 work.

## Address safety

Never copy an address or machine-code patch directly from the original-game
decomp into PROD3. Its target executable is based at `0x80010000`, while the
PROD3 executable and overlays have different layouts and modifications.
Locate the corresponding PROD3 function by instruction pattern, callers,
strings, data flow, and behavior, then verify the exact bytes before editing.

Useful local cross-checks:

- `references/PROD3-pseudocode/NFS4.EXE_prod3_pseudo_c.txt`: generated
  pseudocode for the current PROD3 executable lineage.
- `references/PROD3-pseudocode/FRONT.BIN_prod3_pseudo_c.txt`: generated
  pseudocode for the current frontend lineage.
- `references/PROD3-pseudocode/*_debug_pseudo_c.txt`: generated pseudocode for
  the corresponding debug binaries, useful for names and structural matches.
- `references/NFSHS-PSX-decomp/MATCH_PROGRESS.txt`: current function matching
  status and virtual addresses for the decomp target.
- `references/NFSHS-PSX-decomp/src/`: matched and reconstructed source units.
- `references/NFSHS-PSX-decomp/recon/`: supporting reconstruction material.

## Working rule

Use the matching decomp to answer "what did the original function provably
do?" and the PROD3 pseudocode to locate its modified counterpart. Use the
current PROD3 binary to answer "where and how can this modification be applied
safely?".
