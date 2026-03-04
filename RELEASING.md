# Release Process

## Steps

1. **Bump version** in both files:
   - `pyproject.toml` → `version = "X.Y.Z"`
   - `src/pyaermod/__init__.py` → `__version__ = "X.Y.Z"`

2. **Commit and push**:
   ```bash
   git add pyproject.toml src/pyaermod/__init__.py
   git commit -m "Bump version to X.Y.Z"
   git push origin main
   ```

3. **Create a GitHub Release** (this triggers the PyPI publish):
   ```bash
   gh release create vX.Y.Z --title "vX.Y.Z — Description" --notes "Release notes here"
   ```
   To attach compiled binaries (optional):
   ```bash
   gh release create vX.Y.Z --title "vX.Y.Z — Description" --notes "..." bin/aermod bin/aermap
   ```

4. **Verify** the publish workflow succeeded:
   ```bash
   gh run list --limit 1
   pip install pyaermod==X.Y.Z
   ```

## Important

- **Do NOT run `twine upload` manually.** The GitHub Actions workflow (`.github/workflows/publish.yml`) handles PyPI publishing automatically via trusted publishing when a release is created.
- Manual uploads will cause the workflow to fail with "File already exists."
- PyPI does not allow re-uploading the same version, so version numbers cannot be reused.

## Compiling AERMOD/AERMAP (optional)

To attach macOS binaries to a release:
```bash
./scripts/build_aermod.sh all
```
This builds `bin/aermod` and `bin/aermap` from Fortran source (requires `gfortran` via `brew install gcc`).
