# Remote branch cleanup (prepared 2026-11-20)

The cloud session could not delete remote branches: the git proxy refuses a delete push (HTTP 403) and there is no
branch-delete tool. Run this from a local checkout. It was prepared from the state of `origin` on 2026-11-20.

## Safe to delete: the pull request is merged and the branch tip is the commit that was merged

```bash
git fetch origin --prune
git push origin --delete \
  claude/simplify-plotting-geo \
  claude/simplify-gui \
  claude/fix-igra-missing-values \
  claude/simplify-small-duplicates \
  claude/simplify-validator-tables \
  claude/simplify-api-flags \
  claude/simplify-sources-pathways \
  claude/simplify-runner-exec \
  claude/simplify-gui-form-kinds \
  claude/simplify-input-reader \
  claude/simplify-screen-config-checks \
  claude/simplify-demo-blocks \
  claude/review-follow-ups \
  claude/changelog-and-housekeeping \
  claude/regulatory-text-and-met-year \
  claude/docs-accuracy-concision \
  claude/fix-gui-work-safety \
  claude/fix-deck-writer-reader \
  claude/fix-validator-aermod-semantics \
  claude/fix-output-parsers \
  claude/fix-postprocessing-tools \
  claude/fix-geospatial-exports \
  claude/fix-runner-lifecycle \
  docs/track-practice-deck \
  fix/rectable-rank-fields \
  feat/browser-aermod \
  fix/gui-docs-and-macos-signing \
  chore/untrack-manuscript-plan \
  docs/zenodo-doi-v2.2.0 \
  test/roundtrip-zero-terrain-rows \
  claude/fix-j01-warning-count \
  claude/adoring-margulis-f46010 \
  claude/skip-eventfil-test-unless-26135 \
  claude/e2e-ignore-client-disconnect \
  claude/modest-napier-454c5b \
  claude/modest-wilbur-1cc8b7 \
  claude/fix-e251-line-deposition \
  claude/fix-psd-tail-explicit \
  claude/fix-area-depth-hint-advisory \
  claude/fix-psd-density-convention \
  claude/docs-use-cases \
  claude/docs-gui-seven-steps \
  claude/fix-epa-parity-fixtures \
  claude/fix-output-mtime-race
```

`claude/fix-plot-export-crashes` (#96, merged at 39479a1) also belongs in this list. So does `claude/simplify-output-parser` (#85, merged at 054c87b).

## Do not delete without a decision

| Branch | Last commit | Why it is listed |
|---|---|---|
| `claude/blissful-gauss-6n1wht` | 2026-11-18 | PRs #62 and #68 to #71 merged, but the tip (05fd79c) is past the last merged head (4b97cfb): it has commits no PR carried. |
| `claude/fixes-from-use-cases` | 2026-10-19 | PR #48 merged at 23b12b7, but the tip is 3d76d76: commits after the merge. |
| `claude/fix-use-case-library-bugs` | 2026-10-15 | PR #43 was closed without merging. |
| `claude/festive-pascal-inqv9c` | 2026-11-16 | No pull request. |
| `claude/simplify-postfile-header` | 2026-11-20 | No pull request. An attempt at sharing POSTFILE header parsing that was not taken (it changed behaviour); kept for reference, safe to delete. |
| `claude/codebase-review-2026-11-18` | 2026-11-19 | No pull request. The review report and raw findings (`.10x/reviews/`). |
| `claude/codebase-review-2026-11-18-4uyhje` | 2026-11-20 | No pull request. The cloud session's copy of the above, with the handoff, the local-verification prompt and this file. |
| `release/v2.2.0` | 2026-10-20 | PR #56 merged. A release branch; kept in case anything refers to it. |

None of these is contained in `main` by ancestry, because every merge was a squash.

## Never delete

`main`, `gh-pages`, and any branch a workflow deploys from.

## Local

Not reachable from the cloud: `git worktree prune`, then `git branch --merged origin/main` and delete what is listed,
including `backup/codebase-review-local` once you no longer want it.
