# inkproof: rules for an agent in this repo

- `docs/spec.md` is the sole authority. Prompts never override it. If the spec and a request disagree, stop and say so.
- Tag every test with `@pytest.mark.req("REQ-###")`. `scripts/trace.py` fails CI on an untested MUST.
- Never print, log or report a matched value, term text or text taken from a document.
- Fixtures are generated synthetic PDFs from fixed seeds. No real document enters the repo.
- No model calls. CI never calls a model. No network access at run time.
- Run tests from the lockfile: `uv sync --locked`, then `uv run pytest -q --tb=line`.
- One session, one pull request. Open it as a draft. Never merge or approve.
- Append one row to `docs/BUILD-LOG.md` per session. Log every departure from the spec in `docs/DEVIATIONS.md`.
- British English. Short declarative sentences. No em dashes.
