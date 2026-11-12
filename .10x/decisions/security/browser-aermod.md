# Security — browser-aermod

- Everything runs client-side in the browser sandbox; no server, no uploads leave the browser.
- aermod.js is evaluated with `new Function` — code from our own wheel served same-origin, not user input.
- PROXYFS exposes only Pyodide's in-browser filesystem (the user's own files) to AERMOD.
- Supply chain: flang-wasm image pinned by digest; EPA source fetched over HTTPS from gaftp.epa.gov (same as the
  existing real_aermod.yml); Pyodide fetched from jsDelivr by JupyterLite (pinned via jupyterlite-pyodide-kernel
  0.8.7). New workflow has `contents: read` only; no secrets used.
- Labeling: every notebook and docs/browser.md say "not for regulatory use".
