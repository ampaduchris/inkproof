# Deviations

Every departure from `docs/spec.md`, numbered, with the reason. Any hand edit to code by the owner is logged here. Session 1.2 also logs the places where the adopted spec goes beyond or differs from `BUILD.md`, so that the owner sees each one.

| # | Departure | Reason | Logged |
| --- | --- | --- | --- |
| DEV-001 | `BUILD.md` lists no second extraction engine at run time. The spec makes pdfminer.six (MIT) a runtime dependency so that two-engine verification works after a plain install. | Verification needs two engines with no shared parsing code (REQ-047). The dependency was already added in session 1.1. | 1.2 |
| DEV-002 | `BUILD.md` names `pdftotext` as the third cross-check. The spec uses pypdf instead, as a development dependency used by the tests. | Owner decision of 15 Nov 2026. Reasons and measurements: spec section 12.2. The CI step that installed poppler is removed. | 1.2 |
| DEV-003 | `BUILD.md` plans 4 patterns x 5 layouts (20 cases). The spec plans 30: the two terms are added. | The test plan did not cover `--terms`. | 1.2 |
| DEV-004 | `BUILD.md` and the 1.1 session text list 15 fixtures. The spec lists 24 (5 removal layouts, 10 audit fixtures, 9 control and edge fixtures). | Each added fixture proves a MUST that no other fixture reaches. Session 1.3 is sized for 15; the owner may want to resize it. | 1.2 |
| DEV-005 | Short terms (under three units) are rejected unless `--allow-short-terms` is given (REQ-012). Not in `BUILD.md`. | A two-letter term would remove large parts of a document and the report could not say why. | 1.2 |
| DEV-006 | Loose matches (stray white space, hyphenation at a line end) are removed by default and reported as a separate kind. Not in `BUILD.md`. | PDF text is stored in fragments. Removing only exact matches would under-redact. Loose matching can over-redact (`not able` for `notable`). | 1.2 |
| DEV-007 | The CI traceability step runs `scripts/trace.py --report-only` until session 1.8. `STANDARD.md` control R1 says the script fails CI on an untested MUST. | The spec now has 72 MUSTs and no tests yet; a failing required check would block every pull request until session 1.8. The script still fails on unknown tags, duplicate ids and scope rows with no MUST. Session 1.8 removes the flag. | 1.2 |
| DEV-008 | `apply` writes its report beside the output by default (REQ-005). Not in `BUILD.md`. | `BUILD.md` does not say where it goes. | 1.2 |
