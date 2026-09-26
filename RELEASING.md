# Release Process

A release is a GitHub release on a tag `vX.Y.Z`. Publishing it triggers
`.github/workflows/publish.yml`, which builds the sdist and wheel and
uploads them to PyPI through trusted publishing, and (once the
repository is connected to Zenodo, step 0) makes Zenodo archive the tag
and mint a DOI. The DOI cannot be known before the release exists, so a
release is two commits: the version bump before, and the DOI afterward.

## 0. Once per repository: connect Zenodo

Before the first archival release, log in at <https://zenodo.org> with
the GitHub account that owns `atmmod/pyaermod`, open *GitHub* under the
account menu and switch the repository on. From then on every
**published** GitHub release is archived automatically and gets its own
version DOI plus a concept DOI shared by all versions. (A release
published before the switch is not archived retroactively.)

## 1. Prepare the release commit

1. **Bump the version** in all three files that carry it (the package
   re-exports `api.__version__` over its own, so a bump that misses
   `api.py` leaves `pyaermod.__version__` at the old number;
   `tests/test_citation.py` fails on a partial bump):
   - `pyproject.toml` → `version = "X.Y.Z"`
   - `src/pyaermod/__init__.py` → `__version__ = "X.Y.Z"`
   - `src/pyaermod/api.py` → `__version__ = "X.Y.Z"`
   - `conda-recipe/meta.yaml` → `{% set version = "X.Y.Z" %}`
   - `CITATION.cff` → `version: X.Y.Z`

2. **Date the release**:
   - `CHANGELOG.md`: rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`
     (today's date) and open a fresh, empty `## [Unreleased]` above it.
     For v2.2.0 the section already exists with a `YYYY-MM-DD`
     placeholder; replace the placeholder and delete the comment under
     it.
   - `CITATION.cff`: set `date-released` to the same date.
   - `docs/release-notes/vX.Y.Z.md`: the notes to paste into the release
     (v2.2.0's are written; check them against the final changelog).

3. **Run the gates** and make sure they are green:
   ```bash
   make lint
   make typecheck
   make test-full                       # full suite, slow tests included
   make test-binaries                   # after scripts/build_aermod.sh etc.
   mkdocs build --strict
   python -m build && twine check dist/*
   cffconvert --validate
   ```

4. **Commit and push** (on `main`, or through a PR):
   ```bash
   git add pyproject.toml src/pyaermod/__init__.py src/pyaermod/api.py \
           conda-recipe/meta.yaml CITATION.cff CHANGELOG.md docs/release-notes
   git commit -m "Release vX.Y.Z"
   git push origin main
   ```

## 2. Create the GitHub release (this publishes to PyPI)

```bash
gh release create vX.Y.Z --title "vX.Y.Z — Description" \
    --notes-file docs/release-notes/vX.Y.Z.md
```
To attach compiled binaries (optional):
```bash
gh release create vX.Y.Z --title "vX.Y.Z — Description" \
    --notes-file docs/release-notes/vX.Y.Z.md bin/aermod bin/aermap
```

Then verify the publish workflow succeeded:
```bash
gh run list --workflow publish.yml --limit 1
pip install pyaermod==X.Y.Z
```
The docs site redeploys on the push to `main` (`.github/workflows/docs.yml`).

## 3. Record the Zenodo DOI

A few minutes after the release is published, Zenodo lists the archived
version under the repository's entry (the badge on the Zenodo GitHub
page links to it). Copy the **version** DOI (`10.5281/zenodo.NNNNNNN`,
the one specific to vX.Y.Z, not the concept DOI) and paste it into:

- `CITATION.cff` → `doi: 10.5281/zenodo.NNNNNNN` (replacing the
  placeholder and its comment)
- `README.md` and `docs/index.md` → the "Citing PyAERMOD" section
  (replace `10.5281/zenodo.XXXXXXX` and drop the parenthetical about the
  DOI being minted later)

Commit and push that on `main` ("Record the Zenodo DOI for vX.Y.Z").
The tag itself keeps the placeholder; that is expected, since the DOI
did not exist when the tag was made, and Zenodo's own record carries
the authoritative citation for the tag.

## Important

- **Do NOT run `twine upload` manually.** The GitHub Actions workflow
  (`.github/workflows/publish.yml`) handles PyPI publishing
  automatically via trusted publishing when a release is created.
- Manual uploads will cause the workflow to fail with "File already exists."
- PyPI does not allow re-uploading the same version, so version numbers
  cannot be reused. If a release must be redone, bump the patch version.
- A GitHub release saved as a **draft** publishes nothing and mints no
  DOI; both happen when it is published.

## Compiling AERMOD/AERMAP (optional)

To attach macOS binaries to a release:
```bash
./scripts/build_aermod.sh all
```
This builds `bin/aermod`, `bin/aermap` and `bin/aermet` from Fortran
source (requires `gfortran` via `brew install gcc`).
