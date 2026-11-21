# Mutation testing record (REQ-092)

Date: 2026-11-21
Total mutants: 1104
Killed (including timeouts): 914
Score: 82.8%

Floor: 80% (spec REQ-092). Met.

## What was run
- Tool: mutmut 3.8.1, run locally with `uv run mutmut run` (not in CI; STANDARD.md R2 gate is Release).
- Target: `src/inkproof/matcher.py` and `src/inkproof/verify.py`. Configuration is `[tool.mutmut]` in `pyproject.toml`.
- Tests: the whole suite (`tests/`), which includes the 1.9 exact-value tests in `tests/test_verify_units.py`.
- Time: 7 minutes 49 seconds wall clock on the owner's machine. The cap this session set is 20 minutes.
- Python and dependency versions are those in `uv.lock`.

## Counts
| Status | Mutants |
| --- | --- |
| Killed | 907 |
| Timeout (counted as killed) | 7 |
| Segfault (not counted as killed) | 8 |
| No tests (not counted as killed) | 6 |
| Survived | 176 |

Before the 1.9 tests the run gave 845 killed, 6 timeouts, 239 survivors: 77.1% counting timeouts as killed.

## Survivors reviewed
All 176 survivors were grouped by function. The diffs of ten (sampled evenly) were read in full. The rest are not read; the table says so. Counts are mutants that survived.

| Function | Survived | Class | Note |
| --- | --- | --- | --- |
| `page_text_with_glyphs` | 30 | Four read: thresholds and defaults | For example `>` to `>=` on a 0.4 em line-break test. Fixtures are not near the boundary. The other 26 are not read. |
| `verify` | 26 | Mixed | Some are real gaps: page numbering `start=1` to `start=2` in the V2 findings, and the default in a maximum. Page numbers in V2 survivors are not asserted. Follow-up, not closed. |
| `_action_xrefs_and_dicts` | 24 | Not read | Tests added in 1.9 killed 48 of 72; the rest are not classed. |
| `v3_groups` | 23 | Not read | Not classed. |
| `v4_by_object` | 18 | Two read: cosmetic | An omitted `compressed=False` argument and an encoding name in capitals. The other 16 are not read. |
| `decode_bytes` | 14 | Not read | Tests added in 1.9 killed 19 of 33; the rest are not classed. |
| `revision_count` | 9 | Real gap | The engine's own count is not tested against the `%%EOF` count when they differ. Follow-up, not closed. |
| Others (11 functions) | 32 | Not individually read | One to six each. |
| `matcher.py` (all) | 8 | Not read | Not classed. |

## Not verified
- 166 of the 176 survivors were not read.
- Segfault mutants (8) were not counted as killed. mutmut reports them separately; counting them would give 83.5%.
- Whether any survivor hides a bug in a path the fixtures do not reach.
