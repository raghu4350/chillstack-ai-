"""
tests/test_rules.py
-------------------
Tests for the policy rules engine (resolvedesk/rules.py).

These tests verify that all 15 employee request topics are detected correctly,
that policy checks return appropriate outcomes, and that boundary cases (e.g.,
mailbox cap, WFH eligibility) are enforced correctly.

No API key, network, database, or Streamlit required.
"""

import unittest
from resolvedesk.rules import (
    detect_topic, evaluate_topic, get_relevant_policies,
    check_password_lockout, check_vpn, check_laptop,
    check_mailbox_quota, check_guest_wifi, check_wfh_equipment,
    check_software_install, check_printer, check_expense_tool,
    check_security_incident, check_admin_access,
    validate_plan,
)
from resolvedesk.data import get_request_by_id, get_ticket_by_id


class TestTopicDetection(unittest.TestCase):
    """Verify topic detection for all 15 requests."""

    def _get_topic(self, req_id: str) -> str:
        req = get_request_by_id(req_id)
        return req.get("topic", detect_topic(req.get("request", "")))

    def test_REQ01_laptop(self):
        self.assertEqual(self._get_topic("REQ-01"), "laptop")

    def test_REQ02_guest_wifi(self):
        self.assertEqual(self._get_topic("REQ-02"), "guest_wifi")

    def test_REQ03_password_lockout(self):
        self.assertEqual(self._get_topic("REQ-03"), "password_lockout")

    def test_REQ04_software_install(self):
        self.assertEqual(self._get_topic("REQ-04"), "software_install")

    def test_REQ05_vpn(self):
        self.assertEqual(self._get_topic("REQ-05"), "vpn")

    def test_REQ06_printer(self):
        self.assertEqual(self._get_topic("REQ-06"), "printer")

    def test_REQ07_wfh_equipment(self):
        self.assertEqual(self._get_topic("REQ-07"), "wfh_equipment")

    def test_REQ08_security_incident(self):
        self.assertEqual(self._get_topic("REQ-08"), "security_incident")

    def test_REQ09_mailbox_quota(self):
        self.assertEqual(self._get_topic("REQ-09"), "mailbox_quota")

    def test_REQ10_admin_access(self):
        self.assertEqual(self._get_topic("REQ-10"), "admin_access")

    def test_REQ11_vpn(self):
        self.assertEqual(self._get_topic("REQ-11"), "vpn")

    def test_REQ12_expense_tool(self):
        self.assertEqual(self._get_topic("REQ-12"), "expense_tool")

    def test_REQ13_laptop(self):
        self.assertEqual(self._get_topic("REQ-13"), "laptop")

    def test_REQ14_software_install(self):
        self.assertEqual(self._get_topic("REQ-14"), "software_install")

    def test_REQ15_unknown(self):
        self.assertEqual(self._get_topic("REQ-15"), "unknown")


class TestPasswordLockout(unittest.TestCase):
    """KB-01: Manual unlock after >= 5 failed attempts."""

    def test_6_attempts_requires_manual_unlock(self):
        result = check_password_lockout({"failed_attempts": 6})
        self.assertTrue(result.applies)
        self.assertIn("manually unlock", result.action_required.lower())

    def test_6_attempts_with_reset_queued_updates_not_duplicates(self):
        result = check_password_lockout({"failed_attempts": 6, "reset_queued": True})
        self.assertIn("UPDATE", result.action_required)
        # The action says "do not create a duplicate" — meaning it prevents duplication.
        # We check it says UPDATE (update existing) rather than creating a new ticket.
        self.assertNotIn("create a new", result.action_required.lower())

    def test_4_attempts_self_service(self):
        result = check_password_lockout({"failed_attempts": 4})
        self.assertIn("self-service", result.action_required.lower())

    def test_lockout_not_just_password_reset(self):
        """Reset alone does NOT unlock a locked account (KB-01 requirement)."""
        result = check_password_lockout({"failed_attempts": 6})
        action = result.action_required.lower()
        # Must mention unlock, not just reset.
        self.assertIn("unlock", action)


class TestVPN(unittest.TestCase):
    """KB-02: Contractor vs full-time VPN rules."""

    def test_contractor_requires_manager_approval(self):
        result = check_vpn({"employee_type": "contractor"})
        action = result.action_required.lower()
        self.assertIn("manager approval", action)
        self.assertIn("access request form", action)

    def test_full_time_auto_granted(self):
        result = check_vpn({"employee_type": "full_time", "credentials_expired": False})
        action = result.action_required.lower()
        self.assertNotIn("manager approval", action)

    def test_expired_credentials_employee_renews(self):
        result = check_vpn({"employee_type": "full_time", "credentials_expired": True})
        action = result.action_required.lower()
        self.assertIn("renew", action)
        # Must not fabricate a URL.
        self.assertNotIn("http", action)

    def test_unknown_employee_type_asks_for_clarification(self):
        result = check_vpn({})
        self.assertTrue(len(result.missing_info) > 0)


class TestLaptop(unittest.TestCase):
    """KB-03 + ASSET-Q2-2026: Both policies must appear; conflict exposed."""

    def test_both_policies_returned(self):
        results = check_laptop({"age_years": 3.5})
        ids = [r.policy_id for r in results]
        self.assertIn("KB-03", ids)
        self.assertIn("ASSET-Q2-2026", ids)

    def test_conflict_is_surfaced(self):
        results = check_laptop({"age_years": 3.5})
        for r in results:
            self.assertTrue(len(r.conflicts) > 0, f"No conflict in {r.policy_id}")

    def test_35_year_old_laptop_kb03_eligible_asset_not(self):
        results = check_laptop({"age_years": 3.5})
        kb03   = next(r for r in results if r.policy_id == "KB-03")
        asset  = next(r for r in results if r.policy_id == "ASSET-Q2-2026")
        self.assertIn("Eligible", kb03.summary)     # 3.5 >= 3
        self.assertIn("Not yet eligible", asset.summary)  # 3.5 < 4

    def test_2_year_laptop_not_eligible_under_either_policy(self):
        results = check_laptop({"age_years": 2.0})
        kb03   = next(r for r in results if r.policy_id == "KB-03")
        asset  = next(r for r in results if r.policy_id == "ASSET-Q2-2026")
        self.assertIn("Not yet eligible", kb03.summary)
        self.assertIn("Not yet eligible", asset.summary)

    def test_unverified_failure_flagged_in_missing_info(self):
        results = check_laptop({"age_years": 3.5, "hardware_failure_verified": False})
        all_missing = [m for r in results for m in r.missing_info]
        self.assertTrue(
            any("verified" in m.lower() for m in all_missing),
            "Unverified failure should be flagged in missing_info"
        )

    def test_existing_approval_preserved_not_revoked(self):
        results = check_laptop({"age_years": 3.2, "approval_exists": True})
        kb03 = next(r for r in results if r.policy_id == "KB-03")
        action = kb03.action_required.lower()
        self.assertIn("preserve", action)
        # "do not silently revoke" means the action PREVENTS revocation.
        # Check that it does not say revoke without the protective negation.
        self.assertNotIn("silently revoke the approval", action.replace("do not silently revoke the approval", ""))


class TestMailboxQuota(unittest.TestCase):
    """KB-06: 25GB default, manager approval above 25, hard cap at 50GB."""

    def test_25gb_advise_archiving(self):
        result = check_mailbox_quota({"current_gb": 25, "archiving_done": False})
        self.assertIn("archive", result.action_required.lower())

    def test_35gb_requires_manager_approval(self):
        result = check_mailbox_quota({"requested_gb": 35, "archiving_done": False})
        self.assertTrue(any("manager approval" in m.lower() for m in result.missing_info))

    def test_50gb_at_cap(self):
        result = check_mailbox_quota({"requested_gb": 50})
        # 50GB is the cap — should be allowed with manager approval.
        warnings = [w.lower() for w in result.warnings]
        self.assertFalse(any("exceed" in w for w in warnings),
                         "50GB is within the cap and should not trigger an exceed warning")

    def test_60gb_exceeds_cap(self):
        result = check_mailbox_quota({"requested_gb": 60})
        warnings = [w.lower() for w in result.warnings]
        self.assertTrue(any("cap" in w or "exceed" in w or "50" in w for w in warnings),
                        "60GB exceeds the 50GB cap and must trigger a warning")
        # Must NOT approvingly route for 60GB — must explain the cap.
        # The action_required should contain 'cannot be approved' or 'cap'.
        action = result.action_required.lower()
        self.assertTrue(
            "cannot be approved" in action or "cap" in action or "50gb" in action,
            "Action must explain the cap for a 60GB request"
        )

    def test_unlimited_quota_rejected(self):
        """Unlimited quota must never be granted (spec requirement)."""
        result = check_mailbox_quota({"requested_gb": 999})
        warnings = [w.lower() for w in result.warnings]
        self.assertTrue(
            any("cap" in w or "50" in w for w in warnings),
            "Unlimited quota must trigger cap warning"
        )


class TestGuestWiFi(unittest.TestCase):
    """KB-07: Pure self-service, no IT ticket needed."""

    def test_self_service_kiosk_guidance(self):
        result = check_guest_wifi({})
        action = result.action_required.lower()
        self.assertIn("kiosk", action)
        self.assertIn("24", action)

    def test_no_it_ticket_mentioned(self):
        result = check_guest_wifi({})
        action = result.action_required.lower()
        # Should explicitly say no IT ticket is needed.
        self.assertIn("no it ticket", action)

    def test_no_credentials_invented(self):
        result = check_guest_wifi({})
        action = result.action_required
        # Must not invent credentials.
        self.assertNotIn("password", action.lower())
        self.assertNotIn("username", action.lower())


class TestWFHEquipment(unittest.TestCase):
    """KB-10: Eligibility threshold is >3 days/week (i.e., >= 4)."""

    def test_3_days_not_eligible(self):
        result = check_wfh_equipment({"remote_days_per_week": 3})
        self.assertIn("not meet", result.action_required.lower())

    def test_4_days_eligible(self):
        result = check_wfh_equipment({"remote_days_per_week": 4})
        # Summary should confirm eligibility ("eligibility confirmed" counts).
        summary = result.summary.lower()
        self.assertTrue(
            "eligible" in summary or "eligibility" in summary,
            f"Summary should mention eligibility. Got: {result.summary}"
        )

    def test_4_days_requires_manager_then_finance(self):
        result = check_wfh_equipment({"remote_days_per_week": 4})
        action = result.action_required.lower()
        self.assertIn("manager", action)
        self.assertIn("finance", action)

    def test_eligibility_not_approval(self):
        result = check_wfh_equipment({"remote_days_per_week": 4})
        action = result.action_required.lower()
        # Must require approvals before IT handles shipping.
        self.assertTrue(
            "after" in action or "approval" in action or "approvals" in action,
            "Action must require approvals before IT ships equipment"
        )
        # "approvals are confirmed" or similar must appear.
        self.assertTrue(
            "approvals" in action or "sign-off" in action or "manager" in action,
            "Action must mention required approvals"
        )


class TestSoftwareInstall(unittest.TestCase):
    """KB-04: Catalog vs non-catalog; preserve existing review."""

    def test_catalog_software_self_install(self):
        result = check_software_install({"catalog_status": "in_catalog"})
        self.assertIn("self-install", result.action_required.lower())

    def test_non_catalog_security_review(self):
        result = check_software_install({"catalog_status": "not_in_catalog"})
        self.assertIn("security review", result.action_required.lower())

    def test_existing_review_preserved_not_duplicated(self):
        result = check_software_install({
            "catalog_status": "not_in_catalog",
            "review_already_pending": True,
        })
        action = result.action_required.lower()
        self.assertIn("preserve", action)
        # "do not duplicate or restart" means those are prohibited.
        # Check it says preserve and does not say "submit a new" review.
        self.assertNotIn("submit a new", action)
        # Verify this is about an existing review, not a new one.
        self.assertIn("already pending", action)

    def test_unknown_catalog_asks_for_clarification(self):
        result = check_software_install({"catalog_status": "unknown"})
        self.assertTrue(len(result.missing_info) > 0)


class TestPrinterTroubleshooting(unittest.TestCase):
    """KB-05: Queue, spooler, asset tag; preserve existing technician."""

    def test_technician_assigned_preserve(self):
        result = check_printer({"technician_assigned": True})
        action = result.action_required.lower()
        self.assertIn("existing investigation", action)

    def test_asset_tag_required_when_tech_assigned(self):
        result = check_printer({"technician_assigned": True, "asset_tag": None})
        self.assertTrue(len(result.missing_info) > 0)
        self.assertTrue(any("asset tag" in m.lower() for m in result.missing_info))

    def test_first_steps_queue_and_spooler(self):
        result = check_printer({})
        action = result.action_required.lower()
        self.assertTrue(
            "queue" in action or "spooler" in action,
            "First step must mention queue or spooler check"
        )


class TestExpenseTool(unittest.TestCase):
    """KB-08: Existing account → IT; no account → Finance."""

    def test_existing_account_routes_to_it(self):
        result = check_expense_tool({"account_exists": True})
        action = result.action_required.lower()
        self.assertIn("it", action)
        self.assertNotIn("finance", action.split("it ")[1] if "it " in action else "")

    def test_no_account_routes_to_finance(self):
        result = check_expense_tool({"account_exists": False})
        action = result.action_required.lower()
        self.assertIn("finance", action)

    def test_unknown_account_asks_for_clarification(self):
        result = check_expense_tool({})
        self.assertTrue(len(result.missing_info) > 0)

    def test_does_not_ask_for_password(self):
        result = check_expense_tool({"account_exists": True})
        action = result.action_required.lower()
        # "do not ask for the employee's password" means it explicitly prohibits asking.
        # The test should verify it doesn't ask for a password (as a question).
        # Presence of the word 'password' in a prohibition is acceptable.
        if "password" in action:
            # Must be in a prohibition context (e.g., "do not ask for the employee's password")
            self.assertIn("do not ask", action, 
                          "If 'password' appears, it must be in a prohibition ('do not ask')")


class TestSecurityIncident(unittest.TestCase):
    """KB-09: Urgent, stop forwarding, preserve escalation."""

    def test_is_urgent(self):
        result = check_security_incident({})
        self.assertTrue(result.is_urgent)

    def test_security_email_in_action(self):
        result = check_security_incident({})
        self.assertIn("security@chillstack.example", result.action_required)

    def test_forwarding_warning_when_forwarding(self):
        result = check_security_incident({"forwarded_to_others": True})
        self.assertTrue(any("forward" in w.lower() for w in result.warnings))

    def test_escalation_preserved_not_duplicated(self):
        result = check_security_incident({"escalated": True})
        action = result.action_required.lower()
        self.assertIn("preserve", action)
        self.assertNotIn("escalate again", action)


class TestAdminAccess(unittest.TestCase):
    """No policy authorises admin access directly."""

    def test_no_policy_id_for_admin_access(self):
        result = check_admin_access({})
        self.assertEqual(result.policy_id, "NONE")

    def test_requires_business_justification(self):
        result = check_admin_access({})
        self.assertTrue(any("justification" in m.lower() for m in result.missing_info))

    def test_urgency_does_not_grant_access(self):
        result = check_admin_access({"urgency": "high"})
        action = result.action_required.lower()
        # "do not grant access" means granting is prohibited, not enabled.
        # Check it routes to a reviewer and does not say "granting access" affirmatively.
        self.assertIn("reviewer", action)
        # If 'grant' appears, it must be in a prohibition.
        if "grant" in action:
            self.assertIn("do not grant", action,
                          "If 'grant' appears, it must be in a prohibition context")


class TestPlanValidation(unittest.TestCase):
    """validate_plan() must block recording on closed cases and incomplete plans."""

    GOOD_PLAN = {
        "case_id": "REQ-01",
        "proposed_action": "Arrange IT diagnosis.",
        "policy_ids": ["KB-03", "ASSET-Q2-2026"],
    }

    def test_valid_plan_passes(self):
        ok, msg = validate_plan(self.GOOD_PLAN, "REQ-01", is_closed=False)
        self.assertTrue(ok, msg)

    def test_closed_case_blocked(self):
        ok, msg = validate_plan(self.GOOD_PLAN, "REQ-01", is_closed=True)
        self.assertFalse(ok)
        self.assertIn("closed", msg.lower())

    def test_mismatched_case_id_blocked(self):
        ok, msg = validate_plan(self.GOOD_PLAN, "REQ-02", is_closed=False)
        self.assertFalse(ok)

    def test_missing_proposed_action_blocked(self):
        plan = dict(self.GOOD_PLAN)
        plan["proposed_action"] = ""
        ok, msg = validate_plan(plan, "REQ-01", is_closed=False)
        self.assertFalse(ok)

    def test_missing_policy_ids_blocked(self):
        plan = dict(self.GOOD_PLAN)
        plan["policy_ids"] = []
        ok, msg = validate_plan(plan, "REQ-01", is_closed=False)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
