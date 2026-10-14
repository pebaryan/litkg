from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from .export import export_graph_bundle
from .report import export_annotated_bibliography_bundle
from .store import LitStore


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def export_bundle(
    store: LitStore,
    *,
    output_dir: str | Path = "bundle",
    graph_prefix: str = "graph",
    report_prefix: str = "annotated-bibliography",
    citation_root: str | None = None,
    bibliography_root: str | None = None,
    depth: int = 2,
    fmts: Iterable[str] = ("mermaid", "dot"),
    report_pattern: str = "",
    statuses: Iterable[str] | None = None,
    sort_by: str = "order",
    descending: bool = False,
    library_name: str | None = None,
) -> dict[str, object]:
    base_dir = Path(output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    graphs_dir = base_dir / "graphs"
    reports_dir = base_dir / "reports"
    graph_outputs = export_graph_bundle(
        store,
        output_dir=graphs_dir,
        prefix=graph_prefix,
        citation_root=citation_root,
        bibliography_root=bibliography_root,
        depth=depth,
        fmts=fmts,
    )
    report_outputs = export_annotated_bibliography_bundle(
        store,
        output_dir=reports_dir,
        prefix=report_prefix,
        pattern=report_pattern,
        statuses=statuses,
        sort_by=sort_by,
        descending=descending,
        library_name=library_name,
    )

    summary = store.stats()
    manifest = {
        "generated_at": _timestamp(),
        "output_dir": str(base_dir),
        "summary": summary,
        "graphs": graph_outputs,
        "reports": report_outputs,
    }
    manifest_path = base_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    manifest["manifest"] = str(manifest_path)
    return manifest
