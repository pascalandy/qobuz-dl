# Vision: Credential-Equivalent Query Exposure

Mode: `pa-vision` / AlignmentDraft
Severity: High
Status: proved

## Request Or Decision

Decide how to reduce credential-equivalent query-string exposure before changing or expanding authentication behavior.

## Current State

`Client.auth()` calls `api_call("user/login", email=email, pwd=pwd)` (`qobuz_dl/qopy.py:166-171`). `_login_params()` places `email`, `password`, and `app_id` into request parameters (`qobuz_dl/qopy.py:80-85`). `api_call()` always sends those parameters through `self.session.get()` (`qobuz_dl/qopy.py:52-55`). The HTTP helper appends params into the URL query string with `urlencode()` (`qobuz_dl/http.py:55-59`).

The same query-string path also carries the post-login `user_auth_token` for favorite requests. `_favorite_params()` adds `user_auth_token` to request parameters (`qobuz_dl/qopy.py:118-130`), and `get_favorite_albums()`, `get_favorite_tracks()`, and `get_favorite_artists()` call that endpoint (`qobuz_dl/qopy.py:219-232`). Tests characterize this token-bearing request shape in `tests/test_qopy_characterization.py:213`, `tests/test_qopy_characterization.py:245`, and `tests/test_qopy_characterization.py:270`.

The saved password value is an MD5 hash of the Qobuz password (`qobuz_dl/cli.py:117-119`), but docs correctly warn that this hash is still used for login and should be treated as secret (`docs/use-cases.md:71`).

The module-usage documentation shows `password = "your_password"` and passes that value directly into `qobuz.initialize_client(email, password, qobuz.app_id, qobuz.secrets)` (`docs/module-usage.md:13-18`). `QobuzDL.initialize_client()` passes `pwd` directly to `qopy.Client` (`qobuz_dl/core.py:193-194`), and `qopy.Client` sends that value as the `password` request parameter. Following the sample literally can therefore put a plaintext password in the query string, or at minimum leaves the documented library contract unclear about whether callers must pass the Qobuz password or the MD5 login value.

## Observed Constraints

- The current reverse-engineered endpoint may expect GET-style parameters; this audit did not verify a supported POST alternative from official docs.
- The app uses stdlib `urllib` through `qobuz_dl/http.py`.
- Tests characterize current request construction, so changing this will need careful regression coverage.
- The public module API and docs need to agree on whether `initialize_client()` expects a raw password or a pre-hashed login value.

## Desired End State

Auth and account-scoped API flows should avoid putting credential-equivalent values in URLs when a supported non-query mechanism exists. If Qobuz only accepts this legacy GET form, the project should document that limitation and prevent accidental logging of full auth or favorite-request URLs.

## Proposed Interaction Or Behavior

- Prefer POST body, headers, or another officially supported auth/token flow if verified.
- If forced to keep GET, redact query strings in any error/log path and document why the risk remains.
- Add focused tests proving no logs or raised errors include login query values or `user_auth_token`.
- Correct module-usage docs so examples do not encourage plaintext password query exposure.

## Design Decisions

- Keep all transport changes inside `qobuz_dl/http.py` and `qobuz_dl/qopy.py`.
- Treat the MD5 password hash as a bearer-equivalent credential for storage and transport decisions.
- Treat raw passwords, MD5 login values, and `user_auth_token` as credential-equivalent.
- Do not modify download flows until auth transport is characterized.

## Patterns To Follow

- Centralize credential redaction.
- Test request construction with fakes.
- Preserve offline default tests.

## Patterns To Avoid

- Do not print full URLs for login, favorite, or signed file URL requests.
- Do not assume HTTPS alone solves URL logging risk.
- Do not introduce a second HTTP boundary to work around `qobuz_dl/http.py`.

## Success Signals

- Login credentials and user auth tokens are not sent in URL query strings, or a documented Qobuz constraint explains why this remains.
- Tests fail if email, password hash, app ID, app secret, or user auth token appears in logs/errors.
- Module-usage docs either hash before calling `initialize_client()` or clearly document the credential contract without exposing plaintext in URLs.
- Auth code remains behind the existing HTTP boundary.

## Open Questions And Risks

- Official current endpoint docs were not accessible, so the supported auth method is not confirmed.
- A transport change could break existing Qobuz compatibility if the legacy endpoint only accepts GET params.

## What Needs Human Review

The maintainer should decide how much compatibility risk is acceptable for replacing legacy GET login behavior. If official docs remain blocked, a live integration spike should be opt-in and credential-protected.

## Recommended Next Phase

`pa-architect` for an auth transport spike, then `pa-tdd` for a small request-construction remediation slice.
