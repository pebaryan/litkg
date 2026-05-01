from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

from rdflib import Literal, Namespace, URIRef

BASE = "https://litkg.dev"
ONTOLOGY = Namespace(f"{BASE}/ontology#")
ENTITY_PREFIX = f"{BASE}/entity/"

Paper = ONTOLOGY.Paper
Author = ONTOLOGY.Author
Venue = ONTOLOGY.Venue
ReadingList = ONTOLOGY.ReadingList
ReadingListEntry = ONTOLOGY.ReadingListEntry
Bibliography = ONTOLOGY.Bibliography
BibliographyEntry = ONTOLOGY.BibliographyEntry
ReferenceEntry = ONTOLOGY.ReferenceEntry

hasAuthor = ONTOLOGY.hasAuthor
authoredPaper = ONTOLOGY.authoredPaper
publishedIn = ONTOLOGY.publishedIn
cites = ONTOLOGY.cites
citedBy = ONTOLOGY.citedBy
hasReference = ONTOLOGY.hasReference
title = ONTOLOGY.title
year = ONTOLOGY.year
abstract = ONTOLOGY.abstract
keyword = ONTOLOGY.keyword
doi = ONTOLOGY.doi
sourcePath = ONTOLOGY.sourcePath
sourceKind = ONTOLOGY.sourceKind
pageCount = ONTOLOGY.pageCount
contentExcerpt = ONTOLOGY.contentExcerpt
citationText = ONTOLOGY.citationText
citationDoi = ONTOLOGY.citationDoi
citationTitle = ONTOLOGY.citationTitle
bibliographyFormat = ONTOLOGY.bibliographyFormat
hasEntry = ONTOLOGY.hasEntry
entryKey = ONTOLOGY.entryKey
entryAuthors = ONTOLOGY.entryAuthors
entryYear = ONTOLOGY.entryYear
entryVenue = ONTOLOGY.entryVenue
listName = ONTOLOGY.listName
entryText = ONTOLOGY.entryText
entryStatus = ONTOLOGY.entryStatus
entryNote = ONTOLOGY.entryNote
entryOrder = ONTOLOGY.entryOrder
referenceOrder = ONTOLOGY.referenceOrder
targetRef = ONTOLOGY.targetRef
partOf = ONTOLOGY.partOf
refersTo = ONTOLOGY.refersTo
name = ONTOLOGY.name


def _slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "item"


def _stable_suffix(*parts: str) -> str:
    raw = "::".join(part.strip().lower() for part in parts if part is not None)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def normalize_key(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def paper_uri(source_path: str, paper_title: str | None = None) -> URIRef:
    path = str(Path(source_path).resolve())
    suffix = _stable_suffix(path)
    slug = _slugify(paper_title or Path(source_path).stem)
    return URIRef(f"{ENTITY_PREFIX}paper/{slug}-{suffix}")


def author_uri(author_name: str) -> URIRef:
    suffix = _stable_suffix(author_name)
    slug = _slugify(author_name)
    return URIRef(f"{ENTITY_PREFIX}author/{slug}-{suffix}")


def venue_uri(venue_name: str) -> URIRef:
    suffix = _stable_suffix(venue_name)
    slug = _slugify(venue_name)
    return URIRef(f"{ENTITY_PREFIX}venue/{slug}-{suffix}")


def reading_list_uri(source_path: str, list_title: str | None = None) -> URIRef:
    path = str(Path(source_path).resolve())
    suffix = _stable_suffix(path)
    slug = _slugify(list_title or Path(source_path).stem)
    return URIRef(f"{ENTITY_PREFIX}list/{slug}-{suffix}")


def reading_list_entry_uri(source_path: str, index: int) -> URIRef:
    path = str(Path(source_path).resolve())
    suffix = _stable_suffix(path)
    return URIRef(f"{ENTITY_PREFIX}entry/{suffix}-{index}")


def bibliography_uri(source_path: str, bibliography_title: str | None = None) -> URIRef:
    path = str(Path(source_path).resolve())
    suffix = _stable_suffix(path)
    slug = _slugify(bibliography_title or Path(source_path).stem)
    return URIRef(f"{ENTITY_PREFIX}bibliography/{slug}-{suffix}")


def bibliography_entry_uri(source_path: str, index: int) -> URIRef:
    path = str(Path(source_path).resolve())
    suffix = _stable_suffix(path)
    return URIRef(f"{ENTITY_PREFIX}bibliography-entry/{suffix}-{index}")


def reference_entry_uri(source_path: str, index: int) -> URIRef:
    path = str(Path(source_path).resolve())
    suffix = _stable_suffix(path)
    return URIRef(f"{ENTITY_PREFIX}reference/{suffix}-{index}")


def literal_str(value: str) -> Literal:
    return Literal(value)


def literal_int(value: int) -> Literal:
    return Literal(value)
