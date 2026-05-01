from __future__ import annotations

import re

from rdflib import Literal

from .ontology import ONTOLOGY, normalize_key
from .parser import read_pdf_text
from .store import LitStore

PREFIX = f"""
PREFIX lit: <{ONTOLOGY}>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
"""


def _literal(value: str) -> str:
    return Literal(value).n3()


def list_papers(store: LitStore) -> list[dict]:
    rows = store.query(
        PREFIX
        + """
        SELECT ?paper ?title ?path ?year ?pages ?excerpt ?authorName WHERE {
          ?paper a lit:Paper ;
                 lit:title ?title ;
                 lit:sourcePath ?path .
          OPTIONAL { ?paper lit:year ?year . }
          OPTIONAL { ?paper lit:pageCount ?pages . }
          OPTIONAL { ?paper lit:contentExcerpt ?excerpt . }
          OPTIONAL { ?paper lit:hasAuthor ?author . ?author lit:name ?authorName . }
        }
        ORDER BY LCASE(STR(?title))
        """
    )
    grouped: dict[str, dict] = {}
    for row in rows:
        paper = row["paper"]
        item = grouped.setdefault(
            paper,
            {
                "paper": paper,
                "title": row.get("title"),
                "path": row.get("path"),
                "year": row.get("year"),
                "pages": row.get("pages"),
                "excerpt": row.get("excerpt"),
                "authors": [],
            },
        )
        author = row.get("authorName")
        if author and author not in item["authors"]:
            item["authors"].append(author)
    return sorted(grouped.values(), key=lambda row: str(row.get("title", "")).lower())


def list_reading_lists(store: LitStore) -> list[dict]:
    rows = store.query(
        PREFIX
        + """
        SELECT ?list ?name ?path ?entryText WHERE {
          ?list a lit:ReadingList ;
                lit:listName ?name ;
                lit:sourcePath ?path .
          OPTIONAL { ?entry lit:partOf ?list ; lit:entryText ?entryText . }
        }
        ORDER BY LCASE(STR(?name))
        """
    )
    grouped: dict[str, dict] = {}
    for row in rows:
        list_uri = row["list"]
        item = grouped.setdefault(
            list_uri,
            {
                "list": list_uri,
                "name": row.get("name"),
                "path": row.get("path"),
                "entries": [],
            },
        )
        if row.get("entryText"):
            item["entries"].append(row["entryText"])
    for item in grouped.values():
        item["entry_count"] = len(item["entries"])
    return sorted(grouped.values(), key=lambda row: str(row.get("name", "")).lower())


def list_bibliographies(store: LitStore) -> list[dict]:
    rows = store.query(
        PREFIX
        + """
        SELECT ?bibliography ?name ?path ?format ?entryText WHERE {
          ?bibliography a lit:Bibliography ;
                        lit:title ?name ;
                        lit:sourcePath ?path ;
                        lit:bibliographyFormat ?format .
          OPTIONAL { ?entry lit:partOf ?bibliography ; lit:entryText ?entryText . }
        }
        ORDER BY LCASE(STR(?name))
        """
    )
    grouped: dict[str, dict] = {}
    for row in rows:
        bibliography_uri = row["bibliography"]
        item = grouped.setdefault(
            bibliography_uri,
            {
                "bibliography": bibliography_uri,
                "name": row.get("name"),
                "path": row.get("path"),
                "format": row.get("format"),
                "entries": [],
            },
        )
        if row.get("entryText"):
            item["entries"].append(row["entryText"])
    for item in grouped.values():
        item["entry_count"] = len(item["entries"])
    return sorted(grouped.values(), key=lambda row: str(row.get("name", "")).lower())


def annotated_bibliography(store: LitStore, pattern: str = "") -> list[dict]:
    needle = normalize_key(pattern)
    query = PREFIX + """
        SELECT ?bibliography ?bibliographyName ?bibliographyPath ?bibliographyFormat
               ?entry ?entryOrder ?entryText ?entryTitle ?entryDoi ?entryYear ?entryVenue ?entryKey
               (GROUP_CONCAT(DISTINCT ?entryAuthor; separator="; ") AS ?entryAuthors)
               ?refersTo ?refersToTitle
        WHERE {
          ?bibliography a lit:Bibliography ;
                        lit:title ?bibliographyName ;
                        lit:sourcePath ?bibliographyPath ;
                        lit:bibliographyFormat ?bibliographyFormat .
          ?entry a lit:BibliographyEntry ;
                 lit:partOf ?bibliography ;
                 lit:entryText ?entryText .
          OPTIONAL { ?entry lit:entryOrder ?entryOrder . }
          OPTIONAL { ?entry lit:title ?entryTitle . }
          OPTIONAL { ?entry lit:doi ?entryDoi . }
          OPTIONAL { ?entry lit:year ?entryYear . }
          OPTIONAL { ?entry lit:venue ?entryVenue . }
          OPTIONAL { ?entry lit:entryKey ?entryKey . }
          OPTIONAL { ?entry lit:entryAuthors ?entryAuthorRaw . }
          BIND(COALESCE(?entryAuthorRaw, "") AS ?entryAuthor)
          OPTIONAL {
            ?entry lit:refersTo ?refersTo .
            ?refersTo lit:title ?refersToTitle .
          }
          FILTER(CONTAINS(LCASE(STR(?bibliographyName)), LCASE(STR(%s))))
        }
        GROUP BY ?bibliography ?bibliographyName ?bibliographyPath ?bibliographyFormat
                 ?entry ?entryOrder ?entryText ?entryTitle ?entryDoi ?entryYear ?entryVenue ?entryKey
                 ?refersTo ?refersToTitle
        ORDER BY LCASE(STR(?bibliographyName)) ?entryOrder LCASE(STR(?entryText))
    """ % Literal(needle).n3()
    rows = store.query(query)

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["bibliography"], []).append(row)

    results: list[dict] = []
    for bib_uri, entries in grouped.items():
        identity_counts: dict[str, int] = {}
        for row in entries:
            identity = _bibliography_entry_identity(row)
            identity_counts[identity] = identity_counts.get(identity, 0) + 1

        for row in entries:
            identity = _bibliography_entry_identity(row)
            duplicate_count = identity_counts.get(identity, 0)
            match_status = _entry_match_status(row)
            is_duplicate = duplicate_count > 1
            status = "duplicate" if is_duplicate else match_status
            results.append(
                {
                    "bibliography": row.get("bibliography"),
                    "bibliographyName": row.get("bibliographyName"),
                    "bibliographyPath": row.get("bibliographyPath"),
                    "bibliographyFormat": row.get("bibliographyFormat"),
                    "entry": row.get("entry"),
                    "entryOrder": row.get("entryOrder"),
                    "entryText": row.get("entryText"),
                    "entryTitle": row.get("entryTitle"),
                    "entryDoi": row.get("entryDoi"),
                    "entryYear": row.get("entryYear"),
                    "entryVenue": row.get("entryVenue"),
                    "entryKey": row.get("entryKey"),
                    "entryAuthors": row.get("entryAuthors"),
                    "refersTo": row.get("refersTo"),
                    "refersToTitle": row.get("refersToTitle"),
                    "duplicateCount": duplicate_count,
                    "matchStatus": match_status,
                    "status": status,
                }
            )

    return sorted(
        results,
        key=lambda row: (
            str(row.get("bibliographyName", "")).lower(),
            int(row.get("entryOrder") or 0),
            str(row.get("entryText", "")).lower(),
        ),
    )


def _bibliography_entry_identity(row: dict) -> str:
    if row.get("entryDoi"):
        return f"doi:{normalize_key(str(row['entryDoi']))}"
    if row.get("entryTitle"):
        return f"title:{normalize_key(str(row['entryTitle']))}"
    if row.get("entryKey"):
        return f"key:{normalize_key(str(row['entryKey']))}"
    return f"text:{normalize_key(str(row.get('entryText', '')))}"


def _entry_match_status(row: dict) -> str:
    if row.get("refersTo"):
        return "resolved"
    if any(row.get(field) for field in ("entryTitle", "entryDoi", "entryYear", "entryVenue", "entryAuthors")):
        return "partial"
    return "unresolved"


def papers_by_author(store: LitStore, author_name: str) -> list[dict]:
    needle = _literal(author_name)
    query = PREFIX + """
        SELECT ?paper ?title ?path ?authorName WHERE {
          ?paper a lit:Paper ;
                 lit:title ?title ;
                 lit:sourcePath ?path ;
                 lit:hasAuthor ?author .
          ?author lit:name ?authorName .
          FILTER(CONTAINS(LCASE(STR(?authorName)), LCASE(STR(%s))))
        }
        ORDER BY LCASE(STR(?title))
    """ % needle
    return store.query(query)


def papers_in_list(store: LitStore, list_name: str) -> list[dict]:
    needle = _literal(list_name)
    query = PREFIX + """
        SELECT ?list ?name ?paper ?title ?path ?entryText ?status WHERE {
          ?list a lit:ReadingList ;
                lit:listName ?name .
          FILTER(CONTAINS(LCASE(STR(?name)), LCASE(STR(%s))))
          ?entry lit:partOf ?list ;
                 lit:entryText ?entryText .
          OPTIONAL { ?entry lit:status ?status . }
          OPTIONAL { ?entry lit:refersTo ?paper . ?paper lit:title ?title ; lit:sourcePath ?path . }
        }
        ORDER BY LCASE(STR(?entryText))
    """ % needle
    return store.query(query)


def papers_without_lists(store: LitStore) -> list[dict]:
    return store.query(
        PREFIX
        + """
        SELECT ?paper ?title ?path WHERE {
          ?paper a lit:Paper ;
                 lit:title ?title ;
                 lit:sourcePath ?path .
          FILTER NOT EXISTS {
            ?entry a lit:ReadingListEntry ;
                   lit:refersTo ?paper .
          }
        }
        ORDER BY LCASE(STR(?title))
        """
    )


def search(store: LitStore, pattern: str) -> list[dict]:
    needle = _literal(pattern)
    query = PREFIX + """
        SELECT DISTINCT ?paper ?title ?path ?year ?authorName WHERE {
          ?paper a lit:Paper ;
                 lit:title ?title ;
                 lit:sourcePath ?path .
          OPTIONAL { ?paper lit:year ?year . }
          OPTIONAL { ?paper lit:hasAuthor ?author . ?author lit:name ?authorName . }
          {
            FILTER(CONTAINS(LCASE(STR(?title)), LCASE(STR(%s))))
          }
          UNION
          {
            ?paper lit:abstract ?abstract .
            FILTER(CONTAINS(LCASE(STR(?abstract)), LCASE(STR(%s))))
          }
          UNION
          {
            ?paper lit:keyword ?keyword .
            FILTER(CONTAINS(LCASE(STR(?keyword)), LCASE(STR(%s))))
          }
        }
        ORDER BY LCASE(STR(?title))
    """ % (needle, needle, needle)
    return store.query(query)


def paper_details(store: LitStore, pattern: str) -> list[dict]:
    needle = _literal(pattern)
    query = PREFIX + """
        SELECT ?paper ?title ?path ?year ?venueName ?abstract ?keyword ?authorName ?listName ?entryText WHERE {
          ?paper a lit:Paper ;
                 lit:title ?title ;
                 lit:sourcePath ?path .
          FILTER(CONTAINS(LCASE(STR(?title)), LCASE(STR(%s))))
          OPTIONAL { ?paper lit:year ?year . }
          OPTIONAL { ?paper lit:abstract ?abstract . }
          OPTIONAL { ?paper lit:keyword ?keyword . }
          OPTIONAL {
            ?paper lit:publishedIn ?venue .
            ?venue lit:name ?venueName .
          }
          OPTIONAL {
            ?paper lit:hasAuthor ?author .
            ?author lit:name ?authorName .
          }
          OPTIONAL {
            ?entry lit:refersTo ?paper ;
                   lit:partOf ?list .
            ?list lit:listName ?listName .
            ?entry lit:entryText ?entryText .
          }
        }
        ORDER BY LCASE(STR(?title))
    """ % needle
    return store.query(query)


def paper_references(store: LitStore, pattern: str) -> list[dict]:
    needle = _literal(pattern)
    query = PREFIX + """
        SELECT ?paper ?title ?reference ?citationText ?citationDoi ?citationTitle ?refersToTitle
        WHERE {
          ?paper a lit:Paper ;
                 lit:title ?title ;
                 lit:hasReference ?reference .
          ?reference lit:entryText ?citationText .
          FILTER(CONTAINS(LCASE(STR(?title)), LCASE(STR(%s))))
          OPTIONAL { ?reference lit:citationDoi ?citationDoi . }
          OPTIONAL { ?reference lit:citationTitle ?citationTitle . }
          OPTIONAL {
            ?reference lit:refersTo ?refersTo .
            ?refersTo lit:title ?refersToTitle .
          }
        }
        ORDER BY LCASE(STR(?citationText))
    """ % needle
    return store.query(query)


def papers_citing(store: LitStore, pattern: str) -> list[dict]:
    needle = _literal(pattern)
    query = PREFIX + """
        SELECT ?source ?sourceTitle ?sourcePath ?target ?targetTitle WHERE {
          ?source a lit:Paper ;
                  lit:title ?sourceTitle ;
                  lit:sourcePath ?sourcePath ;
                  lit:cites ?target .
          ?target lit:title ?targetTitle .
          FILTER(CONTAINS(LCASE(STR(?targetTitle)), LCASE(STR(%s))))
        }
        ORDER BY LCASE(STR(?sourceTitle))
    """ % needle
    return store.query(query)


def papers_cited_by(store: LitStore, pattern: str) -> list[dict]:
    needle = _literal(pattern)
    query = PREFIX + """
        SELECT ?source ?sourceTitle ?sourcePath ?target ?targetTitle WHERE {
          ?source a lit:Paper ;
                  lit:title ?sourceTitle ;
                  lit:sourcePath ?sourcePath ;
                  lit:cites ?target .
          ?target lit:title ?targetTitle .
          FILTER(CONTAINS(LCASE(STR(?sourceTitle)), LCASE(STR(%s))))
        }
        ORDER BY LCASE(STR(?targetTitle))
    """ % needle
    return store.query(query)


def read_document(file_path: str, start_page: int = 1, end_page: int | None = None) -> str:
    return read_pdf_text(file_path, start_page=start_page, end_page=end_page)
