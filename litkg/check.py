"""Check every citation in a manuscript: is it defined, consistent, well-formed, and real?"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from pathlib import Path

from .manuscript import Citation, Manuscript, load_manuscript
from .ontology import normalize_key
from .parser import ReferenceInfo, parse_bibliography
from .verify import Finding, Record, Verification, Verifier, is_wellformed_doi, latex_to_text, normalize_doi

SEVERITIES = ("error", "warning", "note")
CONFIG_NAMES = (".litkg.json", "litkg.json")

STATUS_LABELS = {
    "verified": "verified online",
    "in-library": "matched a paper in your library",
    "unchecked": "not checked online",
    "unverified": "could not be verified",
    "mismatch": "metadata does not match the record",
    "not-found": "identifier does not exist",
    "undefined": "no bibliography entry",
    "conflict": "defined differently in several places",
    "skipped": "not checkable online",
    "ignored": "ignored by configuration",
}


@dataclass(slots=True)
class Issue:
    severity: str
    code: str
    message: str
    key: str | None = None
    path: str | None = None
    line: int | None = None
    column: int | None = None

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__slots__ if getattr(self, name) is not None}


@dataclass(slots=True)
class Definition:
    entry: ReferenceInfo
    path: str


@dataclass(slots=True)
class ReferenceResult:
    key: str
    status: str
    citations: list[Citation]
    definition: Definition | None = None
    issues: list[Issue] = field(default_factory=list)
    record: Record | None = None
    candidate: Record | None = None
    library_paper: str | None = None

    @property
    def severity(self) -> str | None:
        for severity in SEVERITIES:
            if any(issue.severity == severity for issue in self.issues):
                return severity
        return None

    def to_dict(self) -> dict:
        entry = self.definition.entry if self.definition else None
        return {
            "key": self.key,
            "status": self.status,
            "severity": self.severity,
            "citations": [{"path": c.path, "line": c.line, "column": c.column} for c in self.citations],
            "entry": None
            if entry is None
            else {
                "path": self.definition.path,
                "type": entry.entry_type,
                "title": entry.title,
                "authors": entry.authors,
                "year": entry.year,
                "doi": entry.doi,
                "venue": entry.venue,
            },
            "issues": [issue.to_dict() for issue in self.issues],
            "record": self.record.to_dict() if self.record else None,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "library_paper": self.library_paper,
        }


@dataclass(slots=True)
class CheckOptions:
    bibliographies: list[str] = field(default_factory=list)
    online: bool = False
    strict: bool = False
    ignore: dict[str, str] = field(default_factory=dict)
    mailto: str | None = None
    store: str | None = None
    cache_dir: str | None = ".litkg_cache"
    workers: int = 4


@dataclass(slots=True)
class CheckReport:
    paper: str
    manuscript: Manuscript
    options: CheckOptions
    results: list[ReferenceResult] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    """Issues not tied to a single cite key (missing files, duplicate works, no citations)."""

    def all_issues(self) -> list[Issue]:
        issues = list(self.issues)
        for result in self.results:
            issues.extend(result.issues)
        return issues

    def counts(self) -> dict[str, int]:
        counts = {severity: 0 for severity in SEVERITIES}
        for issue in self.all_issues():
            counts[issue.severity] += 1
        return counts

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for result in self.results:
            counts[result.status] = counts.get(result.status, 0) + 1
        return counts

    @property
    def passed(self) -> bool:
        counts = self.counts()
        return counts["error"] == 0 and (not self.options.strict or counts["warning"] == 0)

    def to_dict(self) -> dict:
        return {
            "tool": "litkg",
            "paper": self.paper,
            "generated": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "online": self.options.online,
            "strict": self.options.strict,
            "passed": self.passed,
            "files": self.manuscript.files,
            "bibliographies": self.manuscript.bibliographies,
            "summary": {"citations": len(self.manuscript.keys), "statuses": self.status_counts(), "issues": self.counts()},
            "issues": [issue.to_dict() for issue in self.issues],
            "references": [result.to_dict() for result in self.results],
        }


# --------------------------------------------------------------------------- configuration


def find_config(paper: str | Path) -> Path | None:
    for directory in (Path(paper).resolve().parent, Path.cwd()):
        for name in CONFIG_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def load_config(path: str | Path | None) -> dict:
    """Read a JSON config. ``ignore`` may be a list of keys or a ``{key: reason}`` object."""
    if path is None:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    base = Path(path).resolve().parent
    ignore = data.get("ignore", {})
    if isinstance(ignore, list):
        ignore = {str(key): "" for key in ignore}
    data["ignore"] = {str(key): str(reason) for key, reason in dict(ignore).items()}
    data["bib"] = [str((base / item).resolve()) for item in data.get("bib", [])]
    if data.get("store"):
        data["store"] = str((base / data["store"]).resolve())
    return data


# --------------------------------------------------------------------------- checks


def identity(entry: ReferenceInfo) -> str:
    doi = normalize_doi(entry.doi)
    if doi:
        return f"doi:{doi}"
    return f"title:{normalize_key(latex_to_text(entry.title or entry.raw_text))}"


def offline_issues(entry: ReferenceInfo) -> list[Finding]:
    findings: list[Finding] = []
    if not entry.title:
        findings.append(Finding("error", "missing-title", "entry has no title"))
    if not entry.authors and (entry.entry_type or "").lower() not in {"misc", "online", "manual", "software", "www"}:
        findings.append(Finding("warning", "missing-authors", "entry has no authors"))
    if not entry.year:
        findings.append(Finding("warning", "missing-year", "entry has no year"))
    elif entry.year > _dt.date.today().year + 1 or entry.year < 1450:
        findings.append(Finding("warning", "implausible-year", f"year {entry.year} looks wrong"))
    if entry.doi and not is_wellformed_doi(entry.doi):
        findings.append(Finding("error", "malformed-doi", f'"{entry.doi}" is not a valid DOI'))
    return findings


def library_index(store_path: str | None) -> dict[str, str]:
    if not store_path or not Path(store_path).exists():
        return {}
    from .queries import list_papers
    from .store import LitStore

    index: dict[str, str] = {}
    for row in list_papers(LitStore(store_path)):
        uri = str(row.get("paper"))
        if row.get("doi"):
            index[f"doi:{normalize_doi(str(row['doi'])) or ''}"] = uri
        if row.get("title"):
            index.setdefault(f"title:{normalize_key(str(row['title']))}", uri)
    return index


def _anchor(result: ReferenceResult, finding: Finding) -> Issue:
    first = result.citations[0] if result.citations else None
    return Issue(
        severity=finding.severity,
        code=finding.code,
        message=finding.message,
        key=result.key,
        path=first.path if first else None,
        line=first.line if first else None,
        column=first.column if first else None,
    )


def check_paper(paper: str | Path, options: CheckOptions | None = None, verifier: Verifier | None = None) -> CheckReport:
    options = options or CheckOptions()
    manuscript = load_manuscript(paper, options.bibliographies)
    report = CheckReport(paper=str(Path(paper).resolve()), manuscript=manuscript, options=options)

    for reference, source, line in manuscript.missing:
        report.issues.append(
            Issue("error", "missing-file", f"referenced file not found: {reference}", path=source, line=line or None)
        )

    definitions: dict[str, list[Definition]] = {}
    for bib_path in manuscript.bibliographies:
        try:
            bibliography = parse_bibliography(bib_path)
        except (OSError, ValueError) as exc:
            report.issues.append(Issue("error", "unreadable-bibliography", f"cannot read bibliography: {exc}", path=bib_path))
            continue
        for entry in bibliography.entries:
            if entry.key:
                definitions.setdefault(str(entry.key), []).append(Definition(entry, bib_path))

    keys = manuscript.keys
    if not keys:
        report.issues.append(Issue("error", "no-citations", "no citations found; check the citation syntax", path=report.paper))
    elif not manuscript.bibliographies:
        report.issues.append(
            Issue("error", "no-bibliography", "no bibliography found; add \\bibliography{...} or pass --bib", path=report.paper)
        )

    library = library_index(options.store)
    to_verify: list[ReferenceResult] = []
    for key in keys:
        result = ReferenceResult(key=key, status="unchecked", citations=manuscript.locations(key))
        report.results.append(result)
        if key in options.ignore:
            result.status = "ignored"
            reason = options.ignore[key]
            result.issues.append(_anchor(result, Finding("note", "ignored", f"ignored{': ' + reason if reason else ''}")))
            continue
        found = definitions.get(key, [])
        if not found:
            result.status = "undefined"
            result.issues.append(_anchor(result, Finding("error", "undefined", f"no bibliography entry for '{key}'")))
            continue
        result.definition = found[0]
        if len({identity(definition.entry) for definition in found}) > 1:
            result.status = "conflict"
            places = ", ".join(sorted({Path(definition.path).name for definition in found}))
            result.issues.append(
                _anchor(result, Finding("error", "conflict", f"'{key}' is defined differently in {places}"))
            )
            continue
        for finding in offline_issues(result.definition.entry):
            result.issues.append(_anchor(result, finding))
        entry = result.definition.entry
        library_match = library.get(identity(entry)) or library.get(f"title:{normalize_key(latex_to_text(entry.title))}")
        if library_match:
            result.library_paper = library_match
            result.status = "in-library"
        if options.online:
            to_verify.append(result)

    by_identity: dict[str, list[str]] = {}
    for result in report.results:
        if result.definition is not None and result.status != "conflict":
            by_identity.setdefault(identity(result.definition.entry), []).append(result.key)
    for work, same in by_identity.items():
        if len(same) > 1 and not work.endswith(":"):
            for key in same[1:]:
                repeat = report.results[keys.index(key)]
                repeat.issues.append(
                    _anchor(repeat, Finding("warning", "duplicate-work", f"same work as '{same[0]}' under another key"))
                )

    if to_verify:
        _verify_online(to_verify, options, verifier)
    return report


def _verify_online(results: list[ReferenceResult], options: CheckOptions, verifier: Verifier | None) -> None:
    client = None
    if verifier is None:
        from .verify import HttpClient

        client = HttpClient(cache_dir=options.cache_dir, mailto=options.mailto)
        verifier = Verifier(client, mailto=options.mailto)
    try:
        verifications = verifier.verify_many([result.definition.entry for result in results], workers=options.workers)
    finally:
        if client is not None:
            client.save()
    for result, verification in zip(results, verifications, strict=True):
        status, findings = combine_with_library(result.status == "in-library", verification)
        result.status = status
        result.record = verification.record
        result.candidate = verification.candidate
        for finding in findings:
            result.issues.append(_anchor(result, finding))


def combine_with_library(in_library: bool, verification: Verification) -> tuple[str, list[Finding]]:
    """Merge a registry verdict with library evidence.

    A paper in the local library is evidence enough when registries have no record of it.
    """
    if in_library and verification.status in {"unverified", "skipped"}:
        return "in-library", [f for f in verification.findings if f.code not in {"no-match", "not-indexed"}]
    return verification.status, list(verification.findings)
