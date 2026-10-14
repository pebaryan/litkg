from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .bundle import export_bundle
from .citations import find_citations, unique_keys
from .ontology import normalize_key
from .queries import annotated_bibliography

MARKDOWN_SUFFIXES = {".md", ".markdown", ".qmd", ".rmd", ".pmd"}


def parse_cite_keys(text: str, syntax: str = "latex") -> list[str]:
    """Extract citation keys in first-use order.

    ``syntax`` is ``"latex"`` (``\\cite``-family commands) or ``"markdown"``
    (Pandoc ``[@key]`` citations).
    """
    return unique_keys(find_citations(text, syntax))


def cite_syntax_for(path: str | Path) -> str:
    return "markdown" if Path(path).suffix.lower() in MARKDOWN_SUFFIXES else "latex"


def _entry_identity(row: dict) -> str:
    if row.get("entryDoi"):
        return f"doi:{normalize_key(str(row['entryDoi']))}"
    return f"title:{normalize_key(str(row.get('entryTitle') or row.get('entryText') or ''))}"


def _pick_entry(rows: list[dict]) -> tuple[dict, bool]:
    """Choose the entry for a cite key; flag a conflict when its definitions disagree."""
    conflict = len({_entry_identity(row) for row in rows}) > 1
    resolved = [row for row in rows if row.get("refersTo")]
    return (resolved or rows)[0], conflict


def sync(store, paper_path: str | Path) -> dict:
    path = Path(paper_path)
    text = path.read_text(encoding="utf-8")
    cite_keys = parse_cite_keys(text, cite_syntax_for(path))
    by_key: dict[str, list[dict]] = {}
    for row in annotated_bibliography(store, ""):
        key = row.get("entryKey")
        if key:
            by_key.setdefault(str(key), []).append(row)

    results = []
    counts: Counter[str] = Counter()
    for key in cite_keys:
        rows = by_key.get(key)
        if not rows:
            status = "unresolved"
            refers_to = None
            target = None
        else:
            row, conflict = _pick_entry(rows)
            status = "conflict" if conflict else str(row.get("status", "partial"))
            refers_to = row.get("refersTo")
            target = row.get("refersToTitle") or row.get("entryTitle")
        counts[status] += 1
        results.append(
            {
                "cite_key": key,
                "status": status,
                "target": target,
                "refers_to": refers_to,
            }
        )

    return {
        "paper": str(path),
        "cite_keys": cite_keys,
        "counts": dict(counts),
        "unresolved": [r["cite_key"] for r in results if r["status"] == "unresolved"],
        "duplicates": [r["cite_key"] for r in results if r["status"] == "duplicate"],
        "conflicts": [r["cite_key"] for r in results if r["status"] == "conflict"],
        "results": results,
    }


def gate_result(result: dict, allow_partial: bool = False, allow_empty: bool = False) -> tuple[bool, str]:
    if not result.get("cite_keys") and not allow_empty:
        return False, "no citations found; check the citation syntax or pass --allow-empty"
    unresolved = result.get("unresolved", [])
    duplicates = result.get("duplicates", [])
    conflicts = result.get("conflicts", [])
    partial = [r["cite_key"] for r in result.get("results", []) if r["status"] == "partial"]
    if unresolved:
        return False, f"{len(unresolved)} unresolved citation(s): {', '.join(unresolved)}"
    if duplicates:
        return False, f"{len(duplicates)} duplicate citation(s): {', '.join(duplicates)}"
    if conflicts:
        return False, f"{len(conflicts)} cite key(s) defined differently in several bibliographies: {', '.join(conflicts)}"
    if partial and not allow_partial:
        return False, f"{len(partial)} partial citation(s): {', '.join(partial)}"
    return True, "citation gate passed"



def export(store, paper_path: str | Path, output_dir: str | Path = "paper-bundle") -> dict:
    """Sync citations, then export graphs/reports for the paper workflow."""
    result = sync(store, paper_path)
    manifest = export_bundle(store, output_dir=output_dir)
    manifest["papercite"] = result
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / ".litkg_paper.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return manifest

def dump(result: dict, output_path: str | None = None) -> str:
    text = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
    return text
