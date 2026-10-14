# Technical Design — Agentic Paper Workflow on LitKG

## 1. Components
- Parser Adapter (`litkg/papercite/parser.py`): extracts cite keys from LaTeX/BibTeX and Markdown.
- Resolution Engine (`litkg/papercite/resolver.py`): matches cite keys against RDF graph + imported bibliographies.
- Status Store (`litkg/papercite/status.py`): JSON + RDF sidecar for unresolved/partial/resolved/duplicate.
- Suggester (`litkg/papercite/suggest.py`): generates title/author/DOI/URL search plans.
- Importer (`litkg/papercite/importer.py`): adds validated refs from BibTeX/CSL.
- Gate (`litkg/papercite/gate.py`): enforces quality thresholds.
- Exporter (`litkg/papercite/export.py`): writes bibliography/report/graph bundle.
- MCP Bridge (`litkg/mcp_server.py` extension): exposes workflow tools.

## 2. Data Model
### Sidecar JSON (`.litkg_paper.json`)
```json
{
  "paper_id": "string",
  "citation": {
    "cite_keys": ["key1"],
    "status": "resolved|partial|unresolved|duplicate",
    "confidence": 0.0,
    "match_source": "rdf|bibliography|none",
    "target_uri": "optional"
  }
}
```
### RDF extensions
- `lit:Paper` stays unchanged for library.
- Add `lit:PaperDraft` and `lit:hasCitation` links to `BibliographyEntry` or `Paper`.
- Add provenance (`prov:wasDerivedFrom`) for imported refs.

## 3. Resolution Algorithm
1. Normalize cite keys and titles.
2. Exact DOI match → resolved.
3. Normalized title match → resolved if score ≥ 0.92.
4. Partial author/year overlap → partial.
5. None → unresolved.
6. Detect duplicate DOIs/titles → duplicate status.

## 4. CLI Surface
- `litkg papercite init`
- `litkg papercite sync`
- `litkg papercite suggest`
- `litkg papercite fill`
- `litkg papercite gate`
- `litkg papercite export`

## 5. MCP Tools
- `litkg_papercite_sync`
- `litkg_papercite_list_unresolved`
- `litkg_papercite_suggest`
- `litkg_papercite_import_refs`
- `litkg_papercite_gate`

## 6. Error Handling
- Missing store: build or fail with actionable message.
- Duplicate cite keys: hard fail by default (`--allow-duplicates` override).
- DOI mismatch: treat as hallucinated and request re-resolution.

## 7. Testing Strategy
- Unit tests for normalizer/scorer/resolver.
- Integration test with a tiny LaTeX fixture + store.
- Golden tests for exported report and graph.
- Gate test failing on one unresolved ref.

## 8. Security/Privacy
- All operations local; no network in core path.
- Optional network only in `suggest` if `--online` provided.

## 9. Rollout
- Phase A: parser+resolver+sync (MVP)
- Phase B: MCP + gate
- Phase C: export bundle + tests

## 10. Backlog & Governance
- Implementation backlog with task IDs, owners, estimates, dependencies.
- Quality: test matrix, performance budgets (10k papers), memory limits.
- UX: empty/error/loading states, onboarding, microcopy.
- Data migration: schema versioning, backups, restore.
- Security/privacy: threat model, signed updates, encryption options.
- Packaging: installer, signing, offline update strategy.
- Business ops: pricing validation, licensing model, support policy.
- Metrics: activation, retention, citation-resolution accuracy.
- Benchmarks: compare workflows against Zotero/Mendeley/Elicit.
" 