# PyAERMOD — JAWMA Manuscript Plan (for agents)

**Target:** Journal of the Air & Waste Management Association (JA&WMA), Technical Paper.
**Source repository:** https://github.com/atmmod/pyaermod
**Prepared:** 2026-09-25

## Journal fit and constraints

JA&WMA publishes advances in science and technology relevant to decisions for safeguarding human health and the environment, and a validated open-source interface to EPA's regulatory dispersion model is squarely in scope. Requirements to design against:

- Technical Papers are preferred at fewer than 11,000 words excluding references; reviewers flag unnecessarily lengthy manuscripts, and page charges apply per published page, so target 7,000–8,500 words.
- The journal requires an Implications statement, a software availability statement placed before the references, and a data availability statement; software must also be cited in the body and reference list.
- Submission is through ScholarOne. Before drafting begins, an agent must fetch the current Instructions for Authors from Taylor & Francis and extract the abstract rules, reference style, and submission checklist into `paper/JOURNAL-REQUIREMENTS.md`, which becomes binding on all writing agents.

## Thesis

The paper is not "we wrote a wrapper." Its two claims are:

1. PyAERMOD provides a type-safe, open, scriptable interface to the complete AERMOD modeling chain (AERMET, AERMAP, AERSURFACE, BPIP, AERMOD), making regulatory-style dispersion modeling reproducible, batchable, and teachable.
2. Its verification methodology is itself transferable: parity against EPA's published test suite with full provenance, bit-exact regression, analytic ground truths, oracle-driven testing of preprocessors, and a keyword-level completeness audit. The methodology found and corrected real defects — the BPIP GEP clamp reconstruction and the AERSURFACE configuration-space defects are publishable findings in their own right.

## Prerequisites before drafting

1. Code work packages WP-0 through WP-4 from `PLAN-code.md` should land first; the paper's claims strengthen materially with PR #9 merged, AERSCREEN fixed, and the keyword audit improved.
2. The archival release (v2.2.0 with a Zenodo DOI and `CITATION.cff`) must exist, because every number in the paper traces to that tag.
3. The demonstration study (Section 5 below) must be chosen by Shannon and executed before Methods and Results are drafted.

## Section outline, word budgets, and evidence sources

1. **Introduction (~1,200 words).** Establish AERMOD's role as EPA's preferred near-field model under 40 CFR 51 Appendix W; describe the manual runstream workflow and its costs to reproducibility, throughput, and pedagogy; survey existing tooling (commercial GUIs such as AERMOD View and BREEZE, and prior open wrappers) and state the gap. Anchor references: Cimorelli et al. (2005) and Perry et al. (2005) on AERMOD formulation and evaluation; EPA's Appendix W Guideline; current AERMOD, AERMET, and AERMAP user guides; the GRSM and RLINE literature for the chemistry and roadway options the library exposes.
2. **Software design (~1,500 words).** Present the pathway object model, writer/reader symmetry, runner architecture, preprocessor wrappers, optional-dependency layering, and the GUI. Include one architecture figure. Sources: `docs/architecture.md` and module docstrings.
3. **Verification methodology (~1,800 words).** Describe the parity harness and EPA's own ±0.001 best-fit-slope criterion; the bit-exact AERTEST regression; the synthetic-DEM analytic AERMAP test; setup-pass oracle sweeps for AERSURFACE; direction-sweep exactness for BPIP including the GEP clamp; the keyword audit as a completeness metric; and provenance stamping with weekly CI. Sources: `docs/validation.md`, `docs/keyword-audit-v26135.md`, and the PR #9 commit record.
4. **Results (~1,500 words).** Provide a parity table (142/142 comparisons with slope, paired count, and mean absolute difference summaries), a keyword-coverage table by pathway, the BPIP and AERSURFACE defect findings presented as verification case studies, and benchmark timings from WP-6.
5. **Demonstration application (~1,500 words).** This is the one missing scientific ingredient and requires Shannon's decision. The strongest option is a study that only scriptability enables: a design-value sensitivity sweep running hundreds of AERMOD cases that vary stack parameters or NO2 chemistry scheme against the 1-hour NAAQS design values, with contour and wind-rose figures, built on an EPA test case's meteorology so it is fully reproducible from the repository. Alternatives are an applied demonstration or a pedagogical one drawn from her teaching use.
6. **Implications statement (~150 words), Limitations (~400 words), Conclusions (~300 words), and Availability statements.** Limitations must state plainly which keywords remain unmodeled after WP-5, the AERSCREEN status at submission time, and the validated-version scope (`VALIDATED_AERMOD_VERSIONS`). Availability lists GitHub, PyPI, the Zenodo DOI, and the EPA reference sets used.

## Agent workflow and guardrails

1. **Repo-as-ground-truth rule.** Every numeric claim must trace to a checked-in artifact (the parity report, the keyword audit, test outputs, or benchmark logs) at the cited release tag. A dedicated verification agent audits the final draft claim by claim and fails the build on any untraceable number. No agent may invent, round differently, or extrapolate a result.
2. **Figure agents.** All figures are generated by scripts committed to a `paper/figures/` directory (matplotlib, publication style, consistent fonts and units) so that every figure regenerates from the tagged release. No hand-edited figures.
3. **Reference agent.** The bibliography is built from primary sources with DOI verification for every entry; formatting follows the journal style extracted into `paper/JOURNAL-REQUIREMENTS.md`. No citation enters the draft unverified.
4. **Section agents.** Each section is drafted to its word budget by a separate agent working from this outline and the evidence sources listed above. Drafting order: demonstration study first (it feeds the Results and the abstract), then Methods and Results, then Introduction, with the abstract and Implications written last.
5. **Style agent.** Enforce complete sentences throughout, consistent terminology (runstream, pathway, design value, reference set), and the journal's abstract and heading conventions. The manuscript is drafted in Markdown in a `paper/` directory of the repository and exported to Word for ScholarOne at the end.
6. **Review loop.** After assembly, one agent performs a reviewer-simulation pass against JA&WMA's stated review criteria (clarity, efficiency of presentation, technical soundness) and produces a punch list; a revision pass addresses it before the draft goes to Shannon.

## Human-only decisions (for Shannon)

1. The choice of demonstration study.
2. The author list and order, including whether students contributed authorship-level work.
3. Funding acknowledgments and the disclosure statement.
4. Final approval of every claim, the Implications statement, and the submission itself.

## Timeline

After the code prerequisites land, the realistic path is one week to execute the demonstration study, followed by a two-to-three-week drafting cycle through the agent workflow above, ending with Shannon's revision and the ScholarOne submission.
