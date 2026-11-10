# conda-recipe/

The recipe for putting pyaermod on [conda-forge](https://conda-forge.org/).
**pyaermod is not on conda-forge yet.** This directory holds the recipe
that is ready to submit; the steps to submit it are below.

## What the recipe builds

`recipe.yaml` is a v1 recipe (the format
[conda-forge/staged-recipes](https://github.com/conda-forge/staged-recipes)
requires for new submissions; it is built with `rattler-build`, not
`conda-build`). It builds two packages from the PyPI sdist:

| Package | Contents | pip equivalent |
|---|---|---|
| `pyaermod` | The library and the three commands (`pyaermod`, `pyaermod-app`, `pyaermod-desktop`). Depends on `numpy` and `pandas`, the `dependencies` of `pyproject.toml`. `noarch: python`. | `pip install pyaermod` |
| `pyaermod-gui` | No files of its own: it depends on exactly the same build of `pyaermod`, plus `nicegui` and `matplotlib-base`. | `pip install "pyaermod[gui]"` |

conda has no extras, so the `gui` extra becomes a second package, as
conda-forge does for `uvicorn` / `uvicorn-standard` and
`napari-base` / `napari`.

Three choices worth knowing about:

- **The GUI commands are in `pyaermod`, not in `pyaermod-gui`.** That is
  where pip puts them, and a `noarch: python` package must declare every
  console script of the wheel it installs. Without NiceGUI, `pyaermod-app`
  prints one line, which in a conda install reads
  ``Install it with `conda install -c conda-forge pyaermod-gui`.``
  (`napari-base` ships the `napari` command without a Qt binding in the
  same way.)
- **`pyaermod-gui` does not depend on pywebview**, so `pyaermod-desktop`
  needs one more package. conda-forge builds pywebview for Windows and
  Linux only (no macOS build as of November 2026), and its Linux build
  brings no GTK or Qt backend; depending on it would make `pyaermod-gui`
  impossible to install on macOS. `pyaermod` carries a `run_constraints`
  entry for it instead, so a pywebview that is installed is new enough.
  Should conda-forge gain a macOS build, a `pyaermod-desktop` output can
  be added.
- **`matplotlib-base`, not `matplotlib`.** The GUI draws with the Agg
  backend; `matplotlib` on conda-forge adds Qt.

`tests/test_packaging.py` keeps the recipe in step with `pyproject.toml`:
the entry points, the dependencies of both packages, and the version.

## Which version to submit

A recipe can only describe a version that is on PyPI: its source is the
sdist there, by URL and sha256. `recipe.yaml` names the version in
`pyproject.toml`, and `sha256` is that of its sdist on PyPI.

**Submit the first release after 2.2.0, not 2.2.0.** In 2.2.0
`pyaermod-app` reads no options, so the recipe's `pyaermod-app --help`
test would start the server and never return; `pyaermod gui`, the
one-line install hints and the conda wording of them are also newer than
2.2.0. After that release is on PyPI, update `version` and `sha256`
(step 1 below) and submit.

## Build and test it locally

Use a throwaway environment; nothing goes into `base`.

```bash
conda create -n cf-build -c conda-forge rattler-build conda-smithy
conda activate cf-build

# Lint as conda-forge's CI does (the recipe must sit in recipes/<name>/).
mkdir -p /tmp/lint/recipes/pyaermod
cp conda-recipe/recipe.yaml /tmp/lint/recipes/pyaermod/
(cd /tmp/lint && conda-smithy recipe-lint --conda-forge recipes/pyaermod)

# Build both packages and run the recipe's tests. conda_build_config.yaml
# is conda-forge's pinning file (it defines python_min and the channel);
# the conda-forge-pinning package, a dependency of conda-smithy, puts it
# at the root of the environment.
rattler-build build --recipe conda-recipe/recipe.yaml \
    --variant-config "$CONDA_PREFIX/conda_build_config.yaml" \
    --output-dir /tmp/pyaermod-conda

# Install what was built into a new environment and start the GUI.
conda create -n pyaermod-try -c file:///tmp/pyaermod-conda -c conda-forge pyaermod-gui
conda activate pyaermod-try
cd /tmp && python /path/to/pyaermod/scripts/gui_install_smoke.py
```

To try the recipe on a version that is not on PyPI yet (the working
tree), build the sdist and point a copy of the recipe at it:

```bash
python -m build --sdist --outdir /tmp/sdist
shasum -a 256 /tmp/sdist/pyaermod-*.tar.gz      # sha256sum on Linux
```

then, in the copy, set `source.url` to `file:///tmp/sdist/pyaermod-X.Y.Z.tar.gz`
and `sha256` to the value printed. Do not commit that copy.

## Submit to conda-forge (once)

1. Release to PyPI first (`RELEASING.md`). Then set `context.version` in
   `recipe.yaml` to the released version and `source.sha256` to the
   sha256 of its sdist, from the "view hashes" link on
   <https://pypi.org/project/pyaermod/#files> or:

   ```bash
   curl -s https://pypi.org/pypi/pyaermod/X.Y.Z/json \
     | python -c "import json,sys; print([f['digests']['sha256'] for f in json.load(sys.stdin)['urls'] if f['packagetype'] == 'sdist'][0])"
   ```

   Build and lint it as above.
2. Confirm the maintainers in `extra.recipe-maintainers`. Each is a
   GitHub login, becomes a maintainer of the feedstock, and has to
   comment on the pull request that they agree to be listed.
3. Fork <https://github.com/conda-forge/staged-recipes>, make a branch
   from `main`, and copy `recipe.yaml` to `recipes/pyaermod/recipe.yaml`.
   Leave `recipes/example-v1` as it is. Nothing else is needed: the
   license file comes from the sdist.
4. Open a pull request titled "Add pyaermod" and go through its
   checklist. conda-forge's CI builds the recipe on Linux, macOS and
   Windows and lints it.
5. When CI is green, ask for review in a comment:
   `@conda-forge/help-python, ready for review!` (a first-time
   contributor cannot ping teams; use
   `@conda-forge-admin, please ping conda-forge/help-python`).
   Reviewers are volunteers; days to weeks is normal.
6. After the merge, conda-forge creates
   `conda-forge/pyaermod-feedstock`, builds both packages and uploads
   them to the `conda-forge` channel. The maintainers are invited to the
   feedstock's team by email. The packages appear on
   <https://anaconda.org/conda-forge/pyaermod> when the feedstock's first
   build finishes, and reach `conda install` some 15 minutes later.

Only then change the wording in `README.md`, `docs/index.md` and
`docs/gui-guide.md` from "once the conda-forge package is published" to
plain install instructions.

## After each PyPI release

From then on the feedstock, not this directory, is what conda-forge
builds. conda-forge's bot (`regro-cf-autotick-bot`) looks for new
versions on PyPI in a loop, which can take several hours, and opens a
pull request on the feedstock that updates `version` and `sha256` and
resets the build number. A maintainer checks it and merges it:

- The bot does not know about dependency changes. If the release changed
  `dependencies` or the `gui` extra in `pyproject.toml`, the minimum
  Python, the build backend's requirements or `[project.scripts]`, make
  the same change to the feedstock's `recipe/recipe.yaml` in that pull
  request (push to the bot's branch). `conda-recipe/recipe.yaml` here, which `tests/test_packaging.py`
  holds to `pyproject.toml`, is the reference: copy from it.
- If `requires-python` rises above conda-forge's minimum Python, add
  `python_min: "3.NN"` to the recipe's `context`.
- Merge once the feedstock's CI is green.

If no pull request appears within a day, open an issue on the feedstock
whose title is `@conda-forge-admin, please update version`, or make the
change by hand in a pull request from a fork of the feedstock.

## What users will type, once it is published

```bash
conda install -c conda-forge pyaermod        # the library
conda install -c conda-forge pyaermod-gui    # the library and the GUI
pyaermod-app                                 # start the GUI
```

Until then: `python -m pip install "pyaermod[gui]"` inside a conda
environment.
