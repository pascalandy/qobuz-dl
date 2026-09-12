# Agent operation implementation plan

Status: proposed follow-up plan. This documentation change implements none of the proposed commands. The [design](design-agent-ergonomics.md) owns their meaning. The [architecture](../../architecture.md) owns current behavior.

## Evidence and live-work boundary

The source baseline is `master` at `1ef6f5b2cdd741b5bb816bffdf2fad786c56dbff`. GitHub was inspected with `gh` on 2026-09-12. At the frozen observation, `2026-09-12T13:29:33Z`, 26 open PRs formed one linear stack from [#54](https://github.com/pascalandy/qobuz-dl/pull/54) to [#83](https://github.com/pascalandy/qobuz-dl/pull/83). Each was clean and mergeable. The frontier #54 had passing CI and review checks. This is historical evidence, not a current merge verdict.

The stack order at that observation was `54, 55, 56, 57, 58, 59, 60, 61, 62, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 82, 83`. The frontier head was `60e90c0d5ec93fbf49ade12dd638b4aceb6dcff8`; the tip was `d304fb46b89611c5002b8953cc12de19c1bfc7f6`. Only [#53](https://github.com/pascalandy/qobuz-dl/pull/53) from the September implementation program had reached `master`.

[Epic #20](https://github.com/pascalandy/qobuz-dl/issues/20) remains the live work index. Refresh it and the PR base/head state before implementation. A stacked PR's green checks prove its proposed branch, not the checked-out `master`.

| Existing owner | Contract to reuse | Integration consequence |
| --- | --- | --- |
| [#54](https://github.com/pascalandy/qobuz-dl/pull/54), issue #42 | One validation runner, installed-wheel proof | Call `just ci`; inherit its implementation when integrated |
| [#55](https://github.com/pascalandy/qobuz-dl/pull/55), issue #22 | Attempt-owned temporary files | Build cancellation and recovery on this lifecycle |
| [#56](https://github.com/pascalandy/qobuz-dl/pull/56), issue #23 | Immutable download states, reasons, finalized paths | Extend this result; do not create a parallel automation result engine |
| [#57](https://github.com/pascalandy/qobuz-dl/pull/57), [#62](https://github.com/pascalandy/qobuz-dl/pull/62), [#64](https://github.com/pascalandy/qobuz-dl/pull/64) | Config validation, bundle errors, lazy platform paths | Reuse validation and startup boundaries for machine mode |
| [#58](https://github.com/pascalandy/qobuz-dl/pull/58), [#60](https://github.com/pascalandy/qobuz-dl/pull/60), [#61](https://github.com/pascalandy/qobuz-dl/pull/61), [#65](https://github.com/pascalandy/qobuz-dl/pull/65) | Fork identity, safe API diagnostics, purge status, credential transport evidence | Preserve provenance, errors, and command semantics |
| [#59](https://github.com/pascalandy/qobuz-dl/pull/59), [#66](https://github.com/pascalandy/qobuz-dl/pull/66), [#67](https://github.com/pascalandy/qobuz-dl/pull/67), [#68](https://github.com/pascalandy/qobuz-dl/pull/68), [#69](https://github.com/pascalandy/qobuz-dl/pull/69) | Names, per-track quality, artwork policy, format extensions, album labels | Plan previews and artifact facts must agree with these owners |
| [#70](https://github.com/pascalandy/qobuz-dl/pull/70), [#71](https://github.com/pascalandy/qobuz-dl/pull/71), [#72](https://github.com/pascalandy/qobuz-dl/pull/72) | Edition selection, Last.fm pairs, ordered M3U | Preserve identity, source order, and repeated occurrences |
| [#73](https://github.com/pascalandy/qobuz-dl/pull/73), [#74](https://github.com/pascalandy/qobuz-dl/pull/74) | API and media 429 policy | One retry owner; no outer retry loop in agent orchestration |
| [#75](https://github.com/pascalandy/qobuz-dl/pull/75), [#76](https://github.com/pascalandy/qobuz-dl/pull/76) | Native-platform checks and coverage | Reuse their evidence limits; do not equate mocks with native proof |
| [#77](https://github.com/pascalandy/qobuz-dl/pull/77), issue #47 | Opt-in live verifier and sanitized provenance receipt | Reuse its isolation; live execution remains separate issue #48 |
| [#78](https://github.com/pascalandy/qobuz-dl/pull/78), issue #46 | Documentation truth and navigation | Reconcile overlapping docs after integration, preserving its corrections |
| [#82](https://github.com/pascalandy/qobuz-dl/pull/82), issue #38 | Unofficial Beta access framing | Keep provider capability claims conservative |
| [#83](https://github.com/pascalandy/qobuz-dl/pull/83), issue #49 | Selected artifact-satisfaction policy | Adopt the decision; it does not implement history |
| Issues [#79](https://github.com/pascalandy/qobuz-dl/issues/79), [#80](https://github.com/pascalandy/qobuz-dl/issues/80), [#81](https://github.com/pascalandy/qobuz-dl/issues/81) | Artifact schema, direct satisfaction, playlist reuse | These issues own history implementation |
| Issues [#50](https://github.com/pascalandy/qobuz-dl/issues/50), [#51](https://github.com/pascalandy/qobuz-dl/issues/51) | Bandwidth policy and explicit opt-in pacing | Keep pacing separate from retries and from this command-contract work |

## Integration rule

Keep this documentation patch reviewable on its named baseline. Before publishing it, reconcile against the current default branch and the stack owner's integration order. Prefer integration after the overlapping documentation PRs. Do not rebase or retarget the active stack as part of this plan.

Re-read the actual merged or selected prerequisite code before each slice. Update the architecture page when those changes become the checkout baseline. An issue title, green check, or accepted policy does not satisfy a code prerequisite.

## Delivery slices

Each slice ends with its stated observable proof and `just ci`. Fixture networks, temporary config/state roots, and temporary output roots remain the default. The listed test paths are existing homes for new cases, not claims that those future assertions already pass.

### 1. Establish a prompt-free local inspection contract

Outcome: an agent can identify the runtime and effective settings without creating credentials, history, or music directories.

Scope: `commands.py`, `cli.py`, startup paths, and local provenance. Add `inspect`, `--state-dir`, `--no-input`, and the initial versioned JSON envelope. Resolve options once with explicit false overrides. Keep human setup behavior separately characterized.

Dependencies: config validation and lazy-path changes from #57 and #64. Reuse provenance definitions from #77 and error sanitization from #60. Set concrete finite catalog request/time defaults for slice 3 from representative offline fixtures; record them with the budget tests.

Proof in `tests/test_commands.py` and `tests/test_config_persistence.py`:

- Run the actual entry point with closed stdin and a missing isolated config; assert the problem code, exit status, and zero network or directory creation
- Inspect an existing config; assert zero writes and chmod calls, no auth, and no secret values in either output stream
- Verify the selected state/output roots and option provenance; an explicit false overrides a saved true
- Parse stdout as exactly one JSON document for success, invalid arguments, and config failures

Risk checkpoint: importing the package currently loads CLI paths and config setup has permission side effects. Test the whole entry point, not only a new helper. Mark editable source versus installed wheel provenance explicitly.

### 2. Expose accurate download outcomes

Outcome: a batch's machine result and exit status agree with files actually finalized, including partial success and interruption.

Scope: extend #56 through `core.py` aggregation and CLI presentation. Preserve its item states and reasons. Add occurrence identity, artifact facts, resource counters, and safe problem details where execution knows them. Keep one result for human output, JSON, and M3U consumers.

Dependencies: #55, #56, the per-track/artwork/naming fixes, and slice 1. Artifact reuse may claim satisfaction only after #79 and #80, plus #81 for playlists, are implemented. Until then, legacy suppression must remain visibly unverified and cannot count as machine success.

Proof in `tests/test_download_execution_characterization.py`, `tests/test_duplicate_tracking.py`, and command tests:

- Inject one completed track and one tag failure; assert the real finalized path, failed occurrence, partial exit, and no success history for the failed artifact
- Exercise policy exclusion, unavailable media, quality refusal, empty search, invalid download input, and an existing unverified path
- Interrupt during a stream; assert owned cleanup, preservation of other files, finalized-result retention, and exit 130
- Fail history recording after publication; assert separate artifact and history outcomes without claiming that the file disappeared

Risk checkpoint: a result label is not file proof. Verify actual temporary-tree contents and parsed media facts where applicable. Preserve the established artwork exception to history satisfaction.

### 3. Make discovery and selection inspectable

Outcome: an agent can search or produce a bounded ordered plan without downloading or mutating library state.

Scope: `core.py` resolution, `qopy.py` catalog authentication, `commands.py`, and `cli.py`. Expand existing URL plans to text sources, Last.fm matches, and search results. Add `search`, `plan`, explicit exclusions, provisional paths, and supported plan schema validation.

Dependencies: slices 1 and 2, #65 auth evidence, #70 edition selection, and #71 Last.fm pairing. Preserve the existing unofficial access boundary. Separate catalog login from file-secret validation; do not promise a zero-network plan.

Proof in `tests/test_core_regressions.py`, `tests/test_qopy_characterization.py`, and `tests/test_lastfm_characterization.py`:

- Fail the test on any `track/getFileUrl`, media transfer, config write, SQLite mutation, or library creation during search and planning
- Resolve a multi-page collection; assert ordering, exclusions, source identity, and declared unknown quality facts
- Use a repeated playlist entry and an unmatched Last.fm row; preserve both repeated positions and the unmatched reason
- Exceed each item, request, or elapsed-time budget; assert bounded calls and an incomplete plan that execution rejects
- Exercise nested source lists, including a cycle; bound traversal and report the offending source without recursion or silent omission

Risk checkpoint: one API page or source file can exceed the remaining budget. Check before scheduling more work and bound response/source input sizes at the I/O boundary. A rejected plan must never become a smaller executable request implicitly.

### 4. Execute and recover from a saved plan

Outcome: an inspected selection can execute without a new search, and a rerun verifies satisfaction instead of trusting IDs or names.

Scope: `dl --plan`, plan validation, existing executor integration, history satisfaction, and M3U generation. Reuse the history implementation from #79 through #81. Keep migration ownership in those issues.

Dependencies: slices 2 and 3, #79 through #81, and the current HTTP retry contracts. Pacing #51 is optional and independently deliverable.

Proof in download, duplicate, database, and playlist tests:

- Reject incomplete, unsupported, malformed, or conflicting plans before side effects
- Execute the saved IDs without repeating search; resolve fresh media URLs and compare requested with actual quality
- Delete one verified artifact, change the requested template, then change available quality; each new request evaluates its exact destination and fresh-download quality rule
- Preserve unknown path occupants and report conflicts; migration never invents file identity for legacy rows
- Retry a partial album and reuse only verified artifacts; produce exact M3U source order with repeats and no unrelated files
- Exercise database-disabled mode with a database trap; assert no history access and no silent overwrite

Risk checkpoint: publication and SQLite recording cannot be one transaction. Verify the file-published/history-failed crash window. A saved plan has no secret or reusable media URL, and its identifier confers no authority.

### 5. Make the contract cheap to maintain

Outcome: another agent can reproduce a failure, locate its owner, and improve the system without rediscovering the whole repository.

Scope: contract fixtures, CLI/module documentation, architecture ownership links, and the canonical validation runner from #54. Derive machine-output examples from validated fixtures. Add schema/relative-link checks to that runner only when their format is settled; avoid a second CI command list.

Dependencies: the corresponding implemented contracts and #78's documentation corrections. Deliver user reference changes with each earlier slice; this slice checks the connected workflow and removes transitional explanations.

Proof:

- Give a new reader only `AGENTS.md` and the docs index; ask it to locate prompt-free inspection, partial-result semantics, history ownership, and the matching offline test commands
- Drive inspect, plan, execute, interruption, and recovery through the real CLI with fake network and media fixtures
- Validate examples against the maintained schema and the same outcomes used by human output
- Run `just ci` and the integrated installed-artifact checks; record the revision, environment, command, and result

Risk checkpoint: fixtures must assert externally observable results, not duplicate implementation branches. A new lesson updates its owning fixture or canonical page. Do not accumulate generic instructions in `AGENTS.md`.

## Cost and acceptance measures

| Measure | Baseline evidence | Acceptance target |
| --- | --- | --- |
| Local inspection effects | Current config handling can create or chmod state | Zero network, prompts, config writes, history writes, or output-directory creation |
| Plan effects | Current constructor and auth perform setup and file-URL validation | Only declared catalog/auth reads, with bounded request count and elapsed time |
| Outcome interpretation | Logs, normal returns, and global ID rows can disagree with final files | One parseable result agrees with exact artifact contents and exit status |
| Repeated execution | ID or filename can suppress a different destination | Reuse only verified satisfaction at the requested destination and effective quality |
| Transfer overhead | First album track can request its file URL twice | One resolution per track per attempt unless a recorded expiry or retry requires another |
| Maintainer lookup | Historical research includes stale source claims | `AGENTS.md` or `INDEX.md` links directly to an owner/proof map and proposed contracts |

Use fake-clock and request-counter measurements before performance claims. Do not add disk, response-size, or runtime policy knobs without naming the failure they bound. Finite internal limits can remain internal until a user needs an override.

## Remaining external evidence

The live verifier in #77 is a proposal at this baseline. It does not prove live compatibility. [Issue #48](https://github.com/pascalandy/qobuz-dl/issues/48) separately requires an authorized account and title. No live Qobuz or Last.fm request is needed to implement or verify these offline contracts.

Provider catalog-auth behavior, actual media availability, and real throughput remain unverified by this documentation work. [Issue #44](https://github.com/pascalandy/qobuz-dl/issues/44) owns repository protection; the GitHub observation found no protection or rulesets. Neither limitation authorizes broadening this work into service access or repository administration.

The next implementation unit is slice 1 after its prerequisite source and overlapping documentation have been reconciled. This plan does not open issues, modify PRs, or authorize merging the stack.
