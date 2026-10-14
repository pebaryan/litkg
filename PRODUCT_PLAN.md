# LitKG Product Plan

## 1. Positioning

**LitKG is a citation-integrity checker for papers written with AI assistance.**
It verifies that every `\cite` / `[@key]` in a manuscript resolves to a real, consistent
reference, runs locally, plugs into CI, and exposes the same checks to agents over MCP.

The RDF/SPARQL literature graph is the engine and a secondary feature, not the headline.
Researchers do not buy SPARQL; they buy "my paper will not ship with a hallucinated reference."

### Why this wedge
- LLM-drafted papers routinely contain fabricated or mismatched references; reviewers and
  journals now look for them. The failure is visible, embarrassing, and checkable.
- General literature management is crowded (Zotero, Semantic Scholar, Connected Papers, Elicit).
  A CI gate for references is not.
- A gate can be evaluated objectively; see `benchmarks/fabrication.py`.

### Users
1. Researchers and students writing LaTeX/Markdown papers with AI help (free).
2. Labs that want a pre-submission check in CI (free; team features later).
3. Later: journals, conferences, and institutions screening submissions in bulk (paid).

## 2. Status (v0.2.0, 2026-10)

### Shipped
- `litkg check`: natbib/biblatex/Pandoc citations with file:line:column, `\input`/`\include`
  following, bibliography discovery, offline checks (undefined, conflict, malformed DOI, missing
  fields, duplicate works), `.litkg.json` config, ignore lists, `--strict`.
- `--online` verification: doi.org (Crossref + DataCite), arXiv, Crossref and OpenAlex title search;
  title/author/year comparison with suggested corrections; disk cache; per-registry rate limits
  with adaptive backoff on HTTP 429.
- Output: text, JSON, SARIF, JUnit, GitHub annotations, Markdown step summary.
- `litkg fix`: minimal in-place BibTeX edits from verified records, as a dry-run diff by default.
- GitHub Action, pre-commit hook, example workflow, CI on Linux/Windows/macOS.
- MCP server (`litkg mcp`) with `check_paper`, `suggest_reference`, `fix_references`, and the library
  tools, confined to a workspace root, offline unless started with `--online`.
- Web UI citation review queue (`litkg serve --paper`).
- Library graph: incremental indexing, whole-word title matching, DOI-aware library evidence.
- Packaging: `pyproject.toml`, `litkg` entry point, optional extras.
- Benchmark: 40 real Crossref journal articles × 6 cases. No false failures on real references;
  every nonexistent DOI, swapped DOI, and invented-author case detected on a run without rate
  limiting; invented works flagged as warnings.

### Known gaps
- The benchmark covers journal articles only. Preprints, conference papers without DOIs, books,
  and theses still need measured corpora.
- CSL-JSON bibliographies are checked but `fix` only edits BibTeX.
- PDF metadata extraction still trusts embedded fields; the year can fall back to the file creation date.
- Paper identity in the graph is the absolute file path; moving a library changes URIs.
- No signed releases or PyPI package yet; the Action is referenced by tag (`v0.2.0` must be pushed).
- No LICENSE file: choose one before publishing.

## 3. Next

### v0.3: breadth and trust (4 weeks)
- Benchmark corpora for arXiv preprints (arXiv API sample), ACL/NeurIPS proceedings (OpenAlex),
  and books (Crossref `type:book`); publish per-type rates in CI.
- DBLP as an additional source for computer science venues.
- Detect retracted works (Crossref `update-to` / Retraction Watch data) as a warning.
- `fix` for CSL-JSON; `fix --interactive` to accept or reject each change.
- Publish to PyPI; tag `v0.2.0`; sign releases.

### v0.4: agent loop (3 weeks)
- Sidecar decisions file so accepted exceptions and fixes are not re-flagged.
- MCP prompt templates for the check → suggest → fix loop; an end-to-end agent evaluation
  (paper with 5 fabricated references reaches a passing gate unaided).
- Language-server mode for editor squiggles on `\cite` keys (VS Code / Overleaf export).

### v0.5: library graph
- Identity by DOI / arXiv ID / content hash; GROBID option for PDF headers and references.
- Zotero import via Better BibTeX; pyoxigraph store for libraries over a few thousand papers.

## 4. Deferred
Desktop installers, air-gapped/government positioning, team licensing, Obsidian/Notion
integrations, PDF report styling. Revisit after 10 active users run the gate on real submissions.

## 5. Business model
- Free, open-source CLI, MCP server, and GitHub Action.
- Paid tier only after the benchmark earns trust: institutional and editorial batch screening with
  audit reports. That buyer has a budget and a mandate; individual students do not.

## 6. Metrics
- Benchmark detection and false-failure rates per reference type (primary quality metric).
- Repositories running the Action weekly.
- Fraction of flagged issues resolved with `fix` (agent-loop usefulness).
- False-positive reports filed by users.

## 7. Risks
| Risk | Mitigation |
|---|---|
| False positives erode trust in a gate | Benchmark in CI; invented works are warnings, not errors; ignore list with reasons |
| Registry rate limits or outages | Disk cache, shared Crossref budget, adaptive backoff; lookup failures are warnings |
| Reference managers add similar checks | Stay CI- and agent-native, where reference managers do not operate |
| Heterogeneous PDFs | Verification starts from `.bib` files; PDFs are optional evidence |
