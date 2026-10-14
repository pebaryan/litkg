# LitKG

**Catch fabricated, mismatched, and undefined citations before your paper ships.**

LLM-assisted writing produces references that look right and don't exist: invented DOIs,
real titles with the wrong authors, plausible papers nobody wrote. LitKG checks every
`\cite` and `[@key]` in a LaTeX or Markdown manuscript against its bibliography and, if you
ask, against Crossref, DataCite, OpenAlex, and arXiv. It runs locally, works in CI, and
gives AI agents the same checks over MCP.

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

Then `litkg fix main.tex --write` corrects the BERT entry in place, changing only the wrong fields.

## Install

```bash
pip install "litkg @ git+https://github.com/pebaryan/litkg"          # core: check, fix, index
pip install "litkg[all] @ git+https://github.com/pebaryan/litkg"     # + MCP server, web UI, PDF reports
```

Python 3.10 or newer. The core install has three dependencies (click, rdflib, pypdf).

## Usage

```bash
litkg check paper.tex                 # offline: every key defined, entries well formed
litkg check paper.tex --online        # verify against Crossref, DataCite, OpenAlex, arXiv
litkg check paper.tex --online --strict   # fail on warnings too
litkg fix paper.tex                   # show a diff correcting entries from verified records
litkg fix paper.tex --write           # apply it
```

`check` exits with status 1 when it finds an error (or a warning, with `--strict`), so it can
gate a build.

### Inputs

- **LaTeX:** every natbib and biblatex citation command (`\cite`, `\citep[p.~3]{key}`,
  `\parencite`, `\textcite`, `\autocite`, `\cites[a]{x}[b]{y}`, `\nocite`, starred and capitalised
  forms). `\input`, `\include`, `\subfile`, and `\import` are followed, and results are reported in
  document order. Comments, `comment` environments, and verbatim blocks are ignored.
- **Markdown** (`.md`, `.qmd`, `.rmd`): Pandoc citations (`[@key]`, `@key`, `[-@key]`,
  `[see @a, p. 4; @b]`). Code blocks, inline code, and HTML comments are ignored.
- **Bibliographies:** BibTeX/biblatex (`@string` macros and `#` concatenation included) and CSL-JSON.
  They are found from `\bibliography{}`, `\addbibresource{}`, or a YAML `bibliography:` field;
  add more with `--bib`.

### What is checked

| Code | Severity | Meaning |
|---|---|---|
| `undefined` | error | Cited key has no bibliography entry |
| `conflict` | error | Key defined differently in two bibliographies |
| `malformed-doi`, `missing-title` | error | Entry cannot be right as written |
| `doi-not-found`, `arxiv-not-found` | error | The identifier does not exist *(online)* |
| `title-mismatch` | error / warning | The identifier resolves to a different work *(online)* |
| `author-mismatch` | error / warning | Most (error) or some (warning) listed authors are not on the record *(online)* |
| `no-match` | warning | No registry has a work with this title; it may be fabricated *(online)* |
| `author-order`, `year-mismatch` | warning / note | Minor disagreement with the record *(online)* |
| `duplicate-work` | warning | The same work cited under two keys |
| `missing-authors`, `missing-year`, `implausible-year` | warning | Incomplete entry |
| `missing-doi` | note | A DOI was found; `fix --add-doi` adds it |
| `missing-file`, `no-bibliography`, `no-citations` | error | The manuscript itself is broken |

Statuses per key: `verified`, `in-library` (matched a paper in your indexed library),
`unchecked` (offline), `unverified`, `mismatch`, `not-found`, `undefined`, `conflict`,
`skipped` (`@misc` and web entries without a DOI), `ignored`.

### Configuration

Put a `.litkg.json` next to the paper (or in the working directory):

```json
{
  "online": true,
  "strict": false,
  "mailto": "you@example.org",
  "bib": ["extra/refs.bib"],
  "ignore": { "internal-report-2021": "not indexed anywhere; checked by hand" }
}
```

Command-line flags override the file. `mailto` (or `LITKG_MAILTO`) is sent to Crossref and
OpenAlex so requests go to their faster "polite" pool. OpenAlex meters anonymous use with a daily
budget; set `LITKG_OPENALEX_API_KEY` if you check many papers. When OpenAlex is unavailable, LitKG
continues with Crossref alone and says so in any `no-match` warning. Credentials never enter the
response cache.

## Continuous integration

### GitHub Action

```yaml
# .github/workflows/citations.yml
on: [pull_request]
permissions:
  contents: read
  security-events: write   # for the SARIF upload
jobs:
  citations:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pebaryan/litkg@v0.2.0
        with:
          paper: main.tex
          mailto: you@example.org
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with: { sarif_file: litkg.sarif }
```

Problems appear as annotations on the pull request diff and as a table in the job summary.
Registry responses are cached between runs. Inputs: `paper`, `online` (default `true`),
`strict`, `bib`, `ignore`, `mailto`, `sarif`, `python-version`. See
[`examples/github-workflow/citations.yml`](examples/github-workflow/citations.yml).

### Other CI systems

```bash
litkg check paper.tex --online --junit litkg.xml --sarif litkg.sarif --markdown summary.md
```

`--format` sets what goes to stdout: `text`, `json`, `sarif`, `junit`, `github`, or `markdown`.

### pre-commit

```yaml
- repo: https://github.com/pebaryan/litkg
  rev: v0.2.0
  hooks:
    - id: litkg-check
      args: [paper/main.tex]     # offline by default; add --online if you like
```

## AI agents (MCP)

```bash
litkg mcp --root . --online          # stdio transport
claude mcp add litkg -- litkg mcp --root /path/to/paper --online   # Claude Code
```

Tools: `check_paper`, `suggest_reference` (ranked real works for a title), `fix_references`
(returns a diff; writes only with `write=True`), plus the library tools below. All paths are
confined to `--root`, and network access is off unless the server is started with `--online`.
A typical agent loop is check → read `candidate` or call `suggest_reference` → `fix_references`
→ check again.

## Accuracy

[`benchmarks/fabrication.py`](benchmarks/fabrication.py) samples real journal articles from
Crossref, derives fabricated variants from each, and scores `check --online` against the live
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
title" is also true of some real grey literature; use `--strict` to fail on them. Rerun with
`python benchmarks/fabrication.py`, or `--new-corpus 50` to sample a new corpus.

## Privacy and network use

Offline is the default. With `--online`, LitKG sends each entry's DOI, arXiv ID, or title (plus the
first author's surname and the year for title searches) to doi.org, api.crossref.org,
api.openalex.org, and export.arxiv.org. Nothing else leaves your machine. Responses are cached
in `.litkg_cache/`, so later runs only look up new or changed entries.

LitKG obeys the rate and concurrency limits each registry advertises and backs off on HTTP 429.
Crossref's anonymous pool can be as tight as one request per second, so a first online check of a
60-reference paper takes a minute or two. Setting `mailto` moves you to Crossref's faster polite pool.

## Your library as a knowledge graph

LitKG also indexes a folder of PDFs, bibliographies, and reading lists into a local RDF store you
can query with SPARQL. A paper in the library counts as evidence in `check --store`.

```bash
litkg index ./library                     # PDFs, .bib, CSL-JSON, .md/.txt/.csv reading lists
litkg papers                              # also: search attention, author Vaswani, show "<title>"
litkg query 'PREFIX lit: <https://litkg.dev/ontology#> SELECT ?t WHERE { ?p a lit:Paper ; lit:title ?t }'
litkg citation-graph --fmt mermaid        # or dot; --root "<title>" to focus
litkg annotated-bibliography-html --output report.html   # -pdf needs litkg[pdf]
litkg export --output-dir bundle          # graphs + reports + manifest.json
litkg serve --paper main.tex              # local web UI with a citation review queue
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

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check litkg tests
```

| Module | Role |
|---|---|
| `citations.py`, `manuscript.py` | Find cite keys with positions; follow includes; discover bibliographies |
| `check.py` | Offline checks, library evidence, orchestration, the report model |
| `verify.py` | Registry clients, cache, rate limiting, record comparison |
| `formats.py` | Text, JSON, SARIF, JUnit, GitHub, and Markdown output |
| `fix.py` | Minimal in-place BibTeX edits |
| `mcp_server.py` | Sandboxed MCP tools |
| `parser.py`, `triples.py`, `indexer.py`, `store.py`, `queries.py` | Library graph |
| `web.py`, `report.py`, `export.py`, `bundle.py` | UI, reports, and exports |

See [PRODUCT_PLAN.md](PRODUCT_PLAN.md) for the roadmap.
