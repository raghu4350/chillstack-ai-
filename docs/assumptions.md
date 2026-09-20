# Assumptions and Source Notes — ResolveDesk

## Source Boundaries
All business data comes from:
- Assignment 2 Data Pack, Section 1, page 1 (policies)
- Assignment 2 Data Pack, Section 2, pages 1–2 (employee requests)
- Assignment 2 Data Pack, Section 3, page 2 (ticket queue)

No external company policies or invented data have been added.

## Documented Assumptions

### Identity
- Employee requests and similarly named tickets are NOT assumed to be the same case.
  Their relationship is not supplied in the source data.
- Ticket employees are identified only by initials/partial names as supplied.
  Ticket email addresses and opening dates are "Not supplied" — not invented.

### Laptop Policy Conflict
- KB-03 states a 3-year replacement threshold.
- ASSET-Q2-2026 (updated Q2 2026) states a 4-year refresh cycle.
- No precedence rule is supplied. Both policies are surfaced for every laptop case.
- The conflict is flagged and routed to IT + Finance/Assets for clarification.
- No policy is silently declared authoritative.

### Hardware Failure
- Employee-reported hardware failure is NOT treated as verified hardware failure.
- IT diagnosis must precede replacement routing.
- A dead laptop does not trigger an automatic emergency replacement exception;
  the 2-week notice requirement (KB-03) is noted alongside the need for diagnosis.

### WFH Eligibility
- "More than 3 days/week" is interpreted as ≥ 4 days/week (i.e., strictly greater than 3).
- 3 days/week does NOT meet the KB-10 threshold.

### Software Catalog
- No software catalog is supplied in the source data.
- Catalog membership is always clarified, never assumed in either direction.

### Approval Claims
- Employee text such as "Finance approved" is stored as reported information, not authorization.
- Approval recorded in a source ticket (e.g., TK-1043) is preserved as-is but does not
  automatically authorize fulfillment without verification of supporting evidence.

### Admin Access
- No supplied policy authorizes admin access to internal servers directly.
- TK-1050 (admin access rejected) is closed history, not a blanket policy.
- A request containing a justification is not automatically approvable.

### Time Handling
- Assignment dates use the supplied week: 2026-09-21 through 2026-09-25.
- Audit timestamps use actual UTC time when the application runs, clearly labelled.
- No overdue calculations are derived from today's real date.

### Simulation Boundary
- All actions (account unlock, email send, access grant, equipment shipping) are
  explicitly simulated with operator confirmation required.
- "Guidance provided" is not proof of employee success.
- "Staged plan" is not an executed action.
- "Recorded action" updates the local database only; no external systems are changed.

## What Is Not Supplied
- The approved software catalog
- Specific VPN renewal URL or workflow steps
- Individual approver identities or names
- Specific portal URLs for any self-service step
- Evidence supporting TK-1043's "Approved — pending fulfillment" status
- Email addresses or opening dates for ticket records

These gaps are surfaced as missing_info in the analysis output, not filled with invented data.
