"""Config flow for the GitHub Manager integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    GitHubManagerApi,
    GitHubManagerAuthError,
    GitHubManagerError,
    GitHubManagerNotFoundError,
)
from .const import (
    CONF_API_URL,
    CONF_POLL_INTERVAL,
    CONF_REPO,
    CONF_TOKEN,
    DEFAULT_API_URL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MIN_POLL_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REPO): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
        ),
        vol.Required(CONF_TOKEN): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_API_URL, default=DEFAULT_API_URL): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
        ),
    }
)


class GitHubManagerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    VERSION = 1

    _reauth_entry: ConfigEntry | None = None

    async def _validate(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate credentials by fetching repository metadata."""
        api = GitHubManagerApi(
            async_get_clientsession(self.hass),
            data[CONF_TOKEN],
            data[CONF_REPO],
            data.get(CONF_API_URL) or DEFAULT_API_URL,
        )
        return await api.async_get_repo()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle setup initiated by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            repo = user_input[CONF_REPO].strip()
            if "/" not in repo:
                errors[CONF_REPO] = "invalid_repo"
            else:
                data = {
                    CONF_REPO: repo,
                    CONF_TOKEN: user_input[CONF_TOKEN],
                    CONF_API_URL: user_input.get(CONF_API_URL) or DEFAULT_API_URL,
                }
                try:
                    info = await self._validate(data)
                except GitHubManagerAuthError:
                    errors["base"] = "invalid_auth"
                except GitHubManagerNotFoundError:
                    errors["base"] = "invalid_repo"
                except GitHubManagerError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Unexpected exception during validation")
                    errors["base"] = "unknown"
                else:
                    await self.async_set_unique_id(repo.lower())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=info.get("full_name", repo),
                        data=data,
                        options={CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL},
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication when the token stopped working."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh token and re-validate it."""
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None
        if user_input is not None:
            data = {**self._reauth_entry.data, CONF_TOKEN: user_input[CONF_TOKEN]}
            try:
                await self._validate(data)
            except GitHubManagerAuthError:
                errors["base"] = "invalid_auth"
            except GitHubManagerError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data_updates={CONF_TOKEN: user_input[CONF_TOKEN]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    )
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return GitHubManagerOptionsFlow()


class GitHubManagerOptionsFlow(OptionsFlow):
    """Handle options (poll interval)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                    ),
                ): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL, max=3600)
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
