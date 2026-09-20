"""
resolvedesk/database.py
-----------------------
SQLite persistence layer for application state, clarifications, plans, and audit history.

Design decisions:
- The database is created automatically at startup; no manual setup is needed.
- Source records in JSON are immutable. This DB stores only derived application state.
- All SQL uses parameterised queries to prevent injection.
- Transactions are used for multi-statement writes to ensure atomicity.
- The audit log is append-only; completed actions are never deleted.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from resolvedesk.config import DB_PATH


# ── Connection helper ─────────────────────────────────────────────────────────

def _get_conn(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """
    Open (or create) the SQLite database and return a connection.
    row_factory gives us dict-like row access by column name.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safer concurrent access
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Current application state for each source case.
-- source_status is the immutable status from the JSON; current_status tracks changes.
CREATE TABLE IF NOT EXISTS case_state (
    case_id         TEXT PRIMARY KEY,
    record_type     TEXT NOT NULL,          -- 'request' or 'ticket'
    source_status   TEXT NOT NULL,          -- original, never overwritten
    current_status  TEXT NOT NULL,
    topic           TEXT,
    last_updated    TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1
);

-- Clarifications and follow-up inputs submitted by the operator or employee.
-- These are stored as reported information, not verified facts.
-- No FOREIGN KEY constraint: clarifications may be added before case_state exists
-- (e.g., during analysis before an action is recorded). Case ID is validated
-- at the application layer (data.py) instead.
CREATE TABLE IF NOT EXISTS clarifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         TEXT NOT NULL,
    submitted_at    TEXT NOT NULL,
    reported_by     TEXT NOT NULL DEFAULT 'operator',
    clarification   TEXT NOT NULL,
    structured_data TEXT                    -- JSON blob of extracted fields
);

-- Conversation messages for each case (stored as reported context).
CREATE TABLE IF NOT EXISTS conversation (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id     TEXT NOT NULL,
    role        TEXT NOT NULL,              -- 'user' | 'assistant' | 'system'
    content     TEXT NOT NULL,
    timestamp   TEXT NOT NULL
);

-- Plans staged by the agent, pending operator review.
CREATE TABLE IF NOT EXISTS staged_plans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    plan_version    INTEGER NOT NULL DEFAULT 1,
    plan_json       TEXT NOT NULL,          -- full plan as JSON
    status          TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'recorded' | 'superseded'
    recorded_at     TEXT
);

-- Append-only audit log of every simulated action that was recorded.
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,          -- UTC ISO-8601
    case_id         TEXT NOT NULL,
    action_type     TEXT NOT NULL,
    old_status      TEXT,
    new_status      TEXT,
    description     TEXT NOT NULL,
    evidence_ids    TEXT,                   -- JSON array of policy/case IDs cited
    is_simulation   INTEGER NOT NULL DEFAULT 1,  -- always 1 in this app
    operator        TEXT NOT NULL DEFAULT 'operator'
);
"""


def init_db(db_path: Path = DB_PATH) -> None:
    """
    Create all tables if they do not exist.
    Safe to call on every startup — uses CREATE TABLE IF NOT EXISTS.
    """
    with _get_conn(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


# ── Case state ────────────────────────────────────────────────────────────────

def upsert_case_state(
    case_id: str,
    record_type: str,
    source_status: str,
    current_status: str,
    topic: str = "",
    db_path: Path = DB_PATH,
) -> None:
    """
    Insert or update the application state for a case.
    source_status is only written on INSERT — never overwritten on UPDATE,
    preserving the immutable original status.
    """
    now = _utcnow()
    with _get_conn(db_path) as conn:
        existing = conn.execute(
            "SELECT version, source_status FROM case_state WHERE case_id = ?",
            (case_id,),
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE case_state
                   SET current_status = ?, topic = ?, last_updated = ?,
                       version = version + 1
                   WHERE case_id = ?""",
                (current_status, topic, now, case_id),
            )
        else:
            conn.execute(
                """INSERT INTO case_state
                   (case_id, record_type, source_status, current_status, topic, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (case_id, record_type, source_status, current_status, topic, now),
            )
        conn.commit()


def get_case_state(case_id: str, db_path: Path = DB_PATH) -> dict | None:
    """Return the current application state for a case, or None if not yet stored."""
    with _get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM case_state WHERE case_id = ?", (case_id,)
        ).fetchone()
    return dict(row) if row else None


# ── Clarifications ────────────────────────────────────────────────────────────

def add_clarification(
    case_id: str,
    clarification: str,
    structured_data: dict | None = None,
    reported_by: str = "operator",
    db_path: Path = DB_PATH,
) -> int:
    """
    Store a clarification as reported information.
    Returns the new row ID.
    structured_data (if supplied) is serialised to JSON.
    """
    now = _utcnow()
    structured_json = json.dumps(structured_data) if structured_data else None
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO clarifications (case_id, submitted_at, reported_by, clarification, structured_data)
               VALUES (?, ?, ?, ?, ?)""",
            (case_id, now, reported_by, clarification, structured_json),
        )
        conn.commit()
        return cursor.lastrowid


def get_clarifications(case_id: str, db_path: Path = DB_PATH) -> list[dict]:
    """Return all clarifications for a case, oldest first."""
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM clarifications WHERE case_id = ? ORDER BY id ASC",
            (case_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Conversation ──────────────────────────────────────────────────────────────

def add_message(
    case_id: str,
    role: str,
    content: str,
    db_path: Path = DB_PATH,
) -> None:
    """Append a message to the conversation history for a case."""
    with _get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO conversation (case_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (case_id, role, content, _utcnow()),
        )
        conn.commit()


def get_conversation(case_id: str, db_path: Path = DB_PATH) -> list[dict]:
    """Return the conversation history for a case, oldest first."""
    with _get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM conversation WHERE case_id = ? ORDER BY id ASC",
            (case_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def clear_conversation(case_id: str, db_path: Path = DB_PATH) -> None:
    """Clear conversation history for a case (used when restarting analysis)."""
    with _get_conn(db_path) as conn:
        conn.execute("DELETE FROM conversation WHERE case_id = ?", (case_id,))
        conn.commit()


# ── Staged plans ──────────────────────────────────────────────────────────────

def stage_plan(case_id: str, plan: dict, db_path: Path = DB_PATH) -> int:
    """
    Store a plan staged by the agent for operator review.
    Marks any previous pending plan for this case as superseded.
    Returns the new plan row ID.
    """
    now = _utcnow()
    with _get_conn(db_path) as conn:
        # Supersede any pending plans for this case to prevent stale approvals.
        conn.execute(
            "UPDATE staged_plans SET status = 'superseded' WHERE case_id = ? AND status = 'pending'",
            (case_id,),
        )
        cursor = conn.execute(
            """INSERT INTO staged_plans (case_id, created_at, plan_json, status)
               VALUES (?, ?, ?, 'pending')""",
            (case_id, now, json.dumps(plan)),
        )
        conn.commit()
        return cursor.lastrowid


def get_pending_plan(case_id: str, db_path: Path = DB_PATH) -> dict | None:
    """Return the most recent pending plan for a case, or None."""
    with _get_conn(db_path) as conn:
        row = conn.execute(
            """SELECT * FROM staged_plans WHERE case_id = ? AND status = 'pending'
               ORDER BY id DESC LIMIT 1""",
            (case_id,),
        ).fetchone()
    if row:
        r = dict(row)
        r["plan"] = json.loads(r["plan_json"])
        return r
    return None


def record_plan(plan_row_id: int, db_path: Path = DB_PATH) -> bool:
    """
    Mark a staged plan as recorded.
    Returns False if the plan was not in 'pending' state (stale / already recorded).
    This is the guard against duplicate recording.
    """
    now = _utcnow()
    with _get_conn(db_path) as conn:
        cursor = conn.execute(
            """UPDATE staged_plans SET status = 'recorded', recorded_at = ?
               WHERE id = ? AND status = 'pending'""",
            (now, plan_row_id),
        )
        conn.commit()
        return cursor.rowcount == 1   # 0 means it was already recorded or superseded


# ── Audit log ─────────────────────────────────────────────────────────────────

def append_audit(
    case_id: str,
    action_type: str,
    description: str,
    old_status: str | None = None,
    new_status: str | None = None,
    evidence_ids: list[str] | None = None,
    operator: str = "operator",
    db_path: Path = DB_PATH,
) -> None:
    """Append an immutable audit record. API keys are never logged here."""
    with _get_conn(db_path) as conn:
        conn.execute(
            """INSERT INTO audit_log
               (timestamp, case_id, action_type, old_status, new_status,
                description, evidence_ids, is_simulation, operator)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                _utcnow(), case_id, action_type,
                old_status, new_status, description,
                json.dumps(evidence_ids or []), operator,
            ),
        )
        conn.commit()


def get_audit_log(case_id: str | None = None, db_path: Path = DB_PATH) -> list[dict]:
    """
    Return audit records. If case_id is supplied, filter to that case.
    Otherwise return all records (for the Action History tab).
    """
    with _get_conn(db_path) as conn:
        if case_id:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE case_id = ? ORDER BY id ASC",
                (case_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC"
            ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["evidence_ids"] = json.loads(d.get("evidence_ids") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["evidence_ids"] = []
        result.append(d)
    return result


# ── Utility ───────────────────────────────────────────────────────────────────

def _utcnow() -> str:
    """Return the current UTC time as an ISO-8601 string, clearly labelled as UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def export_audit_json(db_path: Path = DB_PATH) -> str:
    """
    Return all audit records as a JSON string for the download button.
    API keys and operator credentials are never included.
    """
    records = get_audit_log(db_path=db_path)
    return json.dumps(records, indent=2, ensure_ascii=False)
