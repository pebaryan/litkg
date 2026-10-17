"""Verify bibliography entries against Crossref, DataCite (via doi.org), OpenAlex, and arXiv.

Network access is opt-in. Every response is cached on disk so repeated runs (and CI) are
fast and deterministic, and each host is rate limited to stay inside its usage policy.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlparse
from urllib.request import Request, urlopen

from . import __version__
from .ontology import normalize_key
from .parser import ReferenceInfo

DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)
DOI_PREFIX_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
ARXIV_NEW_RE = re.compile(r"(?<![\d.])(\d{4}\.\d{4,5})(?:v\d+)?(?![\d])")
ARXIV_OLD_RE = re.compile(r"\b([a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?\b")
ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.(.+)$", re.IGNORECASE)
ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+?)(?:v\d+)?(?:\.pdf)?(?:[?#]|$)", re.IGNORECASE)
LATEX_ACCENT_RE = re.compile(r"\\[`'^\"~=.uvHtcdbk]\s*\{?\s*([A-Za-z])\s*\}?")
LATEX_COMMAND_RE = re.compile(r"\\[A-Za-z]+\*?\s*")

# Entry types that are usually not indexed by scholarly registries.
UNINDEXED_TYPES = {"misc", "online", "electronic", "www", "webpage", "manual", "software", "unpublished", "post", "post-weblog"}

TITLE_MATCH = 0.90
TITLE_RELATED = 0.60

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


class LookupFailed(Exception):
    """A registry could not be reached or returned an unexpected response."""


@dataclass(slots=True)
class Response:
    status: int
    body: str


class Fetcher(Protocol):
    def get(self, url: str, accept: str = "application/json") -> Response: ...


@dataclass(slots=True)
class Record:
    source: str
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    venue: str | None = None
    url: str | None = None
    entry_type: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class Finding:
    severity: str  # "error" | "warning" | "note"
    code: str
    message: str


@dataclass(slots=True)
class Verification:
    status: str  # verified | mismatch | not-found | unverified | skipped
    findings: list[Finding] = field(default_factory=list)
    record: Record | None = None
    candidate: Record | None = None
    """A better-matching record to suggest when the entry is wrong or incomplete."""


# --------------------------------------------------------------------------- text helpers


def latex_to_text(value: str | None) -> str:
    if not value:
        return ""
    text = LATEX_ACCENT_RE.sub(r"\1", value)
    text = text.replace("\\&", "&").replace("~", " ").replace("--", "-")
    text = LATEX_COMMAND_RE.sub("", text)
    return re.sub(r"\s+", " ", text.replace("{", "").replace("}", "")).strip()


def title_similarity(left: str | None, right: str | None) -> float:
    a = normalize_key(latex_to_text(left))
    b = normalize_key(latex_to_text(right))
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    shorter, longer = sorted((a, b), key=len)
    # A missing or extra subtitle should not count as a different work.
    if longer.startswith(shorter) and len(shorter.split()) >= 4:
        return 0.95
    ratio = SequenceMatcher(None, a, b).ratio()
    tokens_a, tokens_b = set(a.split()), set(b.split())
    overlap = 2 * len(tokens_a & tokens_b) / (len(tokens_a) + len(tokens_b))
    return max(ratio, overlap)


def person(author: str) -> tuple[str, str]:
    """Split an author name into (normalized family name, first initial or "")."""
    text = latex_to_text(author)
    if "," in text:
        family, _, given = text.partition(",")
    else:
        tokens = text.split()
        family, given = (tokens[-1], " ".join(tokens[:-1])) if tokens else ("", "")
    family_tokens = normalize_key(family).split()
    given_tokens = normalize_key(given).split()
    return (family_tokens[-1] if family_tokens else "", given_tokens[0][0] if given_tokens else "")


def family_name(author: str) -> str:
    return person(author)[0]


def _people(authors: list[str]) -> list[tuple[str, str]]:
    people = []
    for author in authors:
        if normalize_key(author) in {"others", "et al", "al"}:
            continue
        name = person(author)
        if name[0]:
            people.append(name)
    return people


def _families(authors: list[str]) -> list[str]:
    return [family for family, _ in _people(authors)]


def _same_person(left: tuple[str, str], right: tuple[str, str]) -> bool:
    return left[0] == right[0] and (not left[1] or not right[1] or left[1] == right[1])


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    text = DOI_PREFIX_RE.sub("", value.strip()).strip().rstrip(".")
    return text.lower() if DOI_RE.fullmatch(text) else None


def is_wellformed_doi(value: str) -> bool:
    return normalize_doi(value) is not None


def arxiv_id_for(entry: ReferenceInfo) -> str | None:
    fields = entry.fields or {}
    doi = normalize_doi(entry.doi)
    if doi and (match := ARXIV_DOI_RE.match(doi)):
        return match.group(1)
    archive = (fields.get("archiveprefix") or fields.get("eprinttype") or "").lower()
    eprint = fields.get("eprint", "")
    if eprint and (archive == "arxiv" or ARXIV_NEW_RE.fullmatch(eprint.strip())):
        match = ARXIV_NEW_RE.search(eprint) or ARXIV_OLD_RE.search(eprint)
        if match:
            return match.group(1)
    for name in ("url", "howpublished", "note", "journal", "journaltitle", "publisher"):
        value = fields.get(name, "")
        if not value:
            continue
        if match := ARXIV_URL_RE.search(value):
            return match.group(1)
        if "arxiv" in value.lower():
            match = ARXIV_NEW_RE.search(value) or ARXIV_OLD_RE.search(value)
            if match:
                return match.group(1)
    return None


# --------------------------------------------------------------------------- HTTP


class _Gate:
    """A semaphore whose capacity can change while it is in use."""

    def __init__(self, limit: int) -> None:
        self.limit = max(1, limit)
        self._active = 0
        self._condition = threading.Condition()

    def __enter__(self) -> None:
        with self._condition:
            while self._active >= self.limit:
                self._condition.wait()
            self._active += 1

    def __exit__(self, *exc) -> None:
        with self._condition:
            self._active -= 1
            self._condition.notify_all()

    def resize(self, limit: int) -> None:
        with self._condition:
            self.limit = max(1, limit)
            self._condition.notify_all()


class RateLimiter:
    """Per-registry request spacing and concurrency that stay inside each registry's limits.

    Defaults are conservative; limits a registry advertises in ``x-rate-limit-*`` and
    ``x-concurrency-limit`` headers (Crossref does) replace them. doi.org content negotiation
    is answered by Crossref, so both hosts share one budget. A 429 doubles the spacing;
    successes ease it back toward the advertised rate.
    """

    BUCKETS = {"doi.org": "crossref", "api.crossref.org": "crossref", "export.arxiv.org": "arxiv", "api.openalex.org": "openalex"}
    INTERVALS = {"crossref": 0.25, "arxiv": 3.0, "openalex": 0.12}
    CONCURRENCY = {"crossref": 2, "arxiv": 1, "openalex": 3}
    MAX_INTERVAL = 10.0

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._gates: dict[str, _Gate] = {}
        self._last: dict[str, float] = {}
        self._base = dict(self.INTERVALS)
        self._intervals = dict(self.INTERVALS)
        self._guard = threading.Lock()

    def bucket(self, host: str) -> str:
        return self.BUCKETS.get(host, host)

    def wait(self, host: str) -> None:
        bucket = self.bucket(host)
        with self._guard:
            lock = self._locks.setdefault(bucket, threading.Lock())
        with lock:
            interval = self._intervals.get(bucket, 0.1)
            delay = self._last.get(bucket, 0.0) + interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._last[bucket] = time.monotonic()

    def slot(self, host: str) -> _Gate:
        bucket = self.bucket(host)
        with self._guard:
            return self._gates.setdefault(bucket, _Gate(self.CONCURRENCY.get(bucket, 4)))

    def observe(self, host: str, headers) -> None:
        """Adopt the limits a registry advertises, e.g. ``x-rate-limit-limit: 5`` per ``1s``."""
        if not headers:
            return
        bucket = self.bucket(host)
        limit, window, concurrency = (
            headers.get("x-rate-limit-limit"),
            headers.get("x-rate-limit-interval"),
            headers.get("x-concurrency-limit"),
        )
        try:
            if limit and window:
                seconds = float(str(window).strip().rstrip("s") or 1)
                spacing = seconds / max(int(limit), 1)
                with self._guard:
                    self._base[bucket] = spacing
                    self._intervals[bucket] = max(spacing, min(self._intervals.get(bucket, spacing), self.MAX_INTERVAL))
            if concurrency:
                self.slot(host).resize(int(concurrency))
        except ValueError:
            return

    def penalize(self, host: str) -> None:
        bucket = self.bucket(host)
        with self._guard:
            self._intervals[bucket] = min(max(self._intervals.get(bucket, 0.1), 0.5) * 2, self.MAX_INTERVAL)

    def reward(self, host: str) -> None:
        """Ease back toward the advertised rate after a successful request."""
        bucket = self.bucket(host)
        with self._guard:
            base = self._base.get(bucket, 0.1)
            current = self._intervals.get(bucket, base)
            if current > base:
                self._intervals[bucket] = max(base, current * 0.8)


class HttpClient:
    """Cached, rate-limited HTTP GET with retries. Only 200 and 404 responses are cached."""

    RETRY_STATUSES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        cache_dir: str | Path | None = ".litkg_cache",
        mailto: str | None = None,
        timeout: float = 20.0,
        retries: int = 5,
        refresh: bool = False,
        opener: Callable = urlopen,
    ) -> None:
        self.cache_path = Path(cache_dir) / "http.json" if cache_dir else None
        self.mailto = mailto
        self.timeout = timeout
        self.retries = retries
        self.refresh = refresh
        self._opener = opener
        self._limiter = RateLimiter()
        self._lock = threading.Lock()
        self._dirty = False
        self._blocked: dict[str, float] = {}
        self._cache: dict[str, dict] = {}
        if self.cache_path and self.cache_path.exists():
            try:
                self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._cache = {}

    @property
    def user_agent(self) -> str:
        contact = f"; mailto:{self.mailto}" if self.mailto else ""
        return f"litkg/{__version__} (+https://github.com/pebaryan/litkg{contact})"

    SECRET_PARAMS = {"api_key", "mailto"}

    def _cache_key(self, url: str, accept: str) -> str:
        """Cache by request, never by credential: drop API keys and contact emails from the key."""
        parsed = urlparse(url)
        query = [(name, value) for name, value in parse_qsl(parsed.query, keep_blank_values=True) if name not in self.SECRET_PARAMS]
        return f"{accept} {parsed._replace(query=urlencode(query)).geturl()}"

    def get(self, url: str, accept: str = "application/json") -> Response:
        cache_key = self._cache_key(url, accept)
        with self._lock:
            cached = None if self.refresh else self._cache.get(cache_key)
        if cached is not None:
            return Response(cached["status"], cached["body"])
        response = self._fetch(url, accept)
        if response.status in {200, 404}:
            with self._lock:
                self._cache[cache_key] = {"status": response.status, "body": response.body, "fetched": int(time.time())}
                self._dirty = True
        return response

    LONG_WAIT = 60.0  # a Retry-After longer than this means "quota exhausted", not "slow down"

    def _fetch(self, url: str, accept: str) -> Response:
        host = urlparse(url).hostname or ""
        bucket = self._limiter.bucket(host)
        blocked_until = self._blocked.get(bucket, 0.0)
        if blocked_until > time.time():
            raise LookupFailed(f"{host}: rate limit exhausted; retry after {_clock(blocked_until)}")
        last_error = "unknown error"
        for attempt in range(self.retries):
            request = Request(url, headers={"Accept": accept, "User-Agent": self.user_agent})
            try:
                with self._limiter.slot(host):
                    self._limiter.wait(host)
                    with self._opener(request, timeout=self.timeout) as handle:
                        response = Response(handle.status, handle.read().decode("utf-8", errors="replace"))
                        self._limiter.observe(host, getattr(handle, "headers", None))
                self._limiter.reward(host)
                return response
            except HTTPError as exc:
                self._limiter.observe(host, exc.headers)
                if exc.code not in self.RETRY_STATUSES:
                    return Response(exc.code, exc.read().decode("utf-8", errors="replace") if exc.fp else "")
                last_error = f"HTTP {exc.code}"
                if exc.code == 429:
                    self._limiter.penalize(host)
                    wait = _retry_after(exc.headers.get("Retry-After") if exc.headers else None, attempt, cap=None)
                    if wait > self.LONG_WAIT:
                        self._blocked[bucket] = time.time() + wait
                        raise LookupFailed(f"{host}: rate limit exhausted; retry after {_clock(time.time() + wait)}") from exc
                delay = _retry_after(exc.headers.get("Retry-After") if exc.headers else None, attempt)
            except (URLError, TimeoutError, OSError) as exc:
                last_error = str(getattr(exc, "reason", exc))
                delay = 2**attempt
            if attempt + 1 < self.retries:
                time.sleep(delay)
        raise LookupFailed(f"{host}: {last_error}")

    def save(self) -> None:
        if not (self.cache_path and self._dirty):
            return
        with self._lock:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self._cache, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.cache_path)
            self._dirty = False


def _retry_after(value: str | None, attempt: int, cap: float | None = 30.0) -> float:
    seconds = float(2**attempt)
    if value:
        try:
            seconds = float(value)
        except ValueError:
            try:
                seconds = max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
            except (TypeError, ValueError):
                pass
    return seconds if cap is None else min(seconds, cap)


def _clock(timestamp: float) -> str:
    return time.strftime("%H:%M", time.localtime(timestamp))


# --------------------------------------------------------------------------- record parsing


def _first_text(value) -> str | None:
    if isinstance(value, list):
        value = next((item for item in value if isinstance(item, str) and item.strip()), None)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _csl_authors(items) -> list[str]:
    authors = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if item.get("literal") or item.get("name"):
            authors.append(str(item.get("literal") or item.get("name")))
        elif item.get("family"):
            authors.append(", ".join(part for part in (item.get("family"), item.get("given")) if part))
    return authors


def _csl_year(item: dict) -> int | None:
    for name in ("issued", "published-print", "published-online", "published", "created"):
        parts = (item.get(name) or {}).get("date-parts") if isinstance(item.get(name), dict) else None
        if parts and parts[0] and parts[0][0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                continue
    return None


def record_from_csl(item: dict, source: str) -> Record:
    title = _first_text(item.get("title"))
    subtitle = _first_text(item.get("subtitle"))
    if title and subtitle and normalize_key(subtitle) not in normalize_key(title):
        title = f"{title}: {subtitle}"
    return Record(
        source=source,
        title=title,
        authors=_csl_authors(item.get("author") or item.get("editor")),
        year=_csl_year(item),
        doi=normalize_doi(item.get("DOI") or item.get("doi")),
        venue=_first_text(item.get("container-title")) or _first_text(item.get("publisher")),
        url=item.get("URL"),
        entry_type=item.get("type"),
    )


def record_from_openalex(item: dict) -> Record:
    location = item.get("primary_location") or {}
    source = location.get("source") or {}
    ids = item.get("ids") or {}
    arxiv = ids.get("arxiv")
    return Record(
        source="openalex",
        title=item.get("display_name") or item.get("title"),
        authors=[
            (authorship.get("author") or {}).get("display_name", "")
            for authorship in item.get("authorships") or []
            if (authorship.get("author") or {}).get("display_name")
        ],
        year=item.get("publication_year"),
        doi=normalize_doi(item.get("doi")),
        arxiv_id=ARXIV_URL_RE.search(arxiv).group(1) if arxiv and ARXIV_URL_RE.search(arxiv) else None,
        venue=source.get("display_name"),
        url=item.get("id"),
        entry_type=item.get("type"),
    )


def records_from_arxiv(atom: str) -> list[Record]:
    try:
        root = ET.fromstring(atom)
    except ET.ParseError as exc:
        raise LookupFailed(f"arXiv returned invalid XML: {exc}") from exc
    records = []
    for entry in root.findall(f"{ATOM}entry"):
        title = re.sub(r"\s+", " ", entry.findtext(f"{ATOM}title") or "").strip()
        entry_id = entry.findtext(f"{ATOM}id") or ""
        if not title or title.lower() == "error" or "arxiv.org/api/errors" in entry_id:
            continue
        match = ARXIV_URL_RE.search(entry_id)
        published = entry.findtext(f"{ATOM}published") or ""
        records.append(
            Record(
                source="arxiv",
                title=title,
                authors=[name.findtext(f"{ATOM}name") or "" for name in entry.findall(f"{ATOM}author")],
                year=int(published[:4]) if published[:4].isdigit() else None,
                doi=normalize_doi(entry.findtext(f"{ARXIV_NS}doi")),
                arxiv_id=match.group(1) if match else None,
                venue="arXiv",
                url=entry_id or None,
                entry_type="article",
            )
        )
    return records


# --------------------------------------------------------------------------- comparison


def compare(entry: ReferenceInfo, record: Record, via: str) -> list[Finding]:
    """Compare a bibliography entry with a registry record. ``via`` names how it was found."""
    findings: list[Finding] = []
    similarity = title_similarity(entry.title, record.title)
    if entry.title and record.title:
        if similarity < TITLE_RELATED:
            findings.append(
                Finding("error", "title-mismatch", f'{via} points to a different work: "{record.title}"')
            )
        elif similarity < TITLE_MATCH:
            findings.append(
                Finding("warning", "title-mismatch", f'title differs from the {record.source} record: "{record.title}"')
            )

    entry_people = _people(entry.authors)
    record_people = _people(record.authors)
    if entry_people and record_people:
        named = [(author, person(author)) for author in entry.authors if normalize_key(author) not in {"others", "et al", "al"}]
        # Registries sometimes truncate long author lists; only compare what the record covers.
        compared = [(author, name) for author, name in named if name[0]][: max(len(record_people), 1)]
        entry_people = [name for _, name in compared]
        missing = [author for author, name in compared if not any(_same_person(name, other) for other in record_people)]
        on_record = f"(record: {'; '.join(record.authors[:4])}{' et al.' if len(record.authors) > 4 else ''})"
        if len(missing) * 2 > len(entry_people):
            findings.append(
                Finding("error", "author-mismatch", f"listed authors not on the record: {'; '.join(missing)} {on_record}")
            )
        elif missing:
            findings.append(
                Finding("warning", "author-mismatch", f"listed authors not on the record: {'; '.join(missing)} {on_record}")
            )
        elif not _same_person(entry_people[0], record_people[0]):
            findings.append(
                Finding("warning", "author-order", f"first author differs from the record ({record.authors[0]})")
            )

    if entry.year and record.year and entry.year != record.year:
        severity = "note" if abs(entry.year - record.year) == 1 else "warning"
        findings.append(Finding(severity, "year-mismatch", f"year {entry.year} differs from the record ({record.year})"))

    if not normalize_doi(entry.doi) and record.doi and not ARXIV_DOI_RE.match(record.doi):
        findings.append(Finding("note", "missing-doi", f"add doi = {{{record.doi}}}"))
    return findings


def _status(findings: list[Finding]) -> str:
    return "mismatch" if any(finding.severity == "error" for finding in findings) else "verified"


# --------------------------------------------------------------------------- verifier


class Verifier:
    def __init__(self, fetcher: Fetcher, mailto: str | None = None, openalex_key: str | None = None) -> None:
        self.fetcher = fetcher
        self.mailto = mailto
        self.openalex_key = openalex_key or os.environ.get("LITKG_OPENALEX_API_KEY")
        self.unavailable: dict[str, str] = {}
        """Fallback sources that failed during this run, with the reason."""

    # -- registries

    def resolve_doi(self, doi: str) -> Record | None:
        response = self.fetcher.get(f"https://doi.org/{quote(doi, safe='/:;()')}", accept="application/vnd.citationstyles.csl+json")
        if response.status == 404:
            return None
        if response.status != 200:
            raise LookupFailed(f"doi.org returned HTTP {response.status} for {doi}")
        try:
            return record_from_csl(json.loads(response.body), "doi.org")
        except ValueError as exc:
            raise LookupFailed(f"doi.org returned invalid metadata for {doi}") from exc

    def resolve_arxiv(self, arxiv_id: str) -> Record | None:
        response = self.fetcher.get(
            "https://export.arxiv.org/api/query?" + urlencode({"id_list": arxiv_id, "max_results": 1}),
            accept="application/atom+xml",
        )
        if response.status == 404:
            return None
        if response.status != 200:
            raise LookupFailed(f"arXiv returned HTTP {response.status} for {arxiv_id}")
        records = records_from_arxiv(response.body)
        return records[0] if records else None

    def _polite(self, params: dict) -> dict:
        return {**params, "mailto": self.mailto} if self.mailto else params

    def _crossref(self, entry: ReferenceInfo, rows: int = 5) -> list[Record]:
        title = latex_to_text(entry.title)
        families = _families(entry.authors)
        query = " ".join(part for part in (title, families[0] if families else "", str(entry.year or "")) if part)
        response = self.fetcher.get(
            "https://api.crossref.org/works?"
            + urlencode(
                self._polite(
                    {"query.bibliographic": query, "rows": rows, "select": "DOI,title,subtitle,author,issued,container-title,type,URL"}
                )
            )
        )
        if response.status != 200:
            return []
        try:
            items = json.loads(response.body).get("message", {}).get("items", [])
        except ValueError:
            return []
        return [record_from_csl(item, "crossref") for item in items if isinstance(item, dict)]

    def _openalex(self, entry: ReferenceInfo, rows: int = 5) -> list[Record]:
        """OpenAlex is a fallback: when it is unavailable, carry on with what Crossref found."""
        params = self._polite({"search": latex_to_text(entry.title), "per-page": rows})
        if self.openalex_key:
            params["api_key"] = self.openalex_key
        try:
            response = self.fetcher.get("https://api.openalex.org/works?" + urlencode(params))
        except LookupFailed as exc:
            self.unavailable["OpenAlex"] = str(exc)
            return []
        if response.status != 200:
            self.unavailable["OpenAlex"] = f"HTTP {response.status}"
            return []
        try:
            items = json.loads(response.body).get("results", [])
        except ValueError:
            return []
        return [record_from_openalex(item) for item in items if isinstance(item, dict)]

    def search(self, entry: ReferenceInfo, exclude_doi: str | None = None) -> Record | None:
        """Find the best record for an entry by title (plus first author and year when known)."""
        if len(normalize_key(latex_to_text(entry.title)).split()) < 2:
            return None
        candidates = self._crossref(entry)
        best = _best(entry, candidates, exclude_doi)
        if best is not None:
            return best
        return _best(entry, candidates + self._openalex(entry), exclude_doi)

    def _no_match_message(self) -> str:
        message = "no matching record in Crossref or OpenAlex; check that this work exists"
        if "OpenAlex" in self.unavailable:
            message = "no matching record in Crossref (OpenAlex was unavailable); check that this work exists"
        return message

    def _try_search(self, entry: ReferenceInfo, exclude_doi: str | None = None) -> Record | None:
        """Search for a replacement record; failures only cost the suggestion, not the verdict."""
        try:
            return self.search(entry, exclude_doi=exclude_doi)
        except LookupFailed:
            return None

    def suggest(self, entry: ReferenceInfo, limit: int = 5) -> list[tuple[float, Record]]:
        """Rank candidate records from Crossref and OpenAlex by title similarity."""
        if not normalize_key(latex_to_text(entry.title)):
            return []
        seen: set[str] = set()
        scored = []
        for record in self._crossref(entry, rows=limit) + self._openalex(entry, rows=limit):
            identity = record.doi or normalize_key(record.title)
            if not identity or identity in seen:
                continue
            seen.add(identity)
            scored.append((round(title_similarity(entry.title, record.title), 3), record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[:limit]

    # -- entry point

    def verify(self, entry: ReferenceInfo) -> Verification:
        doi = normalize_doi(entry.doi)
        arxiv_id = arxiv_id_for(entry)
        if doi and not ARXIV_DOI_RE.match(doi):
            record = self.resolve_doi(doi)
            if record is None:
                return Verification(
                    "not-found",
                    [Finding("error", "doi-not-found", f"DOI {doi} does not exist (doi.org returned 404)")],
                    candidate=self._try_search(entry, exclude_doi=doi),
                )
            return self._judge(entry, record, "the DOI", exclude_doi=doi)
        if arxiv_id:
            record = self.resolve_arxiv(arxiv_id)
            if record is None:
                return Verification(
                    "not-found",
                    [Finding("error", "arxiv-not-found", f"arXiv:{arxiv_id} does not exist")],
                    candidate=self._try_search(entry),
                )
            return self._judge(entry, record, f"arXiv:{arxiv_id}")
        if (entry.entry_type or "").lower() in UNINDEXED_TYPES:
            return Verification(
                "skipped", [Finding("note", "not-indexed", f"@{entry.entry_type} entries without a DOI are not checked online")]
            )
        if not entry.title:
            return Verification("skipped", [Finding("note", "no-title", "no title to search for")])
        candidate = self.search(entry)
        if candidate is None:
            return Verification(
                "unverified",
                [Finding("warning", "no-match", self._no_match_message())],
            )
        findings = compare(entry, candidate, f"the closest {candidate.source} match")
        return Verification(_status(findings), findings, record=candidate, candidate=candidate)

    def _judge(self, entry: ReferenceInfo, record: Record, via: str, exclude_doi: str | None = None) -> Verification:
        findings = compare(entry, record, via)
        status = _status(findings)
        candidate = None
        if status == "mismatch" and any(finding.code == "title-mismatch" for finding in findings):
            candidate = self._try_search(entry, exclude_doi=exclude_doi)
        elif any(finding.severity != "note" or finding.code == "missing-doi" for finding in findings):
            candidate = record
        return Verification(status, findings, record=record, candidate=candidate)

    def verify_many(self, entries: list[ReferenceInfo], workers: int = 4) -> list[Verification]:
        def run(entry: ReferenceInfo) -> Verification:
            try:
                return self.verify(entry)
            except LookupFailed as exc:
                return Verification("unverified", [Finding("warning", "lookup-failed", f"lookup failed: {exc}")])

        if workers <= 1 or len(entries) <= 1:
            return [run(entry) for entry in entries]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(run, entries))


def _best(entry: ReferenceInfo, candidates: list[Record], exclude_doi: str | None) -> Record | None:
    scored = [
        (title_similarity(entry.title, candidate.title), candidate)
        for candidate in candidates
        if candidate.title and not (exclude_doi and candidate.doi == exclude_doi)
    ]
    scored = [item for item in scored if item[0] >= TITLE_MATCH]
    if not scored:
        return None
    people = _people(entry.authors)

    def rank(item: tuple[float, Record]) -> tuple:
        score, candidate = item
        others = _people(candidate.authors)
        author_overlap = any(_same_person(name, other) for name in people for other in others)
        year_close = bool(entry.year and candidate.year and abs(entry.year - candidate.year) <= 1)
        return (author_overlap, round(score, 2), year_close, candidate.doi is not None)

    return max(scored, key=rank)[1]
