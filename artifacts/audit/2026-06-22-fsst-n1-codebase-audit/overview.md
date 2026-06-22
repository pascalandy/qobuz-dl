# Plain-Language Audit Overview

`qobuz-dl` is a compact Python CLI with a clear architecture: command parsing in `commands.py`, startup/config wiring in `cli.py`, user workflows in `core.py`, Qobuz API calls in `qopy.py`, HTTP in `http.py`, download/tagging in `downloader.py` and `metadata.py`, and duplicate tracking in `db.py`. The repo is much cleaner than the original dependency footprint suggests: runtime dependencies are down to `mutagen`, package metadata lives in `pyproject.toml`, the lock file is present, and tests cover CLI, HTTP, Qobuz API request construction, Last.fm parsing, downloads, metadata helpers, sanitization, and interactive prompts.

The main risks are not general Python framework problems. They are specific to this app's job: Qobuz API access, credential handling, local file permissions, bulk API behavior, Windows filename/startup compatibility, CI supply-chain hardening, and a stale research artifact. I did not find background workers, cron-like jobs, elevated privileges, shell execution, arbitrary code execution, or a deployment service surface.

The highest-priority client handoff risks are the Qobuz compliance boundary and credential handling. The app scrapes app IDs/secrets from Qobuz web assets and stores those secrets locally, while Qobuz's API Terms say application IDs/secrets are issued by Qobuz and must not be shared. The README also says the tool is unaffiliated, but it does not display the exact "uses the Qobuz API but is not certified by Qobuz" language that the terms require. Separately, login uses a GET request with email and password hash in query parameters, which increases log and proxy exposure.

The external numeric limit check has one important blocked item: I could not verify a current official Qobuz numeric API rate limit. Qobuz's Terms say Qobuz may limit API call volume and content access without notice, but no accessible primary source gave a number. The app itself uses 500-item collection pages, so 501 items require 2 metadata pages, 1001 require 3, and 2500 require 5 before per-track file URL calls.

No application fixes were made. This directory is the audit package: criteria, evidence table, verification log, and one `pa-vision`-style file per material issue.

## Bottom Line

The codebase is testable and reasonably well organized, but it is not client-safe to describe as fully clean. Before implementation work, prioritize credential/compliance risks, then platform compatibility and operational hardening.
