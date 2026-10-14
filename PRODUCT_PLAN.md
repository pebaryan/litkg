# LitKG Product Plan

This replaces `PITCH_PLAN.md`, `TECHNICAL_DESIGN.md`, `AGENTIC_PAPER_WORKFLOW.md`, and
`UI_UX_DESIGN_PLAN.md`. Those documents described features that were never built; this one
separates what exists from what is planned.

## 1. Positioning

**LitKG is a citation-integrity checker for papers written with AI assistance.**
It verifies that every `\cite` / `[@key]` in a manuscript resolves to a real, consistent
reference, runs locally, plugs into CI, and exposes the same checks to agents over MCP.

The RDF/SPARQL literature graph is the engine, not the headline. Researchers do not buy SPARQL;
they buy "my paper will not ship with a hallucinated reference."

### Why this wedge
- LLM-drafted papers routinely contain fabricated or mismatched references; reviewers and
  journals now look for them. The failure is visible, embarrassing, and binary-checkable.
- General literature management is crowded (Zotero, Semantic Scholar, Connected Papers, Elicit).
  A CI gate for references is not.
- A gate is easy to evaluate: precision/recall on a labeled benchmark, not taste.

### Primary users
1. Researchers and students writing LaTeX/Markdown papers with AI help (individual, free).
2. Labs that want a pre-submission check in CI (team).
3. Later: journals, conferences, and institutions batch-screening submissions (paid).

## 2. Current state (as of 2026-10)

What works:
- Index PDFs, BibTeX, CSL-JSON, and reading lists into an rdflib Turtle store.
- Citation edges between indexed papers (DOI / title matching).
- Annotated bibliography statuses (resolved, partial, unresolved, duplicate) with HTML/PDF export.
- Mermaid/DOT graph export, export bundle with manifest.
- `papercite-sync`, `papercite-gate`, `papercite-export` CLI commands and matching MCP tools.
- Cite-key parsing for natbib, biblatex (including multicite), `\nocite`, and Pandoc `[@key]`,
  ignoring LaTeX comments and Markdown code.
- Gate fails on: no citations found, unresolved keys, duplicate entries, keys defined
  differently across bibliographies, and (unless allowed) partial entries.
- Minimal read-only web UI (`serve`).

Known gaps:
- No online verification: a well-formed but fabricated BibTeX entry passes the gate.
- PDF metadata is taken from embedded fields (often junk); year can fall back to file creation date.
- Substring title matching can create false citation edges for short, generic titles.
- Paper identity is the absolute file path: moving the library changes every URI.
- Every `index` run rebuilds the whole store; no incremental indexing.
- MCP `read` and `index_library` accept arbitrary paths.
- No `pyproject.toml`, no `litkg` console script, all optional dependencies are mandatory, no CI.

## 3. Roadmap

### Phase 0 — Hardening (2 weeks)
- [x] Robust cite-key parser (natbib, biblatex, Pandoc, comments).
- [x] Gate fails on zero citations and on conflicting key definitions.
- [ ] `pyproject.toml` with a `litkg` entry point; extras `[mcp]`, `[web]`, `[pdf]`.
- [ ] CI (ruff + pytest on Linux/Windows/macOS, Python 3.10–3.13).
- [ ] Restrict MCP file access to a configured project root.
- [ ] README rewritten around the paper-check workflow.

**Exit:** a corpus of 20 real arXiv `.tex`/`.bib` sources parses with no missed keys.

### Phase 1 — Verification core (4 weeks)
- Opt-in `--online` lookups against Crossref, OpenAlex, and arXiv, cached on disk; offline remains the default.
- Per-entry checks: DOI exists, DOI metadata agrees with title/authors/year, arXiv ID exists,
  title found when DOI is absent.
- Status model: `verified`, `mismatch`, `not-found`, `duplicate`, `conflict`, `unverified-offline`,
  each with a score and human-readable reasons.
- Benchmark: 50 real bibliographies with injected fabricated and corrupted entries.
  Publish precision/recall in the README and track it in CI.

**Exit:** ≥ 95% recall on fabricated entries at ≤ 2% false-positive rate on real ones.

### Phase 2 — CI and agent loop (3 weeks)
- GitHub Action and pre-commit hook; SARIF and JUnit output so issues appear inline on PRs.
- MCP tools: `list_issues`, `suggest_candidates` (ranked verified matches),
  `apply_fix` (writes a corrected `.bib` entry), all scoped to the project root.
- Sidecar `.litkg_paper.json` records decisions so accepted fixes are not re-flagged.

**Exit:** an agent takes a paper with 5 fabricated references to a passing gate unaided.

### Phase 3 — Library graph (later)
- Identity by DOI / arXiv ID / content hash instead of file path; incremental indexing.
- Optional GROBID extraction for PDF headers and references; drop file-date year fallback.
- Confidence-scored matching to replace substring title matching.
- Zotero import via Better BibTeX export.
- Evaluate pyoxigraph as the store once libraries exceed a few thousand papers.

**Exit:** 5,000 PDFs reindex incrementally in minutes; matching precision measured.

### Phase 4 — UI (last)
One screen: the review queue. Issue → evidence (local paper, online record, diff) → accept/reject fix.
The current dashboard/table pages stay as debugging views.

## 4. Explicitly deferred
Desktop installers and signed binaries, air-gapped/government positioning, team licensing,
Obsidian/Notion integrations, PDF report styling. Revisit after 10 active users run the gate on
real submissions.

## 5. Business model
- Free, open-source CLI, MCP server, and GitHub Action.
- Paid tier only after the benchmark earns trust: institutional / editorial batch screening
  with audit reports. This buyer has budget and a mandate; individual students do not.

## 6. Metrics
- Benchmark precision/recall of fabricated-reference detection (primary quality metric).
- Weekly active repositories running the gate.
- Fraction of flagged issues resolved via `apply_fix` (agent loop usefulness).
- False-positive reports filed by users.

## 7. Risks
| Risk | Mitigation |
|---|---|
| False positives erode trust in a gate | Benchmark in CI; `mismatch` vs `not-found` distinction; per-entry allowlist in sidecar |
| Crossref/OpenAlex rate limits or outages | Local cache, polite pool headers, `unverified-offline` status never fails by default |
| Reference managers add similar checks | Stay CI/agent-native; that is not where Zotero lives |
| Heterogeneous PDFs | Verification works from `.bib` files first; PDF extraction is evidence, not the source of truth |
