# Security review: browser-gui (2026-11-12)

Independent reviewer (fresh agent, code only) plus orchestrator checks.

## Threat model
- Client-only app on GitHub Pages; no server, no accounts, no data leaves the browser except fetches of Pyodide from jsDelivr.
- Untrusted inputs: uploaded decks, project JSON, met/terrain files, typed fields.
- Assets: the user's browser origin storage; on the dev server, the developer's file system.

## Findings and dispositions
| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | Dev server accepted cross-origin / DNS-rebinding POSTs; with a real aermod, could write files anywhere | Medium (dev only) | Fixed: JSON content type, loopback Host, matching Origin required; tests |
| 2 | Opened project / typed paths bypassed the output sandbox import applies | Low | Fixed: outside paths are blocking checklist items; run refused |
| 3 | No CSP/SRI for Pyodide from jsDelivr; localStorage/IndexedDB shared with the owner's other Pages sites and /lite | Low | Accepted for phase 1; documented. Mitigation later: self-host Pyodide, add CSP meta |
| H4 | Quoted paths escaped the reader sandbox | High | Fixed earlier on this branch with tests |

## Checked clean
- XSS: only innerHTML is the plan-view SVG; ids and names are escaped by plan_view_svg (tested with injection strings by the reviewer); all other DOM writes use textContent/attributes.
- Path traversal in put/get/remove_file, import_deck, apply_terrain: names cut to their last part; "..", "a/../../x", "C:\\x", absolute paths tested.
- Supply chain: wheels installed by site-relative URL with deps=False (no PyPI lookup); Pyodide version pinned.
- CI step: contents: read; no untrusted interpolation. Playwright not version-pinned in that step (low).

## Sign-off
Security: approved for phase 1 with #3 recorded as accepted risk.
