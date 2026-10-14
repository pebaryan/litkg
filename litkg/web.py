from __future__ import annotations

import html
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from .queries import (
    list_bibliographies,
    list_papers,
    list_reading_lists,
    paper_details,
    paper_references,
    papers_citing,
    search,
)
from .store import LitStore

CSS = """
<style>
:root{
  --bg:#f7f8fb; --card:#ffffff; --muted:#5b6474; --text:#151a24; --border:#dde2ec;
  --accent:#3b4fd8; --chip:#eef1fd; --head:#f1f3f9;
  --ok:#137a3a; --ok-bg:#e3f5ea; --warn:#8a5a00; --warn-bg:#fdf1d6; --bad:#b4232a; --bad-bg:#fbe4e5;
  --note:#3d5a80; --note-bg:#e6eef8;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#0e1320; --card:#161d2e; --muted:#9aa4b6; --text:#e8ecf4; --border:#27314a;
    --accent:#8c9cff; --chip:#1f2942; --head:#1a2236;
    --ok:#6ee59a; --ok-bg:#163526; --warn:#f3c66b; --warn-bg:#3a2f14; --bad:#ff8a8f; --bad-bg:#3d1c20;
    --note:#9cc0ff; --note-bg:#1b2a44;
  }
}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text)}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
a:focus-visible,button:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
nav{border-bottom:1px solid var(--border);background:var(--card)}
nav .wrap{max-width:1180px;margin:0 auto;padding:.8rem 1rem;display:flex;gap:1.4rem;align-items:center;flex-wrap:wrap}
nav .brand{font-weight:700}
nav .links{display:flex;gap:1rem;flex-wrap:wrap}
nav a[aria-current=page]{font-weight:600;text-decoration:underline}
main{max-width:1180px;margin:0 auto;padding:1.5rem 1rem 3rem}
h1{font-size:1.5rem;margin:0 0 .25rem} .sub{color:var(--muted);margin:0 0 1.25rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.75rem;margin:1rem 0 1.5rem}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:1rem}
.card h2{margin:0 0 .3rem;font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600}
.num{font-size:1.7rem;font-weight:700}
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:10px;overflow-x:auto}
table{width:100%;border-collapse:collapse}
th,td{padding:.6rem .8rem;text-align:left;border-bottom:1px solid var(--border);vertical-align:top}
th{background:var(--head);color:var(--muted);font-size:.75rem;text-transform:uppercase;letter-spacing:.06em}
tr:last-child td{border-bottom:none}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.88em}
form.bar{display:flex;gap:.5rem;margin-bottom:1rem;flex-wrap:wrap}
input,textarea{flex:1;min-width:12rem;padding:.6rem .8rem;border-radius:8px;border:1px solid var(--border);background:var(--card);color:var(--text);font:inherit}
textarea{width:100%;font-family:ui-monospace,Menlo,Consolas,monospace}
button,.button{padding:.6rem 1rem;border-radius:8px;border:1px solid var(--accent);background:var(--accent);color:#fff;font-weight:600;cursor:pointer;display:inline-block}
.button.secondary{background:transparent;color:var(--accent)}
.chips{display:flex;flex-wrap:wrap;gap:.3rem}
.chip{background:var(--chip);padding:.05rem .5rem;border-radius:999px;font-size:.8rem}
.status{display:inline-block;padding:.1rem .55rem;border-radius:999px;font-size:.78rem;font-weight:600;white-space:nowrap}
.status.ok{background:var(--ok-bg);color:var(--ok)} .status.warning{background:var(--warn-bg);color:var(--warn)}
.status.error{background:var(--bad-bg);color:var(--bad)} .status.note{background:var(--note-bg);color:var(--note)}
.issue{margin:.15rem 0} .issue b{font-weight:600}
.suggest{margin-top:.35rem;color:var(--muted)}
.empty{padding:2rem;text-align:center;color:var(--muted)}
.error-text{color:var(--bad)}
footer{max-width:1180px;margin:0 auto;padding:1rem;color:var(--muted);font-size:.85rem}
</style>
"""

STAT_LABELS = {
    "papers": "Papers",
    "authors": "Authors",
    "venues": "Venues",
    "bibliographies": "Bibliographies",
    "bibliography_entries": "Bibliography entries",
    "reading_lists": "Reading lists",
    "reading_list_entries": "Reading-list items",
    "reference_entries": "Extracted references",
    "citation_edges": "Citation links",
    "triples": "RDF triples",
}

SEVERITY_WORDS = {"error": "Error", "warning": "Warning", "note": "Note", None: "OK"}


def _e(value) -> str:
    return html.escape("" if value is None else str(value))


def _status_chip(severity: str | None, label: str) -> str:
    css = severity if severity in {"error", "warning", "note"} else "ok"
    return f"<span class='status {css}'>{_e(SEVERITY_WORDS.get(severity, ''))}: {_e(label)}</span>"


def create_app(store_path: str | None = None, paper: str | None = None) -> FastAPI:
    app = FastAPI(title="LitKG")
    state: dict = {"store": None, "mtime": None}
    resolved_store = LitStore._resolve_path(store_path)

    def store() -> LitStore:
        """Reload the store whenever the file on disk changes (e.g. after `litkg index`)."""
        mtime = resolved_store.stat().st_mtime if resolved_store and resolved_store.exists() else None
        if state["store"] is None or mtime != state["mtime"]:
            state["store"] = LitStore(store_path)
            state["mtime"] = mtime
        return state["store"]

    def page(title: str, body: str, current: str) -> str:
        links = [("/", "Dashboard"), ("/papers", "Papers"), ("/bibliographies", "Bibliographies"), ("/reading-lists", "Reading lists"), ("/search", "Search"), ("/query", "SPARQL")]
        if paper:
            links.insert(1, ("/review", "Citation review"))
        nav = "".join(
            f"<a href='{href}'{' aria-current=page' if href == current else ''}>{label}</a>" for href, label in links
        )
        return (
            "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{_e(title)} · LitKG</title>{CSS}</head><body>"
            f"<nav aria-label='Main'><div class='wrap'><span class='brand'>LitKG</span><div class='links'>{nav}</div></div></nav>"
            f"<main>{body}</main><footer>LitKG runs locally. Nothing leaves this machine unless you run an online check.</footer>"
            "</body></html>"
        )

    def table(headers: list[str], rows: list[str], empty: str) -> str:
        if not rows:
            return f"<div class='table-wrap'><div class='empty'>{empty}</div></div>"
        head = "".join(f"<th scope='col'>{_e(header)}</th>" for header in headers)
        return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"

    def paper_link(title) -> str:
        return f"<a href='/paper?title={quote(str(title or ''))}'>{_e(title)}</a>"

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        stats = store().stats()
        cards = "".join(
            f"<div class='card'><h2>{_e(label)}</h2><div class='num'>{_e(stats.get(key, 0))}</div></div>"
            for key, label in STAT_LABELS.items()
        )
        if not stats.get("papers") and not stats.get("bibliographies"):
            start = (
                "<div class='card'><h2>Get started</h2><p>Index a folder of PDFs and .bib files:</p>"
                "<p><code>litkg index ./library</code></p><p>Then check a paper's citations:</p>"
                "<p><code>litkg check paper.tex --online</code></p></div>"
            )
        else:
            start = "<p><a href='/papers'>Browse papers</a> · <a href='/search'>Search</a> · <a href='/query'>Run SPARQL</a></p>"
        review = (
            f"<p><a class='button' href='/review'>Review citations in {_e(Path(paper).name)}</a></p>" if paper else ""
        )
        body = f"<h1>Library</h1><p class='sub'>Store: <code>{_e(resolved_store)}</code></p>{review}<div class='grid'>{cards}</div>{start}"
        return page("Dashboard", body, "/")

    @app.get("/review", response_class=HTMLResponse)
    def review(online: bool = Query(default=False)) -> str:
        if not paper:
            return page("Citation review", "<h1>Citation review</h1><p class='sub'>Start the UI with <code>litkg serve --paper paper.tex</code>.</p>", "/review")
        from .check import STATUS_LABELS, CheckOptions, check_paper, find_config, load_config
        from .formats import describe_record, display_path

        config = load_config(find_config(paper))
        options = CheckOptions(
            bibliographies=config.get("bib", []),
            online=online,
            strict=bool(config.get("strict", False)),
            ignore=config.get("ignore", {}),
            mailto=config.get("mailto"),
            store=str(resolved_store) if resolved_store and resolved_store.exists() else None,
        )
        try:
            report = check_paper(paper, options)
        except (OSError, ValueError) as exc:
            return page("Citation review", f"<h1>Citation review</h1><p class='error-text'>{_e(exc)}</p>", "/review")

        order = {"error": 0, "warning": 1, "note": 2, None: 3}
        rows = []
        for issue in report.issues:
            rows.append(
                f"<tr><td>{_status_chip(issue.severity, issue.code)}</td><td></td><td>{_e(issue.message)}</td>"
                f"<td class='mono'>{_e(display_path(issue.path))}{':' + str(issue.line) if issue.line else ''}</td></tr>"
            )
        for result in sorted(report.results, key=lambda item: order[item.severity]):
            issues = "".join(
                f"<div class='issue'><b>{_e(SEVERITY_WORDS[issue.severity])}:</b> {_e(issue.message)}</div>"
                for issue in result.issues
            ) or f"<div class='issue'>{_e(STATUS_LABELS.get(result.status, result.status))}</div>"
            if result.candidate is not None and result.severity in {"error", "warning"}:
                issues += f"<div class='suggest'>Suggested: {_e(describe_record(result.candidate))}</div>"
            where = result.citations[0] if result.citations else None
            rows.append(
                f"<tr><td>{_status_chip(result.severity, result.status)}</td><td><code>{_e(result.key)}</code></td>"
                f"<td>{issues}</td><td class='mono'>{_e(display_path(where.path)) + ':' + str(where.line) if where else ''}</td></tr>"
            )
        counts = report.counts()
        verdict = "Passed" if report.passed else "Failed"
        toggle = (
            "<a class='button secondary' href='/review'>Re-run offline</a>"
            if online
            else "<a class='button' href='/review?online=true'>Verify online</a>"
        )
        fixable = [result for result in report.results if result.candidate is not None and result.severity in {"error", "warning"}]
        fix_hint = (
            f"<p>Apply the suggested corrections with <code>litkg fix {_e(display_path(paper))} --write</code>.</p>" if fixable else ""
        )
        body = (
            f"<h1>Citation review</h1><p class='sub'><code>{_e(display_path(paper))}</code> · "
            f"{len(report.manuscript.keys)} cited keys · {'online' if online else 'offline'} check</p>"
            f"<div class='grid'><div class='card'><h2>Result</h2><div class='num'>{verdict}</div></div>"
            f"<div class='card'><h2>Errors</h2><div class='num'>{counts['error']}</div></div>"
            f"<div class='card'><h2>Warnings</h2><div class='num'>{counts['warning']}</div></div></div>"
            f"<p>{toggle}</p>{fix_hint}"
            + table(["Status", "Key", "Details", "First cited"], rows, "No citations found.")
        )
        return page("Citation review", body, "/review")

    @app.get("/papers", response_class=HTMLResponse)
    def papers(q: str = Query(default="")) -> str:
        rows = list_papers(store())
        if q:
            needle = q.lower()
            rows = [r for r in rows if needle in str(r.get("title", "")).lower() or needle in ",".join(r.get("authors") or []).lower()]
        trs = [
            f"<tr><td>{paper_link(row.get('title'))}</td><td><div class='chips'>"
            + "".join(f"<span class='chip'>{_e(author)}</span>" for author in row.get("authors") or [])
            + f"</div></td><td>{_e(row.get('year'))}</td><td class='mono'>{_e(row.get('doi'))}</td></tr>"
            for row in rows
        ]
        body = (
            f"<h1>Papers</h1><p class='sub'>{len(rows)} shown</p>"
            f"<form class='bar' method='get' action='/papers' role='search'>"
            f"<input id='q' name='q' aria-label='Filter papers' placeholder='Filter by title or author' value='{_e(q)}'><button>Filter</button></form>"
            + table(["Title", "Authors", "Year", "DOI"], trs, "No papers yet. Run <code>litkg index ./library</code>.")
        )
        return page("Papers", body, "/papers")

    @app.get("/paper", response_class=HTMLResponse)
    def paper_page(title: str = Query(default="")) -> str:
        rows = [row for row in paper_details(store(), title) if str(row.get("title")) == title] if title else []
        if not rows:
            return page("Paper", f"<h1>Paper not found</h1><p class='sub'>{_e(title)}</p>", "/papers")
        first = rows[0]

        def collect(name: str) -> list[str]:
            return list(dict.fromkeys(str(row[name]) for row in rows if row.get(name)))

        references = [row for row in paper_references(store(), title) if str(row.get("title")) == title]
        citing = papers_citing(store(), title)
        ref_rows = [
            f"<tr><td>{paper_link(row['refersToTitle']) if row.get('refersToTitle') else _e(row.get('citationTitle') or row.get('citationText'))}</td>"
            f"<td class='mono'>{_e(row.get('citationDoi'))}</td></tr>"
            for row in references
        ]
        citing_titles = dict.fromkeys(str(row["sourceTitle"]) for row in citing if str(row.get("targetTitle")) == title)
        citing_rows = [f"<tr><td>{paper_link(source)}</td></tr>" for source in citing_titles]
        body = (
            f"<h1>{_e(title)}</h1><p class='sub'>{_e(', '.join(collect('authorName')))}"
            f"{' · ' + _e(first.get('year')) if first.get('year') else ''}{' · ' + _e(first.get('venueName')) if first.get('venueName') else ''}</p>"
            f"<p class='mono'>{_e(first.get('path'))}</p>"
            + (f"<div class='card'><h2>Abstract</h2><p>{_e(first.get('abstract'))}</p></div>" if first.get("abstract") else "")
            + (f"<p><div class='chips'>{''.join(f'<span class=chip>{_e(k)}</span>' for k in collect('keyword'))}</div></p>" if collect("keyword") else "")
            + f"<h2>References ({len(ref_rows)})</h2>"
            + table(["Reference", "DOI"], ref_rows, "No references were extracted from this PDF.")
            + f"<h2>Cited by ({len(citing_rows)})</h2>"
            + table(["Paper"], citing_rows, "No indexed paper cites this one.")
        )
        return page(title, body, "/papers")

    @app.get("/bibliographies", response_class=HTMLResponse)
    def bibliographies() -> str:
        trs = [
            f"<tr><td>{_e(row.get('name'))}</td><td>{_e(row.get('format'))}</td><td>{_e(row.get('entry_count', 0))}</td></tr>"
            for row in list_bibliographies(store())
        ]
        return page("Bibliographies", "<h1>Bibliographies</h1>" + table(["Name", "Format", "Entries"], trs, "No bibliographies indexed."), "/bibliographies")

    @app.get("/reading-lists", response_class=HTMLResponse)
    def reading_lists() -> str:
        trs = [
            f"<tr><td>{_e(row.get('name'))}</td><td>{_e(row.get('entry_count', 0))}</td></tr>"
            for row in list_reading_lists(store())
        ]
        return page("Reading lists", "<h1>Reading lists</h1>" + table(["Name", "Entries"], trs, "No reading lists indexed."), "/reading-lists")

    @app.get("/search", response_class=HTMLResponse)
    def search_page(q: str = Query(default="")) -> str:
        grouped: dict[str, dict] = {}
        for row in search(store(), q) if q.strip() else []:
            item = grouped.setdefault(str(row.get("paper")), {"title": row.get("title"), "year": row.get("year"), "authors": []})
            if row.get("authorName") and row["authorName"] not in item["authors"]:
                item["authors"].append(row["authorName"])
        trs = [
            f"<tr><td>{paper_link(item['title'])}</td><td>{_e(', '.join(item['authors']))}</td><td>{_e(item['year'])}</td></tr>"
            for item in grouped.values()
        ]
        empty = "No matches." if q.strip() else "Search titles, abstracts, and keywords."
        body = (
            "<h1>Search</h1>"
            f"<form class='bar' method='get' action='/search' role='search'><input name='q' aria-label='Search' placeholder='Search titles, abstracts, keywords' value='{_e(q)}'><button>Search</button></form>"
            + table(["Title", "Authors", "Year"], trs, empty)
        )
        return page("Search", body, "/search")

    @app.get("/query", response_class=HTMLResponse)
    def query_page(q: str = Query(default="")) -> str:
        rows: list[dict] = []
        error = ""
        if q.strip():
            try:
                rows = store().query(q)
            except Exception as exc:  # malformed SPARQL is user input; show the parser message
                error = str(exc)
        result = ""
        if rows:
            cols = list(dict.fromkeys(column for row in rows for column in row))
            trs = ["<tr>" + "".join(f"<td>{_e(row.get(c, ''))}</td>" for c in cols) + "</tr>" for row in rows]
            result = table(cols, trs, "")
        elif q.strip() and not error:
            result = table([], [], "The query returned no rows.")
        example = "PREFIX lit: <https://litkg.dev/ontology#>\nSELECT ?title WHERE { ?p a lit:Paper ; lit:title ?title } LIMIT 20"
        body = (
            "<h1>SPARQL</h1><p class='sub'>Read-only queries against the local store.</p>"
            f"<form method='get' action='/query'><textarea name='q' rows='7' aria-label='SPARQL query' placeholder='{_e(example)}'>{_e(q)}</textarea>"
            "<p><button>Run query</button></p></form>"
            + (f"<p class='error-text' role='alert'>{_e(error)}</p>" if error else "")
            + result
        )
        return page("SPARQL", body, "/query")

    return app
