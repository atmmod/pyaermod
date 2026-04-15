# conda-recipe/

Skeleton conda-forge recipe for pyaermod.

## Contents

- `meta.yaml` — build/test/run metadata, suitable for submission to
  [conda-forge/staged-recipes](https://github.com/conda-forge/staged-recipes).

## Local build (smoke test)

```bash
conda install -n base -c conda-forge conda-build
conda build conda-recipe/ -c conda-forge
```

For a local path-based source during development, change `source.url`
in `meta.yaml` to:

```yaml
source:
  path: ..
```

## Publishing to conda-forge

1. Tag and publish the release to PyPI first (so the sdist URL
   resolves).
2. Compute the sha256 of the sdist:
   `curl -L <url> | sha256sum`
3. Update the `sha256` line in `meta.yaml`.
4. Fork `conda-forge/staged-recipes`, copy `meta.yaml` into
   `recipes/pyaermod/`, open a PR.
5. After merge, the recipe is migrated to its own feedstock
   (`conda-forge/pyaermod-feedstock`). Subsequent releases update
   `meta.yaml` via the autotick bot or manual PRs.

## Optional-dependencies note

The recipe deliberately only pins the *core* runtime deps
(`numpy`, `pandas`). Users who need viz / geo / gui / hpc should
install the extras via pip in a conda env, or rely on downstream
conda-forge packages (`matplotlib`, `rasterio`, `streamlit`, etc.)
which are already available on conda-forge.
