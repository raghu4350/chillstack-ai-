"""
tests/test_data.py
------------------
Tests for source data integrity: counts, IDs, and fixture completeness.
These tests verify that the JSON source files contain exactly the records
described in the assignment specification.
No API key, network, or Streamlit required.
"""

import unittest
from resolvedesk.data import (
    get_policies, get_requests, get_tickets,
    get_policy_by_id, get_request_by_id, get_ticket_by_id,
    validate_source_counts,
)
from resolvedesk.config import (
    TOTAL_POLICIES, TOTAL_REQUESTS, TOTAL_TICKETS,
    ACTIVE_TICKETS, CLOSED_TICKETS,
)


class TestSourceCounts(unittest.TestCase):
    """Verify that all supplied records are present and correctly counted."""

    def test_policy_count(self):
        self.assertEqual(len(get_policies()), TOTAL_POLICIES,
                         f"Expected {TOTAL_POLICIES} policies")

    def test_request_count(self):
        self.assertEqual(len(get_requests()), TOTAL_REQUESTS,
                         f"Expected {TOTAL_REQUESTS} employee requests")

    def test_ticket_count(self):
        self.assertEqual(len(get_tickets()), TOTAL_TICKETS,
                         f"Expected {TOTAL_TICKETS} tickets")

    def test_active_ticket_count(self):
        active = [t for t in get_tickets() if not t.get("is_closed")]
        self.assertEqual(len(active), ACTIVE_TICKETS,
                         f"Expected {ACTIVE_TICKETS} active tickets")

    def test_closed_ticket_count(self):
        closed = [t for t in get_tickets() if t.get("is_closed")]
        self.assertEqual(len(closed), CLOSED_TICKETS,
                         f"Expected {CLOSED_TICKETS} closed tickets")

    def test_validate_source_counts_all_pass(self):
        result = validate_source_counts()
        for key, val in result.items():
            if key.endswith("_ok"):
                self.assertTrue(val, f"Count check failed: {key}")


class TestPolicyIDs(unittest.TestCase):
    """Verify all required policy IDs are present."""

    REQUIRED_IDS = [
        "KB-01", "KB-02", "KB-03", "KB-04", "KB-05",
        "KB-06", "KB-07", "KB-08", "KB-09", "KB-10",
        "ASSET-Q2-2026",
    ]

    def test_all_required_policy_ids_present(self):
        for pid in self.REQUIRED_IDS:
            policy = get_policy_by_id(pid)
            self.assertIsNotNone(policy, f"Policy {pid} not found in source data")

    def test_laptop_policy_conflict_note_in_kb03(self):
        p = get_policy_by_id("KB-03")
        self.assertIn("conflict_note", p, "KB-03 must have a conflict_note about ASSET-Q2-2026")
        self.assertIn("ASSET-Q2-2026", p["conflict_note"])

    def test_laptop_policy_conflict_note_in_asset(self):
        p = get_policy_by_id("ASSET-Q2-2026")
        self.assertIn("conflict_note", p, "ASSET-Q2-2026 must have a conflict_note about KB-03")
        self.assertIn("KB-03", p["conflict_note"])

    def test_security_policy_has_email(self):
        p = get_policy_by_id("KB-09")
        self.assertEqual(p.get("security_email"), "security@chillstack.example")

    def test_mailbox_policy_has_limits(self):
        p = get_policy_by_id("KB-06")
        limits = p.get("limits", {})
        self.assertEqual(limits.get("default_gb"), 25)
        self.assertEqual(limits.get("max_gb"), 50)


class TestRequestIDs(unittest.TestCase):
    """Verify all 15 employee request IDs and key fields are present."""

    REQUIRED_IDS = [f"REQ-{i:02d}" for i in range(1, 16)]

    def test_all_request_ids_present(self):
        for rid in self.REQUIRED_IDS:
            req = get_request_by_id(rid)
            self.assertIsNotNone(req, f"Request {rid} not found")

    def test_requests_have_required_fields(self):
        for req in get_requests():
            self.assertIn("id", req)
            self.assertIn("employee", req)
            self.assertIn("email", req)
            self.assertIn("opened", req)
            self.assertIn("request", req)
            self.assertIn("initial_action", req)
            self.assertIn("topic", req)


class TestTicketIDs(unittest.TestCase):
    """Verify all 10 ticket IDs and correct open/closed flags."""

    ACTIVE_IDS = ["TK-1043", "TK-1044", "TK-1047", "TK-1048"]
    CLOSED_IDS = ["TK-1042", "TK-1045", "TK-1046", "TK-1049", "TK-1050", "TK-1051"]

    def test_active_tickets_are_not_closed(self):
        for tid in self.ACTIVE_IDS:
            t = get_ticket_by_id(tid)
            self.assertIsNotNone(t, f"Ticket {tid} not found")
            self.assertFalse(t.get("is_closed"), f"Ticket {tid} should be active")

    def test_closed_tickets_are_closed(self):
        for tid in self.CLOSED_IDS:
            t = get_ticket_by_id(tid)
            self.assertIsNotNone(t, f"Ticket {tid} not found")
            self.assertTrue(t.get("is_closed"), f"Ticket {tid} should be closed")

    def test_tickets_have_required_fields(self):
        for t in get_tickets():
            self.assertIn("id", t)
            self.assertIn("employee", t)
            self.assertIn("issue_summary", t)
            self.assertIn("source_status", t)
            self.assertIn("is_closed", t)


if __name__ == "__main__":
    unittest.main()
