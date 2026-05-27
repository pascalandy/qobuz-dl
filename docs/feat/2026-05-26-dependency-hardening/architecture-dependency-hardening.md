# Dependency Hardening Architecture

## Request Or Framing Goal

Design the macro execution roadmap for hardening `qobuz-dl` dependencies after the direction has been settled in `vision-dependency-hardening.md`.

The roadmap must reduce dependency risk without creating a fragile fork of every library. It should keep the work demonstrable, reversible, and safe to stop after each phase.

Primary Architect mode: `RoadmapDesign`.

## Current Constraints

- The project is a Python CLI downloader with user-facing flows for Qobuz API access, downloads, Last.fm playlist parsing, interactive selection, metadata tagging, and playlist generation.
- Local development uses `uv`; project commands should continue to use `uv run ...` and `just ...`.
- Default tests must not require Qobuz credentials, live Qobuz API calls, live Last.fm pages, active subscriptions, or real media downloads.
- Current runtime dependencies are:
  - `beautifulsoup4`
  - `colorama`
  - `mutagen`
  - `pathvalidate`
  - `pick==1.6.0`
  - `requests`
  - `tqdm`
- The current project metadata declares Python `>=3.8`, while the chosen direction is to modernize to Python `>=3.10`.
- `mutagen` is intentionally retained as a pinned and audited dependency for the first hardening cycle.
- Vendoring is not the default strategy. Any vendored code needs provenance, license preservation, retained API notes, local modification notes, and refresh instructions.

## Target Structure Or Execution Shape

The dependency-hardening work should proceed as a risk-first migration with six macro phases:

1. Establish the policy and runtime baseline.
2. Add characterization tests around dependency-owned behavior.
3. Remove low-risk utility dependencies.
4. Simplify or optionalize secondary user-interface and parsing features.
5. Replace the HTTP stack through a narrow internal boundary.
6. Keep `mutagen` pinned and audited while documenting why it remains.

The architecture principle is: create a testable project-owned boundary before removing a dependency whose behavior is broad, stateful, or externally visible.

Simple dependencies can be replaced directly after tests. Complex dependencies need boundaries first. `mutagen` stays external unless a later architecture review proves replacement is safer than retention.

## Key Decisions

- **Python baseline:** move to Python `>=3.10` before dependency churn so dependency resolution, docs, CI, and package metadata agree.
- **Dependency policy first:** write the policy before removal work so later choices do not become ad hoc.
- **Tests before swaps:** dependency removal must be preceded by characterization tests for user-visible behavior.
- **Small replacements over vendoring:** replace narrow utility behavior with internal modules instead of copying entire libraries.
- **Optionalize non-core features where useful:** interactive menus and Last.fm scraping should not force dependency weight onto core scripted download flows if a smaller path is acceptable.
- **HTTP through a boundary:** remove `requests` only after the code uses a project-owned HTTP module or equivalent seam.
- **Retain `mutagen`:** pin and audit it because metadata writing is specialized and high-consequence.

## Phases Or Workstreams

### Phase 1 — Policy And Runtime Baseline

Strategic goal: align the project around one dependency policy and one supported runtime baseline.

Why it comes now: without this, later dependency removals will mix policy, compatibility, and implementation concerns in the same changes.

What becomes true after it:

- Project metadata, lockfile, CI, and docs agree on Python `>=3.10`.
- The dependency policy explains how dependencies are removed, optionalized, pinned, audited, or vendored.
- `mutagen` is named as an intentional retained dependency.
- Maintainers know which docs and instructions must change when dependency policy changes.

Risk or decision resolved: whether the project continues carrying Python 3.8 compatibility. The chosen answer is no.

Validation gate: local and CI checks run on the new Python baseline, and docs no longer instruct maintainers to verify Python 3.8 compatibility.

Handoff target: `pa-plan-slicer` for the first implementation slice.

### Phase 2 — Characterization Test Net

Strategic goal: make dependency behavior observable before replacing dependencies.

Why it comes now: dependency removal without tests can change filenames, parsing, progress behavior, errors, interactive prompts, or metadata behavior without being noticed.

What becomes true after it:

- Sanitization behavior has explicit examples.
- Last.fm parsing is covered by static HTML fixtures rather than live pages.
- HTTP behavior is mockable and does not require Qobuz or Last.fm availability.
- Download interruption behavior is covered enough to protect the later HTTP migration.
- Interactive behavior is either testable at the prompt boundary or explicitly marked for simplification.

Risk or decision resolved: whether future removals preserve current user-visible behavior or intentionally change it.

Validation gate: tests fail if replacement code changes the behavior that the current dependencies provide.

Handoff target: `pa-plan-slicer` for dependency-specific test slices.

### Phase 3 — Low-Risk Utility Dependency Removal

Strategic goal: remove dependencies whose used behavior is smaller than the dependency itself.

Why it comes now: these removals reduce risk and build confidence before touching broader network or metadata behavior.

What becomes true after it:

- `colorama` is replaced by a project-owned terminal color module or equivalent no-op/color policy.
- `pathvalidate` is replaced by a project-owned sanitizer matched to the filenames and paths this CLI generates.
- `tqdm` is replaced or optionalized behind a small progress interface.

Risk or decision resolved: whether the project can own simple utility behavior without pulling external packages.

Validation gate: CLI output remains acceptable, generated paths remain safe, and download progress remains understandable without depending on large external behavior.

Handoff target: `pa-plan-slicer` for one dependency at a time.

### Phase 4 — Secondary Feature Simplification

Strategic goal: separate core download behavior from convenience features that currently add dependency weight.

Why it comes now: once simple utilities are gone, the remaining removable dependencies are tied to feature shape, not just implementation detail.

What becomes true after it:

- `pick` is replaced with simpler numbered prompts or moved behind an optional interactive extra.
- `beautifulsoup4` is replaced with a small parser for the specific Last.fm selectors in use, or Last.fm support becomes optional.
- Core scripted commands do not require optional interactive or scraping dependencies.

Risk or decision resolved: whether convenience flows stay built-in, become simpler, or become optional.

Validation gate: core download/search workflows remain usable without optional UI/parser dependencies, and Last.fm behavior fails clearly when unsupported page shapes are encountered.

Handoff target: `pa-plan-slicer`, with human review before removing richer interactive behavior.

### Phase 5 — HTTP Boundary And `requests` Removal

Strategic goal: replace the broad `requests` dependency with a narrow project-owned HTTP boundary.

Why it comes now: HTTP touches authentication, Qobuz API calls, bundle scraping, Last.fm fetching, redirects, streaming downloads, errors, and partial-download failures. It should not be replaced until simpler dependency removals and tests have reduced uncertainty.

What becomes true after it:

- API JSON calls, text fetches, and streamed downloads go through a small internal HTTP module or equivalent boundary.
- Callers depend on project-owned errors rather than `requests` exceptions.
- Headers, query parameters, timeouts, redirects, response status handling, JSON parsing, and streamed downloads are preserved where the current code relies on them.
- `requests` and its transitive dependencies can be removed together.

Risk or decision resolved: whether the project can safely own HTTP behavior without losing reliability in downloads or API calls.

Validation gate: mocked HTTP tests cover success, failure, timeout/error mapping, and interrupted downloads before `requests` is removed.

Handoff target: `pa-plan-slicer` after a small structural design note for the HTTP boundary if needed.

### Phase 6 — Retained Metadata Dependency Governance

Strategic goal: keep metadata behavior stable while making the retained dependency visible and governed.

Why it comes last: once the rest of the dependency surface is reduced, `mutagen` becomes a deliberate exception rather than one dependency among many.

What becomes true after it:

- `mutagen` is explicitly pinned according to the dependency policy.
- Audit expectations for `mutagen` are documented.
- Metadata behavior remains stable while other dependency risk has been reduced.
- Any future decision to vendor or replace metadata support is routed to a new architecture review, not hidden inside the general dependency cleanup.

Risk or decision resolved: whether “zero dependencies” is allowed to override file correctness. The chosen answer is no.

Validation gate: packaging, docs, and dependency inventory all show `mutagen` as intentionally retained, not forgotten.

Handoff target: `pa-doc-update` after implementation if the dependency policy or inventory changes.

## Critical Unknowns

- Whether simple numbered prompts are acceptable as a replacement for current `pick`-based multiselect behavior.
- Whether Last.fm support should remain built-in or become optional if the parser replacement becomes brittle.
- Whether `urllib.request` is sufficient for all HTTP/download behavior, or whether the internal boundary should allow a future optional HTTP backend.
- What audit tool should become the project standard for dependency checks.
- How much metadata fixture coverage is practical without adding large binary test assets.

## Validation Strategy

Use three validation layers:

1. **Policy validation:** docs, metadata, CI, lockfile, and repo instructions agree.
2. **Behavior validation:** characterization tests protect user-visible behavior before each dependency is removed.
3. **Runtime validation:** `just ci` remains the local gate, with mocked network tests by default and live checks kept opt-in only.

Human review should happen at these checkpoints:

- after Phase 1, to confirm dropping Python 3.8 is accepted everywhere;
- before Phase 4, to choose between simpler built-in flows and optional extras;
- before Phase 5, to approve the HTTP boundary shape;
- before any future metadata replacement or vendoring decision.

## Risks And Deferrals

- **Vendoring risk:** copying code into the repo can increase maintenance burden. Defer vendoring unless a specific dependency cannot be removed, optionalized, or safely pinned.
- **Behavior drift:** small replacements can still break user workflows. Mitigate with characterization tests before each removal.
- **HTTP reliability risk:** standard-library HTTP code can be correct but verbose. Keep the boundary narrow and test it before removing `requests`.
- **Interactive UX regression:** replacing `pick` with simple prompts may reduce convenience. Treat this as a human-review decision, not a silent downgrade.
- **Parser brittleness:** a small Last.fm parser may be easier to own but less tolerant than BeautifulSoup. Static fixtures and clear failure messages are required.
- **Metadata corruption risk:** replacing `mutagen` is deferred because bad metadata writing can damage the quality of downloaded files even when downloads succeed.

Relevant stress-test lenses:

- **YAGNI / KISS:** do not build a generic vendoring framework or pluggable dependency system before a concrete need exists.
- **Hyrum's Law:** users may depend on current filename, prompt, and error behavior even if it was accidental; tests should capture visible behavior before changing it.
- **Technical Debt:** dependency removal that lacks tests only converts external risk into internal maintenance debt.
- **Inversion:** the fastest way to make this fail is to chase “zero dependencies” harder than correctness, especially around HTTP and metadata.

## What Needs Human Review

- Confirm that Python `>=3.10` is the accepted baseline before Phase 1 implementation.
- Decide whether interactive selection must preserve multiselect richness or can become simpler.
- Decide whether Last.fm support is core, optional, or acceptable as best-effort.
- Approve the HTTP boundary shape before removing `requests`.
- Reconfirm that `mutagen` remains pinned/audited rather than forked after the rest of the dependency surface is reduced.

## Recommended Next Phase

Run `pa-plan-slicer` against Phase 1 first.

The first implementation plan should stay narrow: policy documentation, Python `>=3.10` alignment, CI/doc/metadata updates, lockfile refresh, and `just ci`. Later phases should be sliced one dependency or boundary at a time.
