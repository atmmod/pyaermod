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
        for src in ("viz", "geo", "gui", "terrain", "hpc"):
            for pkg_spec in extras[src]:
                pkg = pkg_spec.split(">=")[0].strip()
                if pkg == "streamlit-folium":
                    # streamlit-folium is optional and not pulled into 'all'
                    continue
                assert pkg in all_pkgs, f"'all' missing {pkg} (from [{src}])"

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

    def test_recipe_readme(self):
        path = REPO / "conda-recipe" / "README.md"
        assert path.exists() and len(path.read_text()) > 400
