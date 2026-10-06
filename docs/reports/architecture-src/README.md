# NEWS INSIGHT interactive system architecture

Deliverable: `../news-insight-architecture.html`. All JavaScript, CSS, graph data and redacted source code are embedded. No CDN is required at viewing time. The sibling original report is linked separately.

## Rebuild

Run from this directory with Node/npm and the project's Python environment available:

```sh
mkdir -p .build
../../../apps/api/.venv/bin/python snapshot.py .build/snapshot.json
../../../apps/api/.venv/bin/python build_data.py .build/snapshot.json .build/data.json
npm ci
npm run build
```

`snapshot.py` reads code and loads FastAPI's OpenAPI metadata; it does not query production data. It excludes runtime `.env` and secrets files and redacts sample passwords/email addresses. Review the embedded source before sharing beyond the intended audience.

`build_data.py` combines curated, evidence-linked processing maps with generated Python import graphs, actual ORM foreign keys, OpenAPI contracts and web file inventories. Update curated descriptions when algorithms change; automatic extraction does not update their explanatory prose. Imports are dependencies, not runtime call traces. The node tour is a reading aid, not an algorithm execution simulator. Source-dialog call names are lexical local references, not full dynamic dispatch resolution.

## UI

React 19.2.8, React Flow 12.12.0, Dagre 3.1.1, Radix UI 1.6.7, Lucide 1.51.0, esbuild 0.28.2. The product application's dependencies are untouched. Built-in graph controls/minimap and Radix dialogs/tabs/tooltips support graph navigation, code inspection and keyboard access. Layout uses custom responsive CSS, with light/dark tokens and reduced-motion handling.

Official references reviewed 2026-10-05:
- https://reactflow.dev/learn/concepts/built-in-components
- https://reactflow.dev/learn/layouting/layouting
- https://www.radix-ui.com/primitives/docs/components/dialog
- https://ui.shadcn.com/docs/components

## Verification

All 60 maps rendered in Chrome; graph drill-down, source dialog, search, mobile navigation and overflow checks passed. Additional browser checks passed for API schema details, FK details, initial deep-link node selection, and login-protected sharing. The artifact has no external script or stylesheet dependencies; direct file:// verification is not available in the in-app browser. JSON export is implemented but its browser download completion was not verified. This is a code snapshot, not a production-health audit.
