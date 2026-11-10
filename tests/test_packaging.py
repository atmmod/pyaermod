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


def _requirement(spec: str) -> tuple[str, str]:
    """('nicegui', '>=3.0') from a pip or a conda requirement."""
    name, _, floor = spec.replace(" ", "").partition(">=")
    return name, f">={floor}" if floor else ""


#: A pip distribution whose conda-forge package has another name.
CONDA_NAMES = {"matplotlib": "matplotlib-base"}


def _as_conda(pip_specs) -> set:
    return {(CONDA_NAMES.get(name, name), floor)
            for name, floor in map(_requirement, pip_specs)}


class TestCondaRecipe:
    """conda-recipe/recipe.yaml, the recipe for conda-forge, against pyproject.toml.

    conda has no extras: the recipe builds ``pyaermod`` (the core
    dependencies) and ``pyaermod-gui`` (the ``gui`` extra as a package).
    """

    RECIPE = REPO / "conda-recipe" / "recipe.yaml"

    @pytest.fixture()
    def recipe(self):
        yaml = pytest.importorskip("yaml")      # with nicegui, so in CI's `.[dev,all]`
        return yaml.safe_load(self.RECIPE.read_text(encoding="utf-8"))

    @pytest.fixture()
    def outputs(self, recipe):
        return {out["package"]["name"]: out for out in recipe["outputs"]}

    def test_it_is_a_v1_recipe(self, recipe):
        # staged-recipes takes new submissions as v1 recipe.yaml only.
        assert self.RECIPE.exists(), "conda-recipe/recipe.yaml missing"
        assert not (REPO / "conda-recipe" / "meta.yaml").exists()
        assert recipe["schema_version"] == 1
        for section in ("context", "recipe", "source", "build", "outputs", "about", "extra"):
            assert section in recipe, f"recipe.yaml has no '{section}'"

    def test_version_is_the_project_version(self, recipe):
        assert recipe["context"]["version"] == _load_pyproject()["project"]["version"]
        assert recipe["recipe"] == {"name": "pyaermod", "version": "${{ version }}"}

    def test_source_is_the_pypi_sdist_with_a_real_checksum(self, recipe):
        source = recipe["source"]
        assert source["url"] == ("https://pypi.org/packages/source/p/pyaermod/"
                                 "pyaermod-${{ version }}.tar.gz")
        sha = source["sha256"]
        assert len(sha) == 64 and set(sha) <= set("0123456789abcdef")
        assert set(sha) != {"0"}, "sha256 is a placeholder"

    def test_it_builds_the_library_and_the_gui_package(self, outputs):
        assert list(outputs) == ["pyaermod", "pyaermod-gui"]
        assert outputs["pyaermod"]["build"]["noarch"] == "python"
        assert outputs["pyaermod-gui"]["build"]["noarch"] == "generic"

    def test_entry_points_match_pyproject(self, outputs):
        scripts = _load_pyproject()["project"]["scripts"]
        declared = dict(line.split(" = ", 1)
                        for line in outputs["pyaermod"]["build"]["python"]["entry_points"])
        assert declared == scripts

    def test_core_dependencies_match_pyproject(self, recipe, outputs):
        project = _load_pyproject()["project"]
        run = outputs["pyaermod"]["requirements"]["run"]
        assert run[0] == "python >=${{ python_min }}"
        assert _as_conda(run[1:]) == _as_conda(project["dependencies"])
        # python_min is conda-forge's minimum Python, 3.11 as of 2026-11
        # (conda-forge-pinning). A requires-python above it has to be
        # written into the recipe's context as python_min.
        python = project["requires-python"].removeprefix(">=")
        assert recipe["context"].get("python_min") == (None if python == "3.11" else python)

    def test_build_requirements_match_pyproject(self, outputs):
        host = outputs["pyaermod"]["requirements"]["host"]
        assert host[:2] == ["python ${{ python_min }}.*", "pip"]
        backend = _load_pyproject()["build-system"]["requires"]
        assert _as_conda(host[2:]) == _as_conda(backend)

    def test_gui_package_is_the_gui_extra_on_the_same_build(self, outputs):
        extras = _load_pyproject()["project"]["optional-dependencies"]
        run = outputs["pyaermod-gui"]["requirements"]["run"]
        assert run[0] == '${{ pin_subpackage("pyaermod", exact=True) }}'
        assert _as_conda(run[1:]) == _as_conda(extras["gui"])

    def test_optional_gui_packages_are_constrained_to_their_floors(self, outputs):
        # pywebview is not a dependency (conda-forge has no macOS build of
        # it), but one that is installed must be new enough.
        extras = _load_pyproject()["project"]["optional-dependencies"]
        constraints = outputs["pyaermod"]["requirements"]["run_constraints"]
        assert _as_conda(constraints) == _as_conda(extras["gui-desktop"])

    def test_both_packages_are_tested(self, outputs):
        core = outputs["pyaermod"]["tests"]
        assert core[0]["python"]["pip_check"] is True
        assert "pyaermod" in core[0]["python"]["imports"]
        assert core[0]["python"]["python_version"] == ["${{ python_min }}.*", "*"]
        assert "pyaermod --help" in core[1]["script"]
        gui = outputs["pyaermod-gui"]["tests"][0]["script"]
        assert "pip check" in gui and "pyaermod-app --help" in gui

    def test_about_and_maintainers(self, recipe):
        about = recipe["about"]
        assert about["license"] == _load_pyproject()["project"]["license"] == "MIT"
        assert about["license_file"] == "LICENSE" and (REPO / "LICENSE").exists()
        urls = _load_pyproject()["project"]["urls"]
        assert about["homepage"] == urls["Homepage"]
        assert about["documentation"] == urls["Documentation"]
        assert recipe["extra"]["recipe-maintainers"]
        assert recipe["extra"]["feedstock-name"] == "pyaermod"

    def test_readme_does_not_say_it_is_published(self):
        text = (REPO / "conda-recipe" / "README.md").read_text(encoding="utf-8")
        assert len(text) > 400
        assert "not on conda-forge yet" in text
        assert "streamlit" not in text.lower()
        for name in ("README.md", "docs/index.md", "docs/gui-guide.md"):
            page = " ".join((REPO / name).read_text(encoding="utf-8").split())
            assert "not on conda-forge yet" in page, name
            assert "Once the conda-forge package is published" in page, name



class TestGuiInstallCheck:
    """scripts/gui_install_smoke.py and the workflows that run it on a built wheel."""

    WORKFLOWS = REPO / ".github" / "workflows"

    def _script(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "gui_install_smoke", REPO / "scripts" / "gui_install_smoke.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_script_looks_for_the_steps_the_gui_has(self):
        # The labels are text in the script, so that it can run without
        # importing pyaermod (its --bin-dir mode).
        from pyaermod.gui_v2.steps import STEPS
        assert tuple(step.label for step in STEPS) == self._script().STEP_LABELS

    def test_the_script_refuses_a_checkout(self):
        # Run from the repository against the editable install, it must
        # say that this is not an installed wheel rather than pass.
        import pyaermod
        if not (Path(pyaermod.__file__).resolve().parents[2] / "pyproject.toml").is_file():
            pytest.skip("pyaermod is installed as a wheel here")
        script = self._script()
        with pytest.raises(script.Failure, match="imported from a checkout"):
            script.check_installed_copy()

    def test_a_missing_command_is_a_failure(self, tmp_path):
        script = self._script()
        with pytest.raises(script.Failure, match="pyaermod-app command is not in"):
            script._command(tmp_path, "pyaermod-app")
        (tmp_path / "pyaermod-app.exe").write_text("")
        assert script._command(tmp_path, "pyaermod-app").endswith("pyaermod-app.exe")

    def test_the_smoke_workflow_installs_the_wheel_not_the_checkout(self):
        text = (self.WORKFLOWS / "gui_install_smoke.yml").read_text(encoding="utf-8")
        assert "workflow_call" in text
        assert "scripts/gui_install_smoke.py" in text
        assert "pip install -e" not in text
        assert '"${WHEEL}[${{ matrix.extra }}]"' in text
        for runner in ("ubuntu-latest", "macos-latest", "windows-latest"):
            assert runner in text

    def test_pushes_and_releases_both_run_it(self):
        uses = "uses: ./.github/workflows/gui_install_smoke.yml"
        assert uses in (self.WORKFLOWS / "gui_install.yml").read_text(encoding="utf-8")
        publish = (self.WORKFLOWS / "publish.yml").read_text(encoding="utf-8")
        assert uses in publish
        # The upload waits for the check.
        upload = publish.split("  publish-pypi:", 1)[1]
        assert "needs: [build, gui-install]" in upload
