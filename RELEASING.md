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
version DOI plus a concept DOI shared by all versions (pyaermod's
concept DOI is `10.5281/zenodo.23512926`). A release published before
the switch is not archived retroactively.

Check that the switch took: the repository's *Settings → Webhooks* must
list a hook to `zenodo.org/api/hooks/receivers/github/events/`. Zenodo's
list of repositories is a snapshot from its last sync, so a repository
made public after that sync is missing from it until you press *Sync
now*. For v2.2.0 this happened: pyaermod, private until February, was
missing from the list, no hook existed, the first release was not archived, and the release had to be deleted (keeping
the tag) and published again once the hook existed. Publishing again
re-runs `publish.yml`, whose `skip-existing` leaves PyPI unchanged.

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
  previous release's DOI and its comment)
- `README.md` and `docs/index.md` → the "Citing PyAERMOD" section
  (the version number and the `https://doi.org/...` link)

Commit and push that on `main` ("Record the Zenodo DOI for vX.Y.Z").
The tag itself keeps the previous DOI; that is expected, since the DOI
did not exist when the tag was made, and Zenodo's own record carries
the authoritative citation for the tag.

## 4. Desktop builds

Publishing the release also triggers
`.github/workflows/build_desktop.yml`, which builds the desktop app with
PyInstaller on Linux, macOS (Apple silicon) and Windows and attaches
`pyaermod-desktop`, `pyaermod-desktop-macos.zip` and
`pyaermod-desktop.exe` to the release. The macOS bundle is signed with
a Developer ID certificate, notarized by Apple and stapled, which is
what lets it open on other Macs. That needs six repository secrets.

Without the secrets, a release run **fails the macOS job** and attaches
no macOS build (an unsigned one would be blocked by Gatekeeper); the
Linux and Windows jobs are unaffected. A manual run without them still
builds an ad-hoc signed bundle, with a warning, for testing.

### Once: create the signing secrets

All of this needs the Apple Developer Program membership. Nothing below
puts a secret value on a command line or in the shell history: each
`gh secret set` reads a file, or prompts.

1. **Developer ID Application certificate.** In Keychain Access, use
   *Certificate Assistant → Request a Certificate From a Certificate
   Authority* (saved to disk) to make a signing request. At
   <https://developer.apple.com/account/resources/certificates>, add a
   certificate of type *Developer ID Application* with that request
   (only the Account Holder can), download the `.cer` and double-click
   it to add it to the login keychain.
2. **Export it as a `.p12`.** In Keychain Access, under *My
   Certificates*, select the "Developer ID Application: ..." entry (it
   must show its private key beneath it), choose *Export*, pick the
   `.p12` format and give it a strong password. Then:
   ```bash
   base64 -i DeveloperID.p12 | gh secret set MACOS_CERT_P12_BASE64
   gh secret set MACOS_CERT_PASSWORD        # prompts; paste the .p12 password
   ```
3. **The identity name.** It is the quoted name in the output of the
   command below, in the form
   `Developer ID Application: Name (TEAMID)`:
   ```bash
   security find-identity -v -p codesigning
   gh secret set MACOS_SIGN_IDENTITY        # prompts; paste the name, without the quotes
   ```
4. **App Store Connect API key**, which is what the workflow uses to
   talk to the notary service. At
   <https://appstoreconnect.apple.com/access/integrations/api>, create
   a *Team* key with the *Developer* role. Download the
   `AuthKey_XXXXXXXXXX.p8` file (it can be downloaded once), and note
   the *Key ID* and the *Issuer ID* shown on that page:
   ```bash
   base64 -i AuthKey_XXXXXXXXXX.p8 | gh secret set APPLE_API_KEY_P8_BASE64
   gh secret set APPLE_API_KEY_ID           # prompts; the 10-character Key ID
   gh secret set APPLE_API_ISSUER_ID        # prompts; the Issuer ID (a UUID)
   ```
5. Delete the `.p12` and `.p8` files, or move them to a password
   manager. `gh secret list` should now show all six:

   | Secret | Holds |
   |--------|-------|
   | `MACOS_CERT_P12_BASE64` | The Developer ID Application certificate and its private key, as a base64-encoded `.p12` |
   | `MACOS_CERT_PASSWORD` | The password the `.p12` was exported with |
   | `MACOS_SIGN_IDENTITY` | The identity name, `Developer ID Application: Name (TEAMID)` |
   | `APPLE_API_KEY_P8_BASE64` | The App Store Connect API key, as a base64-encoded `.p8` |
   | `APPLE_API_KEY_ID` | That key's Key ID |
   | `APPLE_API_ISSUER_ID` | The Issuer ID of the App Store Connect team |

   Set all six or none: the workflow stops with an error if only some
   are present.

Then run the workflow by hand once, before relying on it for a release
(next section). The first signed build is also the first real test of
`packaging/entitlements.plist`, which grants no hardened-runtime
exceptions; if the signed app fails to start where the ad-hoc one
works, that file is the place to look.

To try the hardened runtime on a local build without the certificate,
re-sign a copy ad-hoc with it. An ad-hoc signature has no Team ID, so
this one test needs library validation switched off, which the release
build does not:
```bash
cat > /tmp/local-test.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>com.apple.security.cs.disable-library-validation</key><true/>
</dict></plist>
PLIST
cp -R dist/pyaermod-desktop.app /tmp/hardened.app
codesign --force --deep -s - --options runtime \
    --entitlements /tmp/local-test.plist /tmp/hardened.app
/tmp/hardened.app/Contents/MacOS/pyaermod-desktop
```

### Every release: check the macOS build

1. The workflow is green for all three systems:
   ```bash
   gh run list --workflow build_desktop.yml --limit 1
   ```
   The macOS job has already checked the signature, started the app
   once, had it notarized, stapled the ticket and asked Gatekeeper about
   the unzipped result. If notarization is refused, the *Notarize the
   macOS bundle* step prints Apple's log, which names each offending
   file.
2. On a Mac, download the asset with a browser (so that it is
   quarantined, as it will be for users), unzip it, and ask Gatekeeper:
   ```bash
   spctl -a -vvv -t exec ~/Downloads/pyaermod-desktop.app
   ```
   The answer must be `accepted` with
   `source=Notarized Developer ID`.
3. Double-click the app. It must open without a warning beyond the
   usual "downloaded from the Internet" confirmation, and show the
   Project step.

### Running the build again

The workflow can be started by hand, from the *Actions* tab or with:
```bash
gh workflow run build_desktop.yml --ref main
gh run watch
```
A manual run uploads the three builds as workflow artifacts
(`gh run download`) and attaches nothing to any release. To rebuild the
assets of an existing release, for instance after adding the secrets or
renewing the certificate, re-run that release's own run, which uploads
over the assets already there:
```bash
gh run list --workflow build_desktop.yml --event release
gh run rerun <run-id>            # add --failed to redo only the failed jobs
```
A re-run uses the workflow and the spec as they were at the release's
tag, so this cannot sign v2.2.0 or an earlier release, whose tags
predate the signing steps.

### Certificate and key expiry

A Developer ID Application certificate is valid for five years; the
date is shown in Keychain Access and on the developer site's
certificate list. Apps signed while it was valid keep working after it
expires (the signature carries a secure timestamp), but new builds
cannot be signed with it: the *Import the Developer ID certificate*
step fails because the identity is no longer valid. To renew, create a
new certificate (steps 1 to 3 above) and replace
`MACOS_CERT_P12_BASE64`, `MACOS_CERT_PASSWORD` and, if the name
changed, `MACOS_SIGN_IDENTITY`. Do not revoke the old certificate
unless its key leaked: revoking invalidates every app signed with it.

The API key does not expire, but stops working if it is revoked or if
the membership lapses, and notarization also stops when Apple is
waiting for an updated agreement to be accepted in the developer
account. In each case the *Notarize the macOS bundle* step fails with
Apple's message.

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
source (requires `gfortran` via `brew install gcc`). `BIN_DIR=<dir>`
builds into another directory instead, and each binary's build record
(SHA-256, compiler version, compile and link flags, and AERMOD's banner
version) is printed as it is linked; quote the SHA-256 when attaching a
binary to a release. The other `scripts/build_*.sh` scripts take the same
`BIN_DIR` and print the same record. `make test-binaries` always tests
`./bin`, so build release binaries without `BIN_DIR` (or run pytest with
that directory first on `PATH`).
