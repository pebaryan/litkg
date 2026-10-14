# UI/UX Design Plan — LitKG Desktop Web App

## 1. Design Principle
Local-first, no-surprise, research-grade interface. The UI should feel like a trustworthy desktop tool, not a flashy dashboard.

## 2. Information Architecture
- Dashboard
  - library stats
  - recent papers
  - quick actions
- Library
  - papers table with filters/sort
  - paper detail view (metadata, references, citations, graph)
- Bibliographies
  - import and inspect
  - resolution status dashboard
- Reading Lists
  - coverage and progress
- Citation Review
  - unresolved/partial/duplicate queue
  - one-click import/search actions
- Graph Explorer
  - citation graph and bibliography graph
  - node search and filtering
- Query Console
  - SPARQL editor with saved queries and results export
- Settings
  - store path, parser options, theme

## 3. Visual System
- Dark theme first, high contrast, accessible labels.
- Typography: system stack; use monospace for identifiers/DOI.
- Color tokens for states (resolved/partial/unresolved/duplicate).
- Component primitives: cards, tables, chips, badges, dialogs, toast feedback.

## 4. UX Flows (MVP)
1. First run: choose store → index folder → dashboard populated.
2. Paper detail: open metadata, refs, citing graph.
3. Citation review: queue → resolve → export report.
4. SPARQL: write query → execute → export results CSV/JSON.

## 5. Accessibility
- Keyboard navigation for all actions.
- ARIA labels for interactive controls.
- Color not sole status indicator.
- Responsive layout for desktop + laptop widths.

## 6. Implementation Phases
Phase A: static UI shell + navigation + dashboard + tables (current, replaceable).
Phase B: paper detail, filters, citation review workflow.
Phase C: graph explorer, saved queries, export actions.
Phase D: polish (accessibility audit, responsive QA, empty states).

## 7. Acceptance Criteria
- All primary tasks reachable within 2 clicks.
- Every status state visually distinguishable and screen-reader friendly.
- No blocking network requests in UI startup.
- Empty/error/loading states for each page.
