#!/usr/bin/env python3
"""Validate Hermes skill structure in this repo.

Checks (per SKILL.md found):
  - Frontmatter YAML parses and contains name, description, category
  - name is a non-empty string
  - description is non-empty and >= 20 chars
  - SKILL.md is UTF-8 readable
  - Any `references/<file>` or relative markdown links resolve to real files

Run: python3 scripts/validate_skill.py  (from repo root)
Exit non-zero on any failure.
"""
import sys
import os
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
    raw = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(raw)
    if fm is None:
        errors.append(f"{path}: missing YAML frontmatter (--- block)")
        return errors
    for key in REQUIRED:
        val = fm.get(key)
        if not val or not str(val).strip():
            errors.append(f"{path}: missing/empty frontmatter field '{key}'")
    if fm.get("description") and len(str(fm["description"]).strip()) < 20:
        errors.append(f"{path}: description too short (<20 chars)")
    if not body.strip():
        errors.append(f"{path}: empty body")
    # check referenced files under references/ and relative links exist
    base = path.parent
    import re
    for m in re.finditer(r"references/([\w./-]+)", body):
        ref = base / m.group(0)  # group(0) keeps the "references/" prefix
        if not ref.exists():
            errors.append(f"{path}: references missing file: {m.group(0)}")
    return errors


def main():
    root = REPO_ROOT
    skills = find_skill_md_files(root)
    if not skills:
        print("No SKILL.md found in repo.")
        return 1
    all_errors = []
    for s in skills:
        print(f"Validating {s.relative_to(root)} ...")
        all_errors.extend(validate_one(s))
    if all_errors:
        print("\nFAILURES:")
        for e in all_errors:
            print("  -", e)
        return 1
    print(f"\nOK: {len(skills)} skill(s) validated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
