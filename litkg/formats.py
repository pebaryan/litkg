"""Render a CheckReport for people (text, Markdown) and machines (JSON, SARIF, JUnit, GitHub)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import click

from . import __version__
from .check import STATUS_LABELS, CheckReport, Issue, ReferenceResult
from .verify import Record

FORMATS = ("text", "json", "sarif", "junit", "github", "markdown")

RULES = {
    "undefined": "Cited key has no bibliography entry",
    "conflict": "Cite key is defined differently in several bibliographies",
    "doi-not-found": "DOI does not exist",
    "arxiv-not-found": "arXiv identifier does not exist",
    "title-mismatch": "Title does not match the registry record",
    "author-mismatch": "Authors do not match the registry record",
    "author-order": "First author differs from the registry record",
    "year-mismatch": "Year differs from the registry record",
    "missing-doi": "Entry could include a DOI",
    "no-match": "No matching record found online",
    "lookup-failed": "Online lookup failed",
    "missing-title": "Entry has no title",
    "missing-authors": "Entry has no authors",
    "missing-year": "Entry has no year",
    "implausible-year": "Entry year looks wrong",
    "malformed-doi": "DOI is not well formed",
    "duplicate-work": "Same work cited under several keys",
    "missing-file": "Referenced file not found",
    "unreadable-bibliography": "Bibliography could not be read",
    "no-citations": "No citations found",
    "no-bibliography": "No bibliography found",
    "not-indexed": "Entry type is not checked online",
    "no-title": "Entry has no title to search for",
    "ignored": "Citation ignored by configuration",
}

UNICODE_SYMBOLS = {"error": ("✗", "red"), "warning": ("!", "yellow"), "note": ("·", "blue"), None: ("✓", "green")}
ASCII_SYMBOLS = {"error": ("x", "red"), "warning": ("!", "yellow"), "note": ("-", "blue"), None: ("+", "green")}
SYMBOLS = UNICODE_SYMBOLS


def supports_unicode(stream=None) -> bool:
    encoding = getattr(stream or sys.stdout, "encoding", None) or "ascii"
    try:
        "✓✗·—".encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False
    return True


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def display_path(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).resolve().relative_to(Path.cwd()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _where(issue_or_result) -> str:
    if isinstance(issue_or_result, ReferenceResult):
        citation = issue_or_result.citations[0] if issue_or_result.citations else None
        return f"{display_path(citation.path)}:{citation.line}:{citation.column}" if citation else ""
    location = display_path(issue_or_result.path)
    if issue_or_result.line:
        location += f":{issue_or_result.line}"
        if issue_or_result.column:
            location += f":{issue_or_result.column}"
    return location


def describe_record(record: Record) -> str:
    authors = record.authors[:3]
    names = "; ".join(authors) + (" et al." if len(record.authors) > 3 else "")
    parts = [f'"{record.title}"' if record.title else "", names, f"({record.year})" if record.year else ""]
    if record.doi:
        parts.append(f"doi:{record.doi}")
    elif record.arxiv_id:
        parts.append(f"arXiv:{record.arxiv_id}")
    return " ".join(part for part in parts if part)


# --------------------------------------------------------------------------- text


def render_text(report: CheckReport, verbose: bool = False, color: bool | None = None, unicode: bool | None = None) -> str:
    def style(text: str, **kwargs) -> str:
        return click.style(text, **kwargs) if color is not False else text

    unicode = supports_unicode() if unicode is None else unicode
    SYMBOLS = UNICODE_SYMBOLS if unicode else ASCII_SYMBOLS
    dash = "—" if unicode else "--"

    lines: list[str] = []
    manuscript = report.manuscript
    mode = "online" if report.options.online else "offline"
    lines.append(
        style(display_path(report.paper), bold=True)
        + f" {dash} {len(manuscript.keys)} cited keys, {len(manuscript.bibliographies)} "
        + f"bibliograph{'y' if len(manuscript.bibliographies) == 1 else 'ies'}, {mode}"
    )
    lines.append("")

    for issue in report.issues:
        symbol, colour = SYMBOLS[issue.severity]
        lines.append(f"{style(symbol, fg=colour)} {style(issue.code, fg=colour)}  {issue.message}  {style(_where(issue), dim=True)}")

    width = max((len(result.key) for result in report.results), default=0)
    quiet = 0
    for result in report.results:
        severity = result.severity
        shown = [issue for issue in result.issues if verbose or issue.severity != "note"]
        if not shown and not verbose:
            quiet += 1
            continue
        symbol, colour = SYMBOLS[severity if severity != "note" or verbose else None]
        lines.append(
            f"{style(symbol, fg=colour)} {style(result.key.ljust(width), bold=True)}  "
            f"{result.status:<11} {style(_where(result), dim=True)}"
        )
        for issue in shown:
            _, issue_colour = SYMBOLS[issue.severity]
            lines.append(f"    {style(issue.severity.ljust(7), fg=issue_colour)} {issue.message}")
        if result.candidate is not None and severity in {"error", "warning"}:
            lines.append(f"    {style('suggest', fg='cyan')} {describe_record(result.candidate)}")

    if report.results or report.issues:
        lines.append("")
    statuses = report.status_counts()
    if statuses:
        separator = " · " if unicode else ", "
        tally = separator.join(f"{count} {status}" for status, count in sorted(statuses.items(), key=lambda item: (-item[1], item[0])))
        hidden = f"  ({plural(quiet, 'citation')} without issues hidden; -v shows them)" if quiet else ""
        lines.append(tally + style(hidden, dim=True))
    counts = report.counts()
    verdict = style("PASSED", fg="green", bold=True) if report.passed else style("FAILED", fg="red", bold=True)
    lines.append(f"{verdict}  {plural(counts['error'], 'error')}, {plural(counts['warning'], 'warning')}, {plural(counts['note'], 'note')}")
    if not report.options.online and report.results:
        lines.append(style("Run with --online to verify references against Crossref, DataCite, OpenAlex, and arXiv.", dim=True))
    return "\n".join(lines)


# --------------------------------------------------------------------------- JSON


def render_json(report: CheckReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- SARIF


def _sarif_location(issue: Issue) -> list[dict]:
    if not issue.path:
        return []
    region = {}
    if issue.line:
        region["startLine"] = issue.line
        if issue.column:
            region["startColumn"] = issue.column
    physical: dict = {"artifactLocation": {"uri": display_path(issue.path), "uriBaseId": "%SRCROOT%"}}
    if region:
        physical["region"] = region
    return [{"physicalLocation": physical}]


def render_sarif(report: CheckReport) -> str:
    issues = report.all_issues()
    used = sorted({issue.code for issue in issues})
    results = []
    for issue in issues:
        message = f"[{issue.key}] {issue.message}" if issue.key else issue.message
        item = {"ruleId": issue.code, "level": issue.severity, "message": {"text": message}, "locations": _sarif_location(issue)}
        if issue.key:
            item["partialFingerprints"] = {"litkg/key": f"{issue.code}:{issue.key}"}
        results.append(item)
    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "litkg",
                        "version": __version__,
                        "informationUri": "https://github.com/pebaryan/litkg",
                        "rules": [
                            {"id": code, "name": code, "shortDescription": {"text": RULES.get(code, code)}}
                            for code in used
                        ],
                    }
                },
                "originalUriBaseIds": {"%SRCROOT%": {"uri": Path.cwd().resolve().as_uri() + "/"}},
                "results": results,
            }
        ],
    }
    return json.dumps(sarif, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- JUnit


def render_junit(report: CheckReport) -> str:
    strict = report.options.strict
    suite = ET.Element("testsuite", name="litkg", tests="0", failures="0", skipped="0")
    tests = failures = skipped = 0
    paper = display_path(report.paper)

    def add(name: str, issues: list[Issue], ignored: bool = False) -> None:
        nonlocal tests, failures, skipped
        tests += 1
        case = ET.SubElement(suite, "testcase", classname=paper, name=name)
        failing = [issue for issue in issues if issue.severity == "error" or (strict and issue.severity == "warning")]
        if ignored:
            skipped += 1
            ET.SubElement(case, "skipped", message="ignored by configuration")
        elif failing:
            failures += 1
            failure = ET.SubElement(case, "failure", message=failing[0].message, type=failing[0].code)
            failure.text = "\n".join(f"{issue.severity}: {issue.message} ({_where(issue)})" for issue in issues)

    for issue in report.issues:
        add(f"{issue.code}", [issue])
    for result in report.results:
        add(f"cite:{result.key}", result.issues, ignored=result.status == "ignored")
    suite.set("tests", str(tests))
    suite.set("failures", str(failures))
    suite.set("skipped", str(skipped))
    ET.indent(suite)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(suite, encoding="unicode")


# --------------------------------------------------------------------------- GitHub annotations


def _escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")


def render_github(report: CheckReport) -> str:
    commands = {"error": "error", "warning": "warning", "note": "notice"}
    lines = []
    for issue in report.all_issues():
        properties = []
        if issue.path:
            properties.append(f"file={_escape_property(display_path(issue.path))}")
        if issue.line:
            properties.append(f"line={issue.line}")
        if issue.column:
            properties.append(f"col={issue.column}")
        properties.append(f"title={_escape_property('litkg ' + issue.code + (' ' + issue.key if issue.key else ''))}")
        lines.append(f"::{commands[issue.severity]} {','.join(properties)}::{_escape_data(issue.message)}")
    counts = report.counts()
    lines.append(
        f"litkg: {'passed' if report.passed else 'failed'} - {plural(counts['error'], 'error')}, {plural(counts['warning'], 'warning')}"
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------- Markdown


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: CheckReport) -> str:
    counts = report.counts()
    icon = "✅" if report.passed else "❌"
    lines = [
        f"### {icon} litkg citation check — `{display_path(report.paper)}`",
        "",
        f"**{len(report.manuscript.keys)}** cited keys · **{counts['error']}** errors · "
        f"**{counts['warning']}** warnings · {'online' if report.options.online else 'offline'} check",
        "",
    ]
    statuses = report.status_counts()
    if statuses:
        lines.append(" · ".join(f"{STATUS_LABELS.get(status, status)}: {count}" for status, count in sorted(statuses.items())))
        lines.append("")
    rows = [issue for issue in report.all_issues() if issue.severity != "note"]
    if rows:
        lines += ["| | Key | Problem | Where |", "|---|---|---|---|"]
        for issue in rows:
            mark = "❌" if issue.severity == "error" else "⚠️"
            lines.append(f"| {mark} | `{_cell(issue.key or '')}` | {_cell(issue.message)} | `{_cell(_where(issue))}` |")
        suggestions = [result for result in report.results if result.candidate is not None and result.severity in {"error", "warning"}]
        if suggestions:
            lines += ["", "<details><summary>Suggested corrections</summary>", ""]
            for result in suggestions:
                lines.append(f"- `{result.key}` → {_cell(describe_record(result.candidate))}")
            lines += ["", "Run `litkg fix` to apply them.", "</details>"]
    else:
        lines.append("No problems found.")
    return "\n".join(lines) + "\n"


def render(report: CheckReport, fmt: str, verbose: bool = False, color: bool | None = None) -> str:
    if fmt == "text":
        return render_text(report, verbose=verbose, color=color)
    if fmt == "json":
        return render_json(report)
    if fmt == "sarif":
        return render_sarif(report)
    if fmt == "junit":
        return render_junit(report)
    if fmt == "github":
        return render_github(report)
    if fmt == "markdown":
        return render_markdown(report)
    raise ValueError(f"unknown format: {fmt}")


def write_output(path: str, content: str) -> None:
    target = Path(os.path.expandvars(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if path in {os.environ.get("GITHUB_STEP_SUMMARY", "\0")} else "w"
    with target.open(mode, encoding="utf-8") as handle:
        handle.write(content if content.endswith("\n") else content + "\n")
