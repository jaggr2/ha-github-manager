"""Data update coordinator for the GitHub Manager integration.

Polls recent workflow runs, open issues and open pull requests, and turns
snapshot diffs into bus events (consumed by the EventEntity).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GitHubManagerApi, GitHubManagerError
from .const import (
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    EVENT_BUS,
    EVENT_ISSUE_CLOSED,
    EVENT_ISSUE_OPENED,
    EVENT_PR_CLOSED,
    EVENT_PR_MERGED,
    EVENT_PR_OPENED,
    EVENT_WORKFLOW_RUN_COMPLETED,
    EVENT_WORKFLOW_RUN_STARTED,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class GitHubManagerData:
    """Coordinator data snapshot."""

    runs: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    pulls: list[dict[str, Any]] = field(default_factory=list)
    default_branch: str = "main"

    @property
    def issues_only(self) -> list[dict[str, Any]]:
        """Open issues without pull requests (the API mixes them)."""
        return [issue for issue in self.issues if "pull_request" not in issue]


class GitHubManagerCoordinator(DataUpdateCoordinator[GitHubManagerData]):
    """Poll GitHub and emit change events."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: GitHubManagerApi,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({api.repo})",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.api = api
        self.default_branch = "main"
        self._runs_state: dict[int, dict[str, Any]] = {}
        self._issues_state: dict[int, dict[str, Any]] = {}
        self._pulls_state: dict[int, dict[str, Any]] = {}
        self._initialized = False

    async def _async_update_data(self) -> GitHubManagerData:
        try:
            runs, issues, pulls = await asyncio.gather(
                self.api.async_get_runs(),
                self.api.async_get_open_issues(),
                self.api.async_get_open_pulls(),
            )
        except GitHubManagerError as err:
            raise UpdateFailed(str(err)) from err

        data = GitHubManagerData(
            runs=runs,
            issues=issues,
            pulls=pulls,
            default_branch=self.default_branch,
        )

        if self._initialized:
            await self._emit_events(data)
        self._store_state(data)
        self._initialized = True
        return data

    # ------------------------------------------------------------------ diff

    @staticmethod
    def _run_payload(run: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": run.get("id"),
            "workflow": run.get("name"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "run_number": run.get("run_number"),
            "head_branch": run.get("head_branch"),
            "head_sha": run.get("head_sha"),
            "url": run.get("html_url"),
        }

    async def _emit_events(self, data: GitHubManagerData) -> None:
        """Diff the new snapshot against the previous one and fire bus events."""
        events: list[tuple[str, dict[str, Any]]] = []

        for run in data.runs:
            run_id = run.get("id")
            if run_id is None:
                continue
            prev = self._runs_state.get(run_id)
            completed = run.get("status") == "completed"
            if prev is None:
                etype = (
                    EVENT_WORKFLOW_RUN_COMPLETED
                    if completed
                    else EVENT_WORKFLOW_RUN_STARTED
                )
                events.append((etype, self._run_payload(run)))
            elif prev.get("status") != "completed" and completed:
                events.append((EVENT_WORKFLOW_RUN_COMPLETED, self._run_payload(run)))

        open_issues = {issue["number"]: issue for issue in data.issues_only}
        for number, issue in open_issues.items():
            if number not in self._issues_state:
                events.append(
                    (
                        EVENT_ISSUE_OPENED,
                        {
                            "number": number,
                            "title": issue.get("title"),
                            "url": issue.get("html_url"),
                        },
                    )
                )
        for number, issue in self._issues_state.items():
            if number not in open_issues:
                events.append(
                    (
                        EVENT_ISSUE_CLOSED,
                        {
                            "number": number,
                            "title": issue.get("title"),
                            "url": issue.get("url"),
                        },
                    )
                )

        open_pulls = {pull["number"]: pull for pull in data.pulls}
        for number, pull in open_pulls.items():
            if number not in self._pulls_state:
                events.append(
                    (
                        EVENT_PR_OPENED,
                        {
                            "number": number,
                            "title": pull.get("title"),
                            "url": pull.get("html_url"),
                        },
                    )
                )
        for number, pull in self._pulls_state.items():
            if number not in open_pulls:
                # The PR left the open list: merged or just closed? Ask GitHub.
                merged = False
                try:
                    detail = await self.api.async_get_pull(number)
                    merged = bool(detail.get("merged"))
                except GitHubManagerError:
                    _LOGGER.debug("could not check merged state of PR #%s", number)
                events.append(
                    (
                        EVENT_PR_MERGED if merged else EVENT_PR_CLOSED,
                        {
                            "number": number,
                            "title": pull.get("title"),
                            "url": pull.get("url"),
                        },
                    )
                )

        for etype, payload in events:
            self.hass.bus.async_fire(EVENT_BUS, {"event_type": etype, **payload})

    def _store_state(self, data: GitHubManagerData) -> None:
        self._runs_state = {
            run["id"]: {"status": run.get("status")}
            for run in data.runs
            if run.get("id") is not None
        }
        self._issues_state = {
            issue["number"]: {
                "title": issue.get("title"),
                "url": issue.get("html_url"),
            }
            for issue in data.issues_only
        }
        self._pulls_state = {
            pull["number"]: {
                "title": pull.get("title"),
                "url": pull.get("html_url"),
            }
            for pull in data.pulls
        }

    @callback
    def async_workflow_ids(self) -> dict[int, str]:
        """Return workflow_id -> name for every workflow seen in recent runs."""
        seen: dict[int, str] = {}
        for run in (self.data.runs if self.data else []):
            workflow_id = run.get("workflow_id")
            if workflow_id is not None and workflow_id not in seen:
                seen[workflow_id] = run.get("name") or str(workflow_id)
        return seen
