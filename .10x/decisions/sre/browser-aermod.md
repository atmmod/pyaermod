# SRE — browser-aermod

Static site; no runtime service. Failure modes: Pyodide CDN (jsDelivr) down → kernel cannot start; EPA source URL
changes → docs build fails at the wasm job (docs not deployed; last good site stays up). Monitoring = the
docs and wasm workflows' status.
