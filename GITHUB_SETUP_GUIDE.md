# GitHub Repository Setup Guide

Complete guide for setting up your pyaermod repository at https://github.com/atmmod/pyaermod

## 📁 Recommended Repository Structure

```
pyaermod/
├── README.md                          # Main readme (use GITHUB_README.md)
├── LICENSE                            # MIT License
├── .gitignore                         # Python gitignore
├── setup.py                           # Package setup
├── requirements.txt                   # Dependencies
├── pyproject.toml                     # Modern Python packaging (optional)
│
├── src/
│   └── pyaermod/
│       ├── __init__.py               # Package init
│       ├── input_generator.py        # Input file generation
│       ├── runner.py                 # AERMOD execution
│       ├── output_parser.py          # Output parsing
│       └── visualization.py          # Plotting and maps
│
├── tests/
│   ├── __init__.py
│   ├── test_input_generator.py
│   ├── test_runner.py
│   ├── test_output_parser.py
│   └── test_visualization.py
│
├── examples/
│   ├── 01_simple_point_source.py
│   ├── 02_parameter_sweep.py
│   ├── 03_scenario_comparison.py
│   ├── 04_automated_workflow.py
│   └── end_to_end_example.py
│
├── docs/
│   ├── QUICKSTART.md
│   ├── API.md
│   ├── ARCHITECTURE.md
│   └── CONTRIBUTING.md
│
└── reference/
    ├── aermod_userguide.pdf
    ├── aermod_quick-reference-guide.pdf
    └── AERMOD_Data_Resources.pdf
```

## 🚀 Step-by-Step Setup

### 1. Initialize Git Repository Locally

```bash
cd /path/to/your/project
git init
git branch -M main
```

### 2. Organize Files

Create the directory structure and move files:

```bash
# Create directories
mkdir -p src/pyaermod
mkdir -p tests
mkdir -p examples
mkdir -p docs
mkdir -p reference

# Move core modules to src/pyaermod/
mv pyaermod_input_generator.py src/pyaermod/input_generator.py
mv pyaermod_runner.py src/pyaermod/runner.py
mv pyaermod_output_parser.py src/pyaermod/output_parser.py
mv pyaermod_visualization.py src/pyaermod/visualization.py

# Create __init__.py
touch src/pyaermod/__init__.py

# Move test files
mv test_input_generator.py tests/
mv test_output_parser.py tests/
touch tests/__init__.py

# Move examples
mv end_to_end_example.py examples/

# Move documentation
mv QUICKSTART.md docs/
mv aermod_wrapper_architecture.md docs/ARCHITECTURE.md
mv implementation_priorities.md docs/ROADMAP.md

# Move reference materials
mv aermod_userguide.pdf reference/
mv aermod_quick-reference-guide.pdf reference/
mv AERMOD_Data_Resources.pdf reference/

# Rename main README
mv GITHUB_README.md README.md
```

### 3. Create Package __init__.py

Edit `src/pyaermod/__init__.py`:

```python
"""
PyAERMOD - Python wrapper for EPA's AERMOD atmospheric dispersion model
"""

__version__ = "0.1.0"
__author__ = "Shannon Capps"
__email__ = "shannon.capps@gmail.com"

# Import main components for easy access
from .input_generator import (
    AERMODProject,
    ControlPathway,
    SourcePathway,
    PointSource,
    ReceptorPathway,
    CartesianGrid,
    PolarGrid,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    PollutantType,
    TerrainType,
    SourceType
)

from .runner import (
    AERMODRunner,
    AERMODRunResult,
    run_aermod
)

from .output_parser import (
    AERMODResults,
    parse_aermod_output,
    quick_summary
)

from .visualization import (
    AERMODVisualizer,
    quick_plot,
    quick_map
)

__all__ = [
    # Input generation
    'AERMODProject',
    'ControlPathway',
    'SourcePathway',
    'PointSource',
    'ReceptorPathway',
    'CartesianGrid',
    'PolarGrid',
    'DiscreteReceptor',
    'MeteorologyPathway',
    'OutputPathway',
    'PollutantType',
    'TerrainType',
    'SourceType',

    # Runner
    'AERMODRunner',
    'AERMODRunResult',
    'run_aermod',

    # Output parser
    'AERMODResults',
    'parse_aermod_output',
    'quick_summary',

    # Visualization
    'AERMODVisualizer',
    'quick_plot',
    'quick_map',
]
```

### 4. Add First Files to Git

```bash
# Add files
git add README.md
git add LICENSE
git add .gitignore
git add setup.py
git add requirements.txt
git add src/
git add tests/
git add examples/
git add docs/

# Make initial commit
git commit -m "Initial commit: PyAERMOD v0.1.0

- Input file generator
- AERMOD runner
- Output parser
- Visualization tools
- Complete documentation
- Test suite
- Examples
"
```

### 5. Connect to GitHub (Private Repo)

Since your repo is at `atmmod/pyaermod`:

```bash
# Add remote
git remote add origin https://github.com/atmmod/pyaermod.git

# Push to GitHub
git push -u origin main
```

### 6. Set Up Repository Settings on GitHub

Go to https://github.com/atmmod/pyaermod/settings

**General:**
- Description: "Python wrapper for EPA's AERMOD air dispersion model"
- Topics: `aermod`, `air-quality`, `atmospheric-modeling`, `dispersion-model`, `python`
- Set as private (or public when ready)

**Code:**
- Default branch: `main`
- Template repository: ❌ (unless you want others to use as template)

**Pull Requests:**
- ✅ Allow squash merging
- ✅ Automatically delete head branches

**Security:**
- ✅ Enable Dependabot alerts
- ✅ Enable Dependabot security updates

### 7. Create Additional GitHub Files

Create `.github/` directory for GitHub-specific configs:

```bash
mkdir -p .github/workflows
mkdir -p .github/ISSUE_TEMPLATE
```

### 8. Optional: Add GitHub Actions (CI/CD)

Create `.github/workflows/tests.yml`:

```yaml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python-version: ['3.8', '3.9', '3.10', '3.11']

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e .
        pip install pytest pytest-cov

    - name: Run tests
      run: |
        pytest tests/ --cov=pyaermod --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

### 9. Create CONTRIBUTING.md

Create `docs/CONTRIBUTING.md` with contribution guidelines.

### 10. Create Issue Templates

Create `.github/ISSUE_TEMPLATE/bug_report.md`:

```markdown
---
name: Bug report
about: Create a report to help us improve
title: '[BUG] '
labels: bug
assignees: ''
---

**Describe the bug**
A clear description of what the bug is.

**To Reproduce**
Steps to reproduce:
1. ...
2. ...

**Expected behavior**
What you expected to happen.

**Environment:**
 - OS: [e.g., Windows 10, Ubuntu 22.04]
 - Python version: [e.g., 3.10.5]
 - PyAERMOD version: [e.g., 0.1.0]
 - AERMOD version: [e.g., 24142]

**Additional context**
Any other relevant information.
```

### 11. Add Badges to README

At the top of README.md, add badges:

```markdown
# PyAERMOD

[![Tests](https://github.com/atmmod/pyaermod/workflows/Tests/badge.svg)](https://github.com/atmmod/pyaermod/actions)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
```

### 12. Create Release

Once everything is pushed:

1. Go to https://github.com/atmmod/pyaermod/releases
2. Click "Draft a new release"
3. Tag version: `v0.1.0`
4. Release title: "PyAERMOD v0.1.0 - Initial Release"
5. Description:

```markdown
## PyAERMOD v0.1.0 - Initial Release

First public release of PyAERMOD, a Python wrapper for EPA's AERMOD.

### ✨ Features

- ✅ Input file generator (point sources, receptors, control options)
- ✅ AERMOD subprocess runner (with error handling and batch processing)
- ✅ Output parser (to pandas DataFrames)
- ✅ Visualization tools (contour plots and interactive maps)
- ✅ Complete documentation and examples

### 📦 Installation

```bash
pip install pyaermod
```

Or from source:
```bash
git clone https://github.com/atmmod/pyaermod.git
cd pyaermod
pip install -e .
```

### 🎯 Quick Start

See [QUICKSTART.md](docs/QUICKSTART.md) for detailed guide.

### 📊 What's Included

- Core modules: input_generator, runner, output_parser, visualization
- Test suite with 15+ test cases
- 8+ documentation files
- 4+ working examples
- EPA test cases and reference materials

### 🙏 Credits

Based on AERMOD version 24142 (2024) from EPA SCRAM.

### 📄 License

MIT License - see LICENSE file.
```

6. Attach compiled assets (optional)
7. Publish release

## 📝 Post-Setup Checklist

- [ ] Repository created on GitHub
- [ ] All files pushed to main branch
- [ ] README.md looks good on GitHub
- [ ] LICENSE file is present
- [ ] .gitignore is working (no .pyc files)
- [ ] Package structure is correct
- [ ] Tests can run: `pytest`
- [ ] Package can install: `pip install -e .`
- [ ] Examples work
- [ ] Documentation is readable
- [ ] Release created (v0.1.0)
- [ ] Repository settings configured
- [ ] (Optional) CI/CD workflows added
- [ ] (Optional) Issue templates created

## 🔄 Development Workflow

### For Future Updates

```bash
# Create feature branch
git checkout -b feature/new-feature

# Make changes...

# Commit changes
git add .
git commit -m "Add new feature"

# Push branch
git push origin feature/new-feature

# Create pull request on GitHub
# After review and merge, update main:
git checkout main
git pull origin main

# Tag new version
git tag v0.2.0
git push origin v0.2.0
```

### For Bug Fixes

```bash
# Create bugfix branch
git checkout -b bugfix/fix-issue-123

# Fix bug...

# Commit and push
git add .
git commit -m "Fix issue #123: Description"
git push origin bugfix/fix-issue-123

# Create PR, merge, update main
```

## 🚀 Making Repository Public

When ready to make public:

1. Go to Settings → General → Danger Zone
2. Click "Change repository visibility"
3. Select "Make public"
4. Confirm
5. Announce on social media, mailing lists, etc.

## 📦 Publishing to PyPI

When ready to publish:

```bash
# Install build tools
pip install build twine

# Build distribution
python -m build

# Test upload (TestPyPI first)
twine upload --repository testpypi dist/*

# Real upload
twine upload dist/*
```

## 🎉 You're Done!

Your repository is now set up professionally and ready for:
- Collaboration
- Version control
- Issue tracking
- Documentation
- Testing
- Distribution

**Repository URL:** https://github.com/atmmod/pyaermod

Good luck with your project! 🚀
