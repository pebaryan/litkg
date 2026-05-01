from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from pypdf import PdfReader

from .ontology import normalize_key

YEAR_RE = re.compile(r"(?:19|20)\d{2}")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
DOI_URL_RE = re.compile(r"https?://(?:dx\.)?doi\.org/([^\s<>)\]]+)", re.IGNORECASE)
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+")
CHECKBOX_RE = re.compile(r"^\s*\[(?:x|X| )\]\s+")
REFERENCE_HEADING_RE = re.compile(r"^\s*(references|bibliography|works cited)\s*$", re.IGNORECASE)
REFERENCE_LABEL_RE = re.compile(r"^\s*(?:\[\d+\]|\d+[.)]|[A-Z][A-Za-z'’\-]+,\s+[A-Z]\.)\s*")
REFERENCE_START_RE = re.compile(
    r"^\s*(?:\[\d+\]|\d+[.)]|[A-Z][A-Za-z'’\-]+,\s+[A-Z](?:\.[A-Z])?\.|[A-Z][A-Za-z'’\-]+,\s+[A-Z]\.)"
)
APA_REFERENCE_RE = re.compile(
    r"^(?P<authors>.+?)\s*\((?P<year>(?:19|20)\d{2}[a-z]?)\)\.\s*(?P<rest>.+)$"
)
APA_TITLE_RE = re.compile(r"^(?P<title>.+?)(?:\.\s+|$)")
TITLE_QUOTE_RE = re.compile(r"[\"“”']([^\"“”']{8,200})[\"“”']")


@dataclass(slots=True)
class PaperInfo:
    source_path: str
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    abstract: str | None = None
    keywords: list[str] = field(default_factory=list)
    doi: str | None = None
    excerpt: str | None = None
    references: list["ReferenceInfo"] = field(default_factory=list)
    page_count: int = 0


@dataclass(slots=True)
class ReferenceInfo:
    raw_text: str
    title: str | None = None
    doi: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    key: str | None = None


@dataclass(slots=True)
class BibliographyInfo:
    source_path: str
    title: str
    format: str
    entries: list[ReferenceInfo] = field(default_factory=list)


@dataclass(slots=True)
class ReadingListEntry:
    index: int
    raw_text: str
    title: str | None = None
    target_ref: str | None = None
    status: str | None = None
    note: str | None = None


@dataclass(slots=True)
class ReadingListInfo:
    source_path: str
    title: str
    entries: list[ReadingListEntry] = field(default_factory=list)


def _metadata_value(metadata, *names: str) -> str | None:
    if metadata is None:
        return None
    for name in names:
        value = None
        if isinstance(metadata, dict):
            value = metadata.get(name) or metadata.get(f"/{name.strip('/')}") or metadata.get(name.lower())
        else:
            value = getattr(metadata, name, None) or getattr(metadata, name.lower(), None)
            if value is None and hasattr(metadata, "get"):
                try:
                    value = metadata.get(name) or metadata.get(f"/{name.strip('/')}")
                except Exception:
                    value = None
        if value:
            return str(value)
    return None


def _split_people(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"\s*;\s*|\s+&\s+|\s+\band\b\s+", value, flags=re.IGNORECASE)
    people = []
    for part in parts:
        cleaned = re.sub(r"\s+", " ", part).strip(" ,;")
        if cleaned:
            people.append(cleaned)
    return people


def _split_keywords(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"\s*[,;]\s*", value)
    return [part.strip() for part in parts if part.strip()]


def _extract_year(*values: str | None) -> int | None:
    for value in values:
        if not value:
            continue
        match = YEAR_RE.search(value)
        if match:
            return int(match.group(0))
    return None


def _extract_title_from_text(text: str, fallback: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    for line in lines:
        if not line:
            continue
        if len(line) < 8:
            continue
        if normalize_key(line) in {"abstract", "introduction", "keywords"}:
            continue
        if len(line) > 140:
            continue
        return line
    return fallback


def _extract_abstract(text: str) -> str | None:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    for idx, line in enumerate(lines):
        if normalize_key(line) != "abstract":
            continue
        collected: list[str] = []
        for follow in lines[idx + 1 : idx + 18]:
            if not follow:
                if collected:
                    break
                continue
            if normalize_key(follow) in {"introduction", "keywords", "references"}:
                break
            collected.append(follow)
        abstract = " ".join(collected).strip()
        if abstract:
            return abstract
    return None


def _extract_all_text(reader: PdfReader) -> str:
    chunks: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            chunks.append(text.strip())
    return "\n\n".join(chunks).strip()


def _extract_references_section(text: str) -> str | None:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    start_index = None
    for idx, line in enumerate(lines):
        if REFERENCE_HEADING_RE.match(line):
            start_index = idx + 1
    if start_index is None:
        return None
    collected = [line for line in lines[start_index:] if line]
    if not collected:
        return None
    return "\n".join(collected).strip()


def _split_reference_entries(section_text: str | None) -> list[str]:
    if not section_text:
        return []
    entries: list[str] = []
    current: list[str] = []
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if (REFERENCE_LABEL_RE.match(line) or REFERENCE_START_RE.match(line)) and current:
            entries.append(" ".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        entries.append(" ".join(current).strip())
    return [entry for entry in entries if entry]


def _extract_reference_title(text: str) -> str | None:
    apa_match = APA_REFERENCE_RE.match(text)
    if apa_match:
        rest = re.sub(r"\s+", " ", apa_match.group("rest")).strip()
        title_match = APA_TITLE_RE.match(rest)
        if title_match:
            title = title_match.group("title").strip(" .;")
            if title:
                return title
    cleaned = re.sub(r"^\s*(?:\[\d+\]|\d+[.)])\s*", "", text).strip()
    cleaned = re.split(r"\bdoi\s*:\s*", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    cleaned = re.split(r"\bhttps?://(?:dx\.)?doi\.org/\S+", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    segments = [segment.strip(" .;") for segment in re.split(r"\.\s+", cleaned) if segment.strip(" .;")]
    candidates: list[str] = []
    for segment in segments:
        normalized = normalize_key(segment)
        if not normalized or len(segment) < 8:
            continue
        if normalized.startswith(("et al", "references", "bibliography", "works cited")):
            continue
        if re.fullmatch(r"[a-z]\.?(\s+[a-z]\.)+", normalized):
            continue
        if re.search(r"\b(?:19|20)\d{2}\b", segment) and len(segment) < 40:
            continue
        candidates.append(segment)
    if candidates:
        return max(candidates, key=len)
    match = TITLE_QUOTE_RE.search(text)
    if match:
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        if title:
            return title
    if "." in text:
        first_sentence = text.split(".", 1)[0].strip()
        if len(first_sentence) >= 8 and not normalize_key(first_sentence).startswith("references"):
            return first_sentence
    return None


def _extract_reference_doi(text: str) -> str | None:
    match = DOI_RE.search(text)
    if match:
        return match.group(0)
    match = DOI_URL_RE.search(text)
    if match:
        return match.group(1).rstrip(").,;]")
    return None


def _extract_reference_year(text: str) -> int | None:
    match = APA_REFERENCE_RE.match(text)
    if match:
        year_text = match.group("year")
        year_match = YEAR_RE.search(year_text)
        if year_match:
            return int(year_match.group(0))
    return _extract_year(text)


def _split_authors(raw: str | None) -> list[str]:
    if not raw:
        return []
    text = re.sub(r"\s+", " ", raw).strip(" ,;")
    text = text.replace(" and ", "; ")
    parts = [part.strip() for part in re.split(r"\s*;\s*|\s*&\s*", text) if part.strip()]
    if parts:
        return parts
    return [text]


def _extract_apa_authors(text: str) -> list[str]:
    match = APA_REFERENCE_RE.match(text)
    if not match:
        return []
    return _split_authors(match.group("authors"))


def _parse_csl_author(value) -> list[str]:
    authors: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                cleaned = item.strip()
            elif isinstance(item, dict):
                cleaned = item.get("literal") or " ".join(
                    part for part in [item.get("family"), item.get("given")] if part
                ).strip()
            else:
                cleaned = str(item).strip()
            if cleaned:
                authors.append(cleaned)
    elif isinstance(value, str):
        authors.extend(_split_authors(value))
    return authors


def _csl_year(item: dict) -> int | None:
    for key in ("issued", "published-print", "published-online", "created"):
        data = item.get(key)
        if isinstance(data, dict):
            date_parts = data.get("date-parts")
            if isinstance(date_parts, list) and date_parts and isinstance(date_parts[0], list):
                for part in date_parts[0]:
                    if isinstance(part, int):
                        return part
                    if isinstance(part, str) and part.isdigit():
                        return int(part)
    year_value = item.get("year")
    if isinstance(year_value, int):
        return year_value
    if isinstance(year_value, str) and year_value.isdigit():
        return int(year_value)
    return None


def _parse_csl_json(path: str, data) -> BibliographyInfo:
    if isinstance(data, dict):
        entries = data.get("items") or data.get("entries") or data.get("references") or []
        title = data.get("title") or data.get("name") or Path(path).stem
    else:
        entries = data
        title = Path(path).stem
    bibliography_entries: list[ReferenceInfo] = []
    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            continue
        raw_text = json.dumps(item, ensure_ascii=False, sort_keys=True)
        entry_title = item.get("title") or item.get("article-title") or item.get("container-title")
        if isinstance(entry_title, list):
            entry_title = next((part for part in entry_title if isinstance(part, str) and part.strip()), None)
        authors = _parse_csl_author(item.get("author"))
        doi = item.get("DOI") or item.get("doi")
        venue = item.get("container-title") or item.get("journal") or item.get("publisher")
        if isinstance(venue, list):
            venue = next((part for part in venue if isinstance(part, str) and part.strip()), None)
        bibliography_entries.append(
            ReferenceInfo(
                raw_text=raw_text,
                title=entry_title.strip() if isinstance(entry_title, str) and entry_title.strip() else None,
                doi=doi.strip() if isinstance(doi, str) and doi.strip() else None,
                authors=authors,
                year=_csl_year(item),
                venue=venue.strip() if isinstance(venue, str) and venue.strip() else None,
                key=item.get("id") or item.get("key") or str(idx + 1),
            )
        )
    return BibliographyInfo(
        source_path=path,
        title=title,
        format="csl-json",
        entries=bibliography_entries,
    )


def _bibtex_clean(value: str) -> str:
    text = value.strip().rstrip(",")
    if (text.startswith("{") and text.endswith("}")) or (text.startswith('"') and text.endswith('"')):
        text = text[1:-1]
    return re.sub(r"\s+", " ", text).strip()


def _read_bibtex_value(text: str, start_index: int) -> tuple[str, int]:
    i = start_index
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text):
        return "", i
    if text[i] == "{":
        depth = 0
        begin = i
        while i < len(text):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        return text[begin:i], i
    if text[i] == '"':
        begin = i
        i += 1
        escaped = False
        while i < len(text):
            ch = text[i]
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                i += 1
                break
            i += 1
        return text[begin:i], i
    begin = i
    while i < len(text) and text[i] not in ",}":
        i += 1
    return text[begin:i], i


def _extract_bibtex_field(text: str, field_name: str) -> str | None:
    match = re.search(rf"(?is)\b{re.escape(field_name)}\s*=\s*", text)
    if not match:
        return None
    value, _ = _read_bibtex_value(text, match.end())
    cleaned = _bibtex_clean(value)
    return cleaned or None


def _parse_bibtex(path: str, text: str) -> BibliographyInfo:
    entries: list[ReferenceInfo] = []
    i = 0
    while True:
        at = text.find("@", i)
        if at < 0:
            break
        brace = text.find("{", at)
        if brace < 0:
            break
        entry_type = text[at + 1 : brace].strip().lower()
        depth = 0
        j = brace
        escaped = False
        in_quotes = False
        while j < len(text):
            ch = text[j]
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_quotes = not in_quotes
            elif not in_quotes:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
            j += 1
        block = text[brace + 1 : j - 1].strip()
        i = j
        if not block:
            continue
        key, _, body = block.partition(",")
        raw_text = f"@{entry_type}{{{block}}}"
        title = _extract_bibtex_field(body, "title")
        doi = _extract_bibtex_field(body, "doi")
        author_value = _extract_bibtex_field(body, "author")
        year_value = _extract_bibtex_field(body, "year")
        venue = _extract_bibtex_field(body, "journal") or _extract_bibtex_field(body, "booktitle")
        year = None
        if year_value:
            year_match = YEAR_RE.search(year_value)
            if year_match:
                year = int(year_match.group(0))
        entries.append(
            ReferenceInfo(
                raw_text=raw_text,
                title=title,
                doi=doi,
                authors=_split_authors(author_value),
                year=year,
                venue=venue,
                key=key.strip() or None,
            )
        )
    return BibliographyInfo(
        source_path=path,
        title=Path(path).stem,
        format="bibtex",
        entries=entries,
    )


def parse_bibliography(file_path: str) -> BibliographyInfo:
    source = str(Path(file_path).resolve())
    suffix = Path(source).suffix.lower()
    text = Path(source).read_text(encoding="utf-8", errors="ignore")
    if suffix in {".bib", ".bibtex"}:
        return _parse_bibtex(source, text)
    if suffix == ".json":
        data = json.loads(text)
        return _parse_csl_json(source, data)
    lines = text.splitlines()
    entries: list[ReferenceInfo] = []
    for raw_reference in _split_reference_entries(_extract_references_section(text)):
        entries.append(
            ReferenceInfo(
                raw_text=raw_reference,
                title=_extract_reference_title(raw_reference),
                doi=_extract_reference_doi(raw_reference),
                authors=_extract_apa_authors(raw_reference),
                year=_extract_reference_year(raw_reference),
            )
        )
    return BibliographyInfo(
        source_path=source,
        title=Path(source).stem,
        format="apa-text",
        entries=entries,
    )


def read_pdf_text(file_path: str, start_page: int = 1, end_page: int | None = None) -> str:
    reader = PdfReader(file_path)
    page_count = len(reader.pages)
    if page_count == 0:
        return ""
    start_index = max(start_page - 1, 0)
    stop_index = page_count if end_page in (None, 0) else min(end_page, page_count)
    pages = reader.pages[start_index:stop_index]
    chunks: list[str] = []
    for page in pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            chunks.append(text.strip())
    return "\n\n".join(chunks).strip()


def parse_pdf(file_path: str) -> PaperInfo:
    source = str(Path(file_path).resolve())
    reader = PdfReader(source)
    metadata = getattr(reader, "metadata", None)
    page_count = len(reader.pages)

    page_texts: list[str] = []
    for page in reader.pages[: min(page_count, 3)]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            page_texts.append(text.strip())
    full_excerpt = "\n\n".join(page_texts).strip()
    all_text = _extract_all_text(reader)

    raw_title = _metadata_value(metadata, "title", "/Title")
    text_for_title = page_texts[0] if page_texts else ""
    title = raw_title or _extract_title_from_text(text_for_title, Path(source).stem)
    authors = _split_people(_metadata_value(metadata, "author", "/Author"))
    venue = _metadata_value(metadata, "subject", "/Subject")
    keywords = _split_keywords(_metadata_value(metadata, "keywords", "/Keywords"))
    doi = None
    for candidate in (
        _metadata_value(metadata, "doi", "/DOI"),
        raw_title,
        full_excerpt,
    ):
        if not candidate:
            continue
        match = DOI_RE.search(candidate)
        if match:
            doi = match.group(0)
            break
    year = _extract_year(
        _metadata_value(metadata, "creation_date", "/CreationDate"),
        _metadata_value(metadata, "modification_date", "/ModDate"),
        source,
        title,
        full_excerpt,
    )
    abstract = _extract_abstract(full_excerpt)
    excerpt = full_excerpt[:5000] if full_excerpt else None
    references_section = _extract_references_section(all_text)
    references: list[ReferenceInfo] = []
    for raw_reference in _split_reference_entries(references_section):
        references.append(
            ReferenceInfo(
                raw_text=raw_reference,
                title=_extract_reference_title(raw_reference),
                doi=_extract_reference_doi(raw_reference),
            )
        )
    return PaperInfo(
        source_path=source,
        title=title,
        authors=authors,
        year=year,
        venue=venue,
        abstract=abstract,
        keywords=keywords,
        doi=doi,
        excerpt=excerpt,
        references=references,
        page_count=page_count,
    )


def _strip_list_marker(line: str) -> tuple[str, str | None]:
    status = None
    working = line.strip()
    checkbox_match = CHECKBOX_RE.match(working)
    if checkbox_match:
        marker = working[1].lower()
        status = "done" if marker == "x" else "todo"
        working = working[checkbox_match.end() :].strip()
    working = LIST_MARKER_RE.sub("", working)
    return working.strip(), status


def _split_title_note(text: str) -> tuple[str | None, str | None]:
    for separator in (" — ", " - ", " | ", " : "):
        if separator in text:
            left, right = text.split(separator, 1)
            left = left.strip()
            right = right.strip()
            if left and right:
                return left, right
    return text.strip() or None, None


def parse_reading_list(file_path: str) -> ReadingListInfo:
    source = str(Path(file_path).resolve())
    text = Path(source).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    list_title = Path(source).stem
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                list_title = heading
                break

    entries: list[ReadingListEntry] = []
    for line in lines:
        raw = line.strip()
        if not raw:
            continue
        if raw.startswith("#"):
            continue
        cleaned, status = _strip_list_marker(raw)
        if not cleaned:
            continue
        link_match = LINK_RE.search(cleaned)
        title = None
        target_ref = None
        note = None
        if link_match:
            title = link_match.group(1).strip()
            target_ref = link_match.group(2).strip()
            remainder = (cleaned[: link_match.start()] + cleaned[link_match.end() :]).strip(" -—|:")
            if remainder:
                note = remainder
        else:
            title, note = _split_title_note(cleaned)
        entries.append(
            ReadingListEntry(
                index=len(entries) + 1,
                raw_text=cleaned,
                title=title,
                target_ref=target_ref,
                status=status,
                note=note,
            )
        )

    return ReadingListInfo(source_path=source, title=list_title, entries=entries)
