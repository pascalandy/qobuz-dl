# Vision: Windows Reserved Filename Gap

Mode: `pa-vision` / AlignmentDraft
Severity: Medium
Status: proved

## Request Or Decision

Decide how far the filename sanitizer must go to support the package's OS Independent classifier and Windows users.

Verification caveat: Windows runtime reproduction remains blocked because this audit environment is not Windows.

## Current State

`pyproject.toml` declares `Operating System :: OS Independent` (`pyproject.toml:18-29`). The sanitizer knows about Windows device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1` through `COM9`, `LPT1` through `LPT9`) and returns an empty string when the whole sanitized value exactly matches one (`qobuz_dl/sanitize.py:5-12`, `qobuz_dl/sanitize.py:32-34`).

Generated track basenames are sanitized and truncated, then the extension is appended (`qobuz_dl/downloader.py:252-256`). A custom track format that renders exactly as `CON` becomes an empty basename before the audio extension is appended, but extension-bearing reserved stems such as `CON.txt` are not rejected by the current full-string equality check. Microsoft documents Windows reserved device names and says those names followed immediately by an extension, such as `NUL.txt` and `NUL.tar.gz`, are equivalent to the reserved name. Microsoft also reserves COM/LPT names using superscript digit one, two, and three (`COM`/`LPT` plus U+00B9, U+00B2, or U+00B3). The current sanitizer set does not include those superscript variants. That makes extension-bearing reserved stems and superscript COM/LPT names the risky cases.

The audit environment is not Windows, so I did not reproduce an OS-level failure. The issue is logged because the code itself attempts to address Windows reserved names but only covers exact full-string matches.

## Observed Constraints

- The project intentionally implements only the sanitizer behavior it needs, not a full `pathvalidate` clone.
- Reintroducing a dependency only for this gap would conflict with the dependency-hardening direction unless justified.
- Empty sanitized names also need a fallback naming policy.
- Primary source: [Microsoft file naming docs](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file), reserved names section.

## Desired End State

Generated file and folder names should avoid Windows reserved device stems even when extensions or suffixes are present, or the project should narrow its platform claim. The fix should remain project-owned and test-covered.

## Proposed Interaction Or Behavior

- Normalize the candidate basename and check the stem before adding the audio extension.
- Provide a deterministic fallback for empty or reserved names.
- Add tests for `CON`, `CON.txt`, `AUX.flac`, `COM1`, `LPT9`, superscript COM/LPT names using U+00B9/U+00B2/U+00B3, trailing spaces/dots, and normal names.

## Design Decisions

- Keep sanitizer behavior small and local.
- Test behavior as generated names, not only raw sanitizer strings.
- Avoid changing user-provided download directory semantics.

## Patterns To Follow

- Keep platform compatibility claims tied to tested behavior.
- Prefer deterministic replacement over silent empty paths.
- Add Windows-specific cases to existing sanitization characterization tests.

## Patterns To Avoid

- Do not re-add broad dependencies without a fresh dependency-policy decision.
- Do not claim Windows runtime proof from a non-Windows audit environment.
- Do not silently collapse multiple tracks into the same fallback filename.

## Success Signals

- Sanitization tests cover reserved stems with and without extensions, including Microsoft-documented superscript COM/LPT variants.
- Generated filenames remain stable and collision-resistant.
- Either Windows compatibility is strengthened or the classifier/docs are narrowed.

## Open Questions And Risks

- Full Windows path-length behavior was not reproduced here.
- Some existing users may already rely on current loose sanitization for non-Windows file names.

## What Needs Human Review

The maintainer should decide whether OS Independent remains a hard promise or whether docs should state "tested primarily on Linux/macOS, best-effort Windows support."

## Recommended Next Phase

`pa-tdd` for a focused sanitizer test-and-fix slice.
