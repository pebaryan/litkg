
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .bundle import export_bundle
from .queries import annotated_bibliography


CITE_RE = re.compile(r"\\cite[a-zA-Z*]*\s*\{([^}]*)\}")


def parse_cite_keys(text: str) -> list[str]:
    keys: list[str] = []
    for match in CITE_RE.finditer(text):
        for key in match.group(1).split(","):
            clean = key.strip()
            if clean and clean not in keys:
                keys.append(clean)
    return keys


def sync(store, paper_path: str | Path) -> dict:
    path = Path(paper_path)
    text = path.read_text(encoding="utf-8")
    cite_keys = parse_cite_keys(text)
    entries = annotated_bibliography(store, "")
    by_key: dict[str, dict] = {}
    for row in entries:
        key = row.get("entryKey")
        if key and key not in by_key:
            by_key[key] = row

    results = []
    counts: Counter[str] = Counter()
    for key in cite_keys:
        row = by_key.get(key)
        if row is None:
            status = "unresolved"
            refers_to = None
            target = None
        else:
            status = str(row.get("status", "partial"))
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
        "results": results,
    }


def gate_result(result: dict, allow_partial: bool = False) -> tuple[bool, str]:
    unresolved = result.get("unresolved", [])
    duplicates = result.get("duplicates", [])
    partial = [r["cite_key"] for r in result.get("results", []) if r["status"] == "partial"]
    if unresolved:
        return False, f"{len(unresolved)} unresolved citation(s): {', '.join(unresolved)}"
    if duplicates:
        return False, f"{len(duplicates)} duplicate citation(s): {', '.join(duplicates)}"
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
