"""
tests/test_database.py
----------------------
Tests for SQLite persistence: case state, clarifications, audit log,
duplicate recording prevention, and closed-case protection.
Uses in-memory / temporary SQLite databases so no file cleanup is needed.
No API key, network, or Streamlit required.
"""

import json
import tempfile
import unittest
from pathlib import Path

from resolvedesk.database import (
    init_db, upsert_case_state, get_case_state,
    add_clarification, get_clarifications,
    add_message, get_conversation,
    stage_plan, get_pending_plan, record_plan,
    append_audit, get_audit_log, export_audit_json,
)


def _tmp_db() -> Path:
    """Create a temporary in-memory-ish SQLite database for testing."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    path = Path(f.name)
    init_db(path)
    return path


class TestCaseState(unittest.TestCase):

    def setUp(self):
        self.db = _tmp_db()

    def test_upsert_creates_new_case(self):
        upsert_case_state("REQ-01", "request", "Not started", "In progress", db_path=self.db)
        state = get_case_state("REQ-01", db_path=self.db)
        self.assertIsNotNone(state)
        self.assertEqual(state["current_status"], "In progress")
        self.assertEqual(state["source_status"],  "Not started")

    def test_source_status_not_overwritten_on_update(self):
        upsert_case_state("REQ-01", "request", "Not started", "In progress", db_path=self.db)
        upsert_case_state("REQ-01", "request", "WRONG",        "Resolved",    db_path=self.db)
        state = get_case_state("REQ-01", db_path=self.db)
        self.assertEqual(state["source_status"], "Not started",
                         "source_status must not be overwritten on subsequent updates")
        self.assertEqual(state["current_status"], "Resolved")

    def test_version_increments_on_update(self):
        upsert_case_state("REQ-01", "request", "Not started", "In progress", db_path=self.db)
        upsert_case_state("REQ-01", "request", "Not started", "Resolved",    db_path=self.db)
        state = get_case_state("REQ-01", db_path=self.db)
        self.assertEqual(state["version"], 2)

    def test_get_nonexistent_case_returns_none(self):
        result = get_case_state("REQ-99", db_path=self.db)
        self.assertIsNone(result)


class TestClarifications(unittest.TestCase):

    def setUp(self):
        self.db = _tmp_db()

    def test_add_and_retrieve_clarification(self):
        add_clarification("REQ-03", "Employee confirmed 6 failed attempts.", db_path=self.db)
        clist = get_clarifications("REQ-03", db_path=self.db)
        self.assertEqual(len(clist), 1)
        self.assertIn("6 failed", clist[0]["clarification"])

    def test_structured_data_stored_as_json(self):
        add_clarification("REQ-03", "facts", {"failed_attempts": 6}, db_path=self.db)
        clist = get_clarifications("REQ-03", db_path=self.db)
        sd = json.loads(clist[0]["structured_data"])
        self.assertEqual(sd["failed_attempts"], 6)

    def test_clarifications_isolated_per_case(self):
        add_clarification("REQ-01", "Clarification for REQ-01", db_path=self.db)
        add_clarification("REQ-02", "Clarification for REQ-02", db_path=self.db)
        self.assertEqual(len(get_clarifications("REQ-01", db_path=self.db)), 1)
        self.assertEqual(len(get_clarifications("REQ-02", db_path=self.db)), 1)


class TestConversation(unittest.TestCase):

    def setUp(self):
        self.db = _tmp_db()

    def test_add_and_retrieve_messages(self):
        add_message("REQ-05", "user", "My VPN is not working.", self.db)
        add_message("REQ-05", "assistant", "Please renew your credentials.", self.db)
        conv = get_conversation("REQ-05", db_path=self.db)
        self.assertEqual(len(conv), 2)
        self.assertEqual(conv[0]["role"], "user")
        self.assertEqual(conv[1]["role"], "assistant")


class TestStagedPlans(unittest.TestCase):

    def setUp(self):
        self.db = _tmp_db()

    def _make_plan(self, case_id="REQ-01"):
        return {
            "case_id":              case_id,
            "topic":                "laptop",
            "proposed_action":      "Arrange IT diagnosis.",
            "proposed_route":       "IT",
            "policy_ids":           ["KB-03", "ASSET-Q2-2026"],
            "summary":              "Test plan",
            "employee_explanation": "Test explanation",
            "current_status":       "Not started",
            "proposed_status":      "In progress",
            "is_simulation":        True,
        }

    def test_stage_and_retrieve_pending_plan(self):
        plan = self._make_plan()
        plan_id = stage_plan("REQ-01", plan, db_path=self.db)
        self.assertIsNotNone(plan_id)
        pending = get_pending_plan("REQ-01", db_path=self.db)
        self.assertIsNotNone(pending)
        self.assertEqual(pending["plan"]["case_id"], "REQ-01")

    def test_record_plan_marks_as_recorded(self):
        plan = self._make_plan()
        plan_id = stage_plan("REQ-01", plan, db_path=self.db)
        success = record_plan(plan_id, db_path=self.db)
        self.assertTrue(success)
        # Pending plan should now be gone.
        pending = get_pending_plan("REQ-01", db_path=self.db)
        self.assertIsNone(pending)

    def test_duplicate_recording_is_idempotent(self):
        """Recording the same plan twice should fail the second time."""
        plan = self._make_plan()
        plan_id = stage_plan("REQ-01", plan, db_path=self.db)
        first  = record_plan(plan_id, db_path=self.db)
        second = record_plan(plan_id, db_path=self.db)
        self.assertTrue(first)
        self.assertFalse(second, "Second recording must return False (already recorded)")

    def test_new_plan_supersedes_old_pending(self):
        """Staging a second plan should mark the first as superseded."""
        plan1_id = stage_plan("REQ-01", self._make_plan(), db_path=self.db)
        plan2_id = stage_plan("REQ-01", self._make_plan(), db_path=self.db)
        # Only the latest plan should be pending.
        pending = get_pending_plan("REQ-01", db_path=self.db)
        self.assertEqual(pending["id"], plan2_id)


class TestAuditLog(unittest.TestCase):

    def setUp(self):
        self.db = _tmp_db()

    def test_append_and_retrieve_audit(self):
        append_audit(
            case_id="REQ-01",
            action_type="test_action",
            description="Test audit entry",
            old_status="Not started",
            new_status="In progress",
            evidence_ids=["KB-03"],
            db_path=self.db,
        )
        log = get_audit_log("REQ-01", db_path=self.db)
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0]["action_type"], "test_action")
        self.assertEqual(log[0]["evidence_ids"], ["KB-03"])

    def test_audit_is_simulation_always_true(self):
        append_audit("REQ-01", "test", "Test", db_path=self.db)
        log = get_audit_log("REQ-01", db_path=self.db)
        self.assertEqual(log[0]["is_simulation"], 1)

    def test_export_json_no_secrets(self):
        append_audit("REQ-01", "test", "Test entry", db_path=self.db)
        export = export_audit_json(db_path=self.db)
        # Must not contain anything that looks like an API key pattern.
        self.assertNotIn("sk-", export)
        self.assertNotIn("api_key", export)

    def test_audit_log_global_returns_all(self):
        append_audit("REQ-01", "action1", "A", db_path=self.db)
        append_audit("REQ-02", "action2", "B", db_path=self.db)
        log = get_audit_log(db_path=self.db)
        self.assertGreaterEqual(len(log), 2)


class TestClosedTicketProtection(unittest.TestCase):
    """Closed tickets must be immutable — they cannot be actioned."""

    def setUp(self):
        self.db = _tmp_db()

    def test_validate_plan_blocks_closed_cases(self):
        from resolvedesk.rules import validate_plan
        plan = {
            "case_id": "TK-1042",
            "proposed_action": "Test action",
            "policy_ids": ["KB-01"],
        }
        ok, msg = validate_plan(plan, "TK-1042", is_closed=True)
        self.assertFalse(ok)
        self.assertIn("closed", msg.lower())

    def test_closed_ticket_is_closed_flag(self):
        from resolvedesk.data import get_ticket_by_id
        closed_ids = ["TK-1042", "TK-1045", "TK-1046", "TK-1049", "TK-1050", "TK-1051"]
        for tid in closed_ids:
            t = get_ticket_by_id(tid)
            self.assertTrue(t["is_closed"], f"{tid} should be marked closed")


if __name__ == "__main__":
    unittest.main()
