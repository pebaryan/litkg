from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .parser import BibliographyInfo, PaperInfo, parse_bibliography, parse_pdf, parse_reading_list
from .store import LitStore
from .triples import (
    bibliography_to_triples,
    build_paper_lookup,
    citation_triples,
    paper_to_triples,
    paper_reference_to_triples,
    reading_list_to_triples,
)

PDF_EXTENSIONS = {".pdf"}
BIBLIOGRAPHY_EXTENSIONS = {".bib", ".bibtex", ".json"}
LIST_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".csv"}
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", ".venv", "node_modules", "dist", "build"}


@dataclass(slots=True)
class IndexStats:
    files: int = 0
    papers: int = 0
    reading_lists: int = 0
    bibliographies: int = 0
    bibliography_entries: int = 0
    entries: int = 0
    warnings: list[str] = field(default_factory=list)


def _should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _supported(path: Path) -> bool:
    return path.suffix.lower() in PDF_EXTENSIONS | LIST_EXTENSIONS | BIBLIOGRAPHY_EXTENSIONS


def index_directory(directory: str, store: LitStore | None = None) -> IndexStats:
    root = Path(directory).resolve()
    store = store or LitStore()

    files = [path for path in root.rglob("*") if path.is_file() and _supported(path) and not _should_skip(path)]
    papers: list[PaperInfo] = []
    reading_lists = []
    bibliographies: list[BibliographyInfo] = []
    warnings: list[str] = []

    for path in files:
        try:
            if path.suffix.lower() in PDF_EXTENSIONS:
                papers.append(parse_pdf(str(path)))
            elif path.suffix.lower() in BIBLIOGRAPHY_EXTENSIONS:
                bibliographies.append(parse_bibliography(str(path)))
            else:
                reading_lists.append(parse_reading_list(str(path)))
        except Exception as exc:  # pragma: no cover - defensive guard for dirty libraries
            warnings.append(f"{path}: {exc}")

    paper_lookup = build_paper_lookup(papers)
    triples: list[tuple] = []
    for paper in papers:
        triples.extend(paper_to_triples(paper))
        triples.extend(paper_reference_to_triples(paper, paper_lookup))
    for reading_list in reading_lists:
        triples.extend(reading_list_to_triples(reading_list, paper_lookup))
    for bibliography in bibliographies:
        triples.extend(bibliography_to_triples(bibliography, paper_lookup))
    triples.extend(citation_triples(papers, paper_lookup))

    store.clear()
    store.load_triples(triples)
    store.save()

    entry_count = sum(len(reading_list.entries) for reading_list in reading_lists)
    bibliography_entry_count = sum(len(bibliography.entries) for bibliography in bibliographies)
    return IndexStats(
        files=len(files),
        papers=len(papers),
        reading_lists=len(reading_lists),
        bibliographies=len(bibliographies),
        bibliography_entries=bibliography_entry_count,
        entries=entry_count,
        warnings=warnings,
    )
