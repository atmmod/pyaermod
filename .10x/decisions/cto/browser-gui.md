# CTO: browser-gui

- Build, not buy: Voici and stlite/Panel considered and rejected (UX ceiling; Pyodide pin conflicts; project left Streamlit in v2.0). Hosted server rejected (cost, ops, multi-user isolation).
- No signing, no server, no new hosting: GitHub Pages under /app/, reusing #61's AERMOD-wasm wheel and Pyodide 314.0.6.
- Accepted risk: non-EPA executable; mitigated by a banner and docs, same as /lite/.
