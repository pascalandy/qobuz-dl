# Verification Log

Date: 2026-06-22

## Local Commands Run

| Command | Result | Evidence |
|---|---:|---|
| `git status --short --branch` | PASS | Clean baseline: `## master...origin/master` before artifact writes. |
| `git rev-parse master` | PASS | Immutable audited app/base revision after final rebase: `95fa412108e59272a66c017fbe9b9dcf4d791a05`. |
| `git merge-base master HEAD` | PASS | Final comparison base matched `master`: `95fa412108e59272a66c017fbe9b9dcf4d791a05`. |
| `git diff --name-status master...HEAD` | PASS | Final branch diff contained only the 12 files under `artifacts/audit/2026-06-22-fsst-n1-codebase-audit/`. |
| `uv tree --dev --locked` | PASS | Resolved 12 packages; runtime dependency is `mutagen v1.47.0`; dev dependencies are `pytest v9.0.3` and `ruff v0.15.14`. |
| `find qobuz_dl tests -path '*/__pycache__' -prune -o -type f -name '*.py' -print \| sort \| xargs wc -l` | PASS | 5836 total Python lines, including 2583 production lines and 3253 test lines. |
| `curl -I -L --max-time 20 https://developer.qobuz.com` | BLOCKED | DNS resolution failed: `Could not resolve host: developer.qobuz.com`. |
| `curl -I -L --max-time 20 https://static.qobuz.com/apps/api/Qobuz-AppsGuidelines-V1.0.pdf` | BLOCKED | Current fetch returned `HTTP/1.1 403 Forbidden` from CloudFront/S3. |
| `uv run python - <<'PY' ... PY` | PASS | Calculated Python lifecycle day windows, Qobuz page counts, and bitrate/size ratios. Full script and output are recorded below. |
| `just ci` | PASS | Ruff format check, ruff lint, 157 pytest tests, CLI smoke checks, and `uv build` all passed. |
| `rg -n --glob '*.py' "subprocess\|os\\.system\|eval\\(\|exec\\(\|pickle\|tarfile\|zipfile\|chmod\|chown\|shutil\\.unpack_archive\|Popen\|shell=True" qobuz_dl` | PASS | Returned no matches in production package code. |

## Calculation Command

```bash
uv run python - <<'PY'
from datetime import date
from math import ceil

audit_date = date(2026, 6, 22)
print('python_310_eol_month_start_days=', (date(2026, 10, 1) - audit_date).days)
print('python_310_eol_month_end_days=', (date(2026, 10, 31) - audit_date).days)
print('python_313_eol_month_start_days=', (date(2029, 10, 1) - audit_date).days)
print('python_313_eol_month_end_days=', (date(2029, 10, 31) - audit_date).days)
for item_count in (501, 1001, 2500):
    print(f'qobuz_pages_{item_count}=', ceil(item_count / 500))
cd_mbps = 44100 * 16 * 2 / 1_000_000
hires_mbps = 192000 * 24 * 2 / 1_000_000
print('cd_mbps=', round(cd_mbps, 3))
print('hires_24_192_mbps=', round(hires_mbps, 3))
print('qobuz_9_2_vs_cd_ratio=', round(9.2 / cd_mbps, 2))
print('qobuz_2gb_vs_635mb_ratio=', round(2000 / 635, 2))
PY
```

```text
python_310_eol_month_start_days= 101
python_310_eol_month_end_days= 131
python_313_eol_month_start_days= 1197
python_313_eol_month_end_days= 1227
qobuz_pages_501= 2
qobuz_pages_1001= 3
qobuz_pages_2500= 5
cd_mbps= 1.411
hires_24_192_mbps= 9.216
qobuz_9_2_vs_cd_ratio= 6.52
qobuz_2gb_vs_635mb_ratio= 3.15
```

## Current Primary Sources Checked

Retrieved on 2026-06-22.

| Source | Result | Anchor Checked | Why It Matters |
|---|---:|---|---|
| [Qobuz API Terms of Use PDF](https://static.qobuz.com/apps/api/QobuzAPI-TermsofUse.pdf) | PASS | "Application ID", "Application Secret", API access limits, geoblocking/indexing limits, non-certified disclaimer. | Confirms Application ID/secret model, no sharing of app credentials, Qobuz's right to limit/suspend/modify API access, geoblocking/indexing restrictions, and required non-certified disclaimer. |
| [Qobuz audio quality page](https://www.qobuz.com/us-en/audio-quality) | PASS | CD bitrate formula, Hi-Res range, one-hour storage examples, Hi-Res streaming bitrate. | Confirms 24-bit Hi-Res 44.1-192 kHz range, CD bitrate formula, 2 GB per hour for 24/192, 635 MB per hour for CD quality, and 9.2 Mb/s Hi-Res streaming figure. |
| [Python Developer's Guide versions page](https://devguide.python.org/versions/) | PASS | Python 3.10 and 3.13 lifecycle rows. | Confirms Python 3.10 security status with EOL month `2026-10`, and Python 3.13 bugfix status with EOL month `2029-10`. |
| [PEP 619](https://peps.python.org/pep-0619/) | PASS | Lifespan schedule for Python 3.10. | Confirms Python 3.10 source-only security fixes are expected until approximately October 2026. |
| [PEP 719](https://peps.python.org/pep-0719/) | PASS | Lifespan schedule for Python 3.13. | Confirms Python 3.13 security updates are expected until October 2029. |
| [PyPI `mutagen` project page](https://pypi.org/project/mutagen/) | PASS | Latest release metadata. | Confirms latest Mutagen release is `1.47.0`, released 2023-09-03, matching `uv.lock`. |
| [GitHub Actions secure-use docs](https://docs.github.com/en/actions/reference/security/secure-use) | PASS | Third-party action pinning guidance. | Confirms full-length SHA pinning is the immutable action reference. |
| [GitHub `GITHUB_TOKEN` docs](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token) | PASS | Token permission guidance. | Confirms least-required token permissions are recommended, matching the repo's read-only CI permissions. |
| [Microsoft file naming docs](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file) | PASS | Reserved device names and extension-bearing examples. | Confirms Windows treats names such as `NUL.txt` and `NUL.tar.gz` as reserved device-name equivalents. |
| [RFC 6585 section 4](https://datatracker.ietf.org/doc/html/rfc6585#section-4) | PASS | HTTP `429 Too Many Requests` and `Retry-After`. | Confirms `429` is the standard rate-limit status and may include `Retry-After` guidance. |

## Checked, Still Not Verified

| Item | Status | What I Tried | Why It Remains Blocked |
|---|---:|---|---|
| Current official Qobuz endpoint reference, numeric API rate limit, and media byte-rate guidance | BLOCKED | Checked Qobuz Terms, `developer.qobuz.com`, current static Apps Guidelines URL, and Qobuz public audio-quality pages. | Terms reserve the right to limit calls but publish no number in accessible material; developer portal DNS failed; Apps Guidelines PDF returned 403; audio-quality pages state large media sizes but not third-party media transfer limits. |
| Live Qobuz API behavior for `user/login`, `track/getFileUrl`, app secret validation, and rate limiting | BLOCKED | Inspected code and mocked tests only. | Live checks require credentials, active subscription, and real Qobuz API calls, which project docs prohibit for default verification. |
| Real media download/tagging on Qobuz files | BLOCKED | Inspected `downloader.py`, `metadata.py`, and fixture/mocked tests. | Requires live download and media files. Default tests must avoid real media downloads. |
| Windows runtime behavior for reserved device names and missing `%APPDATA%` | BLOCKED | Inspected code path, sanitization tests, and Microsoft file-naming docs. | This audit environment is not Windows. The code evidence and Microsoft docs are enough to log the Windows filename issue and `%APPDATA%` startup issue, but not to reproduce them on Windows. |
| Repository-level GitHub Actions settings and secrets | BLOCKED | Inspected workflow YAML and primary GitHub docs. | Repo settings/secrets are not present in the checkout. |
| Actual user's existing `~/.config/qobuz-dl/config.ini` mode | BLOCKED | Did not inspect user secrets. | Reading real user config would unnecessarily expose sensitive data. Code and docs are enough to log the permission-enforcement issue. |

## Uncertainty Statements

- I am not claiming Qobuz currently enforces a specific numeric API rate limit. I could not verify one from current primary sources.
- I am not claiming Qobuz currently publishes a specific third-party media byte-rate or bandwidth cap. I could not verify one from current primary sources.
- I am not claiming the reverse-engineered Qobuz endpoint names are official. The accessible official sources do not confirm endpoint paths.
- I am not claiming Windows failures are reproduced in this environment. The Windows issues are based on code behavior and Microsoft-documented Windows reserved-name rules.
- I am not claiming default tests cover legal/compliance correctness. They cover functional request construction and offline behavior.
