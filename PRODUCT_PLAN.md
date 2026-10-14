# LitKG Product Plan

## 1. Positioning

**LitKG is the literature map at the start of a research workflow, and the reference backend for
checking the paper written from it.**

| Stage | Tool | Job |
|---|---|---|
| Read | LitKG | Turn reading lists, PDFs, and bibliographies into a queryable knowledge graph |
| Write | (editor, LLM assistant) | Draft the manuscript, citing works from the map |
| Check | [qalmsw](https://github.com/pebaryan/qalmsw) | The "unit test": LLM artifacts, placeholders, figures, citations, grammar, claims |
| Check → references | LitKG via `litkg.api` | Is each reference a real work, described correctly? Is it in the library? |

qalmsw owns the manuscript-checking experience: the CLI, CI gate, reports, and hosted Space.
LitKG owns knowledge about the literature: the library graph and verification against registries.
Neither duplicates the other's frontend. `litkg check` stays as a references-only CLI for scripting
and debugging the backend, not as a competing paper checker.

### Why this split
- Literature management alone is crowded (Zotero, Semantic Scholar, Connected Papers, Elicit).
  A local, queryable graph that also *grounds the paper being written* is not.
- Reference verification is the highest-risk qalmsw check and needs registry clients, caching,
  rate limiting, and a benchmark. That is library knowledge, so it lives with the library.
- Library evidence closes the gap registries leave: an internal report or a preprint in your
  reading list counts as real even when Crossref has never heard of it.

## 2. Status (v0.2.0, 2026-10)

### Shipped
- Library graph: PDFs, BibTeX/CSL-JSON, Markdown/CSV reading lists; incremental indexing;
  whole-word title matching for citation edges; SPARQL; Mermaid/DOT graphs; HTML/PDF reports;
  export bundles; web UI with a citation review queue.
- Reference backend: `litkg.api.ReferenceBackend` (offline checks, library evidence, online
  verification, suggestions) with plain-data verdicts and `API_VERSION = 1`.
- Verification engine: doi.org (Crossref + DataCite), arXiv, Crossref and OpenAlex title search;
  title/author/year comparison with suggested corrections; disk cache; per-registry rate limits with
  adaptive backoff; circuit breaker on exhausted quotas.
- `litkg check` / `litkg fix`: manuscript-level references check (natbib, biblatex, Pandoc) with
  text/JSON/SARIF/JUnit/GitHub/Markdown output, and minimal in-place BibTeX fixes.
- GitHub Action and pre-commit hook for a references-only gate.
- MCP server with library and reference tools, sandboxed to a root, offline unless `--online`.
- Benchmark: 40 real Crossref journal articles × 6 cases; no false failures on real references.

### Known gaps
- qalmsw does not call the backend yet (see 3.1).
- The benchmark covers journal articles only.
- Paper identity in the graph is the absolute file path; moving a library changes URIs.
- PDF metadata extraction trusts embedded fields.
- No LICENSE file, PyPI package, or pushed `v0.2.0` tag.

## 3. Next

### 3.1 qalmsw integration (now)
- qalmsw's `references` checker delegates to `litkg.api` when LitKG is installed
  (`pip install qalmsw[litkg]`) and falls back to its built-in existence check otherwise.
- qalmsw options for the library store and polite-pool email, mapped to `ReferenceBackend`.
- Move SARIF/GitHub annotation output into qalmsw for all checkers (it is on qalmsw's roadmap);
  then retire LitKG's Action in favour of qalmsw's.
- Publish LitKG's fabrication benchmark as part of qalmsw's regression corpus.

### 3.2 Literature map (next 4 weeks)
- Identity by DOI / arXiv ID / content hash instead of file path.
- Enrich indexed papers from registries (the verifier already fetches the records): DOIs, venues,
  author lists, and outgoing references from Crossref/OpenAlex, so the map reaches beyond local PDFs.
- Reading-list workflow: read/unread state, notes, and "papers cited by my list but not in it".
- Index the paper in progress as a node, so its references link into the map and the web UI shows
  which cited works are in the library, unread, or unverified.
- Zotero import via Better BibTeX; GROBID option for PDF headers and references.

### 3.3 Backend breadth
- Benchmark corpora for preprints, proceedings, and books; DBLP as a source for computer science.
- Retraction detection (Crossref `update-to` / Retraction Watch) as a warning.
- pyoxigraph store for libraries beyond a few thousand papers.

## 4. Deferred
Desktop installers, team licensing, Obsidian/Notion integrations, PDF report styling.

## 5. Metrics
- Benchmark detection and false-failure rates per reference type.
- Share of qalmsw reference findings resolved by library evidence rather than registries.
- Libraries indexed and re-indexed weekly (is the map used, or built once?).

## 6. Risks
| Risk | Mitigation |
|---|---|
| False positives erode trust in the qalmsw gate | Benchmark; invented works are warnings; library evidence; ignore lists |
| Registry rate limits or outages | Disk cache, shared Crossref budget, adaptive backoff; lookup failures are warnings |
| API churn breaks qalmsw | `litkg.api` is the only supported surface; `API_VERSION`; plain-data results |
| Heterogeneous PDFs | Verification starts from `.bib` files; PDFs are optional evidence |
