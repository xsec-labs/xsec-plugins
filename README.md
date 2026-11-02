# XSEC plugin marketplace

XSEC Marketplace Factory registers plugin source repositories and publishes deterministic,
immutable `.xsec-plugin` artifacts. Plugin development lives in independent source
repositories; Factory keeps reviewed registration, package snapshots, release indexes
and source provenance.

## Plugin updates

For registered plugins connected to the source webhook, push the updated plugin source
and version to its registered branch. Factory automatically pulls the latest source,
builds the package and updates the Marketplace. Desktop discovers the published update.

## Registering a new plugin by hand

Updates of plugins that are already registered are not affected (see above). Registering a
**new** plugin used to be driven from Desktop's Marketplace Factory screens. The Go Desktop
does not ship them (they return `FEATURE_DEFERRED`, "此功能暂未提供"), so after the cut-over
a maintainer registers a new plugin here, by hand. Registration is not a permission grant:
users still confirm the plugin's permissions when they install it.

1. **Prepare the source repository.** The Git root is the package root (`plugin.json`,
   `.codex-plugin/plugin.json` and, where it applies, `com.xsec.desktop/`); do not nest
   `plugins/<id>/`. Create the `beta` and `main` branches that the registry will pin, and
   bump the version for the revision you want published. The plugin ID must be an external
   one: `com.xsec.*` is reserved.
2. **Open a registration PR against this repository.** Add one entry to
   `.xsec-factory/official-registry.json` (keep `plugins` sorted by `pluginId`, one entry
   per ID):

   ```json
   {
     "pluginId": "io.example.plugin",
     "trustTier": "external",
     "source": {
       "repository": "owner/repository",
       "path": ".",
       "refs": {"beta": "refs/heads/beta", "stable": "refs/heads/main"}
     },
     "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
     "category": "Security",
     "status": "active"
   }
   ```

   Check it locally before pushing, the same way `validate.yml` does:
   `python scripts/external_source_factory.py validate --allow-unsigned-publication-proofs --allow-unsigned-active-release-sidecars`
   (add `--baseline-root <checkout of main>` to compare against the current registry).
   The PR needs normal review: merging it is what lets the source repository use the
   protected publication workflows. Desktop used to open this PR with the commit message
   `chore(factory): register <pluginId>`; use the same message.
3. **Publish the first version.** Once the registry change is on `main`, either ask a Factory
   maintainer to connect the source webhook (then every push to the registered branch
   publishes, as in "Plugin updates"), or start the first publication yourself with the
   exact commit SHA of the source repository:

   ```sh
   gh workflow run publish.yml --repo xsec-labs/xsec-plugins \
     -f maintenance=release \
     -f plugin_id=io.example.plugin \
     -f source_sha=<40-character lowercase commit SHA on the registered branch>
   ```

   Running it needs permission to trigger workflows in `xsec-labs/xsec-plugins`.
   Native MCP sidecars additionally need `-f native_sidecars_source_sha=<xSecDesktop main SHA>`.
   Follow the generated Factory PR through the finalizer as described in
   [Development and publication](docs/plugin-development-release-lifecycle.md).
4. **Read the result back**: the new version in `.agents/plugins/marketplace.json`, then in
   Desktop after a refresh.

## Current release contract

Each SemVer identifies one immutable release. Desktop selects the highest compatible
version using the Host/API requirements and the current OS/architecture, verifies the
artifact SHA-256, and asks the user to confirm its permissions. Official and external
plugins use the same permission-confirmation model. Registry membership does not grant
runtime permissions.

Marketplace KMS/JWS signing was retired on 2026-09-20. Publication uses protected
Factory workflows, exact source revisions, immutable release records and artifact hashes.
Historical `beta`/`stable` fields remain in some schemas; they do not define a current
promotion requirement. Desktop installer/updater and Managed Skill signing have their
own contracts.

Plugins must support Windows, macOS and Linux. The native target matrix contains four
OS/architecture combinations: Windows x64, Linux x64, macOS arm64 and macOS x86_64.
Routine development, updates and publication do not require cross-platform Desktop Host
Smoke by default. Run source/package checks and verification appropriate to the change.
Optional Host acceptance is recorded separately from publication.

## Documentation

- [Development and publication](docs/plugin-development-release-lifecycle.md): current steps and evidence.
- [Registration and source ownership](docs/first-party-plugin-factory.md): Registry v2, package roots and retained history.
- [Local plugin development](docs/local-plugin-development.md): prepare local MCP binaries before Desktop development checks.
- [Agent Plugins runtime contract](docs/agent-plugins-runtime-contract.md): portable packages, native artifacts and runtime boundaries.
- [Migration playbook](docs/agent-plugins-migration-playbook.md) and [attack-path reference](docs/attack-path-agent-plugin-reference.md).
- [Plugin settings](docs/plugin-settings.md): settings schema, UI and data boundaries.
- [Finalizer ruleset](docs/factory-finalizer-ruleset-policy.md): exact-head merge and credential separation.
- [Optional Desktop Smoke](docs/desktop-remote-marketplace-smoke-contract.md): scope and reporting.
- [Custom Factory template](docs/marketplace-factory-template.md): separately versioned template and its compatibility constraints.

## Repository layout

- `.xsec-factory/official-registry.json`: reviewed source allowlist.
- `plugins/<id>/`: independent source checkouts for local development.
- `.xsec-factory/snapshots/<id>/`: generated package snapshots and release indexes.
- `.agents/plugins/marketplace.json`: Desktop discovery index.
- `.xsec-factory/official-publications/`: retained source provenance.
- `.github/workflows/`: protected publication, source validation and finalization.

Use the workflow definitions at the exact Factory revision being published. Generated
artifacts and historical release records are append-only; documentation cleanup must
not rewrite their bytes. Superseded operating procedures are available in Git history.
