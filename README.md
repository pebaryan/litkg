# LitKG

**Your reading list as a literature map, and the reference backend for checking the paper you write from it.**

LitKG sits at the start of a research workflow. You point it at a folder of PDFs, bibliographies,
and reading lists, and it builds a local RDF knowledge graph of papers, authors, venues, and
citations that you can browse, query with SPARQL, and export. When you write the paper, the same
graph and LitKG's registry verifier answer one question for every reference: is this a real work,
described correctly?

```text
reading list ──► litkg index ──► literature map ──► write the paper ──► qalmsw check
   (.md/.bib/PDFs)   (RDF graph)    (browse, query,                      (the "unit test":
                                     graphs, reports)                     LLM artifacts, figures,
                                                                          grammar, claims, ...)
                                          ▲                                   │
                                          └──── litkg.api: references ◄───────┘
```

[qalmsw](https://github.com/pebaryan/qalmsw) is the frontend for checking a manuscript. It calls
LitKG for its `references` checker, so a reference counts as verified when a registry confirms it
or when it is already a paper in your library. LitKG also works on its own.

## Install

```bash
pip install "litkg @ git+https://github.com/pebaryan/litkg"          # core: index, query, verify
pip install "litkg[all] @ git+https://github.com/pebaryan/litkg"     # + MCP server, web UI, PDF reports
```

Python 3.10 or newer. The core install has three dependencies (click, rdflib, pypdf).

## The literature map

```bash
litkg index ./library                     # PDFs, .bib, CSL-JSON, .md/.txt/.csv reading lists
litkg papers                              # also: search attention, author Vaswani, show "<title>"
litkg query 'PREFIX lit: <https://litkg.dev/ontology#> SELECT ?t WHERE { ?p a lit:Paper ; lit:title ?t }'
litkg citation-graph --fmt mermaid        # or dot; --root "<title>" to focus
litkg annotated-bibliography-html --output report.html   # -pdf needs litkg[pdf]
litkg export --output-dir bundle          # graphs + reports + manifest.json
litkg serve                               # local web UI; --paper main.tex adds a citation review queue
```

Re-indexing reuses unchanged PDFs, so only new or modified files are parsed again (`--no-cache`
forces a full pass). Citation edges between indexed papers come from DOI matches, exact title
matches, and whole-word title matches of four or more words inside reference strings.

Reading lists are parsed forgivingly. A local PDF link is matched to the indexed paper:

```md
# Week 1
- [x] [Attention Is All You Need](papers/attention.pdf) - foundational transformer paper
- [ ] Diffusion Models for Image Generation
```

The ontology lives under `https://litkg.dev/ontology#`: `lit:Paper`, `lit:Author`, `lit:Venue`,
`lit:Bibliography`, `lit:BibliographyEntry`, `lit:ReferenceEntry`, `lit:ReadingList`, and
`lit:ReadingListEntry`, linked by `lit:hasAuthor`, `lit:cites`, `lit:citedBy`,
`lit:hasReference`, `lit:hasEntry`, `lit:partOf`, and `lit:refersTo`.

## Reference verification

LitKG checks bibliography entries against Crossref, DataCite, OpenAlex, and arXiv: an identifier
must exist, and the record it resolves to must have the entry's title, authors, and year. Entries
without an identifier are found by title search. This catches what LLM-assisted writing gets wrong:
invented DOIs, real DOIs pasted onto the wrong paper, real titles with invented authors, and works
nobody wrote.

### From another tool (qalmsw, scripts)

```python
from litkg.api import ReferenceBackend, make_entry

with ReferenceBackend(online=True, store=".litkg_store.ttl", mailto="you@example.org") as backend:
    entries = backend.load_bibliography("refs.bib")        # or [make_entry(key=..., title=..., doi=...)]
    for verdict in backend.verify(entries):
        print(verdict.key, verdict.status, verdict.severity)
        for finding in verdict.findings:
            print("  ", finding.severity, finding.code, finding.message)
        if verdict.candidate:
            print("   suggest", verdict.candidate.title, verdict.candidate.doi)
```

`verify` returns one `ReferenceVerdict` per entry, in order, with `status`, `findings`
(`severity`, `code`, `message`), the registry `record` it was compared against, a `candidate` to
suggest as the correct version, and `library_paper` when the work is in your library. `to_dict()`
gives JSON-ready data. `litkg.api.API_VERSION` changes only on breaking changes.

### From the command line

`litkg check` runs the same verification over a whole manuscript, including the cite-key checks a
manuscript checker also needs. It is handy for a quick look or for scripting; for full
pre-submission QA, use qalmsw.

```bash
litkg check paper.tex                 # offline: every key defined, entries well formed
litkg check paper.tex --online        # verify against Crossref, DataCite, OpenAlex, arXiv
litkg check paper.tex --online --store .litkg_store.ttl   # library papers count as evidence
litkg fix paper.tex                   # show a diff correcting entries from verified records
litkg fix paper.tex --write           # apply it
```

```text
$ litkg check main.tex --online
main.tex — 7 cited keys, 1 bibliography, online

✗ undefined2024         undefined   sections/intro.tex:3:16
    error   no bibliography entry for 'undefined2024'
✗ devlin2019bert        mismatch    main.tex:8:42
    error   listed authors not on the record: Brown, Michael; Lee, Sarah (record: Devlin, Jacob; Chang, Ming-Wei; Lee, Kenton; Toutanova, Kristina)
    suggest "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding" Devlin, Jacob; Chang, Ming-Wei; Lee, Kenton et al. (2019) doi:10.18653/v1/n19-1423
✗ smith2023quantum      not-found   main.tex:9:34
    error   DOI 10.5555/jmlr.2023.99999 does not exist (doi.org returned 404)

3 verified · 1 mismatch · 1 not-found · 1 skipped · 1 undefined  (4 citations without issues hidden; -v shows them)
FAILED  3 errors, 0 warnings, 2 notes
```

`check` exits with status 1 on an error (or a warning, with `--strict`). `--format` sets stdout to
`text`, `json`, `sarif`, `junit`, `github`, or `markdown`, and `--sarif`, `--junit`, `--json`, and
`--markdown` write files alongside.

It reads LaTeX (every natbib and biblatex citation command, including `\cites` and starred or
capitalised forms; `\input`, `\include`, `\subfile`, and `\import` are followed; comments and
verbatim blocks are ignored) and Pandoc Markdown (`.md`, `.qmd`, `.rmd`). Bibliographies are
BibTeX/biblatex (with `@string` macros) or CSL-JSON, found from `\bibliography{}`,
`\addbibresource{}`, a YAML `bibliography:` field, or `--bib`.

### What is checked

| Code | Severity | Meaning |
|---|---|---|
| `undefined` | error | Cited key has no bibliography entry *(check only)* |
| `conflict` | error | Key defined differently in two bibliographies *(check only)* |
| `malformed-doi`, `missing-title` | error | Entry cannot be right as written |
| `doi-not-found`, `arxiv-not-found` | error | The identifier does not exist *(online)* |
| `title-mismatch` | error / warning | The identifier resolves to a different work *(online)* |
| `author-mismatch` | error / warning | Most (error) or some (warning) listed authors are not on the record *(online)* |
| `no-match` | warning | No registry has a work with this title; it may be fabricated *(online)* |
| `author-order`, `year-mismatch` | warning / note | Minor disagreement with the record *(online)* |
| `duplicate-work` | warning | The same work cited under two keys *(check only)* |
| `missing-authors`, `missing-year`, `implausible-year` | warning | Incomplete entry |
| `missing-doi` | note | A DOI was found; `fix --add-doi` adds it |
| `lookup-failed` | warning | A registry could not be reached; the entry is unverified, not wrong |

Statuses: `verified`, `in-library` (matched a paper in your library), `unchecked` (offline),
`unverified`, `mismatch`, `not-found`, `skipped` (`@misc` and web entries without a DOI), and, for
`check`, `undefined`, `conflict`, and `ignored`.

### Configuration

`litkg check` reads a `.litkg.json` next to the paper (or in the working directory):

```json
{
  "online": true,
  "strict": false,
  "mailto": "you@example.org",
  "store": ".litkg_store.ttl",
  "bib": ["extra/refs.bib"],
  "ignore": { "internal-report-2021": "not indexed anywhere; checked by hand" }
}
```

Command-line flags override the file. `mailto` (or `LITKG_MAILTO`) is sent to Crossref and
OpenAlex so requests go to their faster "polite" pool. OpenAlex meters anonymous use with a daily
budget; set `LITKG_OPENALEX_API_KEY` if you check many papers. When OpenAlex is unavailable, LitKG
continues with Crossref alone and says so in any `no-match` warning. Credentials never enter the
response cache.

### Accuracy

[`benchmarks/fabrication.py`](benchmarks/fabrication.py) samples real journal articles from
Crossref, derives fabricated variants from each, and scores verification against the live
registries. On the committed 40-reference corpus (240 cases):

| Case | Expected | Result |
|---|---|---|
| Real entry with DOI | pass | 100% pass |
| Real entry without DOI (found by title search) | pass | 100% pass |
| Nonexistent DOI | fail | 100% fail |
| DOI of a different work | fail | 100% fail |
| Real title, invented authors | fail | 98% fail, 2% warning (rate-limited lookup) |
| Invented title and authors | flag | 100% warning (`no-match`) |

The corpus is all journal articles with DOIs, which is the easy case. Preprints, books, theses, and
conference papers without DOIs are covered by the arXiv and OpenAlex paths but are not yet
measured. Invented works produce a warning rather than an error, because "no registry knows this
title" is also true of some real grey literature. Rerun with `python benchmarks/fabrication.py`, or
`--new-corpus 50` to sample a new corpus.

### Privacy and network use

Offline is the default for the CLI. Online, LitKG sends each entry's DOI, arXiv ID, or title (plus
the first author's surname and the year for title searches) to doi.org, api.crossref.org,
api.openalex.org, and export.arxiv.org. Nothing else leaves your machine. Responses are cached in
`.litkg_cache/`, so later runs only look up new or changed entries.

LitKG obeys the rate and concurrency limits each registry advertises and backs off on HTTP 429.
Crossref's anonymous pool can be as tight as one request per second, so a first online check of a
60-reference paper takes a minute or two. Setting `mailto` moves you to Crossref's faster polite pool.

## Continuous integration

Full manuscript QA in CI belongs to qalmsw. For a references-only gate, LitKG ships a composite
GitHub Action (annotations, job summary, SARIF) and a pre-commit hook:

```yaml
- uses: pebaryan/litkg@v0.2.0
  with: { paper: main.tex, mailto: you@example.org }
```

```yaml
- repo: https://github.com/pebaryan/litkg
  rev: v0.2.0
  hooks:
    - id: litkg-check
      args: [paper/main.tex]
```

See [`examples/github-workflow/citations.yml`](examples/github-workflow/citations.yml) for the full
workflow with the SARIF upload. Action inputs: `paper`, `online` (default `true`), `strict`, `bib`,
`ignore`, `mailto`, `sarif`, `python-version`.

## AI agents (MCP)

```bash
litkg mcp --root . --online          # stdio transport
claude mcp add litkg -- litkg mcp --root /path/to/project --online   # Claude Code
```

Library tools (`index_library`, `list_papers`, `search_papers`, `show`, `cites`, `cited_by`,
`citation_graph`, annotated bibliographies, and more) let an agent work with the literature map. Reference tools (`check_paper`,
`suggest_reference`, `fix_references`, which writes only with `write=True`) let it repair a
bibliography. All paths are confined to `--root`, and network access is off unless the server is
started with `--online`.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check litkg tests benchmarks
```

| Module | Role |
|---|---|
| `parser.py`, `triples.py`, `indexer.py`, `store.py`, `queries.py` | Literature map: parsing, RDF, SPARQL |
| `web.py`, `report.py`, `export.py`, `bundle.py` | UI, reports, graphs, exports |
| `api.py` | Stable reference-backend API for qalmsw and other callers |
| `verify.py` | Registry clients, cache, rate limiting, record comparison |
| `check.py`, `citations.py`, `manuscript.py` | Manuscript-level checks behind `litkg check` |
| `formats.py`, `fix.py` | Report formats; minimal in-place BibTeX edits |
| `mcp_server.py` | Sandboxed MCP tools |

See [PRODUCT_PLAN.md](PRODUCT_PLAN.md) for the roadmap.
