"""Load a manuscript: follow LaTeX includes, collect citations, and discover its bibliographies."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .citations import find_citations, mask_latex

MARKDOWN_SUFFIXES = {".md", ".markdown", ".qmd", ".rmd", ".pmd"}
BIBLIOGRAPHY_SUFFIXES = {".bib", ".bibtex", ".json"}

INCLUDE_RE = re.compile(r"\\(?:input|include|subfile)\s*\{([^}]+)\}")
IMPORT_RE = re.compile(r"\\(?:sub)?import\*?\s*\{([^}]*)\}\s*\{([^}]+)\}")
BIBLIOGRAPHY_RE = re.compile(r"\\bibliography\s*\{([^}]+)\}")
ADDBIBRESOURCE_RE = re.compile(r"\\add(?:bibresource|globalbib|sectionbib)\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.DOTALL)


@dataclass(slots=True, frozen=True)
class Citation:
    key: str
    path: str
    line: int
    column: int


@dataclass(slots=True)
class Manuscript:
    path: str
    syntax: str
    files: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    bibliographies: list[str] = field(default_factory=list)
    missing: list[tuple[str, str, int]] = field(default_factory=list)
    """Referenced files that do not exist, as ``(reference, referencing file, line)``."""

    @property
    def keys(self) -> list[str]:
        seen: dict[str, None] = {}
        for citation in self.citations:
            seen.setdefault(citation.key, None)
        return list(seen)

    def locations(self, key: str) -> list[Citation]:
        return [citation for citation in self.citations if citation.key == key]


def syntax_for(path: str | Path) -> str:
    return "markdown" if Path(path).suffix.lower() in MARKDOWN_SUFFIXES else "latex"


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _resolve(base: Path, reference: str, default_suffix: str) -> Path:
    candidate = (base / reference.strip()).expanduser()
    if candidate.suffix.lower() != default_suffix and not candidate.exists():
        candidate = candidate.with_name(candidate.name + default_suffix)
    return candidate.resolve()


def _front_matter_bibliographies(text: str) -> list[str]:
    """Read ``bibliography:`` from YAML front matter (scalar, flow list, or block list)."""
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return []
    lines = match.group(1).splitlines()
    for index, line in enumerate(lines):
        found = re.match(r"^bibliography\s*:\s*(.*)$", line)
        if not found:
            continue
        value = found.group(1).strip()
        if value.startswith("["):
            return [item.strip().strip("'\"") for item in value.strip("[]").split(",") if item.strip()]
        if value:
            return [value.strip("'\"")]
        items = []
        for follow in lines[index + 1 :]:
            item = re.match(r"^\s+-\s*(.+)$", follow)
            if not item:
                break
            items.append(item.group(1).strip().strip("'\""))
        return items
    return []


def load_manuscript(path: str | Path, bibliographies: list[str | Path] | tuple = ()) -> Manuscript:
    """Read a manuscript and everything it includes.

    Explicit ``bibliographies`` are used in addition to the ones the manuscript declares.
    """
    root = Path(path).resolve()
    syntax = syntax_for(root)
    manuscript = Manuscript(path=str(root), syntax=syntax)
    declared: list[Path] = []

    visited: set[Path] = set()
    base = root.parent  # LaTeX resolves includes relative to the main file.

    def visit(current: Path) -> None:
        if current in visited:
            return
        visited.add(current)
        text = current.read_text(encoding="utf-8", errors="replace")
        manuscript.files.append(str(current))
        # Walk citations and includes together so the result follows document order.
        events: list[tuple[int, Citation | Path]] = [
            (occurrence.offset, Citation(occurrence.key, str(current), occurrence.line, occurrence.column))
            for occurrence in find_citations(text, syntax)
        ]
        if syntax == "markdown":
            declared.extend(_resolve(current.parent, reference, ".bib") for reference in _front_matter_bibliographies(text))
        else:
            masked = mask_latex(text)
            includes = [(match.start(), reference, base) for match in INCLUDE_RE.finditer(masked) for reference in match.group(1).split(",")]
            includes += [(match.start(), match.group(2), base / match.group(1).strip()) for match in IMPORT_RE.finditer(masked)]
            for offset, reference, directory in includes:
                child = _resolve(directory, reference, ".tex")
                if child.exists():
                    events.append((offset, child))
                else:
                    manuscript.missing.append((reference.strip(), str(current), _line_of(text, offset)))
            for match in BIBLIOGRAPHY_RE.finditer(masked):
                declared.extend(_resolve(base, reference, ".bib") for reference in match.group(1).split(",") if reference.strip())
            for match in ADDBIBRESOURCE_RE.finditer(masked):
                declared.append(_resolve(base, match.group(1), ".bib"))
        for _, event in sorted(events, key=lambda item: item[0]):
            if isinstance(event, Path):
                visit(event)
            else:
                manuscript.citations.append(event)

    visit(root)

    seen: set[Path] = set()
    for candidate in [*declared, *(Path(item).resolve() for item in bibliographies)]:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            manuscript.bibliographies.append(str(candidate))
        else:
            manuscript.missing.append((str(candidate), str(root), 0))
    return manuscript
