from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import __version__
from .bundle import export_bundle
from .export import bibliography_graph, citation_graph, export_graph_bundle
from .indexer import index_directory
from .parser import read_pdf_text
from .queries import (
    annotated_bibliography,
    list_bibliographies,
    list_papers,
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
from .report import annotated_bibliography_html, annotated_bibliography_pdf
from .store import LitStore


def _store(path: str | None) -> LitStore:
    return LitStore(path or ".litkg_store.ttl")


def _dump(rows) -> str:
    return json.dumps(rows, indent=2, ensure_ascii=False, default=str)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="litkg")
def cli() -> None:
    """Turn reading lists, PDFs, and bibliographies into a literature map, and verify references.

    
    Quick start:
      litkg index ./library             build the knowledge graph
      litkg papers                      list indexed papers (also: search, cites, cited-by)
      litkg serve                       browse the library in a local web UI
      litkg check paper.tex --online    verify a manuscript's references against registries
    """



@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
@click.option("--no-cache", is_flag=True, help="Re-parse every PDF instead of reusing unchanged results.")
@click.option("--json", "as_json", is_flag=True, help="Print statistics as JSON.")
def index(directory: Path, store_path: str, no_cache: bool, as_json: bool) -> None:
    """Index PDFs, BibTeX/CSL-JSON bibliographies, and reading lists under DIRECTORY."""
    from dataclasses import asdict

    stats = index_directory(str(directory), _store(store_path), use_cache=not no_cache)
    if as_json:
        click.echo(_dump(asdict(stats)))
        return
    reused = f" ({stats.cached} unchanged)" if stats.cached else ""
    click.echo(
        f"Indexed {stats.files} file(s) into {store_path}: {stats.papers} paper(s){reused}, "
        f"{stats.bibliographies} bibliograph{'y' if stats.bibliographies == 1 else 'ies'} "
        f"({stats.bibliography_entries} entries), {stats.reading_lists} reading list(s)."
    )
    for warning in stats.warnings:
        click.echo(click.style("warning ", fg="yellow") + warning, err=True)


@cli.command(name="stats")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def stats_cmd(store_path: str) -> None:
    """Show counts of papers, authors, bibliographies, and citation links."""
    click.echo(_dump(_store(store_path).stats()))


@cli.command()
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def papers(store_path: str) -> None:
    """List indexed papers."""
    click.echo(_dump(list_papers(_store(store_path))))


@cli.command(name="lists")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def lists_cmd(store_path: str) -> None:
    """List indexed reading lists."""
    click.echo(_dump(list_reading_lists(_store(store_path))))


@cli.command(name="bibliographies")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def bibliographies_cmd(store_path: str) -> None:
    """List indexed bibliographies."""
    click.echo(_dump(list_bibliographies(_store(store_path))))


@cli.command(name="annotated-bibliography")
@click.argument("pattern", required=False, default="")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def annotated_bibliography_cmd(pattern: str, store_path: str) -> None:
    """Show bibliography entries with resolution status (JSON)."""
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
    """Write the annotated bibliography as HTML."""
    html = annotated_bibliography_html(
        _store(store_path),
        pattern,
        statuses=statuses,
        sort_by=sort_by.lower(),
        descending=descending,
    )
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
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
    """Write the annotated bibliography as PDF (needs litkg[pdf])."""
    pdf_bytes = annotated_bibliography_pdf(
        _store(store_path),
        pattern,
        statuses=statuses,
        sort_by=sort_by.lower(),
        descending=descending,
        library_name=library_name or None,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
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
    """Write the annotated bibliography as both HTML and PDF."""
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
    """Search paper titles, abstracts, and keywords."""
    click.echo(_dump(search(_store(store_path), pattern)))


@cli.command(name="author")
@click.argument("name")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def author_cmd(name: str, store_path: str) -> None:
    """List papers by an author."""
    click.echo(_dump(papers_by_author(_store(store_path), name)))


@cli.command(name="list-papers")
@click.argument("list_name")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def list_papers_cmd(list_name: str, store_path: str) -> None:
    """List papers on a reading list."""
    click.echo(_dump(papers_in_list(_store(store_path), list_name)))


@cli.command()
@click.argument("pattern")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def show(pattern: str, store_path: str) -> None:
    """Show details for papers whose title matches PATTERN."""
    click.echo(_dump(paper_details(_store(store_path), pattern)))


@cli.command()
@click.argument("pattern")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def references(pattern: str, store_path: str) -> None:
    """Show references extracted from matching papers."""
    click.echo(_dump(paper_references(_store(store_path), pattern)))


@cli.command(name="cited-by")
@click.argument("pattern")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def cited_by_cmd(pattern: str, store_path: str) -> None:
    """Show indexed papers that cite matching papers."""
    click.echo(_dump(papers_citing(_store(store_path), pattern)))


@cli.command(name="cites")
@click.argument("pattern")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def cites_cmd(pattern: str, store_path: str) -> None:
    """Show indexed papers cited by matching papers."""
    click.echo(_dump(papers_cited_by(_store(store_path), pattern)))


@cli.command()
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--start-page", default=1, show_default=True, type=int)
@click.option("--end-page", default=0, show_default=True, type=int)
def read(file_path: Path, start_page: int, end_page: int) -> None:
    """Print the text of a PDF."""
    click.echo(read_pdf_text(str(file_path), start_page=start_page, end_page=end_page or None))


@cli.command(name="orphan-papers")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def orphan_papers_cmd(store_path: str) -> None:
    """List papers that are not on any reading list."""
    click.echo(_dump(papers_without_lists(_store(store_path))))


@cli.command()
@click.argument("sparql")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def query(sparql: str, store_path: str) -> None:
    """Run a SPARQL query against the store."""
    click.echo(_dump(_store(store_path).query(sparql)))


@cli.command(name="citation-graph")
@click.option("--root", default="", show_default=False, help="Root paper title to center the graph on.")
@click.option("--depth", default=2, show_default=True, type=int)
@click.option("--fmt", "fmt", default="mermaid", show_default=True, type=click.Choice(["mermaid", "dot"]))
@click.option("--output", default="", show_default=False, help="Optional file path to write the graph to.")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def citation_graph_cmd(root: str, depth: int, fmt: str, output: str, store_path: str) -> None:
    """Export the citation graph as Mermaid or DOT."""
    graph = citation_graph(_store(store_path), root_paper=root or None, depth=depth, fmt=fmt)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(graph, encoding="utf-8")
    click.echo(graph)


@cli.command(name="bibliography-graph")
@click.option("--root", default="", show_default=False, help="Root bibliography title to center the graph on.")
@click.option("--depth", default=2, show_default=True, type=int)
@click.option("--fmt", "fmt", default="mermaid", show_default=True, type=click.Choice(["mermaid", "dot"]))
@click.option("--output", default="", show_default=False, help="Optional file path to write the graph to.")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
def bibliography_graph_cmd(root: str, depth: int, fmt: str, output: str, store_path: str) -> None:
    """Export bibliography-to-paper links as Mermaid or DOT."""
    graph = bibliography_graph(_store(store_path), root_bibliography=root or None, depth=depth, fmt=fmt)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
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
    """Write citation and bibliography graphs to a directory."""
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
    """Write graphs, reports, and a manifest to one bundle directory."""
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



@cli.command()
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
@click.option("--paper", "paper", default=None, type=click.Path(exists=True, dir_okay=False), help="Paper to show in the citation review queue.")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8765, show_default=True)
def serve(store_path: str, paper: str | None, host: str, port: int) -> None:
    """Run the local LitKG web UI."""
    try:
        import uvicorn
    except ImportError as exc:
        raise click.ClickException("the web UI needs extra packages: pip install 'litkg[web]'") from exc
    from .web import create_app

    app = create_app(store_path, paper=paper)
    click.echo(f"Serving LitKG UI at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


# --------------------------------------------------------------------------- paper checks


def _check_options(
    paper: Path,
    config_path: str | None,
    bibs: tuple[str, ...],
    online: bool | None,
    strict: bool | None,
    ignored: tuple[str, ...],
    store_path: str | None,
    mailto: str | None,
    cache_dir: str | None,
):
    from .check import CheckOptions, find_config, load_config

    try:
        config = load_config(config_path or find_config(paper))
    except (OSError, ValueError) as exc:
        raise click.ClickException(f"invalid config: {exc}") from exc
    return CheckOptions(
        bibliographies=[*config.get("bib", []), *bibs],
        online=bool(config.get("online", False) if online is None else online),
        strict=bool(config.get("strict", False) if strict is None else strict),
        ignore={**config.get("ignore", {}), **{key: "" for key in ignored}},
        mailto=mailto or config.get("mailto"),
        store=store_path or config.get("store"),
        cache_dir=cache_dir or config.get("cache_dir", ".litkg_cache"),
    )


def _check_common(function):
    options = [
        click.option("--bib", "bibs", multiple=True, type=click.Path(exists=True, dir_okay=False), help="Extra bibliography file (repeatable). Bibliographies the paper declares are found automatically."),
        click.option("--store", "store_path", default=None, help="LitKG store; papers in it count as evidence that a reference exists."),
        click.option("--config", "config_path", default=None, type=click.Path(exists=True, dir_okay=False), help="JSON config file. Default: .litkg.json next to the paper or in the current directory."),
        click.option("--mailto", envvar="LITKG_MAILTO", default=None, help="Contact email sent to Crossref/OpenAlex for their polite pool. [env: LITKG_MAILTO]"),
        click.option("--cache-dir", envvar="LITKG_CACHE_DIR", default=None, help="Where online responses are cached. [default: .litkg_cache]"),
    ]
    for option in reversed(options):
        function = option(function)
    return function


@cli.command()
@click.argument("paper", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--online/--offline", default=None, help="Verify references against Crossref, DataCite, OpenAlex, and arXiv. [default: offline]")
@click.option("--strict", is_flag=True, default=None, help="Fail on warnings as well as errors.")
@click.option("--ignore", "ignored", multiple=True, metavar="KEY", help="Cite key to skip (repeatable).")
@_check_common
@click.option("--format", "fmt", type=click.Choice(["text", "json", "sarif", "junit", "github", "markdown"]), default="text", show_default=True)
@click.option("--output", "-o", "output", default=None, help="Write the report to a file instead of stdout.")
@click.option("--sarif", "sarif_path", default=None, metavar="PATH", help="Also write a SARIF report (GitHub code scanning).")
@click.option("--junit", "junit_path", default=None, metavar="PATH", help="Also write a JUnit XML report.")
@click.option("--json", "json_path", default=None, metavar="PATH", help="Also write a JSON report.")
@click.option("--markdown", "markdown_path", default=None, metavar="PATH", help="Also write a Markdown summary (e.g. $GITHUB_STEP_SUMMARY).")
@click.option("--verbose", "-v", is_flag=True, help="Show notes and citations without issues.")
def check(
    paper: Path,
    online: bool | None,
    strict: bool | None,
    ignored: tuple[str, ...],
    bibs: tuple[str, ...],
    store_path: str | None,
    config_path: str | None,
    mailto: str | None,
    cache_dir: str | None,
    fmt: str,
    output: str | None,
    sarif_path: str | None,
    junit_path: str | None,
    json_path: str | None,
    markdown_path: str | None,
    verbose: bool,
) -> None:
    """Check every citation in PAPER (.tex, .md, .qmd, .rmd).

    Follows \\input/\\include, reads the bibliographies the paper declares, and reports
    undefined, conflicting, malformed, and (with --online) fabricated or mismatched
    references. Exits with status 1 when the check fails.
    """
    from .check import check_paper
    from .formats import render, render_text, write_output

    options = _check_options(paper, config_path, bibs, online, strict, ignored, store_path, mailto, cache_dir)
    report = check_paper(paper, options)

    rendered = render(report, fmt, verbose=verbose)
    if output:
        write_output(output, rendered)
        if fmt != "text":
            click.echo(render_text(report, verbose=verbose), err=True)
    else:
        click.echo(rendered)
    for path, side_format in ((sarif_path, "sarif"), (junit_path, "junit"), (json_path, "json"), (markdown_path, "markdown")):
        if path:
            write_output(path, render(report, side_format))
    sys.exit(0 if report.passed else 1)


@cli.command()
@click.argument("paper", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--key", "keys", multiple=True, metavar="KEY", help="Only fix this cite key (repeatable).")
@click.option("--add-doi", is_flag=True, help="Also add DOIs to correct entries that lack one.")
@click.option("--write", is_flag=True, help="Apply the changes. Without it, only a diff is shown.")
@_check_common
def fix(
    paper: Path,
    keys: tuple[str, ...],
    add_doi: bool,
    write: bool,
    bibs: tuple[str, ...],
    store_path: str | None,
    config_path: str | None,
    mailto: str | None,
    cache_dir: str | None,
) -> None:
    """Correct BibTeX entries in PAPER's bibliographies from verified records.

    Runs an online check, then edits only the fields that are wrong (title, author,
    year, doi, eprint). Shows a diff; pass --write to apply it.
    """
    from .check import check_paper
    from .fix import plan_fixes, preview
    from .fix import write as write_files

    options = _check_options(paper, config_path, bibs, True, None, (), store_path, mailto, cache_dir)
    report = check_paper(paper, options)
    plan = plan_fixes(report, list(keys), add_doi=add_doi)
    for message in plan.skipped:
        click.echo(click.style("skip ", fg="yellow") + message, err=True)
    if not plan.fixes:
        click.echo("Nothing to fix.")
        return
    diff, contents = preview(plan)
    for item in plan.fixes:
        click.echo(click.style(item.key, bold=True) + f": {item.reason}")
    click.echo()
    click.echo(diff, nl=False)
    if write:
        written = write_files(contents)
        click.echo(click.style(f"\nUpdated {len(plan.fixes)} entr{'y' if len(plan.fixes) == 1 else 'ies'} in {', '.join(Path(p).name for p in written)}.", fg="green"))
    else:
        click.echo(click.style("\nDry run. Re-run with --write to apply these changes.", dim=True))


@cli.command()
@click.option("--root", default=".", show_default=True, type=click.Path(exists=True, file_okay=False), help="Directory the agent may read and write in.")
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True, help="Store path, relative to --root.")
@click.option("--transport", type=click.Choice(["stdio", "sse", "streamable-http"]), default="stdio", show_default=True)
@click.option("--online/--offline", default=False, show_default=True, help="Allow tools to query Crossref, DataCite, OpenAlex, and arXiv.")
@click.option("--mailto", envvar="LITKG_MAILTO", default=None)
def mcp(root: str, store_path: str, transport: str, online: bool, mailto: str | None) -> None:
    """Run the MCP server so AI agents can check and fix citations."""
    from .mcp_server import run

    try:
        run(transport=transport, root=root, store_path=store_path, online=online, mailto=mailto)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc



@cli.command("papercite-sync")
@click.argument("paper", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
@click.option("--output", "output_path", default=".litkg_paper.json", show_default=True)
def papercite_sync_cmd(paper: Path, store_path: str, output_path: str) -> None:
    """Store-based citation sync (prefer `litkg check`)."""
    from .papercite import dump, sync

    result = sync(_store(store_path), paper)
    click.echo(dump(result, output_path))
    click.echo(f"Wrote {output_path}")


@cli.command("papercite-gate")
@click.argument("paper", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
@click.option("--allow-partial/--no-allow-partial", default=False, show_default=True)
@click.option("--allow-empty/--no-allow-empty", default=False, show_default=True, help="Pass when the paper has no citations.")
def papercite_gate_cmd(paper: Path, store_path: str, allow_partial: bool, allow_empty: bool) -> None:
    """Store-based citation gate (prefer `litkg check`)."""
    from .papercite import gate_result, sync

    result = sync(_store(store_path), paper)
    ok, message = gate_result(result, allow_partial=allow_partial, allow_empty=allow_empty)
    if not ok:
        raise click.ClickException(message)
    click.echo(message)


@cli.command("papercite-export")
@click.argument("paper", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--store", "store_path", default=".litkg_store.ttl", show_default=True)
@click.option("--output", "output_dir", default="paper-bundle", show_default=True)
def papercite_export_cmd(paper: Path, store_path: str, output_dir: str) -> None:
    """Store-based citation gate plus export bundle."""
    from .papercite import export, gate_result, sync

    store = _store(store_path)
    result = sync(store, paper)
    ok, message = gate_result(result)
    click.echo(message)
    manifest = export(store, paper, output_dir)
    click.echo(_dump(manifest))


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        # Titles can contain any character; never crash on a narrow console encoding.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    cli()
