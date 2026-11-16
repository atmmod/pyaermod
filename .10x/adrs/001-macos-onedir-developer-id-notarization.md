# ADR-001: Ship the macOS desktop app as a onedir bundle, Developer ID signed and notarized in CI

**Status:** Superseded by ADR-002
**Date:** 2026-11-10
**Feature:** gui-docs-macos-signing
**Author:** 10x-Team (Architect + Staff Engineer)

## Context
The macOS desktop app is a PyInstaller onefile EXE wrapped in a `.app`, carrying only an ad-hoc signature.
Gatekeeper refuses it. Onefile payloads are extracted at run time, so their Mach-O files cannot be signed in
place or inspected by the notary service. The workflow uses no secrets today.

## Decision
- macOS builds use onedir (`EXE(exclude_binaries=True)` → `COLLECT` → `BUNDLE`). Windows and Linux stay onefile.
- PyInstaller signs with the identity in `MACOS_SIGN_IDENTITY` and `packaging/entitlements.plist` (hardened
  runtime). Unset identity keeps today's ad-hoc behaviour for local builds and forks.
- The workflow notarizes with an App Store Connect API key via `notarytool`, staples the `.app`, and ships a
  `ditto` zip. Signing steps are conditional on the secrets being present.

## Alternatives Considered
| Alternative | Pros | Cons | Why Not |
|-------------|------|------|---------|
| Document `xattr -dr com.apple.quarantine` only | No cost, no secrets | Users must run a terminal command; still looks like malware | Does not fix the problem |
| Keep onefile, sign the outer binary | Smallest diff | Cannot be notarized; PyInstaller 7 makes it an error | Not viable |
| Signed `.dmg` instead of zip | Nicer install UX | More steps, asset rename | Not needed to pass Gatekeeper; can follow later |
| Apple ID + app-specific password for notarytool | Simpler to create | Tied to a personal account, 2FA churn | API key is the CI-appropriate credential |

## Consequences
### Positive
- App opens normally on macOS; removes the PyInstaller 7 onefile-bundle error ahead of time.
### Negative
- Release now depends on six secrets and a certificate that expires (5 years).
- Notarization adds minutes to the release job.
### Risks
- Entitlements too narrow → app crashes under hardened runtime. Mitigation: CI launches nothing, so verify the
  first signed build by hand; start with the standard PyInstaller set.
- Secrets exposed to `workflow_dispatch`. Mitigation: no `pull_request` trigger; secrets only read in the macOS job.

## Dependencies
- Maintainer's Apple Developer Program membership and Developer ID Application certificate.
- Constrains a future Intel/universal2 build to reuse the same signing steps.
