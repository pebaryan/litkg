from __future__ import annotations

import json
from pathlib import Path

import click

from .indexer import index_directory
from .parser import read_pdf_text
from .bundle import export_bundle
from .export import bibliography_graph, citation_graph, export_graph_bundle
from .queries import (
    annotated_bibliography,
    list_papers,
    list_bibliographies,
    list_reading_lists,
    paper_details,
    paper_references,
    papers_by_author,
    papers_cited_by,
    papers_citing,
    papers_in_list,
    papers_without_lists,
    search,
)
from .report import annotated_bibliography_html, annotated_bibliography_pdf, export_annotated_bibliography_bundle
from .store import LitStore


def _store(path: str | None) -> LitStore:
    return LitStore(path or ".litkg_store.ttl")


def _dump(rows) -> str:
    return json.dumps(rows, indent=2, ensure_ascii=False, default=str)


@click.group()
def cli() -> None:
    """LitKG-RDF command line interface."""


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def index(directory: Path, store_path: str) -> None:
    """Index a directory of PDF papers and reading-list files."""

    stats = index_directory(str(directory), _store(store_path))
    click.echo(_dump(stats.__dict__))


@cli.command(name="stats")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def stats_cmd(store_path: str) -> None:
    click.echo(_dump(_store(store_path).stats()))


@cli.command()
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def papers(store_path: str) -> None:
    click.echo(_dump(list_papers(_store(store_path))))


@cli.command(name="lists")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def lists_cmd(store_path: str) -> None:
    click.echo(_dump(list_reading_lists(_store(store_path))))


@cli.command(name="bibliographies")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def bibliographies_cmd(store_path: str) -> None:
    click.echo(_dump(list_bibliographies(_store(store_path))))


@cli.command(name="annotated-bibliography")
@click.argument("pattern", required=False, default="")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def annotated_bibliography_cmd(pattern: str, store_path: str) -> None:
    click.echo(_dump(annotated_bibliography(_store(store_path), pattern)))


@cli.command(name="annotated-bibliography-html")
@click.argument("pattern", required=False, default="")
@click.option(
    "--status",
    "statuses",
    multiple=True,
    type=click.Choice(["resolved", "duplicate", "partial", "unresolved"], case_sensitive=False),
    help="Filter to one or more entry statuses. Repeat the option to include multiple statuses.",
)
@click.option(
    "--sort-by",
    default="order",
    show_default=True,
    type=click.Choice(["order", "status", "entry", "target", "duplicate-count"], case_sensitive=False),
)
@click.option("--descending/--ascending", default=False, show_default=True)
@click.option("--output", default="", show_default=False, help="Optional file path to write the HTML report to.")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def annotated_bibliography_html_cmd(
    pattern: str,
    statuses: tuple[str, ...],
    sort_by: str,
    descending: bool,
    output: str,
    store_path: str,
) -> None:
    html = annotated_bibliography_html(
        _store(store_path),
        pattern,
        statuses=statuses,
        sort_by=sort_by.lower(),
        descending=descending,
    )
    if output:
        Path(output).write_text(html, encoding="utf-8")
        click.echo(f"Wrote HTML report to {output}")
        return
    click.echo(html)


@cli.command(name="annotated-bibliography-pdf")
@click.argument("pattern", required=False, default="")
@click.option(
    "--status",
    "statuses",
    multiple=True,
    type=click.Choice(["resolved", "duplicate", "partial", "unresolved"], case_sensitive=False),
    help="Filter to one or more entry statuses. Repeat the option to include multiple statuses.",
)
@click.option(
    "--sort-by",
    default="order",
    show_default=True,
    type=click.Choice(["order", "status", "entry", "target", "duplicate-count"], case_sensitive=False),
)
@click.option("--descending/--ascending", default=False, show_default=True)
@click.option(
    "--output",
    default="annotated-bibliography.pdf",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
)
@click.option("--library-name", default="", show_default=False, help="Override the library name shown on the PDF cover and footer.")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def annotated_bibliography_pdf_cmd(
    pattern: str,
    statuses: tuple[str, ...],
    sort_by: str,
    descending: bool,
    output: Path,
    library_name: str,
    store_path: str,
) -> None:
    pdf_bytes = annotated_bibliography_pdf(
        _store(store_path),
        pattern,
        statuses=statuses,
        sort_by=sort_by.lower(),
        descending=descending,
        library_name=library_name or None,
    )
    output.write_bytes(pdf_bytes)
    click.echo(f"Wrote PDF report to {output}")


@cli.command(name="annotated-bibliography-export")
@click.argument("pattern", required=False, default="")
@click.option(
    "--status",
    "statuses",
    multiple=True,
    type=click.Choice(["resolved", "duplicate", "partial", "unresolved"], case_sensitive=False),
    help="Filter to one or more entry statuses. Repeat the option to include multiple statuses.",
)
@click.option(
    "--sort-by",
    default="order",
    show_default=True,
    type=click.Choice(["order", "status", "entry", "target", "duplicate-count"], case_sensitive=False),
)
@click.option("--descending/--ascending", default=False, show_default=True)
@click.option("--output-dir", default=".", show_default=True, type=click.Path(file_okay=False, path_type=Path))
@click.option("--prefix", default="annotated-bibliography", show_default=True, help="Filename prefix for the generated reports.")
@click.option("--library-name", default="", show_default=False, help="Override the library name shown on the PDF cover and footer.")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def annotated_bibliography_export_cmd(
    pattern: str,
    statuses: tuple[str, ...],
    sort_by: str,
    descending: bool,
    output_dir: Path,
    prefix: str,
    library_name: str,
    store_path: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    html_output = output_dir / f"{prefix}.html"
    pdf_output = output_dir / f"{prefix}.pdf"
    store = _store(store_path)
    html_output.write_text(
        annotated_bibliography_html(
            store,
            pattern,
            statuses=statuses,
            sort_by=sort_by.lower(),
            descending=descending,
        ),
        encoding="utf-8",
    )
    pdf_output.write_bytes(
        annotated_bibliography_pdf(
            store,
            pattern,
            statuses=statuses,
            sort_by=sort_by.lower(),
            descending=descending,
            library_name=library_name or None,
        )
    )
    click.echo(f"Wrote HTML report to {html_output}")
    click.echo(f"Wrote PDF report to {pdf_output}")


@cli.command()
@click.argument("pattern")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def search_cmd(pattern: str, store_path: str) -> None:
    click.echo(_dump(search(_store(store_path), pattern)))


@cli.command(name="author")
@click.argument("name")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def author_cmd(name: str, store_path: str) -> None:
    click.echo(_dump(papers_by_author(_store(store_path), name)))


@cli.command(name="list-papers")
@click.argument("list_name")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def list_papers_cmd(list_name: str, store_path: str) -> None:
    click.echo(_dump(papers_in_list(_store(store_path), list_name)))


@cli.command()
@click.argument("pattern")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def show(pattern: str, store_path: str) -> None:
    click.echo(_dump(paper_details(_store(store_path), pattern)))


@cli.command()
@click.argument("pattern")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def references(pattern: str, store_path: str) -> None:
    click.echo(_dump(paper_references(_store(store_path), pattern)))


@cli.command(name="cited-by")
@click.argument("pattern")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def cited_by_cmd(pattern: str, store_path: str) -> None:
    click.echo(_dump(papers_citing(_store(store_path), pattern)))


@cli.command(name="cites")
@click.argument("pattern")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def cites_cmd(pattern: str, store_path: str) -> None:
    click.echo(_dump(papers_cited_by(_store(store_path), pattern)))


@cli.command()
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--start-page", default=1, show_default=True, type=int)
@click.option("--end-page", default=0, show_default=True, type=int)
def read(file_path: Path, start_page: int, end_page: int) -> None:
    click.echo(read_pdf_text(str(file_path), start_page=start_page, end_page=end_page or None))


@cli.command(name="orphan-papers")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def orphan_papers_cmd(store_path: str) -> None:
    click.echo(_dump(papers_without_lists(_store(store_path))))


@cli.command()
@click.argument("sparql")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def query(sparql: str, store_path: str) -> None:
    click.echo(_dump(_store(store_path).query(sparql)))


@cli.command(name="citation-graph")
@click.option("--root", default="", show_default=False, help="Root paper title to center the graph on.")
@click.option("--depth", default=2, show_default=True, type=int)
@click.option("--fmt", "fmt", default="mermaid", show_default=True, type=click.Choice(["mermaid", "dot"]))
@click.option("--output", default="", show_default=False, help="Optional file path to write the graph to.")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def citation_graph_cmd(root: str, depth: int, fmt: str, output: str, store_path: str) -> None:
    graph = citation_graph(_store(store_path), root_paper=root or None, depth=depth, fmt=fmt)
    if output:
        Path(output).write_text(graph, encoding="utf-8")
    click.echo(graph)


@cli.command(name="bibliography-graph")
@click.option("--root", default="", show_default=False, help="Root bibliography title to center the graph on.")
@click.option("--depth", default=2, show_default=True, type=int)
@click.option("--fmt", "fmt", default="mermaid", show_default=True, type=click.Choice(["mermaid", "dot"]))
@click.option("--output", default="", show_default=False, help="Optional file path to write the graph to.")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def bibliography_graph_cmd(root: str, depth: int, fmt: str, output: str, store_path: str) -> None:
    graph = bibliography_graph(_store(store_path), root_bibliography=root or None, depth=depth, fmt=fmt)
    if output:
        Path(output).write_text(graph, encoding="utf-8")
    click.echo(graph)


@cli.command(name="graph-export")
@click.option("--citation-root", default="", show_default=False, help="Optional root paper title for the citation graph.")
@click.option("--bibliography-root", default="", show_default=False, help="Optional root bibliography title for the bibliography graph.")
@click.option("--depth", default=2, show_default=True, type=int)
@click.option(
    "--fmt",
    "fmts",
    multiple=True,
    type=click.Choice(["mermaid", "dot"], case_sensitive=False),
    help="Graph format to export. Repeat the option to write multiple formats.",
)
@click.option("--output-dir", default=".", show_default=True, type=click.Path(file_okay=False, path_type=Path))
@click.option("--prefix", default="graph", show_default=True, help="Filename prefix for the generated graph files.")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def graph_export_cmd(
    citation_root: str,
    bibliography_root: str,
    depth: int,
    fmts: tuple[str, ...],
    output_dir: Path,
    prefix: str,
    store_path: str,
) -> None:
    outputs = export_graph_bundle(
        _store(store_path),
        output_dir=output_dir,
        prefix=prefix,
        citation_root=citation_root or None,
        bibliography_root=bibliography_root or None,
        depth=depth,
        fmts=fmts or ("mermaid", "dot"),
    )
    click.echo(_dump(outputs))


@cli.command(name="export")
@click.option("--output-dir", default="bundle", show_default=True, type=click.Path(file_okay=False, path_type=Path))
@click.option("--graph-prefix", default="graph", show_default=True, help="Filename prefix for graph exports.")
@click.option("--report-prefix", default="annotated-bibliography", show_default=True, help="Filename prefix for annotated bibliography exports.")
@click.option("--citation-root", default="", show_default=False, help="Optional root paper title for the citation graph.")
@click.option("--bibliography-root", default="", show_default=False, help="Optional root bibliography title for the bibliography graph.")
@click.option("--depth", default=2, show_default=True, type=int)
@click.option(
    "--fmt",
    "fmts",
    multiple=True,
    type=click.Choice(["mermaid", "dot"], case_sensitive=False),
    help="Graph format to export. Repeat the option to write multiple formats.",
)
@click.option("--report-pattern", default="", show_default=False, help="Optional filter for the annotated bibliography report.")
@click.option(
    "--status",
    "statuses",
    multiple=True,
    type=click.Choice(["resolved", "duplicate", "partial", "unresolved"], case_sensitive=False),
    help="Filter the annotated bibliography report to one or more entry statuses. Repeat the option to include multiple statuses.",
)
@click.option(
    "--sort-by",
    default="order",
    show_default=True,
    type=click.Choice(["order", "status", "entry", "target", "duplicate-count"], case_sensitive=False),
)
@click.option("--descending/--ascending", default=False, show_default=True)
@click.option("--library-name", default="", show_default=False, help="Override the library name shown on the PDF cover and footer.")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def export_cmd(
    output_dir: Path,
    graph_prefix: str,
    report_prefix: str,
    citation_root: str,
    bibliography_root: str,
    depth: int,
    fmts: tuple[str, ...],
    report_pattern: str,
    statuses: tuple[str, ...],
    sort_by: str,
    descending: bool,
    library_name: str,
    store_path: str,
) -> None:
    manifest = export_bundle(
        _store(store_path),
        output_dir=output_dir,
        graph_prefix=graph_prefix,
        report_prefix=report_prefix,
        citation_root=citation_root or None,
        bibliography_root=bibliography_root or None,
        depth=depth,
        fmts=fmts or ("mermaid", "dot"),
        report_pattern=report_pattern,
        statuses=statuses,
        sort_by=sort_by.lower(),
        descending=descending,
        library_name=library_name or None,
    )
    click.echo(_dump(manifest))


def main() -> None:
    cli()
