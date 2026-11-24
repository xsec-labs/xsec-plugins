"""Static contracts for generated Marketplace PR finalization and publication."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
AUTO_FINALIZER = ROOT / ".github" / "workflows" / "auto-finalize-generated-marketplace-pr.yml"
SELECTED_FINALIZER = ROOT / ".github" / "workflows" / "finalize-selected-generated-marketplace-pr.yml"
FINALIZER = ROOT / ".github" / "workflows" / "final-merge-generated-marketplace-pr.yml"
SOURCE_PREFLIGHT = ROOT / ".github" / "workflows" / "first-party-source-preflight.yml"


class MarketplaceBatchAutomationTests(unittest.TestCase):
    def test_default_set_maintenance_is_automatic_and_source_batch_stays_twelve_plugins(self) -> None:
        registry = json.loads((ROOT / ".xsec-factory" / "official-registry.json").read_text(encoding="utf-8"))
        marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        statuses = {entry["pluginId"]: entry["status"] for entry in registry["plugins"]}
        active = [plugin_id for plugin_id, status in statuses.items() if status == "active"]
        market_ids = {entry["name"] for entry in marketplace["plugins"]}

        self.assertEqual(len(active), 12)
        self.assertNotEqual(statuses.get("com.xsec.project-workspace"), "active")
        self.assertNotIn("com.xsec.project-workspace", market_ids)
        publish = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        self.assertFalse((ROOT / ".github" / "workflows" / "disable-host-owned-project-workspace.yml").exists())
        self.assertIn("push:\n    branches: [main]", publish)
        self.assertIn('[ "$EVENT_NAME" = "push" ]', publish)
        self.assertIn("maintenance=align_desktop_defaults", publish)
        self.assertIn("xsec-marketplace/default-set-", publish)

    def test_single_source_publication_retains_untargeted_native_betas(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")

        for rule in (
            'TARGET_PLUGIN_ID: ${{ steps.external-request.outputs.plugin_id }}',
            '[ "$EXTERNAL" = "true" ] && [ "$native_plugin" != "$TARGET_PLUGIN_ID" ]',
            "reconcile-retained-native-beta",
            "--native-sidecar-source-revision-for",
            "Untargeted native plugin $native_plugin does not reproduce its retained Beta.",
            ".inputs | fromjson | if type == \"array\" then . else error(\"retained sidecar inputs are not an array\") end",
            "done < <(printf '%s' \"$retained_inputs\" | jq -rc '.[]')",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, workflow)

    def test_only_successful_exact_generated_prs_enter_the_automatic_finalizer(self) -> None:
        workflow = AUTO_FINALIZER.read_text(encoding="utf-8")
        selected_finalizer = SELECTED_FINALIZER.read_text(encoding="utf-8")
        finalizer = FINALIZER.read_text(encoding="utf-8")
        for branch in (
            "xsec-marketplace/batch-*",
            "xsec-marketplace/default-set-*",
            "xsec-marketplace/external-beta-*",
            "xsec-marketplace/external-stable-*",
        ):
            self.assertIn(branch, workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertIn("Verify generated Marketplace publication merge", workflow)
        self.assertIn("startsWith(github.event.workflow_run.head_branch, 'xsec-marketplace/')", workflow)
        self.assertIn("checks: read", workflow)
        self.assertIn("source-freshness-gate", workflow)
        self.assertIn('.name == "source-freshness-gate"', workflow)
        self.assertIn("expected one open exact-head generated PR", workflow)
        self.assertIn(".head.ref == $branch", workflow)
        self.assertIn('*) echo "eligible=false" >> "$GITHUB_OUTPUT"; exit 0 ;;', workflow)
        self.assertNotIn("final-revalidate-and-merge:", workflow)
        self.assertIn("workflows: [Automatically finalize generated Marketplace PR]", selected_finalizer)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", selected_finalizer)
        self.assertNotIn("github.event.workflow_run.head_branch", selected_finalizer)
        self.assertIn('git/ref/heads/main" --jq .object.sha', selected_finalizer)
        self.assertIn('.base.sha == $main_sha', selected_finalizer)
        self.assertIn('test("^xsec-marketplace/(publish-|batch-|default-set-|external-beta-', selected_finalizer)
        self.assertIn("source-freshness-gate", selected_finalizer)
        self.assertIn('.name == "source-freshness-gate"', selected_finalizer)
        self.assertIn("ready_matches='[]'", selected_finalizer)
        self.assertIn("expected one ready current-baseline generated PR", selected_finalizer)
        self.assertIn("needs.select-exact-generated-pr.result == 'success'", selected_finalizer)
        self.assertIn("outputs.eligible == 'true'", selected_finalizer)
        self.assertIn("!cancelled() && needs.select-exact-generated-pr.result == 'success'", selected_finalizer)
        self.assertIn("group: xsec-marketplace-final-selector-main", selected_finalizer)
        self.assertIn("group: xsec-marketplace-final-merge-main", finalizer)
        self.assertNotIn("group: xsec-marketplace-final-merge-main", selected_finalizer)
        self.assertNotIn("always()", selected_finalizer)
        self.assertIn("workflow_call:", finalizer)
        self.assertIn("Require source-gated automatic finalization", finalizer)
        self.assertIn("workflow_dispatch|workflow_call|workflow_run", finalizer)
        self.assertIn("xsec-marketplace/batch-*", finalizer)

    def test_shared_preflight_preserves_each_source_repositories_real_ci_contract(self) -> None:
        workflow = SOURCE_PREFLIGHT.read_text(encoding="utf-8")
        self.assertIn("Validate the root plugin package, release identity, and whitespace", workflow)
        self.assertIn('manifest="plugin.json"', workflow)
        self.assertIn('codex_manifest=".codex-plugin/plugin.json"', workflow)
        self.assertIn("Nested plugin packages are not supported", workflow)
        self.assertIn('[ -f "$codex_manifest" ]', workflow)
        self.assertIn("git diff --check HEAD^", workflow)
        self.assertNotIn("pnpm install", workflow)
        self.assertNotIn("pnpm test", workflow)


if __name__ == "__main__":
    unittest.main()
