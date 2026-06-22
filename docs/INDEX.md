# Documentation

Project documentation lives here when it is too detailed for the README.

## User documentation

- [Installation](installation.md) — requirements, uvx no-install usage, optional persistent install, first run, and reset instructions.
- [Examples](examples.md) — download mode, Last.fm playlists, interactive mode, lucky mode, and duplicate tracking.
- [Use cases](use-cases.md) — goal-oriented local-library workflows for account setup, hi-res downloads, discovery, organization, duplicate tracking, and maintenance.
- [CLI reference](cli.md) — top-level CLI usage and command overview.
- [Module usage](module-usage.md) — importing `qobuz-dl` as a library.

## Maintainer documentation

- [Dependencies](dependencies.md) — dependency policy, runtime inventory, usage sites, and update rules.
- [Development](development.md) — local fork workflow, global CLI separation, `qdl-dev`, and Chezmoi-managed shell config.
- [Packaging](packaging.md) — Python packaging metadata, dependency locking, build-file ownership, and the release process.
- [Testing](testing.md) — uv-based linting, formatting, tests, smoke checks, and GitHub Actions CI/CD.
- [Changelog](../CHANGELOG.md) — notable changes per release.
- [Contributing](../CONTRIBUTING.md) — setup, workflow, ground rules, and release steps.

## Feature direction

- [Bandwidth limit vision](feat/2026-06-22-bandwidth-limit-vision/vision-bandwidth-limit.md) — direction check for optional download pacing and central rate-limit/backoff handling.

## Research

- [Qobuz official API and SDK research](research/qobuz-official-api.md) — official-source findings, missing developer docs, community substitutes, endpoint confidence, and gaps.
- [go-qobuz unofficial client reference](research/go-qobuz-reference.md) — notes on the Go implementation's auth flow, endpoint surface, signing behavior, and future-use boundaries.
- [Local project capability map](research/local-project-capabilities.md) — current CLI/API coverage, auth behavior, tests/docs constraints, and likely integration points.
