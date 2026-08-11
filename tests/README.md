# Tests

```bash
pip install -r requirements-dev.txt

pytest                 # everything (~10s)
pytest -m unit         # fast layer only
pytest -m integration
pytest -m e2e
pytest --cov           # coverage summary
pytest tests/unit/test_ranking.py::test_bucket_order_dominates_the_final_ordering
```

Run pytest from the `bierre/` directory. `pyproject.toml` sets `pythonpath = ["."]`,
which is what lets tests `import core` / `import cli` / `import webapp` without the
project being pip-installed.

## Layout

```
tests/
  conftest.py        shared fixtures + the network guard (applies to every layer)
  factories.py       builders for Paper / RankedPaper / RunResult / DomainProfile / …
  fixtures/          example wire payloads, byte-identical to bierre-ca's copy
  support/           test doubles: FakeResponse, ScriptedSession, mock profile API server
  unit/              one module under test, everything else stubbed. No I/O.
    sources/         one file per search-source adapter
  integration/       several real components wired together: filesystem, loopback
                     HTTP, the real ASGI app
  e2e/               the adapter entrypoints themselves: cli.main, POST /api/run
```

Each directory is a package (`__init__.py`), so helpers import as
`from tests.factories import make_paper` and two layers may reuse a filename.

## Which layer does my new test belong in?

| Question | Layer |
| --- | --- |
| Does this function return the right value for this input? | `unit/` |
| Do these two components still agree on the data they exchange? | `integration/` |
| Does the thing a user actually invokes still work? | `e2e/` |

Markers are applied automatically from the directory name (see
`pytest_collection_modifyitems` in `conftest.py`) — you do not decorate tests by hand.

## House rules

1. **No network.** An autouse fixture blocks outbound sockets; only loopback is
   allowed (for the integration tests that start a real local server). If a test
   fails with `Blocked outbound network call`, it is reaching a live API — stub
   the transport with `tests/support/http_doubles.py` instead.
2. **Never write to the checked-in `profiles/` directory.** `YamlProfileRepository()`
   with no argument points at real repository data. Use the `profiles_dir` /
   `yaml_repo` fixtures, which are per-test temp directories.
3. **No real sleeping.** `core.util.http` exposes `sleep_fn` / `jitter_fn`
   parameters; use them (or the `captured_sleeps` fixture) so retry tests assert
   the backoff schedule instead of waiting for it.
4. **Never hand-edit one copy of `tests/fixtures/`.** Those payloads exist twice — here and in
   `bierre-ca/tests/fixtures/` — and are byte-identical on purpose. `tests/fixtures/README.md`
   has the update procedure.
5. **Assert behaviour, not arithmetic.** Relevance scores shift when the optional
   ranking libraries are present or absent, so tests assert ordering, bucketing
   and selection — never an exact percentage.
6. **One reason to fail per test.** Prefer several small tests over one long one;
   `pytest.mark.parametrize` for table-shaped cases.

## CI

`.github/workflows/tests.yml` runs on every push and pull request, on Python 3.11
and 3.12. It runs `pytest -m unit` first for fast feedback, then the full suite
with coverage and `--cov-fail-under=90`.
