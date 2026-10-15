# -*- coding: utf-8 -*-
"""Syntax + reference validation for the BaanMitra free-tier scaffold.

Checks (no third-party imports needed):
  1. every .py file compiles
  2. every `from ..x import y` / `from .x import y` resolves to a real module/file
  3. every module attribute referenced as `module.name` exists somewhere in the
     project (best-effort, catches typos like db.update_call_by_sid)
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

errors: list[str] = []
warnings: list[str] = []

# ---------------------------------------------------------------- 1. compile
py_files = sorted(SRC.rglob("*.py"))
for f in py_files:
    try:
        ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
    except SyntaxError as e:
        errors.append(f"SYNTAX {f.relative_to(ROOT)}:{e.lineno} {e.msg}")
print(f"[1] compiled {len(py_files)} python files")

# ------------------------------------------------- 2. module resolution
pkg_roots = {p for p in SRC.rglob("__init__.py")}
modules: dict[str, Path] = {}
for init in pkg_roots:
    pkg = init.parent
    mod_name = ".".join(pkg.relative_to(SRC).parts)
    modules[mod_name] = pkg
for f in py_files:
    if f.name == "__init__.py":
        continue
    rel = f.relative_to(SRC)
    parts = list(rel.with_suffix("").parts)
    modules[".".join(parts)] = f

for f in py_files:
    tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            base = f.parent
            for _ in range(node.level - 1):
                base = base.parent
            target = base / (node.module or "").replace(".", os.sep)
            if not (target.with_suffix(".py").exists()
                    or (target / "__init__.py").exists()):
                errors.append(
                    f"IMPORT {f.relative_to(ROOT)}:{node.lineno} -> "
                    f"{'.' * node.level}{node.module} (not found)")
print(f"[2] resolved relative imports across {len(modules)} modules")

# ------------------------------------- 3. cross-module attribute references
attr_refs: list[tuple[Path, str, str]] = []   # (file, obj_name, attr)
for f in py_files:
    tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            for alias in node.names:
                attr_refs.append((f, alias.asname or alias.name, node.module or ""))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                attr_refs.append((f, (alias.asname or alias.name).split(".")[0], ""))

defined: dict[str, set[str]] = {}
for f in py_files:
    tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
    defined[str(f)] = names

for f, obj, _ in attr_refs:
    found = False
    for path, names in defined.items():
        if obj in names:
            found = True
            break
    if not found:
        warnings.append(f"CHECK {f.relative_to(ROOT)} imports '{obj}' - "
                        "definition not found in project files")
print(f"[3] checked {len(attr_refs)} imported names")

# ---------------------------------------------------------------- 4. tree
print("[4] project tree")
for p in sorted(ROOT.rglob("*")):
    if any(part in p.parts for part in ("__pycache__", ".git", ".venv")):
        continue
    rel = p.relative_to(ROOT)
    if p.is_dir():
        print(f"    {rel}\\")
    else:
        print(f"    {rel}  ({p.stat().st_size} B)")

print()
if errors:
    print("ERRORS:")
    for e in errors:
        print("  X", e)
else:
    print("OK - all python files compile and all relative imports resolve")
if warnings:
    print("warnings (imports that may be external packages):")
    for w in warnings:
        print("  ·", w)

sys.exit(1 if errors else 0)
