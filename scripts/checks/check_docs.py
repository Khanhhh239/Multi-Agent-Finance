"""Check required documentation and local Markdown file links, offline.

Supports inline links/images and reference definitions; ignores fenced/inline
code and HTML comments. Remote URLs and heading fragments are not validated.
No dependency on Git, downloaded datasets, or the model environment.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_DOCS = (
    "AGENTS.md", "README.md", "docs/README.md", "docs/project-overview.md",
    "docs/getting-started.md", "docs/CONTRIBUTING.md",
    "docs/reference/repository-structure.md", "docs/reference/t1-data-contracts.md",
    "data/README.md", "notebooks/README.md", "research/references/README.md",
)
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
INLINE_CODE = re.compile(r"(`+).*?\1", re.DOTALL)
COMMENTS = re.compile(r"<!--.*?-->", re.DOTALL)
DESTINATION = r"(?:<(?P<angle>[^>\n]+)>|(?P<plain>(?:\\.|[^\s()\\]|\([^()\n]*\))+))"
INLINE_LINK = re.compile(
    r"!?\[[^\]\n]*\]\(\s*" + DESTINATION
    + r"(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'))?\s*\)"
)
REFERENCE = re.compile(r"^ {0,3}\[[^\]\n]+\]:\s*" + DESTINATION, re.MULTILINE)


def blank(match):
    """Keep offsets and line numbers while masking non-prose content."""
    return re.sub(r"[^\n]", " ", match.group(0))


def prose(text):
    text = COMMENTS.sub(blank, text)
    lines = []
    fence = None
    for line in text.splitlines(keepends=True):
        marker = FENCE.match(line)
        if fence:
            lines.append(re.sub(r"[^\n]", " ", line))
            if (marker and marker[1][0] == fence[0]
                    and len(marker[1]) >= len(fence) and not marker[2].strip()):
                fence = None
        elif marker:
            fence = marker[1]
            lines.append(re.sub(r"[^\n]", " ", line))
        else:
            lines.append(line)
    return INLINE_CODE.sub(blank, "".join(lines))


def local_links(text):
    text = prose(text)
    matches = sorted([*INLINE_LINK.finditer(text), *REFERENCE.finditer(text)],
                     key=lambda match: match.start())
    for match in matches:
        target = match["angle"] or match["plain"]
        # These are outside this checker's scope, including fragment-only links.
        if target.startswith(("#", "//")) or re.match(r"^[a-zA-Z][\w+.-]*:", target):
            continue
        target = unquote(target.split("#", 1)[0].split("?", 1)[0])
        target = re.sub(r"\\([\\() ])", r"\1", target)
        if target:
            yield text.count("\n", 0, match.start()) + 1, target


def iter_documents(root):
    for current, dirs, files in os.walk(root):
        directory = Path(current)
        in_data = directory.relative_to(root).parts[:1] == ("data",)
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                         and not (in_data and d in {"raw", "interim", "processed"})
                         and not (directory / d).is_symlink())
        for name in sorted(files):
            if name.lower().endswith(".md"):
                yield directory / name


def check_repository(root, required=REQUIRED_DOCS):
    root = Path(root).resolve()
    errors = [f"Missing required document: {name}" for name in required
              if not (root / name).is_file()]
    documents = list(iter_documents(root))
    for document in documents:
        relative = document.relative_to(root).as_posix()
        try:
            if not document.resolve().is_relative_to(root):
                errors.append(f"{relative}: document points outside repository")
                continue
            text = document.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{relative}: cannot read UTF-8 Markdown: {exc}")
            continue
        for line, target in local_links(text):
            destination = (root / target.lstrip("/") if target.startswith("/")
                           else document.parent / target).resolve()
            if not destination.is_relative_to(root):
                errors.append(f"{relative}:{line}: link escapes repository: {target}")
            elif not destination.exists():
                errors.append(f"{relative}:{line}: missing local target: {target}")
    return len(documents), errors


def main():
    count, errors = check_repository(ROOT)
    for error in errors:
        print(error)
    if errors:
        print(f"FAIL: {len(errors)} error(s) in {count} Markdown files.")
        return 1
    print(f"OK: {count} Markdown files; required docs and local file links pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
