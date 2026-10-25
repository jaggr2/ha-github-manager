"""Constants for the GitHub Manager integration."""
from __future__ import annotations

DOMAIN = "github_manager"

DEFAULT_NAME = "GitHub Manager"
DEFAULT_API_URL = "https://api.github.com"
DEFAULT_POLL_INTERVAL = 120
MIN_POLL_INTERVAL = 30

CONF_REPO = "repo"
CONF_TOKEN = "token"
CONF_API_URL = "api_url"
CONF_POLL_INTERVAL = "poll_interval"

# Bus event fired for every interesting change; consumed by the EventEntity.
EVENT_BUS = f"{DOMAIN}_event"

# Event types exposed by event.github_manager
EVENT_RUN_REQUESTED = "run_requested"
EVENT_WORKFLOW_RUN_STARTED = "workflow_run_started"
EVENT_WORKFLOW_RUN_COMPLETED = "workflow_run_completed"
EVENT_ISSUE_OPENED = "issue_opened"
EVENT_ISSUE_CLOSED = "issue_closed"
EVENT_PR_OPENED = "pr_opened"
EVENT_PR_MERGED = "pr_merged"
EVENT_PR_CLOSED = "pr_closed"

EVENT_TYPES = [
    EVENT_RUN_REQUESTED,
    EVENT_WORKFLOW_RUN_STARTED,
    EVENT_WORKFLOW_RUN_COMPLETED,
    EVENT_ISSUE_OPENED,
    EVENT_ISSUE_CLOSED,
    EVENT_PR_OPENED,
    EVENT_PR_MERGED,
    EVENT_PR_CLOSED,
]

MERGE_METHODS = ["merge", "squash", "rebase"]
