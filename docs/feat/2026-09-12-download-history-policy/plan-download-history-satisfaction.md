# Download history satisfaction policy

Status: decision recorded for [issue #49](https://github.com/pascalandy/qobuz-dl/issues/49). [Issue #79](https://github.com/pascalandy/qobuz-dl/issues/79) and [issue #80](https://github.com/pascalandy/qobuz-dl/issues/80) are represented by stacked pull requests and in-progress implementation. [Issue #81](https://github.com/pascalandy/qobuz-dl/issues/81) remains pending. None of these implementation slices are claimed as merged into `master`

## Decision

Download history must support one guarantee. After a request completes successfully, the requested artifacts exist in the requested destination at an acceptable effective quality.

An item ID in the history is evidence of an earlier result. The ID alone never proves that a current request is satisfied. A later request can use history only after it verifies the current artifacts, their destination, and their effective quality.

This policy replaces the global interpretation of "downloaded once" with a destination-scoped satisfaction check. It does not authorize copying, moving, or linking an existing file from another destination.

## Why this policy

The legacy database model stored only one unique item ID. `download_from_id()` checked that ID before it resolved a destination or inspected a file. The global check could therefore suppress work that the current request still required.

The audit attached to [issue #20](https://github.com/pascalandy/qobuz-dl/issues/20#issuecomment-5636304337) demonstrated two failures of that model:

- Downloading the same tracks into a second playlist destination produced no audio there
- Deleting a downloaded file and requesting the track again did not restore the file

The selected guarantee matches the user's request more closely than a global activity log. It also keeps history useful as an optimization without letting stale history override filesystem evidence.

## Terms

**Requested destination.** The directory and file paths produced for the current request from the output root, collection name, current folder template, current track template, and current sanitization rules

**Requested format.** The Qobuz format ID selected for the current request, one of `5`, `6`, `7`, or `27`. This value is provenance rather than proof of effective quality

**Actual media facts.** The codec, bit depth, sample rate, and bitrate of an artifact that exists on disk. MP3 verification also requires the parser to identify constant bitrate mode. A fact can be absent when it does not apply. For example, MP3 uses bitrate rather than bit depth

**Acceptable effective quality.** A file whose actual media facts match the effective Qobuz format resolved for the current request. MP3 requires explicit format `5` evidence and nominal constant bitrate of 320 kbps. FLAC uses the effective bit depth and sample rate. The requested format remains provenance and is not a claim about the format that Qobuz returned

**Satisfied request.** A request for which every required artifact exists at its requested path, is bound to the requested Qobuz track by trustworthy evidence, and has acceptable effective quality. A filename, path, extension, ordinary descriptive tag, or database row without that proof is not satisfaction

## Satisfaction by request type

### Direct track

A direct-track request requires the track's audio file at the path produced for the current destination and templates. The file must have acceptable effective quality. A matching ID elsewhere does not satisfy the request.

### Album

An album is fully satisfied only when every track accepted by the current request exists at its path in the requested album destination. Each file must have acceptable effective quality. History cannot satisfy the album when one accepted track is missing, resolves to a different path, or fails the quality rule. Download failures and quality refusals retain their existing outcomes. They remain absent from the verified artifact set and keep the album result partial or failed as the current aggregation rules require.

### Qobuz playlist

A Qobuz playlist will evaluate each source occurrence in order after issue #81. Successful occurrences will require a verified artifact in the playlist destination. Unavailable, failed, quality-refused, or conflicted occurrences will retain their existing outcomes and will be omitted without reordering later successes. When M3U output is enabled, the M3U will contain the successful occurrences in source order and preserve repeats.

Until issue #81 is implemented, Qobuz playlists retain legacy duplicate handling. The current issue #80 implementation does not extend direct-request artifact satisfaction to playlists.

### Last.fm playlist

A Last.fm playlist will apply the same rule to each source occurrence that resolves to a Qobuz track after issue #81. Successful occurrences will require a verified artifact in the Last.fm playlist destination. Unmatched, unavailable, failed, quality-refused, or conflicted occurrences will retain their existing outcomes and will be omitted without reordering later successes. When M3U output is enabled, the M3U will contain the successful resolved occurrences in source order and preserve repeats.

Until issue #81 is implemented, Last.fm playlists retain legacy duplicate handling. Earlier matches do not prove that the current Last.fm source resolves to the same Qobuz tracks.

## Changes that invalidate satisfaction

### Deleted file

If a required file was deleted, the request is not satisfied. A history row cannot prevent restoration of the missing file.

### Renamed template

If a folder or track template now produces a different path, the new path is the requested destination. A file at the old path does not satisfy the new request.

### Quality fallback

With fallback enabled, a lower-quality result is acceptable only when the normal fresh-download rule accepts that result. History records both the requested format and the actual media facts. It must not rewrite the actual facts to match the request.

With `--no-fallback`, an artifact that represents a rejected downgrade does not satisfy the request. A lower-quality file accepted by an earlier fallback-enabled request cannot satisfy a later no-fallback request unless its actual media facts pass the later request's rule.

### Unverified path conflict

Two Qobuz IDs can resolve to the same requested path. The shared path does not satisfy either ID unless the implementation can verify which item the file represents. If identity cannot be verified, the implementation must report the conflict and must not overwrite the file silently.

## Command semantics

### `--no-db`

`--no-db` disables both reads from and writes to persistent download history for that run. Run-local evidence can satisfy later occurrences in the same process. It does not authorize an overwrite or weaken the identity, destination, or quality rule. A missing path can be downloaded normally. For direct track and album requests, an unexplained pre-existing path reports a conflict and remains unchanged.

### `--purge`

`--purge` deletes persistent download history only. It does not delete media files. After a purge, later requests have no persisted artifact evidence. They can reuse an existing file only when independent trustworthy evidence establishes its identity and effective quality. Otherwise they preserve the file and report a conflict.

## Existing databases

For direct track and album requests, existing ID-only rows are historical evidence and never authoritative satisfaction. They can indicate that an item succeeded before, but they contain no destination or actual media facts. Playlist paths retain their legacy use of these rows until issue #81.

The schema migration retains those IDs as historical evidence. It does not convert them into verified artifact records. Each later direct request must establish satisfaction from the exact requested path and the file's actual media facts.

## Replacement recovery

Direct requests stage, tag, and verify new media in a private `.qdl-*` directory beside the destination. A handled failure or interruption after displacement retains the private recovery directory and logs its path, even when restoration of the prior artifact succeeds. Recovery assumes that the destination parent stays stable and no other process modifies the private workspace.

## Boundaries

- No cross-destination copy, move, hard link, or symbolic link
- No claim that issues #79 or #80 are merged into `master`
- No claim that issue #80 changes Qobuz or Last.fm playlist behavior
- No SQLite migration in this decision artifact
- No change to the Qobuz format IDs or the fresh-download quality rule
- Cover art and embedded artwork remain outside duplicate-history satisfaction

The first boundary favors predictable requests over storage deduplication. A separate product decision would be required before history could reuse media across destinations.

## Consequences

- History becomes an optimization and evidence source, not the final authority
- The filesystem and verified media facts decide whether the current request is satisfied
- The same Qobuz ID may have valid artifacts in several destinations or at several effective qualities
- Verified artifact history preserves requested format separately from actual codec, bit depth, sample rate, bitrate, file size, and digest
- Legacy databases remain usable as history. Their ID-only rows cannot skip direct-request verification

## Follow-up slices

1. [Issue #79: Version SQLite and record verified track artifacts](https://github.com/pascalandy/qobuz-dl/issues/79)
2. [Issue #80: Require destination and effective quality for direct downloads](https://github.com/pascalandy/qobuz-dl/issues/80)
3. [Issue #81: Preserve playlist order and repeats with artifact-based reuse](https://github.com/pascalandy/qobuz-dl/issues/81)

Issues #79 and #80 are represented by stacked pull requests and in-progress implementation. Issue #81 remains pending. This document does not claim that any slice is merged into `master`.

## Evidence

- [`qobuz_dl/db.py`](../../../qobuz_dl/db.py) defines legacy ID history, verified artifacts, and run-local evidence
- [`qobuz_dl/core.py`](../../../qobuz_dl/core.py) limits legacy ID satisfaction to legacy destination paths
- [`tests/test_destination_history.py`](../../../tests/test_destination_history.py) covers exact-destination verification, media matching, conflict handling, replacement recovery, and `--no-db`
- [`tests/test_playlist_m3u.py`](../../../tests/test_playlist_m3u.py) preserves the transitional playlist behavior before issue #81
- [`tests/test_duplicate_tracking.py`](../../../tests/test_duplicate_tracking.py) covers legacy-schema behavior
- [Issue #49](https://github.com/pascalandy/qobuz-dl/issues/49) owns this decision
