"""Stable entry points for tools that build on LitKG.

Manuscript checkers such as qalmsw use this module to ask LitKG about references:
is this entry a real work, does its metadata match the record, and is it already in
the user's library? Everything here takes and returns plain data, so callers do not
depend on LitKG's internal report model. ``API_VERSION`` changes only on breaking
changes to this module.

    from litkg.api import ReferenceBackend

    with ReferenceBackend(online=True, store="library.ttl") as backend:
        for verdict in backend.verify(backend.load_bibliography("refs.bib")):
            print(verdict.key, verdict.status, [f.message for f in verdict.findings])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .check import combine_with_library, identity, library_index, offline_issues
from .ontology import normalize_key
from .parser import ReferenceInfo, _split_people, parse_bibliography
from .verify import Fetcher, Finding, HttpClient, Record, Verification, Verifier, latex_to_text

API_VERSION = 1

__all__ = ["API_VERSION", "Finding", "Record", "ReferenceBackend", "ReferenceVerdict", "make_entry"]


@dataclass(slots=True)
class ReferenceVerdict:
    """What LitKG concluded about one bibliography entry."""

    key: str | None
    status: str
    """verified | in-library | unchecked | unverified | mismatch | not-found | skipped"""
    findings: list[Finding] = field(default_factory=list)
    record: Record | None = None
    """The registry record the entry was compared against."""
    candidate: Record | None = None
    """A record to suggest as the correct version of the entry, if any."""
    library_paper: str | None = None
    """URI of the matching paper in the LitKG library, if any."""

    @property
    def severity(self) -> str | None:
        for severity in ("error", "warning", "note"):
            if any(finding.severity == severity for finding in self.findings):
                return severity
        return None

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "status": self.status,
            "severity": self.severity,
            "findings": [{"severity": f.severity, "code": f.code, "message": f.message} for f in self.findings],
            "record": self.record.to_dict() if self.record else None,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "library_paper": self.library_paper,
        }


def make_entry(
    key: str | None = None,
    title: str | None = None,
    authors: str | list[str] | None = None,
    year: int | str | None = None,
    doi: str | None = None,
    eprint: str | None = None,
    entry_type: str | None = None,
    **fields: str,
) -> ReferenceInfo:
    """Build an entry from loose fields, e.g. one parsed by another tool's BibTeX reader.

    ``authors`` may be a BibTeX author string ("A and B") or a list.
    """
    people = _split_people(authors) if isinstance(authors, str) else list(authors or [])
    try:
        year_value = int(str(year)[:4]) if year else None
    except ValueError:
        year_value = None
    extra = {name.lower(): str(value) for name, value in fields.items() if value}
    if eprint:
        extra.setdefault("eprint", eprint)
        extra.setdefault("archiveprefix", "arXiv")
    return ReferenceInfo(
        raw_text=title or "",
        title=title or None,
        doi=doi or None,
        authors=people,
        year=year_value,
        key=key,
        entry_type=(entry_type or "").lower() or None,
        fields=extra,
    )


class ReferenceBackend:
    """Checks bibliography entries offline, against the library, and (optionally) online.

    Use it as a context manager, or call ``close()``, so the response cache is saved.
    """

    def __init__(
        self,
        *,
        online: bool = True,
        store: str | Path | None = None,
        cache_dir: str | Path | None = ".litkg_cache",
        mailto: str | None = None,
        workers: int = 4,
        fetcher: Fetcher | None = None,
    ) -> None:
        self.online = online
        self.workers = workers
        self._library = library_index(str(store)) if store else {}
        self._client: HttpClient | None = None
        if fetcher is None and online:
            self._client = HttpClient(cache_dir=str(cache_dir) if cache_dir else None, mailto=mailto)
            fetcher = self._client
        self._verifier = Verifier(fetcher, mailto=mailto) if fetcher is not None else None

    # -- inputs

    @staticmethod
    def load_bibliography(path: str | Path) -> list[ReferenceInfo]:
        """Parse a BibTeX/biblatex or CSL-JSON file into entries."""
        return list(parse_bibliography(str(path)).entries)

    # -- queries

    def in_library(self, entry: ReferenceInfo) -> str | None:
        """Return the library paper URI matching the entry by DOI or title, if any."""
        return self._library.get(identity(entry)) or self._library.get(
            f"title:{normalize_key(latex_to_text(entry.title))}"
        )

    def verify(self, entries: list[ReferenceInfo]) -> list[ReferenceVerdict]:
        """Return one verdict per entry, in order."""
        verdicts = []
        for entry in entries:
            paper = self.in_library(entry)
            verdicts.append(
                ReferenceVerdict(
                    key=entry.key,
                    status="in-library" if paper else "unchecked",
                    findings=offline_issues(entry),
                    library_paper=paper,
                )
            )
        if self.online and self._verifier is not None and entries:
            online = self._verifier.verify_many(entries, workers=self.workers)
            for verdict, verification in zip(verdicts, online, strict=True):
                self._merge(verdict, verification)
        return verdicts

    def suggest(self, title: str, authors: str | list[str] | None = None, year: int | None = None, limit: int = 5) -> list[tuple[float, Record]]:
        """Rank real works whose title resembles ``title`` (needs ``online=True``)."""
        if self._verifier is None:
            return []
        return self._verifier.suggest(make_entry(title=title, authors=authors, year=year), limit=limit)

    @staticmethod
    def _merge(verdict: ReferenceVerdict, verification: Verification) -> None:
        status, findings = combine_with_library(verdict.status == "in-library", verification)
        verdict.status = status
        verdict.findings.extend(findings)
        verdict.record = verification.record
        verdict.candidate = verification.candidate

    # -- lifecycle

    def close(self) -> None:
        if self._client is not None:
            self._client.save()

    def __enter__(self) -> ReferenceBackend:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
