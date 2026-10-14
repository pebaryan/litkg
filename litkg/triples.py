from __future__ import annotations

from pathlib import Path

from rdflib import RDF, Literal, URIRef

from .ontology import (
    Author,
    Bibliography,
    Paper,
    ReadingList,
    Venue,
    abstract,
    author_uri,
    authoredPaper,
    bibliography_entry_uri,
    bibliography_uri,
    bibliographyFormat,
    citationDoi,
    citationTitle,
    citedBy,
    cites,
    contentExcerpt,
    doi,
    entryAuthors,
    entryKey,
    entryNote,
    entryOrder,
    entryStatus,
    entryText,
    entryVenue,
    entryYear,
    hasAuthor,
    hasEntry,
    hasReference,
    keyword,
    listName,
    name,
    normalize_key,
    pageCount,
    paper_uri,
    partOf,
    publishedIn,
    reading_list_entry_uri,
    reading_list_uri,
    reference_entry_uri,
    refersTo,
    sourceKind,
    sourcePath,
    targetRef,
    title,
    venue_uri,
    year,
)
from .ontology import (
    BibliographyEntry as BibliographyEntryType,
)
from .ontology import (
    ReadingListEntry as ReadingListEntryType,
)
from .ontology import (
    ReferenceEntry as ReferenceEntryType,
)
from .parser import BibliographyInfo, PaperInfo, ReadingListEntry, ReadingListInfo, ReferenceInfo


def build_paper_lookup(papers: list[PaperInfo]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for paper in papers:
        uri = str(paper_uri(paper.source_path, paper.title))
        candidates = {
            paper.title,
            Path(paper.source_path).stem,
            Path(paper.source_path).name,
            paper.doi or "",
        }
        for candidate in candidates:
            key = normalize_key(candidate)
            if key and key not in lookup:
                lookup[key] = uri
        if paper.doi:
            lookup[f"doi:{paper.doi.lower()}"] = uri
    return lookup


def _candidate_keys(reference: ReferenceInfo) -> list[str]:
    keys: list[str] = []
    if reference.doi:
        keys.append(f"doi:{reference.doi.lower()}")
    if reference.title:
        keys.append(normalize_key(reference.title))
    keys.extend(
        key
        for key in (
            normalize_key(reference.raw_text),
            normalize_key(Path(reference.raw_text).stem),
            normalize_key(Path(reference.raw_text).name),
        )
        if key
    )
    return keys


def resolve_paper_uri(entry: ReadingListEntry, lookup: dict[str, str]) -> str | None:
    candidates = [entry.title, entry.target_ref]
    if entry.target_ref:
        candidates.append(Path(entry.target_ref).stem)
        candidates.append(Path(entry.target_ref).name)
        if "doi.org/" in entry.target_ref.lower():
            candidates.append(entry.target_ref.rsplit("/", 1)[-1])
    for candidate in candidates:
        key = normalize_key(candidate)
        if key and key in lookup:
            return lookup[key]
    return None


def resolve_citation_targets(reference: ReferenceInfo, lookup: dict[str, str]) -> list[str]:
    targets: list[str] = []
    for key in _candidate_keys(reference):
        target = lookup.get(key)
        if target and target not in targets:
            targets.append(target)
    if targets:
        return targets
    reference_key = normalize_key(reference.raw_text)
    if not reference_key:
        return targets
    for key, target in lookup.items():
        if key.startswith("doi:"):
            continue
        if len(key) >= 10 and key in reference_key and target not in targets:
            targets.append(target)
    return targets


def paper_to_triples(paper: PaperInfo) -> list[tuple]:
    paper_node = paper_uri(paper.source_path, paper.title)
    triples: list[tuple] = [
        (paper_node, RDF.type, Paper),
        (paper_node, title, Literal(paper.title)),
        (paper_node, sourcePath, Literal(paper.source_path)),
        (paper_node, sourceKind, Literal("pdf")),
        (paper_node, pageCount, Literal(paper.page_count)),
    ]
    if paper.year is not None:
        triples.append((paper_node, year, Literal(paper.year)))
    if paper.abstract:
        triples.append((paper_node, abstract, Literal(paper.abstract)))
    if paper.excerpt:
        triples.append((paper_node, contentExcerpt, Literal(paper.excerpt)))
    if paper.doi:
        triples.append((paper_node, doi, Literal(paper.doi)))
    for kw in paper.keywords:
        triples.append((paper_node, keyword, Literal(kw)))
    if paper.venue:
        venue_node = venue_uri(paper.venue)
        triples.extend(
            [
                (venue_node, RDF.type, Venue),
                (venue_node, name, Literal(paper.venue)),
                (paper_node, publishedIn, venue_node),
            ]
        )
    for author_name in paper.authors:
        author_node = author_uri(author_name)
        triples.extend(
            [
                (author_node, RDF.type, Author),
                (author_node, name, Literal(author_name)),
                (paper_node, hasAuthor, author_node),
                (author_node, authoredPaper, paper_node),
            ]
        )
    return triples


def paper_reference_to_triples(paper: PaperInfo, paper_lookup: dict[str, str]) -> list[tuple]:
    paper_node = paper_uri(paper.source_path, paper.title)
    triples: list[tuple] = []
    for entry_index, reference in enumerate(paper.references, start=1):
        ref_node = reference_entry_uri(paper.source_path, entry_index)
        triples.extend(
            [
                (ref_node, RDF.type, ReferenceEntryType),
                (paper_node, hasReference, ref_node),
                (ref_node, partOf, paper_node),
                (ref_node, entryOrder, Literal(entry_index)),
                (ref_node, entryText, Literal(reference.raw_text)),
            ]
        )
        if reference.doi:
            triples.append((ref_node, citationDoi, Literal(reference.doi)))
        if reference.title:
            triples.append((ref_node, citationTitle, Literal(reference.title)))
        matched_targets = resolve_citation_targets(reference, paper_lookup)
        if matched_targets:
            triples.append((ref_node, refersTo, URIRef(matched_targets[0])))
    return triples


def bibliography_to_triples(bibliography: BibliographyInfo, paper_lookup: dict[str, str]) -> list[tuple]:
    bibliography_node = bibliography_uri(bibliography.source_path, bibliography.title)
    triples: list[tuple] = [
        (bibliography_node, RDF.type, Bibliography),
        (bibliography_node, title, Literal(bibliography.title)),
        (bibliography_node, sourcePath, Literal(bibliography.source_path)),
        (bibliography_node, bibliographyFormat, Literal(bibliography.format)),
    ]
    for entry_index, entry in enumerate(bibliography.entries, start=1):
        entry_node = bibliography_entry_uri(bibliography.source_path, entry_index)
        triples.extend(
            [
                (entry_node, RDF.type, BibliographyEntryType),
                (entry_node, partOf, bibliography_node),
                (entry_node, entryOrder, Literal(entry_index)),
                (entry_node, entryText, Literal(entry.raw_text)),
            ]
        )
        triples.append((bibliography_node, hasEntry, entry_node))
        if entry.key:
            triples.append((entry_node, entryKey, Literal(entry.key)))
        if entry.title:
            triples.append((entry_node, title, Literal(entry.title)))
        if entry.doi:
            triples.append((entry_node, doi, Literal(entry.doi)))
        if entry.year is not None:
            triples.append((entry_node, entryYear, Literal(entry.year)))
        if entry.venue:
            triples.append((entry_node, entryVenue, Literal(entry.venue)))
        for author_name in entry.authors:
            triples.append((entry_node, entryAuthors, Literal(author_name)))
        matched_targets = resolve_citation_targets(entry, paper_lookup)
        if matched_targets:
            triples.append((entry_node, refersTo, URIRef(matched_targets[0])))
    return triples


def reading_list_to_triples(reading_list: ReadingListInfo, paper_lookup: dict[str, str]) -> list[tuple]:
    list_node = reading_list_uri(reading_list.source_path, reading_list.title)
    triples: list[tuple] = [
        (list_node, RDF.type, ReadingList),
        (list_node, listName, Literal(reading_list.title)),
        (list_node, sourcePath, Literal(reading_list.source_path)),
    ]
    for entry in reading_list.entries:
        entry_node = reading_list_entry_uri(reading_list.source_path, entry.index)
        triples.extend(
            [
                (entry_node, RDF.type, ReadingListEntryType),
                (entry_node, partOf, list_node),
                (entry_node, entryOrder, Literal(entry.index)),
                (entry_node, entryText, Literal(entry.raw_text)),
            ]
        )
        if entry.title:
            triples.append((entry_node, title, Literal(entry.title)))
        if entry.target_ref:
            triples.append((entry_node, targetRef, Literal(entry.target_ref)))
        if entry.status:
            triples.append((entry_node, entryStatus, Literal(entry.status)))
        if entry.note:
            triples.append((entry_node, entryNote, Literal(entry.note)))
        matched_paper = resolve_paper_uri(entry, paper_lookup)
        if matched_paper:
            triples.append((entry_node, refersTo, URIRef(matched_paper)))
    return triples



def citation_triples(papers: list[PaperInfo], paper_lookup: dict[str, str]) -> list[tuple]:
    triples: list[tuple] = []
    cited_by_target: dict[str, set[str]] = {}
    for paper in papers:
        source_uri = paper_uri(paper.source_path, paper.title)
        for reference in paper.references:
            for target_uri in resolve_citation_targets(reference, paper_lookup):
                if target_uri == str(source_uri):
                    continue
                target_ref = URIRef(target_uri)
                triples.append((source_uri, cites, target_ref))
                cited_by_target.setdefault(target_uri, set()).add(str(source_uri))
    for target_uri, sources in cited_by_target.items():
        target_ref = URIRef(target_uri)
        for source_uri in sources:
            triples.append((target_ref, citedBy, URIRef(source_uri)))
    return triples
