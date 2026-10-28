# PR #70 pytest CI correction

## Confirmed cause

[Actions run 40628327682](https://github.com/rooster51/AlphaOS/actions/runs/40628327682),
pytest job `122618529291`, tested the merge of `e2145ab` into `77ef046`.
It finished with **1 failed, 878 passed, 431 errors and 64 subtests passed**.

The shared REST/MCP fixtures patched Starlette `State` with
`monkeypatch.setattr(app.state, 'service', ...)` or `archive_research`.
Those attributes are implemented through `State.__getattr__/__setattr__` and
stored in `State._state`, not directly in the instance `__dict__`.

CI installed **pytest 9.2.0** because the workflow installs unpinned `pytest`.
Its `MonkeyPatch.setattr` records the old value from the instance `__dict__`
when there is no data descriptor. For Starlette State this records `NOTSET`,
even though `getattr` found a service. Teardown consequently deletes the service
instead of restoring it. Subsequent fixtures cannot find `archive_research`.
Deletion of `service` also explains the legacy unsupported-symbol route returning
500 instead of its expected 400. These are test-fixture state leaks, not evidence
that quote verification or entry-record calculations failed.

Controlled reproduction on the unchanged PR head, holding FastAPI 0.162.0 and
Starlette 1.10.0 constant:

```text
python -m pytest tests/test_research2_api.py::test_market_end_to_end_rest_and_oauth_mcp tests/test_research_api.py::test_rejects_unknown_symbol_without_provider_call -q

pytest 9.1.1: 3 passed
pytest 9.2.0: 2 passed, 1 setup error (archive_research deleted after first use)
pytest 9.2.0 after correction, plus restoration regressions: 6 passed
```

## Environment comparison

| Component | Failed GitHub job | Existing local environment | Isolated reproduction/validation |
| --- | --- | --- | --- |
| OS | Ubuntu 24.04.5 | Windows 11 | Windows 11 |
| Python | 3.12.14 | 3.12.14 | 3.12.14 |
| pytest | 9.2.0 | 9.1.1 | 9.1.1 control, then 9.2.0 |
| FastAPI | 0.162.0 | 0.141.1 | 0.162.0 |
| Starlette | 1.10.0 | 1.7.0 | 1.10.0 |
| pandas | 3.1.0 | 3.0.6 | 3.0.1 |
| NumPy | 2.5.4 | 2.5.3 | 2.5.4 |
| MCP | 2.2.0 | 2.2.0 | 2.2.0 |

Freebuff reported **1,310 tests and 64 subtests passed**, but the report does not
include a complete local package manifest. The existing local environment and
controlled pytest-only experiment explain how an older successful environment
can mask this failure; they are not a claim to have captured Freebuff's exact
environment. OS differences are not required to reproduce the failure.

Installing the CI pandas wheel locally hit Windows Application Control on a
compiled pandas DLL. No OS policy was changed. Local full validation therefore
uses the already working pandas 3.0.1; the new Linux Actions run is the verification
for CI's pandas 3.1.0 and complete clean-resolved dependency environment.

## Small correction

Only the three fixture assignments change to
`monkeypatch.setitem(app.state._state, key, service)`. This explicitly patches
the dictionary that State actually uses; dictionary teardown restores the original
value on both pytest versions. No dependency downgrade or production workaround
is needed.

`tests/test_api_fixture_state.py` invokes each real fixture twice and checks that
all original state keys and object identities survive teardown. The legacy
REST/MCP fixture behavior and archive-backed service injection are preserved.

Targeted validation: **163 passed** across fixture restoration, structure
provenance, entry evidence, provenance/entry integration, research REST and OAuth
MCP tests. The complete Python suite and new Actions results are reported with
the correction commit. Existing quote/source/freshness, natural pricing,
fail-closed and entry-evidence behavior are untouched.

The patch is made in an isolated checkout and shared by a normal fast-forward
commit on `validation/provenance-entry-integration`; no Freebuff working files
are edited. Cloudflare configuration, PR #67, website code, production services,
credentials and infrastructure are unchanged. Nothing is merged or deployed.
