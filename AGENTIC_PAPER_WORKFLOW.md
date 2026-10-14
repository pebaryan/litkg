# Agentic Paper Workflow — LitKG Integration Plan

## Goal
Let an agent drive an end-to-end paper workflow where citations are continuously resolved, verified, and exported using LitKG's local RDF store.

## Core LitKG Features Used
- `index` PDF library
- `import-bibliography` (BibTeX/CSL-JSON)
- `resolve-refs` / report review states (resolved, partial, unresolved, duplicate)
- `citation-graph` and `bibliography-graph`
- `export-*` reports (HTML/PDF/MD)
- MCP server tools for agent access

## Proposed Command/MCP Layer
1. `litkg papercite init --paper paper.tex --bib refs.bib`
   - Creates paper sidecar tracking unresolved placeholders.
2. `litkg papercite sync --paper paper.tex --store .litkg_store.ttl`
   - Parse citation placeholders; match against indexed papers/bibs.
   - Output `citation_status.json`.
3. `litkg papercite suggest --unresolved --store .litkg_store.ttl`
   - For each unresolved ref, emit search hints (title/author/year/DOI).
4. `litkg papercite fill --from refs/new.bib --store .litkg_store.ttl`
   - Import found refs, rerun sync, update report.
5. `litkg papercite gate --paper paper.tex --store .litkg_store.ttl`
   - Fail if unresolved or duplicate refs remain.
6. `litkg papercite export --paper paper.tex --out final/`
   - Writes resolved bibliography, citation graph, annotated report.

## MCP Tools (agent-facing)
- `litkg_search_papers`
- `litkg_resolve_ref`
- `litkg_list_unresolved`
- `litkg_import_bibliography`
- `litkg_export_report`

## Acceptance Criteria
- Every bibliography cite key resolves to either an indexed paper or imported bib entry.
- Zero unresolved references before gate.
- Hallucinated DOIs replaced by verified Crossref metadata.
- Exported bibliography compiles in LaTeX without missing citations.
- Citation graph includes at least direct edges from final paper refs.

## 90-Day Implementation Slices
- Slice 1: CLI sync + status JSON
- Slice 2: resolve + report integration
- Slice 3: MCP tool exposure
- Slice 4: gate + export bundle
" 