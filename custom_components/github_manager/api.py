"""Minimal async GitHub REST API client for the GitHub Manager integration.

Dependency-free on purpose: plain aiohttp, which Home Assistant core bundles.
Only the endpoints the integration actually uses are wrapped.
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

API_VERSION = "2022-11-28"
USER_AGENT = "ha-github-manager"

_LOGGER = logging.getLogger(__name__)


class GitHubManagerError(Exception):
    """Base error for the GitHub Manager API client."""


class GitHubManagerAuthError(GitHubManagerError):
    """Authentication or permission failed (HTTP 401/403)."""


class GitHubManagerNotFoundError(GitHubManagerError):
    """Resource does not exist (HTTP 404)."""


class GitHubManagerApi:
    """Thin async wrapper around the GitHub REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str,
        repo: str,
        api_url: str,
    ) -> None:
        self._session = session
        self._token = token
        self.repo = repo
        self._base = api_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        }

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self._base}{path}"
        try:
            async with self._session.request(
                method, url, headers=self._headers(), json=json
            ) as resp:
                if resp.status in (401, 403):
                    body = await resp.text()
                    raise GitHubManagerAuthError(
                        f"auth failed (HTTP {resp.status}): {body[:200]}"
                    )
                if resp.status == 404:
                    raise GitHubManagerNotFoundError(f"not found: {path}")
                if resp.status >= 400:
                    body = await resp.text()
                    raise GitHubManagerError(f"HTTP {resp.status}: {body[:200]}")
                if resp.status == 204:
                    return None
                return await resp.json()
        except aiohttp.ClientError as err:
            raise GitHubManagerError(f"cannot reach {url}: {err}") from err

    # ------------------------------------------------------------------ repo

    async def async_get_repo(self) -> dict[str, Any]:
        """Return repository metadata (validates token + repo)."""
        return await self._request("GET", f"/repos/{self.repo}")

    # -------------------------------------------------------------- workflow

    async def async_dispatch_workflow(
        self,
        workflow: str,
        ref: str,
        inputs: dict[str, Any] | None = None,
    ) -> None:
        """Trigger a workflow_dispatch run.

        `workflow` is a workflow file name (``deploy.yml``), workflow id or name.
        """
        payload: dict[str, Any] = {"ref": ref}
        if inputs:
            payload["inputs"] = inputs
        await self._request(
            "POST",
            f"/repos/{self.repo}/actions/workflows/{workflow}/dispatches",
            json=payload,
        )

    async def async_get_runs(self, per_page: int = 20) -> list[dict[str, Any]]:
        """Return recent workflow runs, newest first."""
        data = await self._request(
            "GET", f"/repos/{self.repo}/actions/runs?per_page={per_page}"
        )
        return data.get("workflow_runs", [])

    async def async_get_workflows(self) -> list[dict[str, Any]]:
        """Return the repository's workflows."""
        data = await self._request(
            "GET", f"/repos/{self.repo}/actions/workflows?per_page=100"
        )
        return data.get("workflows", [])

    async def async_cancel_run(self, run_id: int) -> None:
        """Cancel a workflow run."""
        await self._request(
            "POST", f"/repos/{self.repo}/actions/runs/{run_id}/cancel"
        )

    async def async_rerun_run(self, run_id: int, failed_only: bool = False) -> None:
        """Re-run a workflow run, optionally only its failed jobs."""
        path = f"/repos/{self.repo}/actions/runs/{run_id}/rerun"
        payload = {"scope": "failed"} if failed_only else None
        await self._request("POST", path, json=payload)

    # ----------------------------------------------------------------- issue

    async def async_get_open_issues(self, per_page: int = 50) -> list[dict[str, Any]]:
        """Return open issues (pull requests included, as on the GitHub API)."""
        data = await self._request(
            "GET", f"/repos/{self.repo}/issues?state=open&per_page={per_page}"
        )
        return data if isinstance(data, list) else []

    async def async_create_issue(
        self,
        title: str,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Open an issue."""
        payload: dict[str, Any] = {"title": title}
        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels
        if assignees:
            payload["assignees"] = assignees
        return await self._request("POST", f"/repos/{self.repo}/issues", json=payload)

    async def async_comment_issue(self, number: int, body: str) -> dict[str, Any]:
        """Comment on an issue or pull request."""
        return await self._request(
            "POST", f"/repos/{self.repo}/issues/{number}/comments", json={"body": body}
        )

    async def async_update_issue(
        self,
        number: int,
        state: str | None = None,
        title: str | None = None,
        body: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an issue (or pull request) in place."""
        payload: dict[str, Any] = {}
        if state:
            payload["state"] = state
        if title:
            payload["title"] = title
        if body:
            payload["body"] = body
        if labels is not None:
            payload["labels"] = labels
        if assignees is not None:
            payload["assignees"] = assignees
        return await self._request(
            "PATCH", f"/repos/{self.repo}/issues/{number}", json=payload
        )

    # ---------------------------------------------------------- pull request

    async def async_get_open_pulls(self, per_page: int = 50) -> list[dict[str, Any]]:
        """Return open pull requests."""
        data = await self._request(
            "GET", f"/repos/{self.repo}/pulls?state=open&per_page={per_page}"
        )
        return data if isinstance(data, list) else []

    async def async_get_pull(self, number: int) -> dict[str, Any]:
        """Return one pull request (incl. the `merged` flag)."""
        return await self._request("GET", f"/repos/{self.repo}/pulls/{number}")

    async def async_create_pull_request(
        self,
        title: str,
        head: str,
        base: str,
        body: str | None = None,
        draft: bool = False,
    ) -> dict[str, Any]:
        """Open a pull request."""
        payload: dict[str, Any] = {
            "title": title,
            "head": head,
            "base": base,
            "draft": draft,
        }
        if body:
            payload["body"] = body
        return await self._request("POST", f"/repos/{self.repo}/pulls", json=payload)

    async def async_merge_pull_request(
        self,
        number: int,
        merge_method: str = "merge",
        commit_title: str | None = None,
        commit_message: str | None = None,
    ) -> dict[str, Any]:
        """Merge a pull request."""
        payload: dict[str, Any] = {"merge_method": merge_method}
        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message
        return await self._request(
            "PUT", f"/repos/{self.repo}/pulls/{number}/merge", json=payload
        )

    async def async_close_pull_request(self, number: int) -> dict[str, Any]:
        """Close a pull request without merging."""
        return await self._request(
            "PATCH", f"/repos/{self.repo}/pulls/{number}", json={"state": "closed"}
        )
