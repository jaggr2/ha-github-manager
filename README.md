# GitHub Manager

Home Assistant custom integration for **managing** a GitHub repository:
trigger and control GitHub Actions workflow runs, create/comment/update issues,
open/merge/close pull requests — with run-status sensors and change events on
top. Complements the core (read-only) `github` integration.

Designed for GitOps homelabs where Home Assistant dashboards and automations
should be able to kick off CI (`workflow_dispatch`), file issues on incidents,
and merge the robot's PRs.

## Features

**Actions (services)** — all return response data (`response_variable`) and
accept an optional `repo` field when several repositories are configured:

| Action | Fields | Purpose |
|---|---|---|
| `github_manager.dispatch_workflow` | `workflow`, `ref?`, `inputs?` | Trigger a `workflow_dispatch` run |
| `github_manager.cancel_run` | `run_id` | Cancel a running workflow |
| `github_manager.rerun_run` | `run_id`, `failed_only?` | Re-run a workflow (or only failed jobs) |
| `github_manager.create_issue` | `title`, `body?`, `labels?`, `assignees?` | Open an issue |
| `github_manager.comment_issue` | `number`, `body` | Comment on an issue or pull request |
| `github_manager.update_issue` | `number`, `state?`, `title?`, `body?`, `labels?`, `assignees?` | Update/close/reopen an issue |
| `github_manager.create_pull_request` | `title`, `head`, `base?`, `body?`, `draft?` | Open a pull request |
| `github_manager.merge_pull_request` | `number`, `merge_method?`, `commit_title?`, `commit_message?` | Merge a pull request |
| `github_manager.close_pull_request` | `number` | Close a pull request without merging |

**Entities** (per repository):

- `sensor.<repo>_<workflow> last run` — state is the run conclusion (`success`,
  `failure`, …) or `queued`/`in_progress`; attributes carry `run_id`, `url`,
  `head_sha`, `run_number`, timestamps. One sensor per discovered workflow.
- `sensor.<repo> open issues` / `sensor.<repo> open pull requests` — counts
  with the ten newest entries in `items`.
- `event.<repo> github events` — automation trigger source.

**Events** (`event.github_manager` entity, types):

`run_requested`, `workflow_run_started`, `workflow_run_completed`,
`issue_opened`, `issue_closed`, `pr_opened`, `pr_merged`, `pr_closed` —
payload includes `number`/`run_id`, `title`/`workflow`, `url`, `conclusion`.

## Installation

1. HACS → ⋮ → **Custom repositories** → add `jaggr2/ha-github-manager`,
   category **Integration** → install → restart Home Assistant.
2. Settings → Devices & services → Add Integration → **GitHub Manager**.
3. Enter the repository (`owner/name`), a fine-grained personal access token
   and (optionally) an API URL.

### Token

Create a **fine-grained personal access token** limited to the one repository
with these permissions:

- Actions: **Read and write**
- Issues: **Read and write**
- Pull requests: **Read and write**

The token is stored in the configuration entry (HA `.storage`), never in
`secrets.yaml`. If it expires, the integration prompts for re-authentication.

## Example automations

Notify + file an issue when a workflow fails:

```yaml
automation:
  - alias: "CI failure → issue"
    triggers:
      - trigger: event
        event_type: github_manager_event   # bus events also reach the event entity
        event_data:
          event_type: workflow_run_completed
          conclusion: failure
    actions:
      - action: github_manager.create_issue
        data:
          title: "CI failed: {{ trigger.event.data.workflow }} #{{ trigger.event.data.run_number }}"
          body: "{{ trigger.event.data.url }}"
          labels: ["ci-failure"]
```

Run the nightly ingest from a dashboard button:

```yaml
- action: github_manager.dispatch_workflow
  data:
    workflow: lakehouse-ingest.yml
```

Merge a bot PR after a successful check run:

```yaml
- action: github_manager.merge_pull_request
  data:
    number: 42
    merge_method: squash
```

## Development

```bash
pip install -r requirements_test.txt
pytest -q
```

CI runs [hassfest](https://developers.home-assistant.io/docs/creating_integration_manifest),
HACS validation and the test suite on every push/PR. Releases are tagged
(`v0.1.0`) so HACS can update.
