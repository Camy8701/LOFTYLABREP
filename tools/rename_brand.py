#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".html", ".js", ".json", ".mjs", ".svg", ".txt", ".xml"}
BRAND_REPLACEMENTS = {
    "LOFTY LAB": "LYNCK Studio",
    "Lofty Lab": "LYNCK Studio",
    "loftylab@email.com": "lynckstudio@support.com",
    "loftylab@support.com": "lynckstudio@support.com",
}
LOGO_COMPONENT_RULE_OLD = (
    "`.framer-30Q4Y { -webkit-mask: ${w}; aspect-ratio: 2.3225806451612905; "
    "background-color: var(--token-0e3df59a-d2bd-4221-885a-76d4a23fa9fa, #030f2e); "
    "mask: ${w}; width: 72px; }`"
)
LOGO_COMPONENT_RULE_NEW = (
    "`.framer-30Q4Y { align-items: flex-start; display: flex; flex-direction: column; "
    "gap: 0px; height: 100%; justify-content: center; width: 100%; }`,"
    "`.framer-30Q4Y::before { content: \"LYNCK\"; color: "
    "var(--token-0e3df59a-d2bd-4221-885a-76d4a23fa9fa, #030f2e); font-family: "
    "\"Inter Display\", \"Inter Display Placeholder\", sans-serif; font-size: 14px; "
    "font-style: normal; font-weight: 900; letter-spacing: -0.08em; line-height: 0.82; "
    "text-transform: uppercase; }`,"
    "`.framer-30Q4Y::after { content: \"Studio\"; color: "
    "var(--token-0e3df59a-d2bd-4221-885a-76d4a23fa9fa, #030f2e); font-family: "
    "\"Inter Display\", \"Inter Display Placeholder\", sans-serif; font-size: 12px; "
    "font-style: normal; font-weight: 800; letter-spacing: -0.06em; line-height: 0.88; "
    "margin-top: -1px; text-transform: none; }`"
)
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
    text = text.replace(LOGO_COMPONENT_RULE_OLD, LOGO_COMPONENT_RULE_NEW)
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
