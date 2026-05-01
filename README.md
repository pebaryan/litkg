# LitKG-RDF

**Lightweight RDF/SPARQL knowledge graph for scientific papers and reading lists**

LitKG-RDF is a local-first knowledge graph for a literature library:

- index PDF articles into RDF
- attach authors, venue, year, DOI, keywords, and text excerpts
- extract bibliography references and connect papers with citation edges
- import BibTeX and CSL-JSON bibliographies directly
- parse reading-list files and link list items back to papers
- query the library with SPARQL or simple CLI helpers
- export citation graphs as Mermaid or DOT
- export annotated bibliography reports as HTML
- export annotated bibliography reports as PDF
- review annotated bibliography status for resolved, partial, unresolved, and duplicate entries
- expose the same data through an MCP server for AI tools

This is intentionally similar in shape to a codebase knowledge graph, but the domain is literature instead of source code.

## What it models

- `Paper` documents from `.pdf` files
- `Author` entities
- `Venue` entities
- `Bibliography` documents from `.bib` and CSL-JSON `.json` files
- `BibliographyEntry` items that can resolve to a paper
- `ReadingList` documents from `.md`, `.txt`, `.rst`, or `.csv` files
- `ReadingListEntry` items that can refer to a paper
- citation edges between papers when a DOI or bibliography title matches

## Quick Start

```bash
pip install -r requirements.txt
python -m litkg index ./library --store .litkg_store.ttl
python -m litkg papers --store .litkg_store.ttl
python -m litkg search "attention" --store .litkg_store.ttl
```

## Reading List Format

The parser is intentionally forgiving. It understands lines like:

```md
# Week 1

- [x] [Attention Is All You Need](papers/attention.pdf) - foundational transformer paper
- [ ] Diffusion Models for Image Generation
```

If a list item includes a local PDF link, LitKG will try to match it to the indexed paper automatically.

## Query Examples

```sparql
PREFIX lit: <https://litkg.dev/ontology#>
SELECT ?title ?authorName WHERE {
  ?paper a lit:Paper ;
         lit:title ?title ;
         lit:hasAuthor ?author .
  ?author lit:name ?authorName .
}
ORDER BY LCASE(STR(?title))
```

```sparql
PREFIX lit: <https://litkg.dev/ontology#>
SELECT ?title WHERE {
  ?paper a lit:Paper ;
         lit:title ?title .
  FILTER NOT EXISTS { ?entry lit:refersTo ?paper . }
}
```

## Project Layout

- `litkg/ontology.py` - namespaces and URI helpers
- `litkg/parser.py` - PDF and reading-list extraction
- `litkg/triples.py` - RDF conversion
- `litkg/store.py` - rdflib-backed SPARQL store wrapper
- `litkg/indexer.py` - full-library indexing
- `litkg/queries.py` - common query helpers
- `litkg/export.py` - citation graph export
- `litkg/report.py` - HTML report generation
- `litkg/cli.py` - command line entry point
- `litkg/mcp_server.py` - optional MCP server

### Citation support

LitKG extracts bibliography sections from PDFs and tries to resolve each reference against
the indexed papers using:

- DOI matches
- normalized title matches
- substring matches on bibliography lines
- APA-style reference strings in PDF reference sections

It also imports standalone BibTeX (`.bib`) and CSL-JSON (`.json`) bibliographies as
first-class documents, with entries linked back to matching papers when possible.

When a match is found, the citing paper gets a `lit:cites` edge to the target paper and
the target gets a `lit:citedBy` edge back.

### Citation graph export

```bash
python -m litkg citation-graph --root "A Survey of Generative Models" --fmt mermaid
python -m litkg citation-graph --fmt dot --output citation.dot
```

The export shows the paper, each extracted reference node, and the cited target paper.

### Bibliography graph export

```bash
python -m litkg bibliography-graph --root refs --fmt mermaid
python -m litkg bibliography-graph --fmt dot --output bibliography.dot
```

The export shows bibliography documents, their entries, and any linked target papers.

### Combined graph export

```bash
python -m litkg graph-export --citation-root "A Survey of Generative Models" --bibliography-root refs --output-dir graphs --prefix library
```

This writes:

- `graphs/library-citation.mmd`
- `graphs/library-citation.dot`
- `graphs/library-bibliography.mmd`
- `graphs/library-bibliography.dot`

You can restrict the export to one or more formats with repeated `--fmt` flags.

### Top-level export

```bash
python -m litkg export --output-dir bundle --library-name "My Library"
```

This writes the graph bundle under `bundle/graphs/` and the annotated bibliography bundle
under `bundle/reports/`, plus a top-level `bundle/manifest.json` that lists the generated
files and includes a compact `summary` with paper, bibliography, entry, and citation counts.
The command accepts the same graph, filter, and sort options as the specialized export commands.

### Annotated bibliography

```bash
python -m litkg annotated-bibliography --store .litkg_store.ttl
python -m litkg annotated-bibliography refs --store .litkg_store.ttl
```

Each entry includes a status:

- `resolved` when it links to a paper
- `partial` when it has metadata but no match
- `unresolved` when little or no metadata could be extracted
- `duplicate` when the same bibliography key/title appears more than once

### Annotated bibliography HTML

```bash
python -m litkg annotated-bibliography-html --store .litkg_store.ttl --output annotated-bibliography.html
python -m litkg annotated-bibliography-html refs --status resolved --sort-by duplicate-count --descending
```

The report renders the annotated bibliography as a styled HTML table with summary counts,
status badges, the raw reference text for each entry, and optional filters/sorting by status,
entry, target, order, or duplicate count.

### Annotated bibliography PDF

```bash
python -m litkg annotated-bibliography-pdf --store .litkg_store.ttl
python -m litkg annotated-bibliography-pdf refs --status resolved --sort-by status --library-name "My Library" --output report.pdf
```

The PDF export uses the same filters and sorting, adds a cover page, and prints the library name,
filter settings, and generation timestamp in the footer of each page.

### Combined export

```bash
python -m litkg annotated-bibliography-export refs --output-dir reports --library-name "My Library"
```

This writes both `reports/annotated-bibliography.html` and `reports/annotated-bibliography.pdf`
using the same filter and sort options.
