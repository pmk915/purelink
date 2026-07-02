from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
DOC_PATHS = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
IGNORED_PREFIXES = (
    "http://",
    "https://",
    "mailto:",
    "tel:",
    "#",
)


def _target_path(source: Path, raw_link: str) -> Path | None:
    link = raw_link.strip()
    if not link:
        return None
    if any(link.startswith(prefix) for prefix in IGNORED_PREFIXES):
        return None

    target = link.split("#", 1)[0].strip()
    if not target:
        return None
    if "://" in target:
        return None

    target = unquote(target)
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]

    path = Path(target)
    if path.is_absolute():
        return None
    return (source.parent / path).resolve()


def main() -> int:
    broken: list[tuple[Path, str]] = []

    for doc_path in DOC_PATHS:
        text = doc_path.read_text(encoding="utf-8")
        for match in LINK_PATTERN.finditer(text):
            raw_link = match.group(1)
            target = _target_path(doc_path, raw_link)
            if target is None:
                continue
            try:
                target.relative_to(ROOT)
            except ValueError:
                broken.append((doc_path, raw_link))
                continue
            if not target.exists():
                broken.append((doc_path, raw_link))

    if broken:
        print("Broken Markdown links found:")
        for doc_path, raw_link in broken:
            print(f"- {doc_path.relative_to(ROOT)} -> {raw_link}")
        return 1

    print(f"Checked {len(DOC_PATHS)} Markdown files. No broken relative links found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
