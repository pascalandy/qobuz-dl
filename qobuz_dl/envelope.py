"""The one JSON object that ``qobuz-dl --json`` prints on stdout."""

from __future__ import annotations

import json
import sys

from qobuz_dl.console import ExitCode, redact
from qobuz_dl.downloader import PlannedDestination

SCHEMA_VERSION = 1

STATUS_BY_EXIT = {
    ExitCode.OK: "ok",
    ExitCode.FAILURE: "failed",
    ExitCode.TEMPORARY: "failed",
    ExitCode.USAGE: "usage_error",
    ExitCode.INTERRUPTED: "interrupted",
    ExitCode.TERMINATED: "interrupted",
}

# What a finalized result proves about the file at its path.
_EVIDENCE = {
    "downloaded": "published",
    "verified_artifact": "verified",
    "existing_file": "filename_only",
}


def document(operation, status, data=None, problems=()):
    return {
        "schema_version": SCHEMA_VERSION,
        "operation": operation,
        "status": status,
        "data": data,
        "problems": list(problems),
    }


def problem(code, message, *, source=None, retryable=False, hint=None):
    return {
        "code": code,
        "severity": "error",
        "message": redact(message),
        "source": source,
        "retryable": retryable,
        "hint": None if hint is None else redact(hint),
    }


def usage_error(message, hint):
    """The object for a usage error: no operation ran."""
    return document(
        None, "usage_error", None, [problem("usage_error", message, hint=hint)]
    )


def _item(item):
    result = item.result
    if isinstance(result, PlannedDestination):
        return {
            "source": item.source,
            "kind": item.kind,
            "item_id": item.item_id,
            "state": "planned",
            "reason": None,
            "retryable": False,
            "paths": [result.path],
            "evidence": None,
            "exists": result.exists,
        }
    return {
        "source": item.source,
        "kind": item.kind,
        "item_id": item.item_id,
        "state": result.state,
        "reason": result.reason,
        "retryable": result.retryable,
        "paths": list(result.finalized_paths),
        "evidence": _EVIDENCE.get(result.reason)
        if result.state == "finalized"
        else None,
        "exists": None,
    }


def run_data(run, *, dry_run=False):
    items = [_item(item) for item in run.items]
    totals = {"items": len(items)}
    for state in ("finalized", "planned", "ignored", "failed"):
        totals[state] = sum(1 for item in items if item["state"] == state)
    totals["retryable"] = sum(1 for item in items if item["retryable"])
    totals["problems"] = len(run.problems)
    return {"dry_run": dry_run, "items": items, "totals": totals}


def run_problems(run, retry_hint=None):
    return [
        problem(
            entry.code,
            entry.message,
            source=entry.source,
            retryable=entry.retryable,
            hint=retry_hint if entry.retryable else None,
        )
        for entry in run.problems
    ]


def write(value, stream=None):
    stream = sys.stdout if stream is None else stream
    stream.write(json.dumps(value, ensure_ascii=False) + "\n")
    stream.flush()
