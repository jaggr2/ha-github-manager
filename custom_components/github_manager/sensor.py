"""Sensor platform for the GitHub Manager integration."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import GitHubManagerCoordinator, GitHubManagerData
from .entity import GitHubManagerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GitHub Manager sensors; run sensors appear per discovered workflow."""
    coordinator: GitHubManagerCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]

    async_add_entities(
        [
            GitHubManagerCountSensor(
                coordinator,
                entry,
                key="open_issues",
                name="Open issues",
                icon="mdi:alert-circle-outline",
                value_fn=lambda data: len(data.issues_only),
                attrs_fn=lambda data: [
                    {
                        "number": issue.get("number"),
                        "title": issue.get("title"),
                        "url": issue.get("html_url"),
                    }
                    for issue in data.issues_only[:10]
                ],
            ),
            GitHubManagerCountSensor(
                coordinator,
                entry,
                key="open_prs",
                name="Open pull requests",
                icon="mdi:source-pull",
                value_fn=lambda data: len(data.pulls),
                attrs_fn=lambda data: [
                    {
                        "number": pull.get("number"),
                        "title": pull.get("title"),
                        "url": pull.get("html_url"),
                    }
                    for pull in data.pulls[:10]
                ],
            ),
        ]
    )

    known_workflow_ids: set[int] = set()

    @callback
    def _add_workflow_sensors() -> None:
        new_entities = []
        for workflow_id, name in coordinator.async_workflow_ids().items():
            if workflow_id in known_workflow_ids:
                continue
            known_workflow_ids.add(workflow_id)
            new_entities.append(
                GitHubManagerRunSensor(coordinator, entry, workflow_id, name)
            )
        if new_entities:
            async_add_entities(new_entities)

    _add_workflow_sensors()
    entry.async_on_remove(coordinator.async_add_listener(_add_workflow_sensors))


class GitHubManagerCountSensor(GitHubManagerEntity, SensorEntity):
    """Count sensor (open issues / open pull requests)."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: GitHubManagerCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
        icon: str,
        value_fn: Callable[[GitHubManagerData], int],
        attrs_fn: Callable[[GitHubManagerData], list[dict[str, Any]]],
    ) -> None:
        super().__init__(coordinator, entry)
        self._value_fn = value_fn
        self._attrs_fn = attrs_fn
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_icon = icon

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self._value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        return {"items": self._attrs_fn(self.coordinator.data)}


class GitHubManagerRunSensor(GitHubManagerEntity, SensorEntity):
    """Latest workflow run state (one sensor per workflow)."""

    def __init__(
        self,
        coordinator: GitHubManagerCoordinator,
        entry: ConfigEntry,
        workflow_id: int,
        workflow_name: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._workflow_id = workflow_id
        self._attr_unique_id = f"{entry.entry_id}_run_{workflow_id}"
        self._attr_name = f"{workflow_name} last run"
        self._attr_icon = "mdi:github"

    def _latest_run(self) -> dict[str, Any] | None:
        if self.coordinator.data is None:
            return None
        for run in self.coordinator.data.runs:  # newest first
            if run.get("workflow_id") == self._workflow_id:
                return run
        return None

    @property
    def native_value(self) -> str | None:
        run = self._latest_run()
        if run is None:
            return None
        if run.get("status") == "completed":
            return run.get("conclusion")
        return run.get("status")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        run = self._latest_run()
        if run is None:
            return {}
        return {
            "run_id": run.get("id"),
            "run_number": run.get("run_number"),
            "display_title": run.get("display_title"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "event": run.get("event"),
            "head_branch": run.get("head_branch"),
            "head_sha": run.get("head_sha"),
            "url": run.get("html_url"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
        }
