from __future__ import annotations

from pathlib import Path

from rdflib import Graph, Literal, RDF

from .ontology import (
    Author,
    Bibliography,
    BibliographyEntry,
    cites,
    ONTOLOGY,
    Paper,
    ReferenceEntry,
    ReadingList,
    ReadingListEntry,
    Venue,
)


def _bind(graph: Graph) -> None:
    graph.bind("lit", ONTOLOGY)
    graph.bind("rdf", RDF)


class LitStore:
    """Small rdflib-backed SPARQL store for literature graphs."""

    def __init__(self, path: str | None = None):
        self.path = self._resolve_path(path)
        self.graph = Graph()
        _bind(self.graph)
        if self.path and self.path.exists():
            self.graph.parse(self.path, format="turtle")

    @staticmethod
    def _resolve_path(path: str | None) -> Path | None:
        if not path:
            return None
        candidate = Path(path).expanduser()
        if candidate.suffix.lower() in {".ttl", ".turtle", ".rdf", ".xml", ".jsonld"}:
            return candidate
        return candidate / "litkg.ttl"

    def load_triples(self, triples: list[tuple]) -> int:
        for triple in triples:
            self.graph.add(triple)
        return len(triples)

    def query(self, sparql: str) -> list[dict]:
        result = self.graph.query(sparql)
        rows: list[dict] = []
        variables = [str(var) for var in result.vars]
        for row in result:
            item: dict[str, object] = {}
            for index, variable in enumerate(variables):
                value = row[index]
                if value is None:
                    continue
                if isinstance(value, Literal):
                    item[variable] = value.toPython()
                else:
                    item[variable] = str(value)
            rows.append(item)
        return rows

    def query_raw(self, sparql: str):
        return self.graph.query(sparql)

    def clear(self) -> None:
        self.graph.remove((None, None, None))

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.graph.serialize(destination=str(self.path), format="turtle")

    def stats(self) -> dict:
        def _count(type_uri: str) -> int:
            rows = self.query(
                f"""
                PREFIX lit: <{ONTOLOGY}>
                SELECT (COUNT(?item) AS ?count) WHERE {{
                  ?item a <{type_uri}> .
                }}
                """
            )
            return int(rows[0]["count"]) if rows else 0

        return {
            "triples": len(self.graph),
            "papers": _count(str(Paper)),
            "authors": _count(str(Author)),
            "venues": _count(str(Venue)),
            "reading_lists": _count(str(ReadingList)),
            "reading_list_entries": _count(str(ReadingListEntry)),
            "bibliographies": _count(str(Bibliography)),
            "bibliography_entries": _count(str(BibliographyEntry)),
            "reference_entries": _count(str(ReferenceEntry)),
            "citation_edges": len(list(self.graph.triples((None, cites, None)))),
        }
