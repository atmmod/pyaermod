"""Verify pyproject extras and conda recipe shape."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent


def _load_pyproject():
    try:
        import tomllib  # py3.11+
    except ImportError:  # pragma: no cover
        import tomli as tomllib
    return tomllib.loads((REPO / "pyproject.toml").read_text())


class TestExtras:
    def test_has_core_extras(self):
        data = _load_pyproject()
        extras = data["project"]["optional-dependencies"]
        for name in ("viz", "geo", "gui", "terrain", "met", "hpc", "all", "dev"):
            assert name in extras, f"missing extra: {name}"

    def test_hpc_includes_tqdm(self):
        extras = _load_pyproject()["project"]["optional-dependencies"]
        joined = " ".join(extras["hpc"])
        assert "tqdm" in joined

    def test_all_is_superset_of_common_extras(self):
        extras = _load_pyproject()["project"]["optional-dependencies"]
        all_pkgs = set(s.split(">=")[0].strip() for s in extras["all"])
        # gui-desktop too: pyaermod[all] must be able to run pyaermod-desktop.
        for src in ("viz", "geo", "terrain", "met", "hpc", "cad", "gui", "gui-desktop"):
            for pkg_spec in extras[src]:
                pkg = pkg_spec.split(">=")[0].strip()
                assert pkg in all_pkgs, f"'all' missing {pkg} (from [{src}])"

    def test_all_floors_have_a_min_constraint(self):
        # CI's min-deps leg installs ".[dev,all]" against min-constraints.txt;
        # a package of [all] without a pin there is tested only at its latest.
        extras = _load_pyproject()["project"]["optional-dependencies"]
        pinned = {line.split("==")[0].strip()
                  for line in (REPO / "min-constraints.txt").read_text().splitlines()
                  if "==" in line and not line.lstrip().startswith("#")}
        for pkg_spec in extras["all"]:
            pkg = pkg_spec.split(">=")[0].strip()
            assert pkg in pinned, f"min-constraints.txt has no pin for {pkg}"

    def test_py_typed_shipped(self):
        data = _load_pyproject()
        pd = data.get("tool", {}).get("setuptools", {}).get("package-data", {})
        assert "py.typed" in pd.get("pyaermod", [])


class TestCondaRecipe:
    def test_meta_yaml_present(self):
        path = REPO / "conda-recipe" / "meta.yaml"
        assert path.exists(), "conda-recipe/meta.yaml missing"

    def test_meta_yaml_has_required_sections(self):
        text = (REPO / "conda-recipe" / "meta.yaml").read_text()
        for section in ("package:", "source:", "build:", "requirements:",
                        "test:", "about:"):
            assert section in text, f"meta.yaml missing '{section}'"

    def test_meta_yaml_noarch_python(self):
        text = (REPO / "conda-recipe" / "meta.yaml").read_text()
        assert "noarch: python" in text

    def test_meta_yaml_entry_points_match_pyproject(self):
        scripts = _load_pyproject()["project"]["scripts"]
        text = (REPO / "conda-recipe" / "meta.yaml").read_text()
        block = text.split("entry_points:", 1)[1].split("\n\n", 1)[0]
        recipe = dict(line.strip()[2:].split(" = ", 1)
                      for line in block.splitlines() if line.strip().startswith("- "))
        assert recipe == scripts

    def test_recipe_does_not_name_the_removed_streamlit_gui(self):
        for name in ("meta.yaml", "README.md"):
            text = (REPO / "conda-recipe" / name).read_text().lower()
            assert "streamlit" not in text and "pyaermod-gui" not in text, name

    def test_recipe_readme(self):
        path = REPO / "conda-recipe" / "README.md"
        assert path.exists() and len(path.read_text()) > 400
