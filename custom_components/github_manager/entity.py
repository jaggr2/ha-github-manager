"""Base entity for the GitHub Manager integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_REPO, DOMAIN
from .coordinator import GitHubManagerCoordinator


class GitHubManagerEntity(CoordinatorEntity[GitHubManagerCoordinator]):
    """Base entity bound to one repository (device)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GitHubManagerCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._repo = entry.data[CONF_REPO]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_REPO],
            manufacturer="GitHub",
            configuration_url=f"https://github.com/{entry.data[CONF_REPO]}",
        )
