"""Find citation keys, with source positions, in LaTeX and Pandoc Markdown text."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Any LaTeX command whose name contains "cite" (natbib, biblatex, \nocite, ...),
# except the few that configure citations rather than make them.
CITE_COMMAND_RE = re.compile(r"\\([A-Za-z]*cite[A-Za-z]*)\*?", re.IGNORECASE)
NON_CITING_COMMANDS = {"citestyle", "citesetup", "citereset"}
OPTIONAL_ARG_RE = re.compile(r"\s*(?:\[[^\]]*\]|\([^)]*\))")
KEY_GROUP_RE = re.compile(r"\s*\{([^}]*)\}")
LATEX_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")
COMMENT_ENV_RE = re.compile(r"\\begin\{comment\}.*?\\end\{comment\}", re.DOTALL)
VERBATIM_ENV_RE = re.compile(r"\\begin\{(verbatim|lstlisting|minted)\}.*?\\end\{\1\}", re.DOTALL)

FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.DOTALL)
FENCED_CODE_RE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1", re.DOTALL | re.MULTILINE)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
PANDOC_CITE_RE = re.compile(r"(?<![\w@\\])-?@(\{[^}]+\}|[A-Za-z0-9_][\w:.#$%&+?<>~/-]*)")
PANDOC_KEY_TRAILING = ":.#$%&+?<>~/-"

SYNTAXES = ("latex", "markdown")


@dataclass(slots=True, frozen=True)
class CiteOccurrence:
    key: str
    offset: int
    line: int
    column: int


def _blank(match: re.Match[str]) -> str:
    """Replace a match with spaces, keeping newlines so offsets and line numbers survive."""
    return re.sub(r"[^\n]", " ", match.group(0))


def mask_latex(text: str) -> str:
    text = COMMENT_ENV_RE.sub(_blank, text)
    text = VERBATIM_ENV_RE.sub(_blank, text)
    return LATEX_COMMENT_RE.sub(_blank, text)


def mask_markdown(text: str) -> str:
    text = FRONT_MATTER_RE.sub(_blank, text)
    text = FENCED_CODE_RE.sub(_blank, text)
    text = HTML_COMMENT_RE.sub(_blank, text)
    return INLINE_CODE_RE.sub(_blank, text)


def _line_starts(text: str) -> list[int]:
    starts = [0]
    starts.extend(index + 1 for index, char in enumerate(text) if char == "\n")
    return starts


def _position(starts: list[int], offset: int) -> tuple[int, int]:
    low, high = 0, len(starts) - 1
    while low < high:
        middle = (low + high + 1) // 2
        if starts[middle] <= offset:
            low = middle
        else:
            high = middle - 1
    return low + 1, offset - starts[low] + 1


def _latex_keys(masked: str):
    for match in CITE_COMMAND_RE.finditer(masked):
        name = match.group(1).lower()
        if name in NON_CITING_COMMANDS:
            continue
        # biblatex multicite commands (\cites, \parencites, ...) take several key groups.
        multi = name.endswith("cites")
        position = match.end()
        while True:
            while (optional := OPTIONAL_ARG_RE.match(masked, position)) is not None:
                position = optional.end()
            group = KEY_GROUP_RE.match(masked, position)
            if group is None:
                break
            cursor = group.start(1)
            for raw in group.group(1).split(","):
                key = raw.strip()
                if key and key != "*":
                    yield key, cursor + (len(raw) - len(raw.lstrip()))
                cursor += len(raw) + 1
            position = group.end()
            if not multi:
                break


def _pandoc_keys(masked: str):
    for match in PANDOC_CITE_RE.finditer(masked):
        key = match.group(1)
        if key.startswith("{"):
            key = key[1:-1].strip()
        else:
            # Pandoc keys may contain internal punctuation but never end with it.
            key = key.rstrip(PANDOC_KEY_TRAILING)
        if key:
            yield key, match.start(1)


def find_citations(text: str, syntax: str = "latex") -> list[CiteOccurrence]:
    """Return every citation occurrence in ``text`` in document order."""
    if syntax == "latex":
        found = _latex_keys(mask_latex(text))
    elif syntax == "markdown":
        found = _pandoc_keys(mask_markdown(text))
    else:
        raise ValueError(f"unknown citation syntax: {syntax}")
    starts = _line_starts(text)
    occurrences = []
    for key, offset in found:
        line, column = _position(starts, offset)
        occurrences.append(CiteOccurrence(key=key, offset=offset, line=line, column=column))
    return occurrences


def unique_keys(occurrences) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for occurrence in occurrences:
        if occurrence.key not in seen:
            seen.add(occurrence.key)
            keys.append(occurrence.key)
    return keys
