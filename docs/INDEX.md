# Documentation

Project documentation lives here when it is too detailed for the README.

## Start with the question

| Question | Read next |
| --- | --- |
| How does the checked-out system work, and where should a change go? | [Architecture](architecture.md), including the owner and proof map |
| Which checkout and command am I testing? | [Development](development.md#identify-the-checkout-and-current-work) |
| What would make the CLI reliable for agents? | [Agent operation design](feat/2026-09-12-agent-ergonomics/design-agent-ergonomics.md) |
| What is the proposed delivery order and how does it fit open PRs? | [Agent operation implementation plan](feat/2026-09-12-agent-ergonomics/impl-plan-agent-ergonomics.md) |

Source in the named checkout owns current behavior. Feature documents label future contracts. [Epic #20](https://github.com/pascalandy/qobuz-dl/issues/20) and its child issues own live work status. Research and audit artifacts retain their observation dates; confirm their claims against current source before acting.

## User documentation

- [Qobuz access and project status](qobuz-access.md) records the current access decision, Beta maturity, public notices, and evidence limits
- [Installation](installation.md): explicit fork source, no-install and persistent usage, reproducible revisions, config persistence, and install verification.
- [Examples](examples.md) — download mode, Last.fm playlists, interactive mode, lucky mode, and duplicate tracking.
- [Use cases](use-cases.md) — goal-oriented local-library workflows for account setup, hi-res downloads, discovery, organization, duplicate tracking, and maintenance.
- [CLI reference](cli.md) — top-level CLI usage and command overview.
- [Module usage](module-usage.md) — importing `qobuz-dl` as a library.

## Maintainer documentation

- [Dependencies](dependencies.md) — dependency policy, runtime inventory, usage sites, and update rules.
- [Development](development.md) covers the reusable local workflow, global CLI separation, and Pascal's optional `qdl-dev` setup.
- [Packaging](packaging.md) — Python packaging metadata, dependency locking, build-file ownership, and the release process.
- [Testing](testing.md): uv-based checks, isolated package tests, opt-in Git install and live Qobuz verification, and GitHub Actions CI/CD.
- [Changelog](../CHANGELOG.md) — notable changes per release.
- [Contributing](../CONTRIBUTING.md) — setup, workflow, ground rules, and release steps.

## Feature direction

- [Agent operation design and implementation plan](feat/2026-09-12-agent-ergonomics/design-agent-ergonomics.md) connects inspectable requests, bounded selection, artifact results, and recovery; proposed behavior only
- [Qobuz API direction](feat/2026-05-26-qobuz-api-direction/vision-qobuz-api-direction.md) keeps read-only source expansion within the downloader mission
- [Bandwidth limit vision](feat/2026-06-22-bandwidth-limit-vision/vision-bandwidth-limit.md) — approved policy for optional audio media pacing and central rate-limit/backoff handling.
- [Download history satisfaction policy](feat/2026-09-12-download-history-policy/plan-download-history-satisfaction.md) defines when history may satisfy a request and records the follow-up implementation slices.

## Historical design

- [Dependency hardening architecture](feat/2026-05-26-dependency-hardening/architecture-dependency-hardening.md) records the completed migration and links its historical plans; [Dependencies](dependencies.md) owns current policy

## Research

- [Qobuz access and project status](qobuz-access.md) is the canonical current decision. The research documents below preserve dated evidence and uncertainty
- [Authentication credential and transport evidence](research/authentication-transport.md). Local credential representations, current request placement, dated public-client observations, and server-contract limits.
- [Qobuz official API and SDK research](research/qobuz-official-api.md) — official-source findings, missing developer docs, community substitutes, endpoint confidence, and gaps.
- [go-qobuz unofficial client reference](research/go-qobuz-reference.md) — notes on the Go implementation's auth flow, endpoint surface, signing behavior, and future-use boundaries.
- [Local project capability map](research/local-project-capabilities.md) is the 26 May 2026 project snapshot with dated corrections and current-source anchors.
