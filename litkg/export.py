from __future__ import annotations

import hashlib
from collections import deque
from pathlib import Path
from typing import Iterable

from rdflib import RDF, URIRef

from .ontology import (
    Bibliography,
    BibliographyEntry,
    Paper,
    ReferenceEntry,
    bibliographyFormat,
    hasEntry,
    citationTitle,
    entryText,
    title,
    bibliography_uri,
    bibliography_entry_uri,
    hasReference,
    refersTo,
    sourcePath,
    normalize_key,
)
from .store import LitStore


def _safe_id(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"n{digest}"


def _shorten(text: str, limit: int = 72) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _paper_label(store: LitStore, paper_uri: str) -> str:
    value = store.graph.value(subject=URIRef(paper_uri), predicate=title)
    if value:
        return str(value)
    return paper_uri.rsplit("/", 1)[-1]


def _reference_label(store: LitStore, ref_uri: str) -> str:
    value = store.graph.value(subject=URIRef(ref_uri), predicate=citationTitle)
    if value:
        return str(value)
    value = store.graph.value(subject=URIRef(ref_uri), predicate=title)
    if value:
        return str(value)
    value = store.graph.value(subject=URIRef(ref_uri), predicate=entryText)
    if value:
        return _shorten(str(value))
    return ref_uri.rsplit("/", 1)[-1]


def _bibliography_label(store: LitStore, bib_uri: str) -> str:
    value = store.graph.value(subject=URIRef(bib_uri), predicate=title)
    if value:
        return str(value)
    return bib_uri.rsplit("/", 1)[-1]


def _bibliography_entry_label(store: LitStore, entry_uri: str) -> str:
    value = store.graph.value(subject=URIRef(entry_uri), predicate=title)
    if value:
        return str(value)
    value = store.graph.value(subject=URIRef(entry_uri), predicate=entryText)
    if value:
        return _shorten(str(value))
    return entry_uri.rsplit("/", 1)[-1]


def _matching_papers(store: LitStore, root_paper: str) -> set[str]:
    needle = normalize_key(root_paper)
    if not needle:
        return set()
    matches: set[str] = set()
    for paper_uri in store.graph.subjects(RDF.type, Paper):
        paper_title = store.graph.value(subject=paper_uri, predicate=title)
        if paper_title and needle in normalize_key(str(paper_title)):
            matches.add(str(paper_uri))
    return matches


def _reachable_nodes(store: LitStore, seeds: set[str], depth: int) -> tuple[set[str], set[str], set[tuple[str, str, str]]]:
    papers: set[str] = set()
    references: set[str] = set()
    edges: set[tuple[str, str, str]] = set()
    queue: deque[tuple[str, int]] = deque((seed, 0) for seed in seeds)
    seen: set[tuple[str, int]] = set()

    while queue:
        node, dist = queue.popleft()
        if (node, dist) in seen or dist > depth:
            continue
        seen.add((node, dist))

        node_ref = URIRef(node)
        if store.graph.value(subject=node_ref, predicate=RDF.type) == Paper:
            papers.add(node)
            if dist == depth:
                continue
            for ref in store.graph.objects(node_ref, hasReference):
                ref_str = str(ref)
                references.add(ref_str)
                edges.add((node, ref_str, "references"))
                queue.append((ref_str, dist + 1))
        else:
            if store.graph.value(subject=node_ref, predicate=RDF.type) == ReferenceEntry:
                references.add(node)
            if dist == depth:
                continue
            for target in store.graph.objects(node_ref, refersTo):
                target_str = str(target)
                papers.add(target_str)
                edges.add((node, target_str, "cites"))
                queue.append((target_str, dist + 1))

    return papers, references, edges


def citation_graph(store: LitStore, root_paper: str | None = None, depth: int = 2, fmt: str = "mermaid") -> str:
    """Export a paper-reference-paper citation graph as Mermaid or DOT."""

    if depth < 1:
        depth = 1

    if root_paper:
        seeds = _matching_papers(store, root_paper)
    else:
        seeds = {str(paper) for paper in store.graph.subjects(RDF.type, Paper)}

    papers, references, edges = _reachable_nodes(store, seeds, depth) if root_paper else _all_nodes(store)

    if fmt == "dot":
        return _to_dot(store, papers, references, edges)
    return _to_mermaid(store, papers, references, edges)


def _matching_bibliographies(store: LitStore, root_bibliography: str) -> set[str]:
    needle = normalize_key(root_bibliography)
    if not needle:
        return set()
    matches: set[str] = set()
    for bib_uri in store.graph.subjects(RDF.type, Bibliography):
        bib_title = store.graph.value(subject=bib_uri, predicate=title)
        source_path = store.graph.value(subject=bib_uri, predicate=sourcePath)
        candidates = [
            normalize_key(str(bib_title)) if bib_title else "",
            normalize_key(str(source_path)) if source_path else "",
            normalize_key(str(URIRef(bib_uri)).rsplit("/", 1)[-1]),
            normalize_key(Path(str(source_path)).stem) if source_path else "",
        ]
        if any(needle in candidate for candidate in candidates if candidate):
            matches.add(str(bib_uri))
    return matches


def _bib_reachable_nodes(
    store: LitStore, seeds: set[str], depth: int
) -> tuple[set[str], set[str], set[str], set[tuple[str, str, str]]]:
    bibliographies: set[str] = set()
    entries: set[str] = set()
    papers: set[str] = set()
    edges: set[tuple[str, str, str]] = set()
    queue: deque[tuple[str, int]] = deque((seed, 0) for seed in seeds)
    seen: set[tuple[str, int]] = set()

    while queue:
        node, dist = queue.popleft()
        if (node, dist) in seen or dist > depth:
            continue
        seen.add((node, dist))
        node_ref = URIRef(node)

        node_type = store.graph.value(subject=node_ref, predicate=RDF.type)
        if node_type == Bibliography:
            bibliographies.add(node)
            if dist == depth:
                continue
            for entry in store.graph.objects(node_ref, hasEntry):
                entry_str = str(entry)
                entries.add(entry_str)
                edges.add((node, entry_str, "hasEntry"))
                queue.append((entry_str, dist + 1))
        elif node_type == BibliographyEntry:
            entries.add(node)
            if dist == depth:
                continue
            for target in store.graph.objects(node_ref, refersTo):
                target_str = str(target)
                papers.add(target_str)
                edges.add((node, target_str, "refersTo"))
                queue.append((target_str, dist + 1))
        elif node_type == Paper:
            papers.add(node)

    return bibliographies, entries, papers, edges


def bibliography_graph(store: LitStore, root_bibliography: str | None = None, depth: int = 2, fmt: str = "mermaid") -> str:
    """Export a bibliography-entry-paper graph as Mermaid or DOT."""

    if depth < 1:
        depth = 1

    if root_bibliography:
        seeds = _matching_bibliographies(store, root_bibliography)
        bibliographies, entries, papers, edges = _bib_reachable_nodes(store, seeds, depth)
    else:
        bibliographies = {str(bib) for bib in store.graph.subjects(RDF.type, Bibliography)}
        entries = {str(entry) for entry in store.graph.subjects(RDF.type, BibliographyEntry)}
        papers = {str(paper) for paper in store.graph.subjects(RDF.type, Paper)}
        edges: set[tuple[str, str, str]] = set()
        for bib in bibliographies:
            for entry in store.graph.objects(URIRef(bib), hasEntry):
                entry_str = str(entry)
                entries.add(entry_str)
                edges.add((bib, entry_str, "hasEntry"))
        for entry in entries:
            for target in store.graph.objects(URIRef(entry), refersTo):
                target_str = str(target)
                papers.add(target_str)
                edges.add((entry, target_str, "refersTo"))

    if fmt == "dot":
        return _bibliography_to_dot(store, bibliographies, entries, papers, edges)
    return _bibliography_to_mermaid(store, bibliographies, entries, papers, edges)


def export_graph_bundle(
    store: LitStore,
    *,
    output_dir: str | Path = ".",
    prefix: str = "graph",
    citation_root: str | None = None,
    bibliography_root: str | None = None,
    depth: int = 2,
    fmts: Iterable[str] = ("mermaid", "dot"),
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    selected_fmts = tuple(dict.fromkeys(fmt.lower() for fmt in fmts if fmt))
    if not selected_fmts:
        selected_fmts = ("mermaid", "dot")

    outputs: dict[str, str] = {}
    for fmt in selected_fmts:
        ext = "mmd" if fmt == "mermaid" else "dot"
        citation_path = output_path / f"{prefix}-citation.{ext}"
        bibliography_path = output_path / f"{prefix}-bibliography.{ext}"
        citation_path.write_text(
            citation_graph(store, root_paper=citation_root, depth=depth, fmt=fmt),
            encoding="utf-8",
        )
        bibliography_path.write_text(
            bibliography_graph(store, root_bibliography=bibliography_root, depth=depth, fmt=fmt),
            encoding="utf-8",
        )
        outputs[f"citation:{fmt}"] = str(citation_path)
        outputs[f"bibliography:{fmt}"] = str(bibliography_path)

    return outputs


def _all_nodes(store: LitStore) -> tuple[set[str], set[str], set[tuple[str, str, str]]]:
    papers: set[str] = {str(paper) for paper in store.graph.subjects(RDF.type, Paper)}
    references: set[str] = {str(ref) for ref in store.graph.subjects(RDF.type, ReferenceEntry)}
    edges: set[tuple[str, str, str]] = set()
    for paper in papers:
        for ref in store.graph.objects(paper, hasReference):
            ref_str = str(ref)
            references.add(ref_str)
            edges.add((paper, ref_str, "references"))
    for ref in references:
        for target in store.graph.objects(ref, refersTo):
            target_str = str(target)
            papers.add(target_str)
            edges.add((ref, target_str, "cites"))
    return papers, references, edges


def _to_mermaid(store: LitStore, papers: set[str], references: set[str], edges: set[tuple[str, str, str]]) -> str:
    lines = ["flowchart LR"]
    for paper in sorted(papers):
        node_id = _safe_id(paper)
        label = _paper_label(store, paper)
        lines.append(f'  {node_id}["{label}"]')
    for ref in sorted(references):
        node_id = _safe_id(ref)
        label = _reference_label(store, ref)
        lines.append(f'  {node_id}["{label}"]')
    for source, target, rel in sorted(edges):
        source_id = _safe_id(source)
        target_id = _safe_id(target)
        label = "references" if rel == "references" else "cites"
        lines.append(f'  {source_id} -->|{label}| {target_id}')
    return "\n".join(lines)


def _to_dot(store: LitStore, papers: set[str], references: set[str], edges: set[tuple[str, str, str]]) -> str:
    lines = ["digraph citation_graph {", "  rankdir=LR;"]
    for paper in sorted(papers):
        node_id = _safe_id(paper)
        label = _paper_label(store, paper).replace('"', '\\"')
        lines.append(f'  {node_id} [label="{label}", shape=box];')
    for ref in sorted(references):
        node_id = _safe_id(ref)
        label = _reference_label(store, ref).replace('"', '\\"')
        lines.append(f'  {node_id} [label="{label}", shape=ellipse];')
    for source, target, rel in sorted(edges):
        source_id = _safe_id(source)
        target_id = _safe_id(target)
        label = rel
        lines.append(f'  {source_id} -> {target_id} [label="{label}"];')
    lines.append("}")
    return "\n".join(lines)


def _bibliography_to_mermaid(
    store: LitStore,
    bibliographies: set[str],
    entries: set[str],
    papers: set[str],
    edges: set[tuple[str, str, str]],
) -> str:
    lines = ["flowchart LR"]
    for bib in sorted(bibliographies):
        node_id = _safe_id(bib)
        label = _bibliography_label(store, bib)
        lines.append(f'  {node_id}["{label}"]')
    for entry in sorted(entries):
        node_id = _safe_id(entry)
        label = _bibliography_entry_label(store, entry)
        lines.append(f'  {node_id}["{label}"]')
    for paper in sorted(papers):
        node_id = _safe_id(paper)
        label = _paper_label(store, paper)
        lines.append(f'  {node_id}["{label}"]')
    for source, target, rel in sorted(edges):
        source_id = _safe_id(source)
        target_id = _safe_id(target)
        lines.append(f'  {source_id} -->|{rel}| {target_id}')
    return "\n".join(lines)


def _bibliography_to_dot(
    store: LitStore,
    bibliographies: set[str],
    entries: set[str],
    papers: set[str],
    edges: set[tuple[str, str, str]],
) -> str:
    lines = ["digraph bibliography_graph {", "  rankdir=LR;"]
    for bib in sorted(bibliographies):
        node_id = _safe_id(bib)
        label = _bibliography_label(store, bib).replace('"', '\\"')
        lines.append(f'  {node_id} [label="{label}", shape=box];')
    for entry in sorted(entries):
        node_id = _safe_id(entry)
        label = _bibliography_entry_label(store, entry).replace('"', '\\"')
        lines.append(f'  {node_id} [label="{label}", shape=ellipse];')
    for paper in sorted(papers):
        node_id = _safe_id(paper)
        label = _paper_label(store, paper).replace('"', '\\"')
        lines.append(f'  {node_id} [label="{label}", shape=box3d];')
    for source, target, rel in sorted(edges):
        source_id = _safe_id(source)
        target_id = _safe_id(target)
        lines.append(f'  {source_id} -> {target_id} [label="{rel}"];')
    lines.append("}")
    return "\n".join(lines)
