"""MCP server exposing citation checks, fixes, and the literature graph to AI agents.

Every path an agent passes is resolved inside a workspace root; anything outside it is
rejected. Online lookups are disabled unless the server is started with ``--online``.
"""

from __future__ import annotations

import functools
import json
from dataclasses import asdict
from pathlib import Path

from .bundle import export_bundle
from .export import bibliography_graph as export_bibliography_graph
from .export import citation_graph as export_citation_graph
from .export import export_graph_bundle
from .indexer import index_directory
from .parser import ReferenceInfo, read_pdf_text
from .queries import annotated_bibliography as query_annotated_bibliography
from .queries import list_bibliographies as query_list_bibliographies
from .queries import list_papers as query_list_papers
from .queries import list_reading_lists as query_list_reading_lists
from .queries import (
    paper_details,
    paper_references,
    papers_by_author,
    papers_cited_by,
    papers_citing,
    search,
)
from .queries import papers_in_list as query_papers_in_list
from .queries import papers_without_lists as query_papers_without_lists
from .report import annotated_bibliography_html as render_annotated_bibliography_html
from .report import annotated_bibliography_pdf as render_annotated_bibliography_pdf
from .store import LitStore

try:  # pragma: no cover - optional dependency; mcp 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # pragma: no cover
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError
    except ImportError:
        FastMCP = None
        ToolError = RuntimeError


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


class WorkspaceError(ValueError):
    pass


class Workspace:
    """The tools an agent can call, confined to one directory."""

    def __init__(
        self,
        root: str | Path = ".",
        store_path: str = ".litkg_store.ttl",
        online: bool = False,
        mailto: str | None = None,
        cache_dir: str = ".litkg_cache",
    ) -> None:
        self.root = Path(root).resolve()
        self.store_path = self.path(store_path, must_exist=False)
        self.online = online
        self.mailto = mailto
        self.cache_dir = self.path(cache_dir, must_exist=False)
        self._store: LitStore | None = None
        self._store_mtime: float | None = None

    # -- sandbox

    def path(self, value: str | Path, must_exist: bool = True) -> Path:
        candidate = Path(value).expanduser()
        resolved = (candidate if candidate.is_absolute() else self.root / candidate).resolve()
        if resolved != self.root and not resolved.is_relative_to(self.root):
            raise WorkspaceError(f"{value} is outside the workspace {self.root}")
        if must_exist and not resolved.exists():
            raise WorkspaceError(f"{value} does not exist")
        return resolved

    @property
    def store(self) -> LitStore:
        mtime = self.store_path.stat().st_mtime if self.store_path.exists() else None
        if self._store is None or mtime != self._store_mtime:
            self._store = LitStore(str(self.store_path))
            self._store_mtime = mtime
        return self._store

    def _verifier(self):
        from .verify import HttpClient, Verifier

        client = HttpClient(cache_dir=self.cache_dir, mailto=self.mailto)
        return client, Verifier(client, mailto=self.mailto)

    def _require_online(self) -> None:
        if not self.online:
            raise WorkspaceError("online lookups are disabled; start the server with `litkg mcp --online`")

    # -- citation integrity

    def check_paper(
        self,
        paper_path: str,
        online: bool = True,
        bibliographies: list[str] | None = None,
        strict: bool = False,
        ignore: list[str] | None = None,
    ) -> str:
        """Check every citation in a .tex/.md/.qmd paper.

        Finds the paper's bibliographies automatically (\\bibliography, \\addbibresource,
        YAML `bibliography:`), follows \\input/\\include, and reports each cite key with a
        status (verified, in-library, unchecked, unverified, mismatch, not-found, undefined,
        conflict) and issues. With online=True (and the server started with --online), DOIs,
        arXiv IDs, and titles are verified against Crossref, DataCite, OpenAlex, and arXiv;
        mismatched entries include a `candidate` record with the correct metadata.
        """
        from .check import CheckOptions, check_paper, find_config, load_config

        paper = self.path(paper_path)
        config = load_config(find_config(paper))
        options = CheckOptions(
            bibliographies=[*config.get("bib", []), *(str(self.path(item)) for item in bibliographies or [])],
            online=online and self.online,
            strict=strict or bool(config.get("strict", False)),
            ignore={**config.get("ignore", {}), **{key: "" for key in ignore or []}},
            mailto=self.mailto,
            store=str(self.store_path) if self.store_path.exists() else None,
            cache_dir=str(self.cache_dir),
        )
        return _json(check_paper(paper, options).to_dict())

    def suggest_reference(self, title: str, authors: list[str] | None = None, year: int | None = None, limit: int = 5) -> str:
        """Search Crossref and OpenAlex for real works matching a title (and optionally authors/year).

        Returns candidates ranked by title similarity (1.0 = identical), each with title,
        authors, year, DOI, venue, and arXiv ID. Use it to replace an unverified or
        fabricated reference with one that exists. Requires the server to run with --online.
        """
        self._require_online()
        client, verifier = self._verifier()
        try:
            entry = ReferenceInfo(raw_text=title, title=title, authors=authors or [], year=year)
            ranked = verifier.suggest(entry, limit=max(1, min(limit, 10)))
        finally:
            client.save()
        return _json([{"similarity": score, **record.to_dict()} for score, record in ranked])

    def fix_references(self, paper_path: str, keys: list[str] | None = None, add_doi: bool = False, write: bool = False) -> str:
        """Correct a paper's BibTeX entries from verified registry records.

        Runs an online check, then edits only the wrong fields (title, author, year, doi,
        eprint) of entries with errors or warnings. Returns a unified diff; nothing is
        written unless write=True. Requires the server to run with --online.
        """
        self._require_online()
        from .check import CheckOptions, check_paper, find_config, load_config
        from .fix import plan_fixes, preview
        from .fix import write as write_files

        paper = self.path(paper_path)
        config = load_config(find_config(paper))
        options = CheckOptions(
            bibliographies=config.get("bib", []),
            online=True,
            ignore=config.get("ignore", {}),
            mailto=self.mailto,
            cache_dir=str(self.cache_dir),
        )
        plan = plan_fixes(check_paper(paper, options), keys, add_doi=add_doi)
        diff, contents = preview(plan) if plan.fixes else ("", {})
        for path in contents:
            self.path(path)  # never write outside the workspace
        written = write_files(contents) if write else []
        return _json(
            {
                "fixes": [{"key": item.key, "path": item.path, "changes": item.changes, "reason": item.reason} for item in plan.fixes],
                "skipped": plan.skipped,
                "diff": diff,
                "written": written,
            }
        )

    # -- library graph

    def index_library(self, path: str = ".") -> str:
        """Index PDFs, BibTeX/CSL-JSON bibliographies, and reading lists under a directory into the store."""
        stats = index_directory(str(self.path(path)), LitStore(str(self.store_path)))
        self._store = None
        return _json(asdict(stats))

    def papers(self) -> str:
        """List indexed papers with title, authors, year, and DOI."""
        return _json(query_list_papers(self.store))

    def reading_lists(self) -> str:
        """List indexed reading lists."""
        return _json(query_list_reading_lists(self.store))

    def bibliographies(self) -> str:
        """List indexed bibliographies."""
        return _json(query_list_bibliographies(self.store))

    def annotated_bibliography(self, pattern: str = "") -> str:
        """Bibliography entries (optionally for bibliographies matching a name) with resolution status."""
        return _json(query_annotated_bibliography(self.store, pattern))

    def annotated_bibliography_html(self, pattern: str = "", status: list[str] | None = None, sort_by: str = "order", descending: bool = False) -> str:
        """Render the annotated bibliography as HTML."""
        return render_annotated_bibliography_html(self.store, pattern, statuses=status, sort_by=sort_by, descending=descending)

    def annotated_bibliography_pdf(
        self,
        pattern: str = "",
        status: list[str] | None = None,
        sort_by: str = "order",
        descending: bool = False,
        output: str = "annotated-bibliography.pdf",
        library_name: str = "",
    ) -> str:
        """Write the annotated bibliography as a PDF inside the workspace and return its path."""
        target = self.path(output, must_exist=False)
        target.write_bytes(
            render_annotated_bibliography_pdf(
                self.store, pattern, statuses=status, sort_by=sort_by, descending=descending, library_name=library_name or None
            )
        )
        return str(target)

    def author(self, name: str) -> str:
        """Papers by an author (substring match)."""
        return _json(papers_by_author(self.store, name))

    def list_papers(self, list_name: str) -> str:
        """Papers in a reading list."""
        return _json(query_papers_in_list(self.store, list_name))

    def search_papers(self, pattern: str) -> str:
        """Search paper titles, abstracts, and keywords."""
        return _json(search(self.store, pattern))

    def show(self, pattern: str) -> str:
        """Full details for papers whose title matches."""
        return _json(paper_details(self.store, pattern))

    def references(self, pattern: str) -> str:
        """References extracted from papers whose title matches."""
        return _json(paper_references(self.store, pattern))

    def cited_by(self, pattern: str) -> str:
        """Papers that cite papers whose title matches."""
        return _json(papers_citing(self.store, pattern))

    def cites(self, pattern: str) -> str:
        """Papers cited by papers whose title matches."""
        return _json(papers_cited_by(self.store, pattern))

    def orphan_papers(self) -> str:
        """Papers that are not on any reading list."""
        return _json(query_papers_without_lists(self.store))

    def citation_graph(self, root: str = "", depth: int = 2, fmt: str = "mermaid") -> str:
        """Citation graph as Mermaid or DOT."""
        return export_citation_graph(self.store, root_paper=root or None, depth=depth, fmt=fmt)

    def bibliography_graph(self, root: str = "", depth: int = 2, fmt: str = "mermaid") -> str:
        """Bibliography graph as Mermaid or DOT."""
        return export_bibliography_graph(self.store, root_bibliography=root or None, depth=depth, fmt=fmt)

    def graph_export(
        self,
        citation_root: str = "",
        bibliography_root: str = "",
        depth: int = 2,
        fmt: list[str] | None = None,
        output_dir: str = "graphs",
        prefix: str = "graph",
    ) -> str:
        """Write citation and bibliography graphs to a directory inside the workspace."""
        return _json(
            export_graph_bundle(
                self.store,
                output_dir=str(self.path(output_dir, must_exist=False)),
                prefix=prefix,
                citation_root=citation_root or None,
                bibliography_root=bibliography_root or None,
                depth=depth,
                fmts=fmt or ("mermaid", "dot"),
            )
        )

    def export(
        self,
        output_dir: str = "bundle",
        library_name: str = "",
        status: list[str] | None = None,
    ) -> str:
        """Write graphs, annotated bibliography reports, and a manifest to a directory inside the workspace."""
        return _json(
            export_bundle(
                self.store,
                output_dir=str(self.path(output_dir, must_exist=False)),
                statuses=status,
                library_name=library_name or None,
            )
        )

    def read(self, file_path: str, start_page: int = 1, end_page: int = 0) -> str:
        """Extract text from a PDF in the workspace (pages are 1-based; end_page=0 means last)."""
        return read_pdf_text(str(self.path(file_path)), start_page=start_page, end_page=end_page or None)


TOOLS = (
    "check_paper",
    "suggest_reference",
    "fix_references",
    "index_library",
    "papers",
    "reading_lists",
    "bibliographies",
    "annotated_bibliography",
    "annotated_bibliography_html",
    "annotated_bibliography_pdf",
    "author",
    "list_papers",
    "search_papers",
    "show",
    "references",
    "cited_by",
    "cites",
    "orphan_papers",
    "citation_graph",
    "bibliography_graph",
    "graph_export",
    "export",
    "read",
)


def create_server(workspace: Workspace):
    if FastMCP is None:
        raise RuntimeError("the MCP server needs extra packages: pip install 'litkg[mcp]'")
    server = FastMCP(
        "litkg",
        instructions=(
            "Use check_paper to find citations that are undefined, malformed, or do not match a real work. "
            "For each problem, prefer the `candidate` in the report; otherwise call suggest_reference. "
            "Apply corrections with fix_references (diff first, then write=True)."
        ),
    )
    for name in TOOLS:
        server.tool(name=name)(_reporting_errors(getattr(workspace, name)))
    return server


def _reporting_errors(method):
    """Expose expected failures to the agent as readable tool errors instead of a generic message."""

    @functools.wraps(method)
    def tool(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (WorkspaceError, OSError, ValueError, KeyError) as exc:
            raise ToolError(str(exc)) from exc

    return tool


def run(
    transport: str = "stdio",
    root: str = ".",
    store_path: str = ".litkg_store.ttl",
    online: bool = False,
    mailto: str | None = None,
) -> None:
    server = create_server(Workspace(root, store_path, online=online, mailto=mailto))
    server.run(transport=transport)
