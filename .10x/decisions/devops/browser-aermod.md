# DevOps — browser-aermod

- wasm_aermod.yml: builds on ubuntu-latest in the digest-pinned flang-wasm container (amd64; never under local
  emulation — that crashed the dev Mac). Uploads `aermod-wasm-<variant>`.
- docs.yml: job `wasm` (workflow_call, release only) → `build` downloads the artifact, runs mkdocs then
  scripts/wasm/build_lite_site.sh into _site/lite → deploy (main/dispatch only).
- Rollback: revert the docs.yml change; Pages redeploys mkdocs only.
- A new EPA release is picked up at the next docs build (the source URL is EPA's latest archive); the parity
  tests in the called workflow must pass before the site is rebuilt.
