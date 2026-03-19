#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".html", ".js", ".json", ".mjs", ".txt", ".xml"}
BRAND_REPLACEMENTS = {
    "Lofty Lab": "LYNCK Studio",
    "loftylab@support.com": "lynckstudio@support.com",
}
EXCLUDED_PATHS = {
    PROJECT_ROOT / "tools" / "build_loftylab.py",
    PROJECT_ROOT / "tools" / "rename_brand.py",
}
EXCLUDED_PARTS = {".git"}


def should_process(path: Path) -> bool:
    if not path.is_file():
        return False
    if path in EXCLUDED_PATHS:
        return False
    if any(part in EXCLUDED_PARTS for part in path.parts):
        return False
    return path.suffix.lower() in TEXT_SUFFIXES


def apply_replacements(text: str) -> str:
    for source, target in BRAND_REPLACEMENTS.items():
        text = text.replace(source, target)
    return text


def main() -> None:
    changed = 0
    for path in sorted(PROJECT_ROOT.rglob("*")):
        if not should_process(path):
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rewritten = apply_replacements(original)
        if rewritten == original:
            continue
        path.write_text(rewritten, encoding="utf-8")
        changed += 1
        print(path.relative_to(PROJECT_ROOT))
    print(f"Updated {changed} files")


if __name__ == "__main__":
    main()
