# Vision: Qobuz API Credential And Certification Boundary

Mode: `pa-vision` / AlignmentDraft
Severity: High
Status: proved

## Request Or Decision

Decide how to bring `qobuz-dl`'s Qobuz API credential and certification story into a client-safe state before expanding API functionality or presenting the app as production-stable.

## Current State

The app fetches `https://play.qobuz.com/login`, locates the web bundle, and extracts production app ID and app secrets from that JavaScript bundle (`qobuz_dl/bundle.py:32-80`). First-run config writes those values into `config.ini` (`qobuz_dl/cli.py:140-148`). The API client then sends `X-App-Id` and validates candidate secrets against `track/getFileUrl` (`qobuz_dl/qopy.py:37-50`, `qobuz_dl/qopy.py:237-255`).

Qobuz's API Terms define Application ID and Application secret as identifiers Qobuz grants to a developer, state that they are required to access the API, and state they must not be shared with a third party. The terms also say Qobuz may modify, suspend, or limit API use without notice and require applications to display: `This application uses the Qobuz API but is not certified by Qobuz.`

The README only says the tool was written for educational purposes, that users accept the Qobuz API Terms, and that `qobuz-dl` is not affiliated with Qobuz (`README.md:121-124`). It does not use the required certification wording.

The package metadata also declares `Development Status :: 5 - Production/Stable` (`pyproject.toml:19`). That classifier is a public packaging signal and should be reconciled with the credential/certification boundary before the project is presented as production-stable.

## Observed Constraints

- Official endpoint-level docs were not accessible during this audit.
- The current app appears to rely on reverse-engineered behavior for its core download flow.
- Users still need an active Qobuz subscription; this issue is not about bypassing account eligibility.
- The audit did not exercise live Qobuz API calls.

## Desired End State

The project should make the official/unofficial boundary explicit and should not imply that scraped app credentials are equivalent to Qobuz-issued developer credentials. The user-facing docs and CLI should display or link the required non-certified Qobuz API disclaimer exactly. Any future auth work should treat official credentials, user-provided credentials, or a documented partner flow as the safer target state.

## Proposed Interaction Or Behavior

- On first run and in docs, state plainly that the tool is not certified by Qobuz.
- Document that endpoint behavior and app-secret extraction are fragile because official endpoint docs were not verified.
- Avoid adding broader API features until the auth/credential model is settled.

## Design Decisions

- Keep Qobuz-specific risk at the auth/API boundary, not scattered across download code.
- Treat `Bundle` scraping as a compatibility fallback, not as a clean official integration.
- Separate legal/compliance language from marketing language.

## Patterns To Follow

- Use primary-source language for Qobuz terms.
- Keep endpoint claims qualified unless verified from current official docs.
- Prefer a future design where users bring explicit credentials or the project obtains a legitimate app credential path.

## Patterns To Avoid

- Do not claim official SDK parity.
- Do not describe scraped web-player app secrets as project-owned credentials.
- Do not bury the certification disclaimer in vague "not affiliated" language.
- Do not add catalog-scale scraping or indexing features.

## Success Signals

- README and CLI display the required Qobuz non-certified disclaimer.
- Package metadata no longer overstates production readiness, or the compliance boundary has been remediated enough to justify the classifier.
- Docs clearly separate verified official terms from reverse-engineered endpoint behavior.
- The auth layer has an explicit design note that names the credential source and risk.
- Future API work has acceptance criteria that do not depend on unverified official endpoints.

## Open Questions And Risks

- Current official Qobuz developer docs and numeric rate limits are blocked: `developer.qobuz.com` did not resolve here, and the Apps Guidelines PDF returned 403.
- The app may continue to work technically while remaining fragile from a terms/compliance perspective.
- Fixing this fully may require product/legal judgment, not only code.

## What Needs Human Review

The maintainer needs to decide whether to keep the current reverse-engineered credential path with stronger disclaimers, seek a legitimate Qobuz app credential path, or narrow the project description so it does not appear to be an official or certified integration.

## Recommended Next Phase

`pa-architect` for an auth/compliance boundary design, then `pa-plan-slicer` for small remediation slices.
