"""Tests for the coordinator, entities and event emission."""
from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.github_manager.const import DOMAIN

from .conftest import ISSUE, RUN, capture_events


async def test_setup_creates_entities(hass: HomeAssistant, setup_entry) -> None:
    registry = er.async_get(hass)
    unique_ids = {
        entity.unique_id
        for entity in registry.async_entries_for_config_entry(setup_entry.entry_id)
    }
    base = setup_entry.entry_id
    assert f"{base}_open_issues" in unique_ids
    assert f"{base}_open_prs" in unique_ids
    assert f"{base}_run_7" in unique_ids
    assert f"{base}_events" in unique_ids


async def test_run_sensor_state(hass: HomeAssistant, setup_entry) -> None:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{setup_entry.entry_id}_run_7"
    )
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "success"
    assert state.attributes["run_number"] == 55
    assert state.attributes["head_sha"] == "abc123"


async def test_new_failed_run_fires_event(
    hass: HomeAssistant, setup_entry, mock_api
) -> None:
    events = capture_events(hass)
    failed = dict(
        RUN, id=102, run_number=56, status="completed", conclusion="failure"
    )
    mock_api.async_get_runs = AsyncMock(return_value=[failed, dict(RUN)])
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]["coordinator"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert [event.data["event_type"] for event in events] == [
        "workflow_run_completed"
    ]
    assert events[0].data["conclusion"] == "failure"
    assert events[0].data["run_id"] == 102


async def test_no_events_on_unchanged_snapshot(
    hass: HomeAssistant, setup_entry, mock_api
) -> None:
    events = capture_events(hass)
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]["coordinator"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert events == []


async def test_issue_opened_and_closed_events(
    hass: HomeAssistant, setup_entry, mock_api
) -> None:
    events = capture_events(hass)
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]["coordinator"]

    new_issue = dict(
        ISSUE, number=13, title="ZFS scrub overdue", html_url="https://example/issues/13"
    )
    mock_api.async_get_open_issues = AsyncMock(
        return_value=[dict(ISSUE), new_issue]
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert [event.data["event_type"] for event in events] == ["issue_opened"]
    assert events[0].data["number"] == 13

    events.clear()
    mock_api.async_get_open_issues = AsyncMock(return_value=[])
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    closed = [event.data["event_type"] for event in events]
    assert "issue_closed" in closed
    assert {event.data["number"] for event in events} == {12, 13}


async def test_event_entity_updates(hass: HomeAssistant, setup_entry, mock_api) -> None:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "event", DOMAIN, f"{setup_entry.entry_id}_events"
    )
    new_issue = dict(ISSUE, number=14, html_url="https://example/issues/14")
    mock_api.async_get_open_issues = AsyncMock(
        return_value=[dict(ISSUE), new_issue]
    )
    coordinator = hass.data[DOMAIN][setup_entry.entry_id]["coordinator"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["event_type"] == "issue_opened"
    assert state.attributes["number"] == 14
