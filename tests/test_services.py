"""Tests for the github_manager actions."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.github_manager.api import GitHubManagerError
from custom_components.github_manager.const import CONF_REPO, DOMAIN

from .conftest import ENTRY_DATA, REPO, capture_events


async def test_dispatch_workflow(hass: HomeAssistant, setup_entry, mock_api) -> None:
    events = capture_events(hass)
    response = await hass.services.async_call(
        DOMAIN,
        "dispatch_workflow",
        {"workflow": "deploy.yml", "ref": "main"},
        blocking=True,
        return_response=True,
    )
    assert response == {"queued": True}
    mock_api.async_dispatch_workflow.assert_awaited_once_with(
        "deploy.yml", "main", {}
    )
    assert events[0].data["event_type"] == "run_requested"
    assert events[0].data["workflow"] == "deploy.yml"


async def test_dispatch_defaults_ref_to_default_branch(
    hass: HomeAssistant, setup_entry, mock_api
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "dispatch_workflow",
        {"workflow": "deploy.yml", "inputs": {"run_agent": "yes"}},
        blocking=True,
    )
    mock_api.async_dispatch_workflow.assert_awaited_once_with(
        "deploy.yml", "main", {"run_agent": "yes"}
    )


async def test_cancel_and_rerun(hass: HomeAssistant, setup_entry, mock_api) -> None:
    response = await hass.services.async_call(
        DOMAIN,
        "cancel_run",
        {"run_id": 101},
        blocking=True,
        return_response=True,
    )
    assert response == {"cancelled": True, "run_id": 101}
    mock_api.async_cancel_run.assert_awaited_once_with(101)

    response = await hass.services.async_call(
        DOMAIN,
        "rerun_run",
        {"run_id": 101, "failed_only": True},
        blocking=True,
        return_response=True,
    )
    assert response == {"rerun": True, "run_id": 101}
    mock_api.async_rerun_run.assert_awaited_once_with(101, failed_only=True)


async def test_create_issue(hass: HomeAssistant, setup_entry, mock_api) -> None:
    response = await hass.services.async_call(
        DOMAIN,
        "create_issue",
        {"title": "Backup failed", "labels": ["ops"]},
        blocking=True,
        return_response=True,
    )
    assert response == {
        "number": 99,
        "url": f"https://github.com/{REPO}/issues/99",
    }
    mock_api.async_create_issue.assert_awaited_once_with(
        title="Backup failed", body=None, labels=["ops"], assignees=None
    )


async def test_comment_and_update_issue(
    hass: HomeAssistant, setup_entry, mock_api
) -> None:
    response = await hass.services.async_call(
        DOMAIN,
        "comment_issue",
        {"number": 12, "body": "looking into it"},
        blocking=True,
        return_response=True,
    )
    assert response["url"].endswith("issuecomment-1")

    response = await hass.services.async_call(
        DOMAIN,
        "update_issue",
        {"number": 12, "state": "closed"},
        blocking=True,
        return_response=True,
    )
    assert response["state"] == "closed"
    mock_api.async_update_issue.assert_awaited_once_with(
        number=12,
        state="closed",
        title=None,
        body=None,
        labels=None,
        assignees=None,
    )


async def test_pull_request_lifecycle(
    hass: HomeAssistant, setup_entry, mock_api
) -> None:
    response = await hass.services.async_call(
        DOMAIN,
        "create_pull_request",
        {"title": "feat: digest card", "head": "feature/digest"},
        blocking=True,
        return_response=True,
    )
    assert response == {"number": 7, "url": f"https://github.com/{REPO}/pull/7"}
    mock_api.async_create_pull_request.assert_awaited_once_with(
        title="feat: digest card",
        head="feature/digest",
        base="main",
        body=None,
        draft=False,
    )

    response = await hass.services.async_call(
        DOMAIN,
        "merge_pull_request",
        {"number": 7, "merge_method": "squash"},
        blocking=True,
        return_response=True,
    )
    assert response["merged"] is True
    mock_api.async_merge_pull_request.assert_awaited_once_with(
        number=7, merge_method="squash", commit_title=None, commit_message=None
    )

    response = await hass.services.async_call(
        DOMAIN,
        "close_pull_request",
        {"number": 8},
        blocking=True,
        return_response=True,
    )
    assert response["number"] == 7
    mock_api.async_close_pull_request.assert_awaited_once_with(8)


async def test_api_error_becomes_homeassistant_error(
    hass: HomeAssistant, setup_entry, mock_api
) -> None:
    mock_api.async_dispatch_workflow = AsyncMock(
        side_effect=GitHubManagerError("boom")
    )
    with pytest.raises(HomeAssistantError, match="dispatch failed"):
        await hass.services.async_call(
            DOMAIN,
            "dispatch_workflow",
            {"workflow": "deploy.yml"},
            blocking=True,
        )


async def test_multiple_entries_require_repo(
    hass: HomeAssistant, setup_entry, mock_api
) -> None:
    second = MockConfigEntry(
        domain=DOMAIN,
        unique_id="other/repo",
        data={**ENTRY_DATA, CONF_REPO: "other/repo"},
    )
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError, match="Multiple repositories"):
        await hass.services.async_call(
            DOMAIN,
            "dispatch_workflow",
            {"workflow": "deploy.yml"},
            blocking=True,
        )

    response = await hass.services.async_call(
        DOMAIN,
        "dispatch_workflow",
        {"workflow": "deploy.yml", "repo": REPO},
        blocking=True,
        return_response=True,
    )
    assert response == {"queued": True}
