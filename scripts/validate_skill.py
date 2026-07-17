#!/usr/bin/env python3
"""Validate Hermes skill structure in this repo against the agentskills.io spec.

Checks (per SKILL.md found):
  - Frontmatter YAML parses; name + description required
  - name: 1-64 chars, lowercase a-z/0-9/hyphen, no leading/trailing hyphen, no --
  - name must match its parent directory
  - description: 1-1024 chars
  - 'license' field recommended when a LICENSE file is bundled (warning)
  - SKILL.md UTF-8 readable, non-empty body
  - Any local references/, scripts/, or templates/ path resolves to a real file

Run: python3 scripts/validate_skill.py  (from repo root)
Exit non-zero on any failure.
"""
import sys
import os
import re
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML not installed; installing is one option, but we parse manually instead.")
    yaml = None

REQUIRED = ("name", "description", "category")
REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_frontmatter(text: str):
    """Return (dict, body) or (None, text) if no frontmatter."""
    if not text.startswith("---"):
        return None, text
    # find closing ---
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, text
    fm = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1:])
    data = {}
    if yaml is not None:
        data = yaml.safe_load(fm) or {}
    else:
        # minimal fallback parser: key: value
        for ln in fm.splitlines():
            if ":" in ln:
                k, _, v = ln.partition(":")
                data[k.strip()] = v.strip()
    return data, body


def find_skill_md_files(root: Path):
    return list(root.rglob("SKILL.md"))


def validate_one(path: Path):
    errors = []
    warnings = []
    raw = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(raw)
    if fm is None:
        errors.append(f"{path}: missing YAML frontmatter (--- block)")
        return errors
    # name: required, 1-64, lowercase alnum + hyphen, no leading/trailing, no --
    name = fm.get("name")
    if not name or not str(name).strip():
        errors.append(f"{path}: missing/empty frontmatter field 'name'")
    else:
        n = str(name)
        if not (1 <= len(n) <= 64):
            errors.append(f"{path}: name length must be 1-64 (got {len(n)})")
        if not re.fullmatch(r"[a-z0-9-]+", n):
            errors.append(f"{path}: name must be lowercase letters, numbers, hyphens only")
        if n.startswith("-") or n.endswith("-"):
            errors.append(f"{path}: name must not start/end with hyphen")
        if "--" in n:
            errors.append(f"{path}: name must not contain consecutive hyphens")
        if n != path.parent.name:
            errors.append(f"{path}: name '{n}' must match parent dir '{path.parent.name}'")
    # description: required, 1-1024, non-empty
    desc = fm.get("description")
    if not desc or not str(desc).strip():
        errors.append(f"{path}: missing/empty frontmatter field 'description'")
    else:
        d = str(desc)
        if not (1 <= len(d) <= 1024):
            errors.append(f"{path}: description length must be 1-1024 (got {len(d)})")
    # license: optional per spec, but recommended when a LICENSE file is bundled
    if "license" not in fm and (path.parent / "LICENSE").exists():
        warnings.append(f"{path}: no 'license' field though LICENSE is bundled (recommended)")
    if not body.strip():
        errors.append(f"{path}: empty body")
    # Check referenced local support files and relative links exist
    base = path.parent
    for m in re.finditer(r"(?:references|scripts|templates)/([\w./-]+)", body):
        ref = base / m.group(0)
        if not ref.exists():
            errors.append(f"{path}: missing support file: {m.group(0)}")
    return errors, warnings


def main():
    root = REPO_ROOT
    skills = find_skill_md_files(root)
    if not skills:
        print("No SKILL.md found in repo.")
        return 1
    all_errors = []
    all_warnings = []
    for s in skills:
        print(f"Validating {s.relative_to(root)} ...")
        errs, warns = validate_one(s)
        all_errors.extend(errs)
        all_warnings.extend(warns)
    for w in all_warnings:
        print(f"  WARNING: {w}")
    if all_errors:
        print("\nFAILURES:")
        for e in all_errors:
            print("  -", e)
        return 1
    print(f"\nOK: {len(skills)} skill(s) validated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
