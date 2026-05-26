# Dependencies

This page is the canonical dependency policy and runtime dependency inventory for `qobuz-dl`. It documents the dependencies declared in `pyproject.toml` and `requirements.txt`, why they exist, where the code uses them, and the allowed paths for future dependency hardening.

## Dependency policy

Every runtime dependency should have one explicit maintenance path:

1. **Remove or replace internally** — use this when the project only needs a small, well-understood behavior that can be covered by tests and maintained locally. Replacement work must be preceded by characterization tests for the current user-visible behavior.
2. **Optionalize** — use this when a dependency supports a secondary feature and core scripted download flows should not require it.
3. **Pin and audit** — use this when a dependency is still the safest owner for specialized or high-consequence behavior. Keep the version policy visible and review security or compatibility updates deliberately.
4. **Vendor with provenance** — use this only as a last-resort path when removing, optionalizing, or pinning/auditing is worse. Vendored code must record upstream source, version or commit, license, retained API surface, local modifications, refresh procedure, and tests.

Vendoring transfers maintenance responsibility to this repository. It is not automatic risk removal: the project becomes responsible for tracking upstream fixes, security issues, license preservation, and local patch correctness.

Later dependency removals require characterization tests first. Default tests must continue to mock network behavior and must not require Qobuz credentials, live Qobuz or Last.fm access, an active subscription, or real media downloads.

`mutagen` is intentionally retained as a pin-and-audit dependency because audio metadata writing is specialized and high-consequence. A poor replacement can corrupt files, omit tags, or create compatibility bugs across players. Any future decision to vendor or replace metadata support should go through a separate architecture review with stronger fixture coverage.

## Dependency inventory

| Dependency | Declared version | Current path | Used for | Main import sites |
|---|---:|---|---|---|
| `mutagen` | `>=1.47,<2` | Pin and audit; retained intentionally | Read and write FLAC and MP3 metadata | `qobuz_dl/metadata.py`, `qobuz_dl/utils.py` |

## Removed dependency replacements

| Removed dependency | Replacement |
|---|---|
| `colorama` | Project-owned ANSI string constants in `qobuz_dl/color.py` |
| `pathvalidate` | Project-owned generated-name sanitizer in `qobuz_dl/sanitize.py` |
| `tqdm` | Narrow project-owned progress logging around streamed downloads |
| `pick` | Built-in numbered prompts, comma/range multiselect, yes/no confirmation, and quality choice in `qobuz_dl/core.py` |
| `beautifulsoup4` | Small `html.parser`-based Last.fm playlist extractor in `qobuz_dl/core.py`, covered by fixtures |
| `requests` | Project-owned stdlib `urllib` HTTP boundary in `qobuz_dl/http.py` for JSON API calls, text fetches, and streamed downloads |

## Active dependency role

### `mutagen`

`mutagen` handles audio metadata:

- `qobuz_dl/metadata.py` writes FLAC pictures and ID3 tags
- `qobuz_dl/utils.py` reads metadata from MP3 and FLAC files

`mutagen` remains external by design. Keep the bounded range `mutagen>=1.47,<2`, keep it visible in dependency audits, and avoid replacing, forking, or vendoring it without a dedicated metadata architecture review.

## Project-owned replacement roles

### Terminal colors

`qobuz_dl/color.py` exports the stable constants used by the application: `DF`, `BG`, `RESET`, `OFF`, `RED`, `BLUE`, `GREEN`, `YELLOW`, `CYAN`, and `MAGENTA`. They are ANSI strings, with a small logging autoreset hook so colored log messages do not leak terminal state after each record.

### Sanitization

`qobuz_dl/sanitize.py` owns the generated filename/path sanitization needed by album, artist, playlist, folder, and track naming. It is intentionally project-specific rather than a full `pathvalidate` clone.

### HTTP

`qobuz_dl/http.py` is the only production HTTP boundary. It uses stdlib `urllib` and exposes narrow behavior for:

- GET requests with params and headers
- JSON responses for Qobuz API calls
- text fetches for Last.fm and bundle pages
- streamed downloads with content-length mismatch detection
- project-owned HTTP errors

Future optional HTTP backends can fit behind this boundary, but the default runtime must not import `requests`.

## Dependency source of truth

- `pyproject.toml` is the package metadata source of truth
- `uv.lock` captures the resolved dependency graph for reproducible local installs
- `requirements.txt` exists only for compatibility with legacy requirements-based workflows

Use `uv` by default. Do not document `pip` or direct `python` commands as the default project workflow.

When runtime dependencies change, update `pyproject.toml`, keep `requirements.txt` synchronized while it exists, and refresh `uv.lock` with `uv lock` or `uv sync`.
