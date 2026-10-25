"""Shared fixtures for the GitHub Manager test suite."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.core import Event, HomeAssistant, callback

from custom_components.github_manager.const import (
    CONF_API_URL,
    CONF_POLL_INTERVAL,
    CONF_REPO,
    CONF_TOKEN,
    DEFAULT_API_URL,
    DOMAIN,
    EVENT_BUS,
)

pytest_plugins = "pytest_homeassistant_custom_component"

REPO = "jaggr2/home-control-server-config"
REPO_URL = f"https://github.com/{REPO}"

ENTRY_DATA = {
    CONF_REPO: REPO,
    CONF_TOKEN: "ghp_test_token",
    CONF_API_URL: DEFAULT_API_URL,
}

RUN = {
    "id": 101,
    "workflow_id": 7,
    "name": "Server Health",
    "display_title": "Server Health + OpenCode Agent",
    "status": "completed",
    "conclusion": "success",
    "event": "schedule",
    "run_number": 55,
    "head_branch": "main",
    "head_sha": "abc123",
    "html_url": f"{REPO_URL}/actions/runs/101",
    "created_at": "2026-10-25T05:15:00Z",
    "updated_at": "2026-10-25T05:20:00Z",
}

ISSUE = {
    "number": 12,
    "title": "Backup tier2 failed",
    "html_url": f"{REPO_URL}/issues/12",
    "state": "open",
}


def make_api_mock() -> MagicMock:
    """Build a fully mocked GitHubManagerApi."""
    api = MagicMock()
    api.repo = REPO
    api.async_get_repo = AsyncMock(
        return_value={"full_name": REPO, "default_branch": "main"}
    )
    api.async_get_runs = AsyncMock(return_value=[dict(RUN)])
    api.async_get_open_issues = AsyncMock(return_value=[dict(ISSUE)])
    api.async_get_open_pulls = AsyncMock(return_value=[])
    api.async_get_pull = AsyncMock(return_value={"number": 3, "merged": False})
    api.async_dispatch_workflow = AsyncMock(return_value=None)
    api.async_cancel_run = AsyncMock(return_value=None)
    api.async_rerun_run = AsyncMock(return_value=None)
    api.async_create_issue = AsyncMock(
        return_value={"number": 99, "html_url": f"{REPO_URL}/issues/99"}
    )
    api.async_comment_issue = AsyncMock(
        return_value={"html_url": f"{REPO_URL}/issues/12#issuecomment-1"}
    )
    api.async_update_issue = AsyncMock(
        return_value={"number": 12, "html_url": f"{REPO_URL}/issues/12", "state": "closed"}
    )
    api.async_create_pull_request = AsyncMock(
        return_value={"number": 7, "html_url": f"{REPO_URL}/pull/7"}
    )
    api.async_merge_pull_request = AsyncMock(
        return_value={"merged": True, "sha": "def456", "message": "Pull Request successfully merged"}
    )
    api.async_close_pull_request = AsyncMock(
        return_value={"number": 7, "html_url": f"{REPO_URL}/pull/7"}
    )
    return api


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in every test."""
    yield


@callback
def capture_events(
    hass: HomeAssistant, event_name: str = EVENT_BUS
) -> list[Event]:
    """Return a live list of bus events with the given name."""
    events: list[Event] = []

    @callback
    def _capture(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen(event_name, _capture)
    return events


@pytest.fixture
def mock_api():
    """Patch the API client class wherever the integration instantiates it."""
    api = make_api_mock()
    with (
        patch(
            "custom_components.github_manager.GitHubManagerApi", return_value=api
        ),
        patch(
            "custom_components.github_manager.config_flow.GitHubManagerApi",
            return_value=api,
        ),
    ):
        yield api


@pytest.fixture
async def setup_entry(hass, mock_api):
    """Set up the integration with one repository."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=REPO.lower(),
        data=ENTRY_DATA,
        options={CONF_POLL_INTERVAL: 120},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
