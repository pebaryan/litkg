"""Turn verification results into minimal, reviewable edits to BibTeX files."""

from __future__ import annotations

import difflib
import html
import re
from dataclasses import dataclass, field
from pathlib import Path

from .check import CheckReport, ReferenceResult
from .parser import _read_bibtex_value, bibtex_entry_spans
from .verify import Record, normalize_doi, title_similarity

FIELD_RE = re.compile(r"([A-Za-z][\w:.+-]*)\s*=\s*")
TAG_RE = re.compile(r"<[^>]+>")
BIBTEX_SPECIALS = {"&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_"}
FIXABLE_CODES = {
    "doi-not-found",
    "arxiv-not-found",
    "title-mismatch",
    "author-mismatch",
    "author-order",
    "year-mismatch",
    "missing-doi",
    "no-match",
}


@dataclass(slots=True)
class EntryFix:
    key: str
    path: str
    changes: dict[str, str | None]
    """Field name to new value; ``None`` removes the field."""
    reason: str
    record: Record


@dataclass(slots=True)
class FixPlan:
    fixes: list[EntryFix] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _bibtex_text(value: str) -> str:
    text = html.unescape(TAG_RE.sub("", value))
    text = re.sub(r"\s+", " ", text).strip()
    return "".join(BIBTEX_SPECIALS.get(char, char) for char in text)


def _protect_case(title: str) -> str:
    """Brace words BibTeX styles would otherwise lowercase (acronyms, CamelCase names)."""
    return re.sub(r"\b([A-Za-z]*[A-Z][a-z]*[A-Z][A-Za-z0-9]*)\b", r"{\1}", title)


def _authors_value(record: Record) -> str:
    return " and ".join(_bibtex_text(author) for author in record.authors if author.strip())


def changes_for(result: ReferenceResult, add_doi: bool = False) -> dict[str, str | None]:
    """Fields to change so the entry matches its suggested record."""
    record = result.candidate
    entry = result.definition.entry if result.definition else None
    if record is None or entry is None:
        return {}
    codes = {issue.code for issue in result.issues}
    replacing = bool(codes & {"doi-not-found", "arxiv-not-found"}) or (
        "title-mismatch" in codes and title_similarity(entry.title, record.title) < 0.9
    )
    changes: dict[str, str | None] = {}
    if record.title and (replacing or "title-mismatch" in codes):
        changes["title"] = _protect_case(_bibtex_text(record.title))
    if record.authors and (replacing or codes & {"author-mismatch", "author-order"}):
        changes["author"] = _authors_value(record)
    if record.year and (replacing or "year-mismatch" in codes):
        changes["year"] = str(record.year)
    current_doi = normalize_doi(entry.doi)
    # Pin the verified record whenever an entry is corrected for an error.
    pin = replacing or add_doi or any(issue.severity == "error" and issue.code in FIXABLE_CODES for issue in result.issues)
    if record.doi and record.doi != current_doi and pin:
        changes["doi"] = record.doi
    elif "doi-not-found" in codes and not record.doi:
        changes["doi"] = None
    if "arxiv-not-found" in codes:
        changes["eprint"] = record.arxiv_id  # None removes the nonexistent identifier
        changes["archiveprefix"] = "arXiv" if record.arxiv_id else None
    elif record.arxiv_id and replacing and not record.doi:
        changes["eprint"] = record.arxiv_id
        changes["archiveprefix"] = "arXiv"
    return changes


def plan_fixes(report: CheckReport, keys: list[str] | None = None, add_doi: bool = False) -> FixPlan:
    plan = FixPlan()
    wanted = set(keys or [])
    for result in report.results:
        if wanted and result.key not in wanted:
            continue
        codes = {issue.code for issue in result.issues}
        actionable = (result.severity in {"error", "warning"}) or (add_doi and "missing-doi" in codes)
        if not actionable or not codes & FIXABLE_CODES:
            continue
        if result.candidate is None:
            plan.skipped.append(f"{result.key}: no verified record to correct it from")
            continue
        if result.definition is None or Path(result.definition.path).suffix.lower() not in {".bib", ".bibtex"}:
            plan.skipped.append(f"{result.key}: only BibTeX files can be edited")
            continue
        changes = changes_for(result, add_doi=add_doi)
        if not changes:
            continue
        reason = "; ".join(
            issue.message
            for issue in result.issues
            if issue.code in FIXABLE_CODES and (issue.code != "missing-doi" or "doi" in changes)
        )
        plan.fixes.append(EntryFix(result.key, result.definition.path, changes, reason, result.candidate))
    for key in wanted - {result.key for result in report.results}:
        plan.skipped.append(f"{key}: not cited in this paper")
    return plan


def _field_spans(text: str, start: int, end: int) -> tuple[dict[str, tuple[int, int, int]], int]:
    """Top-level fields of the entry text[start:end] as name -> (name_start, value_start, value_end)."""
    brace = text.index("{", start)
    comma = text.find(",", brace, end)
    spans: dict[str, tuple[int, int, int]] = {}
    position = comma + 1 if comma >= 0 else end - 1
    closing = end - 1  # offset of the entry's closing brace
    while position < closing:
        while position < closing and (text[position].isspace() or text[position] == ","):
            position += 1
        match = FIELD_RE.match(text, position, closing)
        if not match:
            break
        value_start = match.end()
        cursor = value_start
        while True:
            _, cursor = _read_bibtex_value(text, cursor)
            tail = re.match(r"\s*#\s*", text[cursor:closing])
            if not tail:
                break
            cursor += tail.end()
        spans[match.group(1).lower()] = (match.start(), value_start, cursor)
        position = cursor
    return spans, closing


def apply_to_text(text: str, fix: EntryFix) -> str:
    spans = bibtex_entry_spans(text)
    if fix.key not in spans:
        raise KeyError(f"entry '{fix.key}' not found in {fix.path}")
    start, end = spans[fix.key]
    fields, closing = _field_spans(text, start, end)
    indent_match = re.search(r"\n([ \t]+)[A-Za-z]", text[start:end])
    indent = indent_match.group(1) if indent_match else "  "

    edits: list[tuple[int, int, str]] = []
    additions: list[str] = []
    for name, value in fix.changes.items():
        if name in fields:
            name_start, value_start, value_end = fields[name]
            if value is None:
                # Remove the field and the comma that follows it, if any.
                tail = re.match(r"\s*,", text[value_end:closing])
                stop = value_end + (tail.end() if tail else 0)
                line_start = text.rfind("\n", start, name_start)
                begin = line_start if line_start >= 0 and not text[line_start + 1 : name_start].strip() else name_start
                edits.append((begin, stop, ""))
            else:
                edits.append((value_start, value_end, "{" + value + "}"))
        elif value is not None:
            display = "archivePrefix" if name == "archiveprefix" else name
            additions.append(f"{indent}{display} = {{{value}}}")
    if additions:
        body_end = closing
        while body_end > start and text[body_end - 1].isspace():
            body_end -= 1
        separator = "" if text[body_end - 1] == "," else ","
        newline = "\r\n" if "\r\n" in text[start:end] else "\n"
        edits.append((body_end, closing, separator + newline + ("," + newline).join(additions) + newline))
    for begin, stop, replacement in sorted(edits, reverse=True):
        text = text[:begin] + replacement + text[stop:]
    return text


def preview(plan: FixPlan) -> tuple[str, dict[str, str]]:
    """Return a unified diff of the plan and the new content per file."""
    originals: dict[str, str] = {}
    updated: dict[str, str] = {}
    for fix in plan.fixes:
        if fix.path not in originals:
            with open(fix.path, encoding="utf-8", newline="") as handle:
                originals[fix.path] = handle.read()
            updated[fix.path] = originals[fix.path]
        updated[fix.path] = apply_to_text(updated[fix.path], fix)
    diff = []
    for path, before in originals.items():
        diff.extend(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                updated[path].splitlines(keepends=True),
                fromfile=f"a/{Path(path).name}",
                tofile=f"b/{Path(path).name}",
            )
        )
    return "".join(diff), {path: content for path, content in updated.items() if content != originals[path]}


def write(contents: dict[str, str]) -> list[str]:
    for path, content in contents.items():
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    return list(contents)
