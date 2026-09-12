# Agent operation design

Status: proposed system contract, not implemented CLI behavior. This design builds on the accepted history policy and the open work mapped in the [implementation plan](impl-plan-agent-ergonomics.md). The [current architecture](../../architecture.md) describes the checked-out runtime separately.

## Purpose and choice

An agent should be able to establish which program it is driving, inspect the work it will perform, limit that work, and verify the resulting music files. A maintainer should find each decision and its proof in one place.

Keep the synchronous Python CLI and library. Give both the same request, selection, and result contracts. The existing private URL plans, HTTP boundary, and pending `DownloadResult` provide useful starting points.

| Approach considered | Consequence | Decision |
| --- | --- | --- |
| Wrap the current CLI and parse its logs | Cannot recover swallowed errors, distinguish a skip from completion, or prevent startup effects | Reject |
| Share explicit contracts within the existing CLI and library | Makes selection and completion inspectable while retaining current owners | Select |
| Add a daemon, job queue, or agent service | Adds shared state, scheduling, recovery, and another interface to maintain | Defer until a concrete user need requires it |

The system remains a downloader for a local music library. A general Qobuz SDK, provider mutations, full-catalog indexing, parallel transfers, and a separate agent-memory database are outside this design. Keep `mutagen` and the existing dependency policy.

## One connected model

```text
arguments + selected config
          -> effective request
          -> ordered selection plan
          -> sequential file execution
          -> verified artifacts + item outcomes
          -> run result -> human output / JSON / exit status
                       -> history evidence / ordered M3U entries
```

These are data boundaries. They do not require a module or class for every arrow.

| Contract | Information it owns | Owner to evolve |
| --- | --- | --- |
| Effective request | Operation, typed source identity, output root, state root, resolved options with provenance, work limits | `commands.py` and `cli.py` resolve once |
| Selection plan | Ordered source occurrences, selected Qobuz kinds and IDs, exclusions and reasons, frozen settings, provisional destinations, unresolved facts | The existing resolution seam in `core.py` |
| Artifact result | Finalized audio paths, requested format, observed media facts, identity evidence, failure or reuse reason | `downloader.py`, informed by `metadata.py` |
| History satisfaction | Whether current files satisfy this request at these paths and effective quality | `db.py` with the executor, under issue #49 |
| Run result | Ordered item outcomes, totals, problems, resource use, interruption state | `core.py` aggregates, `cli.py` presents |
| Network policy | Request timeouts, bounded retries, provider wait signals, optional media pacing | `http.py`; `qopy.py` owns endpoint semantics and signing |

Normalize untrusted arguments, config, plan files, and provider responses at their boundaries. Internal callers consume the resulting values. Domain policy must not be reconstructed in the JSON formatter or a second agent-only downloader.

## Proposed command contract

Every command and option below is a proposal. Existing `dl`, `lucky`, and `fun` remain the human entry points during delivery. Their current syntax is in the [CLI reference](../../cli.md).

| Operation | Input and result | Permitted effects |
| --- | --- | --- |
| `inspect` | Local runtime provenance, supported contract versions, selected paths, redacted effective settings and their sources | Reads local metadata and an existing config; no authentication, directory creation, chmod, database migration, or network |
| `search QUERY` | Bounded, ordered candidates with kind, ID, display facts, and matching source | Authentication and catalog reads only; no library or history writes |
| `plan SOURCE...` | A complete ordered selection document, including rejected or unresolved inputs | Authentication and bounded catalog reads only; no file-URL requests, media transfer, library creation, or history mutation |
| `dl --plan PATH` | Validate and execute a saved complete plan | Reads the plan and current artifact evidence; downloads, tags, finalizes, records evidence, and writes M3U as requested |
| Existing `dl` and `lucky` | Resolve and execute through those same contracts | Existing user intent, with the same results and limits as saved-plan execution |
| Existing `fun` | Collect choices, then submit an effective request | Prompts only in an interactive terminal |

The initial machine interface uses these shared options:

| Option | Proposed meaning |
| --- | --- |
| `--json` | One versioned JSON document on stdout; implies `--no-input` |
| `--no-input` | Never prompt or create missing credentials; missing input fails before network or output writes |
| `--state-dir PATH` | Select the config and history root independently of `--directory`; keep the existing user root as the human default |
| `--max-items COUNT` | Positive bound on resolved track occurrences, including repeats; required for the new `plan` operation |

Catalog planning also needs finite request and elapsed-time budgets. Fix their initial defaults in the first implementation slice using offline large-collection fixtures. A 500-item API page is not a total-work limit. Reaching a limit produces `budget_exceeded` with consumed counts and an incomplete, non-executable plan. Do not silently truncate a request into apparent success.

Use the existing config format. Resolve explicit CLI values, then the selected config, then built-in defaults. Preserve explicit false values with paired boolean options where needed. Report the source of each effective setting. Do not add project configs, environment overlays, or another settings file without a use case.

Missing config in machine mode yields a stable `config_missing` problem and a recovery instruction. `inspect` reports the absence without initializing it. Interactive setup remains an explicit user workflow. Credentials never appear in argv, plans, results, or diagnostic receipts.

The proposed workflow below assumes an existing isolated config under `./private-state`. These commands illustrate the target interface and do not run on the current baseline. Check each exit status before consuming the redirected document.

```sh
uv run qobuz-dl --state-dir ./private-state --json inspect
uv run qobuz-dl --state-dir ./private-state --json search "artist album"
uv run qobuz-dl --state-dir ./private-state --json plan https://play.qobuz.com/album/qxjbxh1dc3xyb --directory ./intake --max-items 100 > plan.json
uv run qobuz-dl --state-dir ./private-state --json dl --plan plan.json > first-result.json
uv run qobuz-dl --state-dir ./private-state --json dl --plan plan.json > retry-result.json
```

The second execution uses the same selection. Its result must explain verified reuse and any remaining work, even when it transfers no bytes.

## Planning without hidden execution

Planning cannot instantiate today's `QobuzDL` unchanged because its constructor creates directories and may initialize SQLite. Catalog authentication also cannot use today's `Client` unchanged because secret validation requests `track/getFileUrl`. Separate those effects before exposing `search` or `plan` as catalog-only operations.

A plan records ordered source occurrences separately from unique transfer work. A playlist containing the same track twice retains both positions. Last.fm entries retain their source artist and title, chosen Qobuz ID, and match or no-match reason. A saved plan never silently repeats a search and chooses a different edition.

Store public item identities, normalized settings, plan schema version, producer version, and selection provenance. Keep passwords, tokens, signing secrets, and expiring media URLs out. Actual quality, exact output names that depend on quality, byte sizes, and availability can remain explicitly unknown until execution.

The plan is a selection snapshot, not a promise that Qobuz will return particular bytes. Execution revalidates availability, quality, destination conflicts, and current file identity. A changed source selection or unsupported plan version requires replanning. Quality resolution follows the frozen fallback policy and records any downgrade. Never label catalog maximum quality as observed file quality.

`dl --plan` accepts only a complete document from the plan operation with a supported schema. Conflicting source or download-policy flags are usage errors. Changing destination, templates, selection, or quality requires a new plan. A plan ID identifies the normalized selection and settings; it is not an authorization token. Credential state is selected at execution time.

## Completion, reuse, and recovery

Adopt the [history satisfaction policy in PR #83](https://github.com/pascalandy/qobuz-dl/pull/83). A verified file must exist at the expected destination and have acceptable effective quality. Legacy ID rows, a matching filename, ordinary descriptive tags, or a file in another destination cannot prove satisfaction. Unknown path occupants produce conflicts and stay untouched.

The pending [result contract in PR #56](https://github.com/pascalandy/qobuz-dl/pull/56) uses `finalized`, `ignored`, and `failed`, a closed reason, and ordered finalized paths. Evolve that contract instead of adding a competing success flag. Preserve each selected track occurrence and its outcome when constructing the run result.

In the target contract, `finalized` covers newly completed audio and reuse verified for the current request. The reason distinguishes them. A filename-only `existing_file` or legacy `database_duplicate` observation cannot qualify. Count verified reuse as satisfied work even when zero bytes transfer.

Streaming, tagging, publication, and recording evidence form one artifact lifecycle. A track becomes finalized only after the final file and its media facts have been verified. Tagging failures remain failures. If publication succeeds but history recording fails, report the file and the history failure separately. A rerun must verify the file before reuse.

Only the current attempt owns its temporary files. Cancellation cleans those files, preserves prior finalized artifacts, and reports incomplete work. Independent runs use separate output and state roots. Shared-path concurrent writers remain unsupported until exclusive final publication is proven; temporary-name uniqueness alone does not make concurrent runs safe.

History is a rebuildable optimization, not command truth. Issues [#79](https://github.com/pascalandy/qobuz-dl/issues/79), [#80](https://github.com/pascalandy/qobuz-dl/issues/80), and [#81](https://github.com/pascalandy/qobuz-dl/issues/81) own migration and satisfaction. Preserve their `--no-db`, purge, no-overwrite, and no-cross-destination-reuse rules. Artwork remains outside that history policy; report artwork outcomes separately.

M3U uses successful ordered occurrences from the same result that the agent sees. Preserve repeats, omit unsuccessful occurrences without reordering later entries, and exclude unrelated pre-existing files. Retry only unresolved work after revalidation. A missing terminal receipt after a crash means the run outcome is unknown, so inspect artifacts before retrying.

## Output and error semantics

Machine stdout contains one JSON object with `schema_version`, `operation`, `status`, `data`, and `problems`. `data` is specific to inspect, search, plan, or execution. An execution result includes a run ID, plan ID when present, effective non-secret settings, ordered item outcomes, artifact facts, and totals for occurrences, unique transfers, bytes, requests, and wait time.

Each problem has a stable code, severity, affected source or item, safe message, retryability, and a recovery hint. Severity distinguishes warnings from errors. Keep the item reason from `DownloadResult`; a human message is not a second status field. Optional media facts use explicit absence when unknown or inapplicable. A zero byte count means zero observed bytes, not unknown size.

Diagnostics and bounded progress go to stderr. JSON contains no ANSI sequences, prompts, raw HTTP bodies, credential-bearing URLs, or tracebacks. `--json` covers parser and startup failures too. Honor `NO_COLOR` for human output. Keep human text free to improve while maintaining the versioned machine contract.

| Exit | Proposed interpretation |
| --- | --- |
| `0` | No operation-level error; inspection or search completed, planning produced a complete valid plan, or execution satisfied all required audio through new finalization or verified reuse; empty search and policy-only no-op are explicit successes |
| `1` | Operational failure, or execution satisfied no required audio and was not a policy-only no-op |
| `2` | Invalid invocation, config values, incompatible plan, or conflicting options |
| `3` | Partial completion; at least one required occurrence is satisfied through new finalization or verified reuse and at least one remains unsatisfied |
| `130` | Interrupted; any finalized paths still appear in the terminal result when cleanup can complete |

Policy exclusions are explicit and outside the required set. Unavailable tracks, rejected quality, unmatched requested downloads, conflicts, and tagging failures are unsatisfied work. An empty input is a usage error. `search` returning no candidates is successful discovery with an empty result. Never use exit 0 alone as proof that files were produced.

Interruption takes precedence over other outcomes. Otherwise invalid input exits 2 before execution, partial audio satisfaction exits 3, and remaining operational errors exit 1. A history-write error after all audio is satisfied therefore exits 1 while retaining the successful artifact facts. Warnings alone do not change a successful exit.

An unexpected crash or forced termination may prevent JSON emission. Consumers require both a valid terminal document and its consistent exit status. Additive fields can extend a schema version. Changed meanings or removed fields require a new version and a documented migration. Generate examples and schema checks from the same maintained contract fixtures.

## Resource use and accumulated knowledge

Keep transfers sequential. Reuse catalog metadata and resolved URLs within one attempt when valid, avoiding the current duplicate first-track file-URL lookup. Revalidate provider-dependent facts across attempts. Do not add a persistent catalog cache before measured duplication justifies its invalidation cost.

API and media retries remain in `http.py`, with endpoint signing handled by `qopy.py`. A whole-run deadline includes retry waits. Stop if the remaining budget cannot honor a provider delay. Never retry earlier than the provider requested to fit a local cap. Mid-stream failures retain explicit cleanup and retry eligibility. Optional byte pacing belongs to issues [#50](https://github.com/pascalandy/qobuz-dl/issues/50) and [#51](https://github.com/pascalandy/qobuz-dl/issues/51), independently of retry delivery.

Use three durable knowledge owners. Source and offline fixtures own executable behavior. Canonical docs own operational meaning and rationale. [Epic #20](https://github.com/pascalandy/qobuz-dl/issues/20) and its children own live work status. A useful discovery becomes a focused fixture or a correction to its owning document, with source revision and evidence. Session notes and receipts remain task artifacts rather than a second backlog or instruction layer.

The [implementation plan](impl-plan-agent-ergonomics.md) defines the slice order and observable acceptance gates. No live-provider compatibility claim follows from this design or its offline verification.
