"""Event platform for the GitHub Manager integration.

One event entity per repository; it turns coordinator diffs (and action
calls) into `event.github_manager` events for automation triggers.
"""
from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, EVENT_BUS, EVENT_TYPES
from .coordinator import GitHubManagerCoordinator
from .entity import GitHubManagerEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the event entity."""
    coordinator: GitHubManagerCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities([GitHubManagerEventEntity(coordinator, entry)])


class GitHubManagerEventEntity(GitHubManagerEntity, EventEntity):
    """Fires on workflow run, issue and pull request changes."""

    _attr_event_types = EVENT_TYPES
    _attr_name = "GitHub events"
    _attr_icon = "mdi:flash"

    def __init__(
        self,
        coordinator: GitHubManagerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_events"

    async def async_added_to_hass(self) -> None:
        """Listen for integration bus events."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_BUS, self._handle_bus_event)
        )

    @callback
    def _handle_bus_event(self, event) -> None:
        event_type = event.data.get("event_type")
        if event_type not in self._attr_event_types:
            return
        payload = {k: v for k, v in event.data.items() if k != "event_type"}
        self._trigger_event(event_type, payload)
        self.async_write_ha_state()
