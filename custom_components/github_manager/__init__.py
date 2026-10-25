"""The GitHub Manager integration.

Manage GitHub workflow runs, issues and pull requests from Home Assistant:
dispatch/cancel/re-run Actions workflows and create/comment/update issues and
pull requests — with run status sensors and change events on top.
"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import (
    GitHubManagerApi,
    GitHubManagerAuthError,
    GitHubManagerError,
)
from .const import (
    CONF_API_URL,
    CONF_POLL_INTERVAL,
    CONF_REPO,
    CONF_TOKEN,
    DEFAULT_API_URL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    EVENT_BUS,
    EVENT_RUN_REQUESTED,
    MERGE_METHODS,
)
from .coordinator import GitHubManagerCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.EVENT]

SERVICE_DISPATCH_WORKFLOW = "dispatch_workflow"
SERVICE_CANCEL_RUN = "cancel_run"
SERVICE_RERUN_RUN = "rerun_run"
SERVICE_CREATE_ISSUE = "create_issue"
SERVICE_COMMENT_ISSUE = "comment_issue"
SERVICE_UPDATE_ISSUE = "update_issue"
SERVICE_CREATE_PULL_REQUEST = "create_pull_request"
SERVICE_MERGE_PULL_REQUEST = "merge_pull_request"
SERVICE_CLOSE_PULL_REQUEST = "close_pull_request"

_REPO_FIELD = {vol.Optional("repo"): cv.string}

DISPATCH_SCHEMA = vol.Schema(
    {
        vol.Required("workflow"): cv.string,
        vol.Optional("ref"): cv.string,
        vol.Optional("inputs"): dict,
        **_REPO_FIELD,
    }
)
CANCEL_SCHEMA = vol.Schema({vol.Required("run_id"): vol.Coerce(int), **_REPO_FIELD})
RERUN_SCHEMA = vol.Schema(
    {
        vol.Required("run_id"): vol.Coerce(int),
        vol.Optional("failed_only", default=False): cv.boolean,
        **_REPO_FIELD,
    }
)
CREATE_ISSUE_SCHEMA = vol.Schema(
    {
        vol.Required("title"): cv.string,
        vol.Optional("body"): cv.string,
        vol.Optional("labels"): [cv.string],
        vol.Optional("assignees"): [cv.string],
        **_REPO_FIELD,
    }
)
COMMENT_SCHEMA = vol.Schema(
    {
        vol.Required("number"): vol.Coerce(int),
        vol.Required("body"): cv.string,
        **_REPO_FIELD,
    }
)
UPDATE_ISSUE_SCHEMA = vol.Schema(
    {
        vol.Required("number"): vol.Coerce(int),
        vol.Optional("state"): vol.In(["open", "closed"]),
        vol.Optional("title"): cv.string,
        vol.Optional("body"): cv.string,
        vol.Optional("labels"): [cv.string],
        vol.Optional("assignees"): [cv.string],
        **_REPO_FIELD,
    }
)
CREATE_PR_SCHEMA = vol.Schema(
    {
        vol.Required("title"): cv.string,
        vol.Required("head"): cv.string,
        vol.Optional("base"): cv.string,
        vol.Optional("body"): cv.string,
        vol.Optional("draft", default=False): cv.boolean,
        **_REPO_FIELD,
    }
)
MERGE_PR_SCHEMA = vol.Schema(
    {
        vol.Required("number"): vol.Coerce(int),
        vol.Optional("merge_method", default="merge"): vol.In(MERGE_METHODS),
        vol.Optional("commit_title"): cv.string,
        vol.Optional("commit_message"): cv.string,
        **_REPO_FIELD,
    }
)
CLOSE_PR_SCHEMA = vol.Schema({vol.Required("number"): vol.Coerce(int), **_REPO_FIELD})


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the domain: register the actions once."""
    hass.data.setdefault(DOMAIN, {})
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one repository from a config entry."""
    api = GitHubManagerApi(
        async_get_clientsession(hass),
        entry.data[CONF_TOKEN],
        entry.data[CONF_REPO],
        entry.data.get(CONF_API_URL, DEFAULT_API_URL),
    )
    try:
        repo_info = await api.async_get_repo()
    except GitHubManagerAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except GitHubManagerError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = GitHubManagerCoordinator(
        hass,
        api,
        entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
    )
    coordinator.default_branch = repo_info.get("default_branch") or "main"
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


# -------------------------------------------------------------------------


def _resolve_entry(hass: HomeAssistant, repo: str | None) -> ConfigEntry:
    """Pick the config entry a service call targets."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise HomeAssistantError("GitHub Manager is not configured")
    if repo is not None:
        for entry in entries:
            if entry.entry_id == repo or entry.data[CONF_REPO].lower() == repo.lower():
                return entry
        raise HomeAssistantError(f"No config entry for repository '{repo}'")
    if len(entries) == 1:
        return entries[0]
    raise HomeAssistantError(
        "Multiple repositories configured — pass 'repo' (owner/name) in the call"
    )


def _api(hass: HomeAssistant, entry: ConfigEntry) -> GitHubManagerApi:
    return hass.data[DOMAIN][entry.entry_id]["api"]


def _coordinator(hass: HomeAssistant, entry: ConfigEntry) -> GitHubManagerCoordinator:
    return hass.data[DOMAIN][entry.entry_id]["coordinator"]


def _register_services(hass: HomeAssistant) -> None:
    """Register the github_manager actions (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_DISPATCH_WORKFLOW):
        return

    async def _handle_dispatch(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data.get("repo"))
        api = _api(hass, entry)
        workflow = call.data["workflow"]
        ref = call.data.get("ref") or _coordinator(hass, entry).default_branch
        try:
            await api.async_dispatch_workflow(
                workflow, ref, call.data.get("inputs") or {}
            )
        except GitHubManagerError as err:
            raise HomeAssistantError(f"dispatch failed: {err}") from err
        hass.bus.async_fire(
            EVENT_BUS,
            {"event_type": EVENT_RUN_REQUESTED, "workflow": workflow, "ref": ref},
        )
        return {"queued": True}

    async def _handle_cancel(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data.get("repo"))
        run_id = call.data["run_id"]
        try:
            await _api(hass, entry).async_cancel_run(run_id)
        except GitHubManagerError as err:
            raise HomeAssistantError(f"cancel failed: {err}") from err
        return {"cancelled": True, "run_id": run_id}

    async def _handle_rerun(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data.get("repo"))
        run_id = call.data["run_id"]
        try:
            await _api(hass, entry).async_rerun_run(
                run_id, failed_only=call.data.get("failed_only", False)
            )
        except GitHubManagerError as err:
            raise HomeAssistantError(f"re-run failed: {err}") from err
        return {"rerun": True, "run_id": run_id}

    async def _handle_create_issue(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data.get("repo"))
        try:
            issue = await _api(hass, entry).async_create_issue(
                title=call.data["title"],
                body=call.data.get("body"),
                labels=call.data.get("labels"),
                assignees=call.data.get("assignees"),
            )
        except GitHubManagerError as err:
            raise HomeAssistantError(f"create_issue failed: {err}") from err
        return {"number": issue.get("number"), "url": issue.get("html_url")}

    async def _handle_comment(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data.get("repo"))
        try:
            comment = await _api(hass, entry).async_comment_issue(
                call.data["number"], call.data["body"]
            )
        except GitHubManagerError as err:
            raise HomeAssistantError(f"comment failed: {err}") from err
        return {"url": comment.get("html_url")}

    async def _handle_update_issue(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data.get("repo"))
        try:
            issue = await _api(hass, entry).async_update_issue(
                number=call.data["number"],
                state=call.data.get("state"),
                title=call.data.get("title"),
                body=call.data.get("body"),
                labels=call.data.get("labels"),
                assignees=call.data.get("assignees"),
            )
        except GitHubManagerError as err:
            raise HomeAssistantError(f"update_issue failed: {err}") from err
        return {
            "number": issue.get("number"),
            "url": issue.get("html_url"),
            "state": issue.get("state"),
        }

    async def _handle_create_pr(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data.get("repo"))
        base = call.data.get("base") or _coordinator(hass, entry).default_branch
        try:
            pr = await _api(hass, entry).async_create_pull_request(
                title=call.data["title"],
                head=call.data["head"],
                base=base,
                body=call.data.get("body"),
                draft=call.data.get("draft", False),
            )
        except GitHubManagerError as err:
            raise HomeAssistantError(f"create_pull_request failed: {err}") from err
        return {"number": pr.get("number"), "url": pr.get("html_url")}

    async def _handle_merge_pr(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data.get("repo"))
        try:
            result = await _api(hass, entry).async_merge_pull_request(
                number=call.data["number"],
                merge_method=call.data.get("merge_method", "merge"),
                commit_title=call.data.get("commit_title"),
                commit_message=call.data.get("commit_message"),
            )
        except GitHubManagerError as err:
            raise HomeAssistantError(f"merge failed: {err}") from err
        return {
            "merged": bool(result.get("merged")),
            "sha": result.get("sha"),
            "message": result.get("message"),
        }

    async def _handle_close_pr(call: ServiceCall) -> ServiceResponse:
        entry = _resolve_entry(hass, call.data.get("repo"))
        try:
            pr = await _api(hass, entry).async_close_pull_request(call.data["number"])
        except GitHubManagerError as err:
            raise HomeAssistantError(f"close_pull_request failed: {err}") from err
        return {"number": pr.get("number"), "url": pr.get("html_url")}

    services = [
        (SERVICE_DISPATCH_WORKFLOW, _handle_dispatch, DISPATCH_SCHEMA),
        (SERVICE_CANCEL_RUN, _handle_cancel, CANCEL_SCHEMA),
        (SERVICE_RERUN_RUN, _handle_rerun, RERUN_SCHEMA),
        (SERVICE_CREATE_ISSUE, _handle_create_issue, CREATE_ISSUE_SCHEMA),
        (SERVICE_COMMENT_ISSUE, _handle_comment, COMMENT_SCHEMA),
        (SERVICE_UPDATE_ISSUE, _handle_update_issue, UPDATE_ISSUE_SCHEMA),
        (SERVICE_CREATE_PULL_REQUEST, _handle_create_pr, CREATE_PR_SCHEMA),
        (SERVICE_MERGE_PULL_REQUEST, _handle_merge_pr, MERGE_PR_SCHEMA),
        (SERVICE_CLOSE_PULL_REQUEST, _handle_close_pr, CLOSE_PR_SCHEMA),
    ]
    for service, handler, schema in services:
        hass.services.async_register(
            DOMAIN,
            service,
            handler,
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
