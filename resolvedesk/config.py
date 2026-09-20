"""
resolvedesk/config.py
---------------------
Centralised configuration: paths, environment variables, and application settings.

Design decision: All paths are derived from this file so that the project works
wherever it is extracted, as long as relative references from this file remain intact.
"""

import os
from pathlib import Path

# ── Directory structure ───────────────────────────────────────────────────────

# Root of the project (one level above this file)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

DATA_DIR   = PROJECT_ROOT / "data"
DB_PATH    = PROJECT_ROOT / "resolvedesk.db"   # created automatically at runtime
DOCS_DIR   = PROJECT_ROOT / "docs"
TESTS_DIR  = PROJECT_ROOT / "tests"

DATA_POLICIES_FILE = DATA_DIR / "policies.json"
DATA_REQUESTS_FILE = DATA_DIR / "requests.json"
DATA_TICKETS_FILE  = DATA_DIR / "tickets.json"

# ── Environment variables ─────────────────────────────────────────────────────

# Read from environment; sidebar can override at runtime (stored in session state,
# never in code or logs).
MISTRAL_API_KEY_ENV = os.environ.get("MISTRAL_API_KEY", "")

# The model name is configurable via env var and the sidebar.
# mistral-large-latest is documented as tool-capable in the Mistral API.
DEFAULT_MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-large-latest")

# ── Agent safety limits ───────────────────────────────────────────────────────

# Maximum number of tool-calling iterations before the agent gives up gracefully.
# Prevents infinite loops if the model keeps requesting tools.
MAX_TOOL_ITERATIONS = 8

# Network timeout in seconds for Mistral API calls.
API_TIMEOUT_SECONDS = 30

# ── Assignment metadata ───────────────────────────────────────────────────────

ASSIGNMENT_WEEK_START = "2026-09-21"
ASSIGNMENT_WEEK_END   = "2026-09-25"
COMPANY_NAME          = "Chillstack"

# Count constants — used for display and test assertions.
TOTAL_POLICIES        = 11   # KB-01 through KB-10 + ASSET-Q2-2026
TOTAL_REQUESTS        = 15
TOTAL_TICKETS         = 10
ACTIVE_TICKETS        = 4
CLOSED_TICKETS        = 6
TOTAL_SOURCE_RECORDS  = 25   # 15 requests + 10 tickets
ACTIONABLE_RECORDS    = 19   # 15 requests + 4 active tickets
