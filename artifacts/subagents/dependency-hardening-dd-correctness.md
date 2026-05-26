I did **not write** `/artifacts/subagents/dependency-hardening-dd-correctness.md` because the task also says **read-only only / do not edit files**. Findings below are the requested artifact content.

# Dependency hardening due diligence — correctness

## Validation summary

- `git status --short`: working tree has many modified/untracked files, including implementation artifacts.
- `just ci`: **passed** — 30 tests, Ruff, smoke help, build.
- `uv tree --no-dev`: runtime tree is only:
  - `qobuz-dl v0.9.9.10`
  - `mutagen v1.47.0`
- Production grep found **no imports/references** to removed runtime deps: `requests`, `colorama`, `pathvalidate`, `tqdm`, `pick`, `bs4`/`BeautifulSoup`.
- `pyproject.toml` and `requirements.txt` only declare `mutagen>=1.47,<2`.
- `uv.lock` still contains `colorama` only as a Windows-only transitive dev dependency of pytest, not runtime.

## Findings

### P3 — HTTP boundary behavior is under-tested despite AC-4/AC-7 coverage claims

**Evidence**

- `qobuz_dl/http.py` owns important behavior:
  - `get()` and HTTPError mapping: `qobuz_dl/http.py:63-86`
  - `stream_download()`: `qobuz_dl/http.py:100-134`
  - content-length parsing/check: `qobuz_dl/http.py:115-116`, `qobuz_dl/http.py:133`
- Existing tests monkeypatch `qobuz_dl.downloader.http.stream_download` instead of testing the real implementation:
  - `tests/test_bundle_downloader_characterization.py:83-92`
  - `tests/test_bundle_downloader_characterization.py:106-111`
- No tests import or directly exercise `qobuz_dl.http.HttpClient`, `HttpStatusError`, `HttpRequestError`, real param encoding, header forwarding, HTTPError mapping, or real content-length mismatch logic.

**Risk**

Regression in the new urllib replacement could break all live API/download flows while tests still pass. This is the main remaining coverage gap for removed `requests`/`tqdm`.

**Recommended fix**

Add `tests/test_http.py` with offline monkeypatched `qobuz_dl.http.urlopen` fakes covering:

1. `get()` appends query params and forwards headers.
2. `HTTPError` becomes an `HttpResponse` and `raise_for_status()` raises `HttpStatusError`.
3. `URLError`/`OSError` becomes `HttpRequestError`.
4. `stream_download()` writes chunks and calls progress.
5. `stream_download()` raises `ConnectionError` on content-length mismatch.
6. Explicit policy test for absent/malformed `content-length`.

---

### P3 — Test fake still exposes stale `requests` API shape

**Evidence**

- `tests/test_bundle_downloader_characterization.py:9-21` defines `FakeHTTPResponse.iter_content()`, which is a `requests.Response`-style API.
- Current production `Bundle` no longer uses `iter_content`; this method is dead in the fake.

**Risk**

Low, but it can hide accidental drift back toward requests-shaped assumptions in tests.

**Recommended fix**

Remove unused `iter_content()` from the fake, or split HTTP-boundary tests into dedicated urllib-shaped fakes.

## AC check

- AC-1: Pass — removed production deps are gone.
- AC-2: Pass — color constants are strings.
- AC-3: Mostly pass — sanitizer behavior characterized for current generated names.
- AC-4: Implementation pass, coverage gap noted above.
- AC-5: Pass — built-in interactive prompts covered.
- AC-6: Pass — Last.fm parser covered with fixtures.
- AC-7: Implementation pass, coverage gap noted above.
- AC-8: Mostly pass — offline fakes exist; HTTP boundary itself under-tested.
- AC-9: Pass — runtime metadata only keeps mutagen.
- AC-10: Pass — dependency/packaging/CLI/examples docs updated.
- AC-11: Pass — default tests are offline.
- AC-12: Pass — `just ci` passed locally.

## Overall verdict

No P0/P1/P2 correctness blockers found. The dependency removals appear real for production runtime. The main remaining issue is **test confidence around the new stdlib HTTP boundary**.