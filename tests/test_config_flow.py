"""Tests for the GitHub Manager config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.github_manager.api import GitHubManagerAuthError
from custom_components.github_manager.const import (
    CONF_API_URL,
    CONF_POLL_INTERVAL,
    CONF_REPO,
    CONF_TOKEN,
    DEFAULT_API_URL,
    DOMAIN,
)

from .conftest import REPO

USER_INPUT = {
    CONF_REPO: REPO,
    CONF_TOKEN: "ghp_test_token",
    CONF_API_URL: DEFAULT_API_URL,
}


async def _start_user_flow(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_flow_success(hass: HomeAssistant, mock_api) -> None:
    result = await _start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == REPO
    assert result["data"][CONF_REPO] == REPO
    assert result["data"][CONF_TOKEN] == "ghp_test_token"
    assert result["options"][CONF_POLL_INTERVAL] == 120
    mock_api.async_get_repo.assert_awaited()


async def test_user_flow_invalid_auth(hass: HomeAssistant, mock_api) -> None:
    mock_api.async_get_repo = AsyncMock(side_effect=GitHubManagerAuthError("401"))

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_invalid_repo_format(hass: HomeAssistant, mock_api) -> None:
    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_REPO: "not-a-repo"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_REPO: "invalid_repo"}
    mock_api.async_get_repo.assert_not_awaited()


async def test_already_configured(hass: HomeAssistant, mock_api) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=REPO.lower(), data=USER_INPUT
    )
    entry.add_to_hass(hass)

    result = await _start_user_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(hass: HomeAssistant, mock_api) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=REPO.lower(), data=USER_INPUT)
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=USER_INPUT,
    )
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "ghp_fresh_token"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == "ghp_fresh_token"


async def test_options_flow(hass: HomeAssistant, setup_entry) -> None:
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL: 60}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_POLL_INTERVAL] == 60
