from __future__ import annotations

import json
from pathlib import Path

from .indexer import index_directory
from .bundle import export_bundle
from .export import bibliography_graph as export_bibliography_graph
from .export import citation_graph as export_citation_graph
from .export import export_graph_bundle
from .parser import read_pdf_text
from .report import annotated_bibliography_html as render_annotated_bibliography_html
from .report import export_annotated_bibliography_bundle
from .report import annotated_bibliography_pdf as render_annotated_bibliography_pdf
from .queries import (
    annotated_bibliography as query_annotated_bibliography,
    list_bibliographies as query_list_bibliographies,
    list_papers as query_list_papers,
    list_reading_lists as query_list_reading_lists,
    paper_details,
    paper_references,
    papers_by_author,
    papers_cited_by,
    papers_citing,
    papers_in_list as query_papers_in_list,
    papers_without_lists as query_papers_without_lists,
    search,
)
from .store import LitStore

try:  # pragma: no cover - optional dependency
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover - optional dependency
    FastMCP = None


_store: LitStore | None = None
_store_path: str = ".litkg_store.ttl"


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def _get_store() -> LitStore:
    global _store
    if _store is None:
        _store = LitStore(_store_path)
    return _store


def init_store(path: str) -> None:
    global _store, _store_path
    _store_path = path
    _store = LitStore(path)


if FastMCP is not None:  # pragma: no cover - optional dependency
    mcp = FastMCP("litkg")

    @mcp.tool()
    def index_library(path: str, store_path: str = ".litkg_store.ttl") -> str:
        init_store(store_path)
        stats = index_directory(path, _get_store())
        return _json(stats.__dict__)

    @mcp.tool()
    def papers() -> str:
        return _json(query_list_papers(_get_store()))

    @mcp.tool()
    def reading_lists() -> str:
        return _json(query_list_reading_lists(_get_store()))

    @mcp.tool()
    def bibliographies() -> str:
        return _json(query_list_bibliographies(_get_store()))

    @mcp.tool()
    def annotated_bibliography(pattern: str = "") -> str:
        return _json(query_annotated_bibliography(_get_store(), pattern))

    @mcp.tool()
    def annotated_bibliography_html(
        pattern: str = "",
        status: list[str] | None = None,
        sort_by: str = "order",
        descending: bool = False,
    ) -> str:
        return render_annotated_bibliography_html(
            _get_store(),
            pattern,
            statuses=status,
            sort_by=sort_by,
            descending=descending,
        )

    @mcp.tool()
    def annotated_bibliography_pdf(
        pattern: str = "",
        status: list[str] | None = None,
        sort_by: str = "order",
        descending: bool = False,
        output: str = "annotated-bibliography.pdf",
        library_name: str = "",
    ) -> str:
        Path(output).write_bytes(
            render_annotated_bibliography_pdf(
                _get_store(),
                pattern,
                statuses=status,
                sort_by=sort_by,
                descending=descending,
                library_name=library_name or None,
            )
        )
        return output

    @mcp.tool()
    def annotated_bibliography_export(
        pattern: str = "",
        status: list[str] | None = None,
        sort_by: str = "order",
        descending: bool = False,
        output_dir: str = ".",
        prefix: str = "annotated-bibliography",
        library_name: str = "",
    ) -> str:
        base_dir = Path(output_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        html_path = base_dir / f"{prefix}.html"
        pdf_path = base_dir / f"{prefix}.pdf"
        html_path.write_text(
            render_annotated_bibliography_html(
                _get_store(),
                pattern,
                statuses=status,
                sort_by=sort_by,
                descending=descending,
            ),
            encoding="utf-8",
        )
        pdf_path.write_bytes(
            render_annotated_bibliography_pdf(
                _get_store(),
                pattern,
                statuses=status,
                sort_by=sort_by,
                descending=descending,
                library_name=library_name or None,
            )
        )
        return _json({"html": str(html_path), "pdf": str(pdf_path)})

    @mcp.tool()
    def author(name: str) -> str:
        return _json(papers_by_author(_get_store(), name))

    @mcp.tool()
    def list_papers(list_name: str) -> str:
        return _json(query_papers_in_list(_get_store(), list_name))

    @mcp.tool()
    def search_papers(pattern: str) -> str:
        return _json(search(_get_store(), pattern))

    @mcp.tool()
    def show(pattern: str) -> str:
        return _json(paper_details(_get_store(), pattern))

    @mcp.tool()
    def references(pattern: str) -> str:
        return _json(paper_references(_get_store(), pattern))

    @mcp.tool()
    def cited_by(pattern: str) -> str:
        return _json(papers_citing(_get_store(), pattern))

    @mcp.tool()
    def cites(pattern: str) -> str:
        return _json(papers_cited_by(_get_store(), pattern))

    @mcp.tool()
    def orphan_papers() -> str:
        return _json(query_papers_without_lists(_get_store()))

    @mcp.tool()
    def citation_graph(root: str = "", depth: int = 2, fmt: str = "mermaid") -> str:
        return export_citation_graph(_get_store(), root_paper=root or None, depth=depth, fmt=fmt)

    @mcp.tool()
    def bibliography_graph(root: str = "", depth: int = 2, fmt: str = "mermaid") -> str:
        return export_bibliography_graph(_get_store(), root_bibliography=root or None, depth=depth, fmt=fmt)

    @mcp.tool()
    def graph_export(
        citation_root: str = "",
        bibliography_root: str = "",
        depth: int = 2,
        fmt: list[str] | None = None,
        output_dir: str = ".",
        prefix: str = "graph",
    ) -> str:
        return _json(
            export_graph_bundle(
                _get_store(),
                output_dir=output_dir,
                prefix=prefix,
                citation_root=citation_root or None,
                bibliography_root=bibliography_root or None,
                depth=depth,
                fmts=fmt or ("mermaid", "dot"),
            )
        )

    @mcp.tool()
    def export(
        citation_root: str = "",
        bibliography_root: str = "",
        depth: int = 2,
        fmt: list[str] | None = None,
        output_dir: str = "bundle",
        graph_prefix: str = "graph",
        report_prefix: str = "annotated-bibliography",
        report_pattern: str = "",
        status: list[str] | None = None,
        sort_by: str = "order",
        descending: bool = False,
        library_name: str = "",
    ) -> str:
        return _json(
            export_bundle(
                _get_store(),
                output_dir=output_dir,
                graph_prefix=graph_prefix,
                report_prefix=report_prefix,
                citation_root=citation_root or None,
                bibliography_root=bibliography_root or None,
                depth=depth,
                fmts=fmt or ("mermaid", "dot"),
                report_pattern=report_pattern,
                statuses=status,
                sort_by=sort_by,
                descending=descending,
                library_name=library_name or None,
            )
        )

    @mcp.tool()
    def read(file_path: str, start_page: int = 1, end_page: int = 0) -> str:
        return read_pdf_text(file_path, start_page=start_page, end_page=end_page or None)


    @mcp.tool()
    def papercite_sync(paper_path: str) -> str:
        from .papercite import sync

        return _json(sync(_get_store(), paper_path))

    @mcp.tool()
    def papercite_gate(paper_path: str, allow_partial: bool = False, allow_empty: bool = False) -> str:
        from .papercite import gate_result, sync

        result = sync(_get_store(), paper_path)
        ok, message = gate_result(result, allow_partial=allow_partial, allow_empty=allow_empty)
        return _json({"ok": ok, "message": message, **result})


def run(transport: str = "stdio", store_path: str = ".litkg_store.ttl", port: int = 8000):
    if FastMCP is None:
        raise RuntimeError("mcp is not installed. Install dependencies to run the MCP server.")
    init_store(store_path)
    if transport == "sse":
        mcp.run(transport="sse", port=port)
    else:
        mcp.run(transport=transport)
