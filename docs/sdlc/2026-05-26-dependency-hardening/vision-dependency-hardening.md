# Dependency Hardening Vision

## Request / Decision

Move `qobuz-dl` toward a smaller, safer dependency surface because the upstream project is not maintained and unbounded dependency updates can break compatibility or introduce vulnerabilities.

Direction is settled for the full dependency-hardening effort:

- Modernize the project runtime target to Python `>=3.10`.
- Create a dependency policy document before removing or vendoring libraries.
- Reduce dependencies in phases, starting with low-risk utility replacements.
- Keep `mutagen` pinned and audited instead of forking or rewriting audio metadata support in the first pass.
- Treat vendoring as a controlled last-resort protocol, not the default answer to dependency risk.

## Current State

Repository evidence shows these direct runtime dependencies in `pyproject.toml` and `requirements.txt`:

- `beautifulsoup4`
- `colorama`
- `mutagen`
- `pathvalidate`
- `pick==1.6.0`
- `requests`
- `tqdm`

`uv tree --no-dev` resolves a larger runtime graph because `beautifulsoup4` and `requests` pull transitive packages. The lockfile carries version branches for older Python support and newer Python runtimes. In the Python `>=3.10` branch, several resolved packages have already moved beyond Python 3.8:

- `requests 2.34.2` requires Python `>=3.10`
- `urllib3 2.7.0` requires Python `>=3.10`
- `pathvalidate 3.3.1` requires Python `>=3.9`
- `soupsieve 2.8.4` requires Python `>=3.9`

The project currently declares `requires-python = ">=3.8"`, while CI context includes Python 3.8 and 3.13. That is workable only by carrying legacy dependency branches. If the project wants simpler dependency maintenance and current dependency versions, Python support should move to `>=3.10` deliberately and be reflected everywhere.

## Desired End State

The project should have an explicit dependency policy and a dependency surface small enough to understand, test, and maintain without relying on the abandoned upstream project.

Target state:

1. Python support is modernized to `>=3.10` so dependency resolution, CI, docs, and packaging metadata agree.
2. Runtime dependencies are categorized as:
   - remove and replace internally,
   - make optional,
   - keep pinned and audited,
   - or vendor only with provenance and tests.
3. Most lightweight dependencies are removed or replaced by small internal modules.
4. `requests` is replaced only after an internal HTTP boundary and mocked behavior tests exist.
5. `mutagen` remains an external dependency for now, pinned and audited, because audio metadata writing is specialized and risky to reimplement casually.
6. Any future vendoring uses a documented protocol: upstream source, version/commit, license, retained API surface, local changes, refresh procedure, and tests.
7. Replacement work proceeds only after tests capture the behavior currently provided by each dependency.

## Phased Direction

### Phase 1 — Policy And Runtime Baseline

Purpose: make the project’s dependency rules explicit before code churn starts.

Decisions:

- Add a dependency policy document.
- Modernize `requires-python` from `>=3.8` to `>=3.10`.
- Align CI, docs, package metadata, and lockfile with Python `>=3.10`.
- Document the dependency categories: remove, optionalize, pin/audit, or vendor.
- Name `mutagen` as the retained pinned/audited dependency.

Success signals:

- A maintainer can explain why each runtime dependency exists and what its future path is.
- `pyproject.toml`, CI, docs, and `uv.lock` no longer contradict each other on Python support.
- The project has an explicit rule that vendoring is not risk removal unless maintenance ownership is accepted.

### Phase 2 — Characterization Tests Before Replacement

Purpose: prevent dependency removal from changing behavior silently.

Decisions:

- Add tests around the behavior currently delegated to dependencies.
- Mock network behavior; do not require Qobuz credentials, live Qobuz API calls, Last.fm availability, or real downloads by default.
- Cover filename/path sanitization, progress/download behavior, Last.fm parsing, HTTP error behavior, and interactive selection behavior where feasible.
- Add limited metadata tests only where fixtures are practical and stable.

Success signals:

- Each dependency-removal PR has tests that describe expected user-visible behavior.
- The test suite catches behavior drift before libraries are removed.
- `just ci` remains the main proof command.

### Phase 3 — Remove Low-Risk Utility Dependencies

Purpose: shrink the dependency surface where the replacement is smaller than the dependency.

Candidate removals:

- Replace `colorama` with a tiny internal terminal color module.
- Replace `pathvalidate` with a project-specific filename/path sanitizer.
- Replace or optionalize `tqdm` with a small internal progress reporter.

Success signals:

- These removals reduce direct runtime dependencies without changing CLI behavior materially.
- Sanitization behavior is explicitly tested, especially illegal characters, reserved names, empty names, long paths, and cross-platform edge cases.
- Download progress remains useful but is not over-engineered.

### Phase 4 — Simplify Optional/User-Interface Features

Purpose: reduce dependencies that support secondary flows rather than the core downloader.

Candidate changes:

- Replace `pick` with simple numbered prompts, or make rich interactive selection optional.
- Replace `beautifulsoup4` for Last.fm playlist scraping with a small `html.parser`-based extractor, or make Last.fm support optional.
- Keep the CLI usable in non-interactive/scripted workflows first.

Success signals:

- Core search/download flows do not require interactive UI dependencies.
- Last.fm parsing has fixture tests and fails clearly when the page shape is unsupported.
- Optional features do not force unnecessary dependencies onto minimal installations.

### Phase 5 — Replace The HTTP Stack Deliberately

Purpose: remove `requests` and its transitive dependency graph only after the project owns a narrow HTTP boundary.

Candidate shape:

- Introduce `qobuz_dl/http.py` or equivalent.
- Provide focused helpers for JSON API calls, text fetches, and streamed downloads.
- Normalize errors behind project-owned exceptions.
- Preserve headers, params, timeouts, streaming, redirects, and status handling required by current code.
- Migrate `qopy.py`, `bundle.py`, `core.py`, and `downloader.py` through the internal boundary.

Success signals:

- `requests`, `urllib3`, `certifi`, `charset-normalizer`, and `idna` can be removed together.
- HTTP behavior is covered with mocked responses before migration.
- Download interruption and partial-content failures still fail loudly.

### Phase 6 — Keep `mutagen` Pinned And Audited

Purpose: avoid replacing specialized audio metadata code before the project has enough proof that doing so is safer.

Decision:

- Keep `mutagen` as a retained runtime dependency.
- Pin it explicitly and audit it as part of dependency maintenance.
- Do not fork, strip, or rewrite it in the first dependency-hardening cycle.

Rationale:

- `mutagen` owns FLAC and MP3 metadata details that are easy to get subtly wrong.
- A poor replacement can corrupt files, omit tags, or create compatibility bugs across players.
- Since this project is already GPL-licensed, license compatibility is not the main blocker; long-term maintenance and correctness are.

Success signals:

- The dependency policy names `mutagen` as an intentional exception, not forgotten debt.
- Metadata behavior stays stable while other dependency risk is reduced.
- A future decision to vendor or replace metadata support would require a separate architecture review and stronger fixture coverage.

## Key Pattern Choices

- Prefer **dependency reduction** over blind vendoring. Copying third-party code into the repo transfers maintenance burden; it does not remove risk by itself.
- Prefer **small internal replacements** for simple utilities such as terminal colors, filename/path sanitization, and progress display.
- Prefer **optional features** for non-core surfaces such as interactive menus or Last.fm scraping when replacement would complicate the core downloader.
- Keep `mutagen` as a **pinned, audited exception** until the project has enough tests and expertise to consider a narrower tagging layer.
- Use `uv` as the source of truth for local dependency workflows, and keep lockfile behavior reproducible.
- Make replacement work pass through tests first, then implementation, then docs.

## Impacted Artifacts

Phase 1 is expected to affect these project artifacts:

- `pyproject.toml` — Python requirement, classifiers if added, dependency pins or dependency groups.
- `uv.lock` — regenerated after metadata or dependency-policy changes.
- `.github/workflows/ci.yml` — remove Python 3.8 from the matrix and choose a `>=3.10` baseline.
- `docs/installation.md` — update the documented Python requirement.
- `docs/packaging.md` — update packaging/runtime-support notes and any Python 3.8-specific comments.
- `docs/testing.md` — update CI matrix and remove Python 3.8 verification guidance once the baseline changes.
- `docs/dependencies.md` — evolve from inventory-only documentation into the dependency policy, or link to the new policy if split out.
- `AGENTS.md` — update repository instructions that currently mention Python 3.8 verification and Python 3.8-compatible build constraints after the project baseline changes.

Later phases are expected to affect source modules only when their corresponding dependency is removed or optionalized. Those code changes should update the canonical docs in the same slice.

## Scope And Non-Goals

In scope for the full effort:

- dependency policy documentation
- Python `>=3.10` metadata, docs, and CI alignment
- dependency inventory refresh
- pin/audit policy for retained dependencies, especially `mutagen`
- characterization tests for dependency-owned behavior
- low-risk internal replacements for simple dependencies
- optionalization or simplification of secondary features
- deliberate HTTP boundary design before removing `requests`

Not in scope for the first dependency-hardening cycle:

- vendoring all dependencies immediately
- replacing `mutagen` with a homegrown metadata writer
- changing downloader behavior without characterization tests
- adding live network tests to the default suite
- broad refactors unrelated to dependency risk
- treating “zero dependencies” as more important than correctness, maintainability, or file safety

## Success Signals

- A maintainer can read one policy doc and understand why each dependency is kept, removed, optionalized, or considered for vendoring.
- `pyproject.toml`, CI, and docs agree on Python `>=3.10`.
- `mutagen` has a clear retained-dependency rationale and audit expectations.
- Easy dependencies are removed without changing expected CLI behavior.
- `requests` is removed only after a tested internal HTTP boundary exists.
- Future updates fail loudly when dependency policy, lockfile, and declared Python support drift apart.

## Risks And Review Points

- **Security risk may move, not disappear.** Vendoring creates an internal patch responsibility. The policy must make this explicit.
- **Compatibility break:** dropping Python 3.8 is intentional but must be reflected in docs, CI, and packaging metadata.
- **Behavior drift:** replacing `pathvalidate`, `pick`, `tqdm`, `beautifulsoup4`, or `requests` without tests can subtly change filenames, prompts, parsing, downloads, or errors.
- **Metadata complexity:** replacing `mutagen` too early risks corrupt or incomplete audio tags. Keep it pinned and audited unless a later architecture review proves a narrower safe path.
- **HTTP subtlety:** `requests` replacement must preserve timeout, redirect, streaming, header, params, JSON, and error behavior that the current code assumes.
- **Licensing/provenance:** any vendored code must preserve licenses and record modifications.

## Recommended Next Phase

`pa-plan-slicer` should convert this vision into small implementation slices.

Recommended first implementation slice:

1. Add/update dependency policy documentation.
2. Change Python support from `>=3.8` to `>=3.10` across metadata, CI, and docs.
3. Update lockfile with `uv`.
4. Run `just ci`.

Then continue with separate slices for characterization tests, low-risk removals, optional feature simplification, HTTP replacement, and retained `mutagen` audit policy.
