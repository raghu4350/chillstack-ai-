"""
tests/test_agent.py
-------------------
Tests for the agent module: offline mode, error handling, and mocked Mistral protocol.

These tests do NOT make real API calls.
- Offline mode tests verify correct plan structure without any LLM.
- Error handling tests verify that missing keys and API failures are reported correctly.
- The mock Mistral test verifies that the tool-calling loop wires correctly,
  using a mock that produces a realistic Mistral response structure.

No real API key or network required.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from resolvedesk.database import init_db
from resolvedesk.agent import run_offline, run_agent, AgentResult


def _tmp_db() -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    p = Path(f.name)
    init_db(p)
    return p


class TestOfflineMode(unittest.TestCase):
    """Verify offline analysis produces correct plans without any API."""

    def setUp(self):
        self.db = _tmp_db()

    def _run(self, case_id: str) -> AgentResult:
        return run_offline(case_id, db_path=self.db)

    def test_offline_mode_labelled_offline(self):
        result = self._run("REQ-02")
        self.assertEqual(result.mode, "offline")

    def test_guest_wifi_offline(self):
        result = self._run("REQ-02")
        self.assertTrue(result.success)
        plan = result.plan
        self.assertIn("KB-07", plan["policy_ids"])
        self.assertIn("kiosk", plan["employee_explanation"].lower())

    def test_phishing_offline_is_urgent(self):
        result = self._run("REQ-08")
        self.assertTrue(result.success)
        self.assertTrue(result.plan.get("is_urgent"), "Phishing case must be flagged urgent")

    def test_vague_request_offline_asks_questions(self):
        result = self._run("REQ-15")
        self.assertTrue(result.success)
        plan = result.plan
        self.assertTrue(
            len(plan.get("questions_for_employee", [])) > 0,
            "Vague request must produce clarifying questions"
        )

    def test_laptop_conflict_offline_shows_both_policies(self):
        result = self._run("REQ-01")
        self.assertTrue(result.success)
        pids = result.plan.get("policy_ids", [])
        self.assertIn("KB-03", pids)
        self.assertIn("ASSET-Q2-2026", pids)

    def test_security_offline_preserves_escalation(self):
        result = self._run("REQ-08")
        plan = result.plan
        explanation = plan.get("employee_explanation", "").lower()
        self.assertIn("security", explanation)

    def test_closed_ticket_offline_mode_closed(self):
        result = self._run("TK-1042")
        self.assertEqual(result.mode, "closed")
        # A closed ticket result always has a plan (the closed-history plan),
        # but it should not be actionable. Check the plan is marked closed.
        self.assertTrue(
            result.plan is not None and result.plan.get("closed_history_only", False),
            "Closed ticket plan must have closed_history_only=True"
        )

    def test_all_active_requests_produce_plan(self):
        """All 15 employee requests must produce a plan in offline mode."""
        for i in range(1, 16):
            req_id = f"REQ-{i:02d}"
            result = self._run(req_id)
            self.assertIn(result.mode, ("offline", "closed"),
                          f"{req_id} returned unexpected mode: {result.mode}")
            if result.mode == "offline":
                self.assertIsNotNone(result.plan, f"{req_id} returned no plan")

    def test_active_tickets_produce_plan(self):
        active_ids = ["TK-1043", "TK-1044", "TK-1047", "TK-1048"]
        for tid in active_ids:
            result = self._run(tid)
            self.assertEqual(result.mode, "offline", f"{tid} should be in offline mode")
            self.assertIsNotNone(result.plan, f"{tid} returned no plan")

    def test_offline_mode_is_simulation(self):
        result = self._run("REQ-01")
        self.assertTrue(result.plan.get("is_simulation"),
                        "All plans must be marked as simulation")


class TestAgentErrorHandling(unittest.TestCase):
    """Verify honest error reporting when API key is missing or API fails."""

    def setUp(self):
        self.db = _tmp_db()

    def test_missing_api_key_returns_error(self):
        result = run_agent("REQ-01", api_key="", db_path=self.db)
        self.assertEqual(result.mode, "error")
        self.assertIsNone(result.plan)
        self.assertIn("api key", result.error.lower())

    def test_invalid_case_id_returns_error(self):
        result = run_offline("REQ-99", db_path=self.db)
        self.assertEqual(result.mode, "error")
        self.assertIsNone(result.plan)

    @patch("resolvedesk.agent.Mistral")
    def test_api_exception_reported_honestly(self, mock_mistral_class):
        """Simulate an API exception and verify it is reported, not silenced."""
        mock_client = MagicMock()
        mock_mistral_class.return_value = mock_client
        mock_client.chat.complete.side_effect = Exception("Connection timeout")

        result = run_agent("REQ-01", api_key="fake_key_for_test", db_path=self.db)
        self.assertEqual(result.mode, "error")
        self.assertIsNotNone(result.error)
        # Error must not expose the fake key.
        self.assertNotIn("fake_key_for_test", result.error)

    @patch("resolvedesk.agent.Mistral")
    def test_api_key_not_in_error_message(self, mock_mistral_class):
        """API key must never appear in error messages."""
        mock_client = MagicMock()
        mock_mistral_class.return_value = mock_client
        secret_key = "sk-secret-test-key-12345"
        mock_client.chat.complete.side_effect = Exception(f"Auth failed: {secret_key}")

        result = run_agent("REQ-01", api_key=secret_key, db_path=self.db)
        self.assertNotIn(secret_key, result.error or "")


class TestMockedMistralToolLoop(unittest.TestCase):
    """
    Verify that the agent loop correctly handles a realistic Mistral tool-calling
    response, executes the tools, and stages a plan.
    Uses mock objects that replicate the structure returned by the Mistral SDK.
    """

    def setUp(self):
        self.db = _tmp_db()

    def _make_tool_call(self, tool_id, name, arguments_dict):
        tc = MagicMock()
        tc.id = tool_id
        tc.function.name = name
        tc.function.arguments = json.dumps(arguments_dict)
        return tc

    def _make_assistant_msg(self, tool_calls=None, content=""):
        msg = MagicMock()
        msg.tool_calls = tool_calls or []
        msg.content = content
        return msg

    def _make_response(self, message, finish_reason="tool_calls"):
        choice = MagicMock()
        choice.message = message
        choice.finish_reason = finish_reason
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    @patch("resolvedesk.agent.Mistral")
    def test_tool_loop_stages_plan(self, mock_mistral_class):
        """
        Simulate: Mistral calls evaluate_case, then stage_plan.
        Verify the loop completes and a plan is staged.
        """
        mock_client = MagicMock()
        mock_mistral_class.return_value = mock_client

        # Round 1: model calls evaluate_case
        tc1 = self._make_tool_call("tc1", "evaluate_case", {
            "case_id": "REQ-02",
            "topic": "guest_wifi",
            "facts": {},
        })
        msg1 = self._make_assistant_msg(tool_calls=[tc1])
        resp1 = self._make_response(msg1, finish_reason="tool_calls")

        # Round 2: model calls stage_plan
        tc2 = self._make_tool_call("tc2", "stage_plan", {
            "case_id": "REQ-02",
            "topic": "guest_wifi",
            "category": "Self-service",
            "summary": "Guest Wi-Fi — front-desk kiosk, 24-hour credentials, no IT ticket needed.",
            "employee_explanation": "Please use the front-desk kiosk to generate guest Wi-Fi credentials.",
            "policy_ids": ["KB-07"],
            "proposed_action": "Direct employee to front-desk kiosk.",
            "proposed_route": "Self-service",
            "current_status": "Not started",
            "proposed_status": "Resolved — self-service",
        })
        msg2 = self._make_assistant_msg(tool_calls=[tc2])
        resp2 = self._make_response(msg2, finish_reason="tool_calls")

        # Round 3: model sends final text (no more tool calls)
        msg3 = self._make_assistant_msg(
            tool_calls=[],
            content="Analysis complete. Plan staged."
        )
        resp3 = self._make_response(msg3, finish_reason="stop")

        mock_client.chat.complete.side_effect = [resp1, resp2, resp3]

        result = run_agent("REQ-02", api_key="test_key", db_path=self.db)

        self.assertEqual(result.mode, "mistral")
        self.assertIsNotNone(result.plan)
        self.assertIn("KB-07", result.plan.get("policy_ids", []))
        # Verify tool trace contains the calls.
        tool_names = [step["tool"] for step in result.trace]
        self.assertIn("evaluate_case", tool_names)
        self.assertIn("stage_plan", tool_names)


class TestToolExecution(unittest.TestCase):
    """Verify individual tool execution guards."""

    def setUp(self):
        self.db = _tmp_db()

    def test_unknown_tool_name_rejected(self):
        from resolvedesk.tools import execute_tool
        result = execute_tool("exec_shell", {"cmd": "rm -rf /"}, db_path=self.db)
        self.assertFalse(result["ok"])
        self.assertIn("Unknown tool", result["error"])

    def test_ask_clarification_rejects_password_question(self):
        from resolvedesk.tools import execute_tool
        result = execute_tool("ask_clarification", {
            "case_id": "REQ-03",
            "question": "What is your password?",
        }, db_path=self.db)
        self.assertFalse(result["ok"])
        self.assertIn("password", result["error"].lower())

    def test_get_policy_invalid_id_returns_error(self):
        from resolvedesk.tools import execute_tool
        result = execute_tool("get_policy", {"policy_id": "KB-99"}, db_path=self.db)
        self.assertFalse(result["ok"])

    def test_get_case_valid_request(self):
        from resolvedesk.tools import execute_tool
        result = execute_tool("get_case", {"case_id": "REQ-01"}, db_path=self.db)
        self.assertTrue(result["ok"])
        self.assertIn("source_record", result["result"])


if __name__ == "__main__":
    unittest.main()
