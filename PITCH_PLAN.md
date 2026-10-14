# Pitch Plan — LitKG-RDF (Working Name: LitGraph)

## One-Liner
Turn a folder of PDFs into a queryable, SPARQL-first literature knowledge graph that AI agents can use.

## Target ICP (first)
- ML/AI researchers and PhD students with 50–5,000 paper libraries.
- Secondary: research labs and R&D teams in biotech/legal/policy (heavy citation workflows).

## Core Problem
Researchers waste hours searching, linking, and synthesizing scattered PDFs; reference managers store bibliographies but do not expose graph structure or agent-ready queries.

## Product Scope (standalone desktop, offline-first)
- No cloud required, no account, no telemetry by default.
- One binary + local database; everything runs on the user's machine.
- Sources: local PDFs, exported Zotero libraries, BibTeX/CSL files.
- Outputs: local reports, graphs, and citation files.

## Differentiation
- Structured RDF entities + relationships (not just search index).
- Local privacy by default.
- Agent-native interfaces from day one.

## Monetization (offline-friendly)
- Free core for personal library indexing and basic graph queries.
- Pro one-time license (or annual maintenance) for advanced parsers, premium export templates, and priority support.
- Team license for shared read-only offline bundles (optional enterprise deployments).

## Distribution & Trust
- Signed installers; verify-at-rest encryption optional.
- Air-gapped/secure environments supported (government, hospital, defense).

## GTM (standalone)
- Developer/researcher led: GitHub releases, HN, arXiv-friendly communities, Reddit, AI tool directories.
- Content: benchmark against Zotero workflow; tutorials for PhD thesis literature reviews.
- Growth loop: export citation graph + “Powered by LitGraph” in reports.
- Target secure/air-gapped verticals (gov/hospital/lab) with bundled offline installer.

## Top Risks
- Data extraction accuracy and dedup quality.
- Incumbents (Zotero) integrating similar AI features.
- Support burden for heterogeneous PDFs.

## Next 90-Day Milestones
1. Ship desktop MVP (UI + import + graph view) — 30 days
2. Add Zotero import + BibTeX/CSL export — 45 days
3. Publish public API + 2 integrations (Obsidian/Notion) — 75 days
4. Start paid beta with 50 power users — 90 days
" 