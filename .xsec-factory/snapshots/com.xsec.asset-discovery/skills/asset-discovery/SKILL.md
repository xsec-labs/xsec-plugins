---
name: asset-discovery
description: Run the asset-discovery workflow for an explicitly authorized network scope - create a collection run, watch it, filter the asset pool, and import the assets that are in scope into a project.
---

# Asset discovery workflow

Use this Skill only for a scope the user explicitly authorizes. A scope is a
wildcard domain such as `*.example.com`, or one fixed host/domain/IP/URL. Do
not expand company names, HackerOne programs, local files, browser state or
proxy traffic into scopes, and do not pass a provider query expression, a
credential, an internal URL or an unbounded range.

## Tools

Read (no side effects):

- `asset_discovery_runs_list` - collection runs, newest first, optionally by `status`.
- `asset_discovery_run_get` - one run's status, collected count, failure reason and latest log lines.
- `asset_discovery_assets_list` - filter the asset pool by `runId`, `provider`, `assetType`, a host keyword (`query`) or `importedOnly`; paged, at most 100 per page.
- `asset_discovery_projects_list` - projects, as import targets.

Change state:

- `asset_discovery_run_start` - create a collection run for one authorized scope (`provider` `hunter` or `fofa`, `scope`, optional `name`). It launches a collector Agent that uses the user's provider credential and quota.
- `asset_discovery_run_stop` - stop a run that is starting or running.
- `asset_discovery_assets_import` - import pool assets (`assetIds`, at most 200) into a project (`projectId`). They become part of that project's assets.
- `asset_discovery_run_delete` - delete a finished run **and every asset that run collected into the pool**. Irreversible, and those assets cost provider quota to collect; assets already imported into a project are not affected. Stop a running run first.
- `asset_discovery_assets_delete` - delete the requested assets from the pool. Irreversible; assets already imported into a project stay there. The result's `requested` is how many ids you sent, not how many existed.

Also available: `asset_hunter_query` and `asset_fofa_query` query one scope
directly without creating a run or touching the pool, and
`asset_candidates_normalize` validates and deduplicates candidate values.

## Typical flow

1. Confirm the scope and provider with the user. State both in your answer.
2. `asset_discovery_run_start`, then poll `asset_discovery_run_get` with a pause between calls. A run is finished when its status is `done`, `failed` or `cancelled`; `failed` carries `failureCode` and `failureMessage`. Report a failed run as failed, do not treat a partial pool as a complete result.
3. `asset_discovery_assets_list` with the run's `runId` to review what was found. Page with `offset`/`limit` instead of asking for everything at once.
4. Import only assets that match the authorized scope: choose the project from `asset_discovery_projects_list`, then `asset_discovery_assets_import`. Check `created`, `skipped`, `failed` and `errors` in the answer.
5. Delete only what the user asked to delete. Before `asset_discovery_run_delete`, call `asset_discovery_assets_list` with the run's `runId`, tell the user how many pool assets will go with it, and get their consent. Never delete or import in bulk on your own judgment.

A `scope` takes one scope per line; text after `#` on a line is ignored and not
passed to the collector. Credentials are never tool arguments or output fields. Start with small
pages, and tell the user which tool calls changed state.
