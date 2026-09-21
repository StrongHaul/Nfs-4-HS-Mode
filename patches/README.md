# Patch scripts

This directory contains the Python scripts used to patch the PROD3 binaries
and generate or update DuckStation cheats.

Run scripts from the repository root so their relative paths continue to
resolve against the project files:

```powershell
python patches/patch_prod3_example.py
```

Scripts may import other modules from this directory. Reference tooling under
`references/` and the root-level `tools_mips_disasm.py` are intentionally kept
separate.
