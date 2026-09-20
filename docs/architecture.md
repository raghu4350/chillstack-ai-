# Architecture — ResolveDesk

## Component Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                         app.py (Streamlit UI)                      │
│  Tab 1: Agent Workspace  │  Tab 2: All Cases  │  Tab 3: Policies   │
│  Tab 4: Action History   │  Tab 5: Project Guide                   │
└──────────────────────────┬─────────────────────────────────────────┘
                           │ imports
       ┌───────────────────┼──────────────────────┐
       ▼                   ▼                      ▼
 agent.py            database.py              data.py
 (Mistral loop)      (SQLite CRUD)            (JSON loader)
       │                   ▲                      │
       ▼                   │                      ▼
 tools.py            rules.py              policies.json
 (tool schemas +     (policy checks,       requests.json
  execution)          topic detection,     tickets.json
       │              plan validation)
       ▼
 prompts.py
 (system prompt +
  context builder)
       │
       ▼
 Mistral API
 (tool-capable model)
```

## Data Flow

1. **Operator selects a case** in the Agent Workspace tab.
2. **`app.py`** reads the case from `data.py` (JSON, read-only).
3. **`app.py`** loads the current DB state and clarifications from `database.py`.
4. **`agent.py`** builds the prompt via `prompts.py` (case + policies + conversation).
5. **`agent.py`** sends the prompt to Mistral with tool schemas from `tools.py`.
6. **Mistral** decides which tools to call. `tools.py` validates and executes each call.
7. **`rules.py`** is called by `tools.py` (via `evaluate_case`) to apply policy checks.
8. **Mistral** calls `stage_plan` with a structured recommendation.
9. **`database.py`** stores the staged plan.
10. **`app.py`** displays the plan to the operator.
11. **Operator confirms** → `app.py` calls `rules.py` to validate the plan.
12. **`database.py`** updates case state and appends the audit record.
13. **`app.py`** refreshes the display.

## Safety Architecture

| Concern | How it is addressed |
|---|---|
| Real actions | All actions are simulated; no external APIs called |
| API key exposure | Key in session_state only; never in DB, logs, or prompts |
| Infinite loops | MAX_TOOL_ITERATIONS = 8 |
| Duplicate recording | SQL UPDATE with status='pending' guard; session_state flag |
| Closed case mutation | validate_plan() blocks recording; UI disables button |
| SQL injection | Parameterised queries throughout database.py |
| Arbitrary tool execution | execute_tool() checks name against TOOL_SCHEMAS whitelist |
| Model instruction injection | System prompt does not execute user text as instructions |
| Eval/exec | Never used anywhere in the codebase |
