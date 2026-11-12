# com.xsec.workspace.approvals

This is the public source repository for `com.xsec.workspace.approvals`. It was materialized from
the immutable signed XSEC Marketplace release during the first-party source
migration. Develop on `beta`; merge reviewed, tested changes to `main` for the
Stable source line.

Marketplace artifacts, release indexes, signatures, and Factory adoption proof
remain in [xsec-labs/xsec-plugins](https://github.com/xsec-labs/xsec-plugins).
This source repository never stores Factory credentials or KMS material.

Source repository: <https://github.com/xsec-labs/xsec-plugin-approvals>

## Source validation

Run `npm ci && npm run validate` before opening a pull request. The check validates
the full XSEC Desktop extension against the pinned Desktop schema snapshot, its
Frontend API and permission contract, all plugin-tree paths and entrypoints, and
the marketplace descriptor. It also syntax-checks the production frontend.

The schema snapshot is sourced from `desktop/packages/plugin-api/schemas/` in
the matching XSEC Desktop source revision. Update it together with the semantic
checks whenever Desktop changes the plugin contract.

## Release provenance

Factory records the exact Beta and Stable source revisions with each immutable
Approvals release. Published source revisions include the declared frontend
artifact validated by the source-validation command.

## Host boundary

The root manifest uses Agent Plugins v1 with a `com.xsec.desktop` schema v2
extension. Approvals remains a Host package: its five frontend methods read
Desktop-owned approval pages, details and statistics, and read or write plugin
settings.

The UI requests up to 40 summaries per page from `xsec.approvals.list`,
which returns `{ rows, nextCursor }`. The UI forwards the cursor as `beforeCreatedAt` and `beforeId`.
Opening a record loads `xsec.approvals.detail` in UTF-8 chunks, retaining the
Host revision until the full record has been received. Session changes cancel
in-flight list and detail rendering. Approval decisions, policy evaluation and
audit records remain under the Desktop session and capability boundary; this package has no portable MCP
server, Skill or `agentTools` declaration.

## Live Host regression

Start Desktop Debug with `XSEC_DEBUG_DATA_ROOT` pointing to a disposable directory
under the OS temporary directory. Attach this source in the plugin development
workbench, reload it, and connect `@hypothesi/tauri-mcp-cli` to that Host.

```sh
rtk python3 scripts/approval-host-fixture.py seed "$APPROVAL_TEST_DATABASE" > /tmp/approval-host-options.json
rtk env TAURI_MCP_CLI="$TAURI_MCP_CLI" node scripts/run-live-host.mjs /tmp/approval-host-options.json
rtk node "$TAURI_MCP_CLI" webview-execute-js --script 'window.approvalHostRegression'
rtk python3 scripts/approval-host-fixture.py remove "$APPROVAL_TEST_DATABASE"
```

`APPROVAL_TEST_DATABASE` is the initialized Debug Host SQLite database. Seeding
adds 85 same-timestamp records plus one record in another session; removal only
matches those two fixture sessions. Wait for the result to contain `passed: true`.
The check loads the active frontend through `plugin_frontend_load`, runs it in the
native WebView, and sends every data request through the real `plugin_frontend_rpc`.
It covers pagination, UTF-8 detail chunks, filters, session changes, access rejection,
explicit error recovery, remounting, and settings reads and saves. Separately open the sandbox
workspace tool and inspect its native appearance and development logs.
