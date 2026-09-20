"""
resolvedesk/data.py
-------------------
Load and validate source records from the JSON files in data/.

These records are the authoritative source of truth for the assignment.
They are loaded once and treated as read-only. Application state is stored
separately in the SQLite database (database.py).

Design decision: We use simple dicts rather than ORM objects so that the data
layer remains readable for beginners and independent of the database module.
"""

import json
from pathlib import Path
from typing import Any

from resolvedesk.config import (
    DATA_POLICIES_FILE,
    DATA_REQUESTS_FILE,
    DATA_TICKETS_FILE,
)

# ── Internal cache (populated on first load) ──────────────────────────────────
_policies: list[dict] | None = None
_requests: list[dict] | None = None
_tickets:  list[dict] | None = None


def _load_json(path: Path) -> list[dict]:
    """Read a JSON file and return its contents as a list of dicts."""
    if not path.exists():
        raise FileNotFoundError(
            f"Source data file not found: {path}\n"
            "Make sure the data/ directory is present in the project root."
        )
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# ── Public loaders ────────────────────────────────────────────────────────────

def get_policies() -> list[dict]:
    """Return all 11 KB policies. Cached after first load."""
    global _policies
    if _policies is None:
        _policies = _load_json(DATA_POLICIES_FILE)
    return _policies


def get_requests() -> list[dict]:
    """Return all 15 employee requests. Cached after first load."""
    global _requests
    if _requests is None:
        _requests = _load_json(DATA_REQUESTS_FILE)
    return _requests


def get_tickets() -> list[dict]:
    """Return all 10 existing tickets. Cached after first load."""
    global _tickets
    if _tickets is None:
        _tickets = _load_json(DATA_TICKETS_FILE)
    return _tickets


# ── Lookup helpers ────────────────────────────────────────────────────────────

def get_policy_by_id(policy_id: str) -> dict | None:
    """Return a single policy dict by ID (e.g. 'KB-01'), or None."""
    return next(
        (p for p in get_policies() if p["id"] == policy_id.upper()),
        None,
    )


def get_request_by_id(req_id: str) -> dict | None:
    """Return a single employee request dict by ID (e.g. 'REQ-01'), or None."""
    return next(
        (r for r in get_requests() if r["id"] == req_id.upper()),
        None,
    )


def get_ticket_by_id(ticket_id: str) -> dict | None:
    """Return a single ticket dict by ID (e.g. 'TK-1043'), or None."""
    return next(
        (t for t in get_tickets() if t["id"] == ticket_id.upper()),
        None,
    )


def get_policies_for_topic(topic: str) -> list[dict]:
    """
    Return all policies whose topics list contains the given keyword (case-insensitive).
    Used by the rules engine and agent tools to retrieve relevant policy text.
    """
    topic_lower = topic.lower()
    return [
        p for p in get_policies()
        if any(topic_lower in t.lower() for t in p.get("topics", []))
    ]


def get_all_cases() -> list[dict]:
    """
    Return all 25 source records (15 requests + 10 tickets) in a unified format
    suitable for the All Cases tab display.
    Each record is tagged with 'record_type': 'request' or 'ticket'.
    """
    cases = []
    for r in get_requests():
        cases.append({**r, "record_type": "request", "is_closed": False})
    for t in get_tickets():
        cases.append({**t, "record_type": "ticket"})
    return cases


def get_active_cases() -> list[dict]:
    """Return only actionable (non-closed) source records."""
    return [c for c in get_all_cases() if not c.get("is_closed", False)]


def validate_source_counts() -> dict[str, Any]:
    """
    Sanity-check that the loaded data matches the expected counts.
    Returns a dict with pass/fail per category and any discrepancies found.
    Used by the test suite.
    """
    from resolvedesk.config import (
        TOTAL_POLICIES, TOTAL_REQUESTS, TOTAL_TICKETS,
        ACTIVE_TICKETS, CLOSED_TICKETS,
    )
    policies = get_policies()
    requests = get_requests()
    tickets  = get_tickets()

    active_tix  = [t for t in tickets if not t.get("is_closed")]
    closed_tix  = [t for t in tickets if t.get("is_closed")]

    return {
        "policies_ok":      len(policies) == TOTAL_POLICIES,
        "requests_ok":      len(requests) == TOTAL_REQUESTS,
        "tickets_ok":       len(tickets)  == TOTAL_TICKETS,
        "active_tickets_ok":  len(active_tix) == ACTIVE_TICKETS,
        "closed_tickets_ok":  len(closed_tix) == CLOSED_TICKETS,
        "policy_count":     len(policies),
        "request_count":    len(requests),
        "ticket_count":     len(tickets),
        "active_ticket_count":  len(active_tix),
        "closed_ticket_count":  len(closed_tix),
    }
