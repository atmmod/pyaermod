# QA: PR #70 review verification

- 9 of 10 findings confirmed by reproduction; behaviour-dependent ones confirmed by EPA's AERMOD v26135 (probes 33-33e).
- Finding 5 partly refuted: pyaermod's unit handling for PROFBASE matches meset.f (W203, value kept in metres).
- Highest severity: finding 3 (partial year can become the annual NO2 design value).
- Report: .10x/reviews/2026-11-17-pr70-review-verification.md
