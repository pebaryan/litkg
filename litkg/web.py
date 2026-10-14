
from __future__ import annotations

import html

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from .queries import list_bibliographies, list_papers, list_reading_lists, search
from .store import LitStore

CSS = """
<style>
:root{
  --bg:#0b1020; --card:#141b2d; --muted:#98a2b3; --text:#ecf0f7;
  --accent:#7c8cf8; --accent2:#6dd3ff; --border:#24304f; --ok:#4ade80;
}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:radial-gradient(circle at 20% 0%,#1a2440,#0b1020 40%);color:var(--text);min-height:100vh}
a{color:var(--accent2);text-decoration:none}
a:hover{text-decoration:underline}
nav{padding:1rem 2rem;border-bottom:1px solid var(--border);backdrop-filter:blur(8px);position:sticky;top:0;background:rgba(11,16,32,.8)}
nav .wrap{max-width:1200px;margin:0 auto;display:flex;gap:1.5rem;align-items:center}
nav .brand{font-weight:700;letter-spacing:.5px}
nav .links{display:flex;gap:1rem;flex-wrap:wrap}
.hero{padding:4rem 2rem 2rem;max-width:1200px;margin:0 auto}
.hero h1{font-size:2.6rem;margin:0 0 1rem;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p{color:var(--muted);max-width:720px;font-size:1.1rem;line-height:1.6}
.container{max-width:1200px;margin:0 auto;padding:0 2rem 3rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin:2rem 0}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:1.4rem 1.2rem;box-shadow:0 8px 24px rgba(0,0,0,.25)}
.card h3{margin:.2rem 0 .6rem;font-size:.85rem;text-transform:uppercase;color:var(--muted);letter-spacing:.08em}
.card .num{font-size:2rem;font-weight:700}
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:16px;overflow:auto;box-shadow:0 8px 24px rgba(0,0,0,.25)}
table{width:100%;border-collapse:collapse}
th,td{padding:.8rem 1rem;text-align:left;border-bottom:1px solid var(--border);vertical-align:top}
th{background:rgba(124,140,248,.08);color:var(--muted);font-size:.75rem;text-transform:uppercase;letter-spacing:.08em}
tr:hover td{background:rgba(109,211,255,.04)}
.badge{display:inline-block;padding:.2rem .6rem;border-radius:999px;background:rgba(74,222,128,.15);color:var(--ok);font-size:.75rem;font-weight:600}
input,textarea{width:100%;padding:.75rem 1rem;border-radius:10px;border:1px solid var(--border);background:#0f162a;color:var(--text);font-family:inherit}
button{padding:.7rem 1.2rem;border-radius:10px;border:none;background:linear-gradient(90deg,var(--accent),var(--accent2));color:#0b1020;font-weight:700;cursor:pointer}
.chips{display:flex;flex-wrap:wrap;gap:.4rem}
.chip{background:rgba(124,140,248,.12);color:var(--accent2);padding:.15rem .5rem;border-radius:999px;font-size:.75rem}
footer{padding:2rem;text-align:center;color:var(--muted);font-size:.85rem}
</style>
"""


def create_app(store_path: str | None = None) -> FastAPI:
    app = FastAPI(title="LitKG Web UI")
    store = LitStore(store_path)

    def page(title: str, body: str, nav: bool = True) -> str:
        nav_html = (
            "<nav><div class='wrap'><span class='brand'>LitKG</span>"
            "<div class='links'><a href='/'>Dashboard</a><a href='/papers'>Papers</a>"
            "<a href='/bibliographies'>Bibliographies</a><a href='/reading-lists'>Reading lists</a>"
            "<a href='/search'>Search</a><a href='/query'>SPARQL</a></div></div></nav>"
        ) if nav else ""
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>{html.escape(title)} · LitKG</title>"
            f"{CSS}</head><body>{nav_html}<main>{body}</main>"
            "<footer>LitKG · local-first literature knowledge graph</footer></body></html>"
        )

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        stats = store.stats()
        body = (
            "<section class='hero'><h1>Literature, as a graph.</h1>"
            "<p>Index PDFs, resolve citations, and explore your research library in one offline workspace.</p></section>"
            "<div class='container'><div class='grid'>"
            + "".join(
                f"<div class='card'><h3>{html.escape(str(k).replace('_',' '))}</h3><div class='num'>{html.escape(str(v))}</div></div>"
                for k, v in stats.items()
            )
            + "</div><div class='card'><h3>Quick actions</h3>"
            "<p><a href='/papers'>Browse papers</a> · <a href='/search'>Search citations</a> · <a href='/query'>Run SPARQL</a></p></div></div>"
        )
        return page("Dashboard", body)

    @app.get("/papers", response_class=HTMLResponse)
    def papers(q: str = Query(default="")) -> str:
        rows = list_papers(store)
        if q:
            needle = q.lower()
            rows = [r for r in rows if needle in str(r.get("title", "")).lower() or needle in ",".join(r.get("authors") or []).lower()]
        trs = []
        for row in rows:
            authors = row.get("authors") or []
            chips = "".join(f"<span class='chip'>{html.escape(str(a))}</span>" for a in authors)
            trs.append(
                "<tr><td>{title}</td><td><div class='chips'>{chips}</div></td><td>{year}</td><td>{pages}</td></tr>".format(
                    title=html.escape(str(row.get("title", ""))),
                    chips=chips,
                    year=html.escape(str(row.get("year", ""))),
                    pages=html.escape(str(row.get("pages", ""))),
                )
            )
        body = (
            "<div class='container'><form method='get' action='/papers' style='margin-bottom:1rem;display:flex;gap:.5rem'>"
            f"<input name='q' placeholder='Filter papers...' value='{html.escape(q)}'/><button>Filter</button></form>"
            "<div class='table-wrap'><table><tr><th>Title</th><th>Authors</th><th>Year</th><th>Pages</th></tr>"
            + "".join(trs)
            + "</table></div></div>"
        )
        return page("Papers", body)

    @app.get("/bibliographies", response_class=HTMLResponse)
    def bibliographies() -> str:
        rows = list_bibliographies(store)
        trs = [
            "<tr><td>{name}</td><td>{fmt}</td><td>{n}</td></tr>".format(
                name=html.escape(str(row.get("name", ""))),
                fmt=html.escape(str(row.get("format", ""))),
                n=html.escape(str(row.get("entry_count", 0))),
            )
            for row in rows
        ]
        body = (
            "<div class='container'><div class='table-wrap'><table><tr><th>Name</th><th>Format</th><th>Entries</th></tr>"
            + "".join(trs)
            + "</table></div></div>"
        )
        return page("Bibliographies", body)

    @app.get("/reading-lists", response_class=HTMLResponse)
    def reading_lists() -> str:
        rows = list_reading_lists(store)
        trs = [
            "<tr><td>{name}</td><td>{n}</td></tr>".format(
                name=html.escape(str(row.get("name", ""))),
                n=html.escape(str(row.get("entry_count", 0))),
            )
            for row in rows
        ]
        body = (
            "<div class='container'><div class='table-wrap'><table><tr><th>Name</th><th>Entries</th></tr>"
            + "".join(trs)
            + "</table></div></div>"
        )
        return page("Reading Lists", body)

    @app.get("/search", response_class=HTMLResponse)
    def search_page(q: str = Query(default="")) -> str:
        rows = search(store, q) if q else []
        cards = "".join(
            "<div class='card' style='margin-bottom:1rem'><div style='font-weight:600'>{t}</div>"
            "<div style='color:var(--muted);font-size:.9rem'>{r}</div></div>".format(
                t=html.escape(str(row.get("title", row))),
                r=html.escape(str(row)),
            )
            for row in rows
        )
        body = (
            "<div class='container'><form method='get' action='/search' style='margin-bottom:1rem;display:flex;gap:.5rem'>"
            f"<input name='q' placeholder='Search papers, refs, authors...' value='{html.escape(q)}'/><button>Search</button></form>"
            + (cards if rows else "<p style='color:var(--muted)'>No results or enter a query.</p>")
            + "</div>"
        )
        return page("Search", body)

    @app.get("/query", response_class=HTMLResponse)
    def query_page(q: str = Query(default="")) -> str:
        rows = []
        error = ""
        if q.strip():
            try:
                rows = store.query(q)
            except Exception as exc:
                error = str(exc)
        table = ""
        if rows:
            cols = list(rows[0].keys())
            head = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
            trs = "".join(
                "<tr>" + "".join(f"<td>{html.escape(str(row.get(c, '')))}</td>" for c in cols) + "</tr>"
                for row in rows
            )
            table = f"<div class='table-wrap'><table><tr>{head}</tr>{trs}</table></div>"
        body = (
            "<div class='container'><form method='get' action='/query'>"
            f"<textarea name='q' rows='6' placeholder='SPARQL query...'>{html.escape(q)}</textarea>"
            "<div style='margin-top:.5rem'><button>Run</button></div></form>"
            + (f"<p style='color:#ff6b6b'>{html.escape(error)}</p>" if error else "")
            + table
            + "</div>"
        )
        return page("SPARQL", body)

    return app
