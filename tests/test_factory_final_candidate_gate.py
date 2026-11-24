from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARM_WORKFLOW = ROOT / ".github" / "workflows" / "arm-generated-marketplace-final-merge.yml"
FINAL_WORKFLOW = ROOT / ".github" / "workflows" / "final-merge-generated-marketplace-pr.yml"
SELECTED_FINALIZER_WORKFLOW = ROOT / ".github" / "workflows" / "finalize-selected-generated-marketplace-pr.yml"
ADOPTION_WORKFLOW = ROOT / ".github" / "workflows" / "adopt-first-party.yml"


class FactoryFinalCandidateGateWorkflowTests(unittest.TestCase):
    def test_retained_sidecar_refresh_is_a_pending_factory_candidate(self) -> None:
        workflow = ARM_WORKFLOW.read_text(encoding="utf-8")
        # Both the event branch and every same-repository Factory PR with a
        # shared head SHA must identify the generated repair, even if that
        # Factory PR was closed without merging. The commit-association API
        # omits such closed PRs before default-branch inclusion, so this must
        # use the complete main-targeting PR inventory. Otherwise an ordinary
        # same-SHA PR could overwrite its required pending status with success.
        self.assertGreaterEqual(workflow.count("xsec-marketplace/refresh-retained-sidecar-"), 2)
        self.assertIn('pulls?state=all&base=main&per_page=100', workflow)
        self.assertIn('any(.[][]; .head.sha == $sha and .head.repo.full_name == $repo', workflow)
        self.assertNotIn('commits/${PR_HEAD_SHA}/pulls', workflow)
        self.assertIn("factory_generated=true", workflow)
        self.assertIn("state=pending", workflow)
        # Both stages are privileged Factory changes. The arm
        # workflow must keep an ordinary same-SHA PR from overwriting either
        # candidate's required pending finalizer status.
        self.assertGreaterEqual(workflow.count("xsec-marketplace/stage-first-party-adoption-"), 2)

    def test_release_shaped_content_is_pending_even_on_an_ordinary_branch(self) -> None:
        workflow = ARM_WORKFLOW.read_text(encoding="utf-8")
        # A Factory change may be cherry-picked and followed by an empty commit
        # on a normally named branch, producing a new SHA with no historical
        # Factory PR association. The trusted pull_request_target workflow may
        # read GitHub's authenticated file inventory, but must never check out
        # or execute that PR's files merely to make this safety classification.
        self.assertIn('pulls/${PR_NUMBER}/files?per_page=100', workflow)
        self.assertIn('repos/${REPOSITORY}/pulls/${PR_NUMBER}', workflow)
        self.assertIn('changed_file_count=', workflow)
        self.assertIn('returned_file_count=', workflow)
        self.assertIn('factory_content=true', workflow)
        self.assertIn('def release_index:', workflow)
        self.assertIn('def release_sidecar:', workflow)
        self.assertIn('def factory_document:', workflow)
        self.assertIn('any(.[][]; [.filename, (.previous_filename? // "")]', workflow)
        self.assertIn("git/trees/" + "$" + "{PR_BASE_SHA}?recursive=1", workflow)
        self.assertIn("gitlink_changed", workflow)
        self.assertIn('|| { [ "$factory_content" = "true" ]', workflow)
        self.assertIn('|| { [ "$gitlink_changed" = "true" ]', workflow)
        self.assertIn("disabled_subproject_retirement", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("never checks out or executes PR content", workflow)
        self.assertNotIn("actions/checkout", workflow)

    def test_disabled_subproject_retirement_needs_a_trusted_disabled_registry_entry(self) -> None:
        workflow = ARM_WORKFLOW.read_text(encoding="utf-8")

        # Removing an inactive source checkout is maintenance, but only after
        # the trusted base Registry proves every removed Gitlink is disabled
        # first-party identity. Additions, revision changes, release records
        # and active subprojects stay on the protected Finalizer path.
        for required_rule in (
            "missing trusted Factory registry",
            "disabled_subproject_retirement=false",
            ".trustTier == \"first-party\"",
            ".status == \"disabled\"",
            "($added | length == 0)",
            "all($head_gitlinks[]; $base_by_path[.path] == .sha)",
            "($factory_files | index(\".gitmodules\") != null)",
        ):
            with self.subTest(required_rule=required_rule):
                self.assertIn(required_rule, workflow)

    def test_registry_metadata_uses_the_source_gate_without_release_finalization(self) -> None:
        arm = ARM_WORKFLOW.read_text(encoding="utf-8")
        freshness = (ROOT / ".github" / "workflows" / "verify-generated-marketplace-publication.yml").read_text(encoding="utf-8")

        self.assertIn('registry_only="$(printf', arm)
        self.assertIn('[ "$registry_only" != "true" ]', arm)
        self.assertEqual(freshness.count('marketplace_paths" = ".xsec-factory/official-registry.json"'), 2)

    def test_final_gate_revalidates_narrow_adoption_and_sidecar_candidates(self) -> None:
        workflow = FINAL_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("xsec-marketplace/stage-first-party-adoption-*", workflow)
        self.assertIn("Adoption is a two-step non-release transition", workflow)
        self.assertIn("staging PR adds one unsigned assertion", workflow)
        self.assertIn("activation PR later adds only the matching sidecar", workflow)
        self.assertIn("xsec-marketplace/refresh-retained-sidecar-*", workflow)
        self.assertIn('elif [ "$kind" = "maintenance" ]; then', workflow)
        self.assertIn("--allow-unsigned-active-release-sidecars", workflow)
        self.assertIn("(.promotions // [])[]", workflow)
        self.assertIn("beta-smoke-ready", workflow)
        self.assertIn("Only external Beta or signed batch branches may reopen a no-pointer Desktop smoke cycle", workflow)
        self.assertIn("--verify-first-party-adoption-candidate", workflow)
        self.assertIn("--verify-retained-sidecar-refresh-candidate", workflow)
        self.assertIn("--verify-retained-release-signature --retained-release-plugin-id", workflow)
        self.assertIn("exact PR head has no successful Factory source gate", workflow)
        self.assertIn("Require a current source gate", workflow)
        self.assertIn("Require source-gated automatic finalization", workflow)
        self.assertIn("require_current_review_state() {\n            :", workflow)

    def test_release_pr_is_smoked_on_desktop_before_it_can_merge(self) -> None:
        workflow = FINAL_WORKFLOW.read_text(encoding="utf-8")
        selected = SELECTED_FINALIZER_WORKFLOW.read_text(encoding="utf-8")
        smoke = workflow.index("Smoke the exact release head on every Desktop platform before merging")
        recheck = workflow.index("Require the smoked head and main to be unchanged")
        merge = workflow.index("Merge the exact revalidated head with the isolated Finalizer App")
        # The smoke and its recheck precede the Finalizer token and the merge:
        # a merged release is visible to every Desktop at once.
        self.assertLess(smoke, recheck)
        self.assertLess(recheck, merge)
        self.assertLess(workflow.index("Create a repository-scoped Finalizer App token"), merge)
        self.assertLess(recheck, workflow.index("Create a repository-scoped Finalizer App token"))
        step = workflow[smoke:recheck]
        self.assertIn("event_type:\"xsec_official_marketplace_candidate\"", step)
        self.assertIn("candidate_branch:$branch", step)
        self.assertIn("XSEC_DESKTOP_REPOSITORY_DISPATCH_TOKEN", step)
        self.assertIn('[ "$waited" -lt 10800 ]', step)
        # Only a smoke that ran and failed closes the PR; every other outcome
        # leaves it open for a later trigger.
        self.assertIn("failure) reject_release", step)
        self.assertIn('*) echo "The Desktop smoke concluded ${conclusion}', step)
        for branch in ("external-version-", "publish-"):
            self.assertIn(f"startsWith(steps.pr.outputs.head_ref, 'xsec-marketplace/{branch}')", step + workflow[recheck:merge])
        self.assertNotIn("default-set-", step)
        # Closing the PR needs write access in the reusable workflow and its caller.
        self.assertIn("pull-requests: write", workflow.split("jobs:", 1)[0])
        self.assertIn("pull-requests: write", selected.split("jobs:", 1)[0])

    def test_every_generated_candidate_skips_bot_review_requests(self) -> None:
        workflows = (
            "publish.yml",
            "stage-first-party-adoption.yml",
            "adopt-first-party.yml",
            "refresh-retained-sidecars.yml",
            "migrate-factory-layout-sidecars.yml",
        )
        for workflow_name in workflows:
            workflow = (ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
            with self.subTest(workflow=workflow_name):
                self.assertNotIn("@coderabbitai review", workflow)

    def test_adoption_signer_uses_the_retained_protected_pre_staging_revision(self) -> None:
        workflow = ADOPTION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(".legacy.factoryRevision", workflow)
        self.assertIn('git merge-base --is-ancestor "$baseline_revision" HEAD', workflow)
        self.assertIn('git cat-file -e "${baseline_revision}^{commit}"', workflow)
        self.assertNotIn("git log --diff-filter=A", workflow)

    def test_final_gate_never_turns_the_arm_owned_candidate_status_green(self) -> None:
        workflow = FINAL_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("The arm workflow owns factory-final-merge-gate", workflow)
        self.assertNotIn("state=success -f context=factory-final-merge-gate", workflow)
        self.assertNotIn("statuses: write", workflow)
        self.assertNotIn("trap ", workflow)
        self.assertNotIn("XSEC_MARKETPLACE_PUBLISH_TOKEN", workflow)
        self.assertIn("XSEC_MARKETPLACE_FINALIZER_APP_ID", workflow)
        self.assertIn("XSEC_MARKETPLACE_FINALIZER_APP_PRIVATE_KEY", workflow)
        self.assertIn("permission-contents: write", workflow)
        # GitHub's merge endpoint needs Contents:write. Requesting a separate
        # Pull requests:write grant would widen the short-lived bypass token
        # without enabling its one exact-head merge call.
        self.assertNotIn("permission-pull-requests: write", workflow)
        self.assertIn("-f sha=\"$HEAD_SHA\"", workflow)

    def test_finalizer_token_follows_the_last_external_source_sha_check(self) -> None:
        workflow = FINAL_WORKFLOW.read_text(encoding="utf-8")
        merge_step = workflow.split(
            "- name: Merge the exact revalidated head with the isolated Finalizer App", 1
        )[1]
        source_check = "while IFS= read -r source; do"
        token_assignment = 'GH_TOKEN="${{ steps.finalizer.outputs.token }}" gh api --method PUT'

        # The short-lived bypass token must not exist in the source-read loop.
        # A source beta/main push while the token action runs is therefore
        # detected by this second proof, immediately before the only PUT that
        # receives the token. Private registered sources use the separate
        # exact-repository Source App reader; the Finalizer App never crosses
        # that repository boundary.
        self.assertNotIn("GH_TOKEN: ${{ steps.finalizer.outputs.token }}", workflow)
        self.assertIn("XSEC_MARKETPLACE_SOURCE_APP_ID", workflow)
        self.assertIn("XSEC_MARKETPLACE_SOURCE_APP_PRIVATE_KEY", workflow)
        self.assertIn("permission-contents: read", workflow)
        self.assertIn("SOURCE_TOKEN: ${{ steps.source-token.outputs.token }}", merge_step)
        self.assertIn(
            '-c http.https://github.com/.extraheader= \\\n              -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $token_header"',
            merge_step,
        )
        self.assertIn('http.https://github.com/.extraheader=AUTHORIZATION: basic $token_header', merge_step)
        self.assertEqual(
            workflow.count(
                '-c http.https://github.com/.extraheader= \\\n              -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $token_header"'
            ),
            3,
        )
        self.assertIn(source_check, merge_step)
        self.assertIn('factory-publication-sources.json', merge_step)
        self.assertIn(token_assignment, merge_step)
        self.assertIn(
            "advanced or could not be read immediately before the Finalizer merge; it remains pending.",
            merge_step,
        )
        self.assertLess(merge_step.index(source_check), merge_step.index(token_assignment))
        review_check = "require_current_review_state"
        self.assertIn(review_check, merge_step)
        self.assertLess(merge_step.rindex(review_check), merge_step.index(token_assignment))
        self.assertNotIn("steps.finalizer.outputs.token", merge_step[: merge_step.index(token_assignment)])
        self.assertEqual(merge_step.count('GH_TOKEN="${{ github.token }}"'), 4)
        self.assertEqual(merge_step.count('GH_TOKEN="${{ steps.finalizer.outputs.token }}"'), 1)
        self.assertEqual(merge_step.count("gh api graphql --paginate --slurp"), 2)
        self.assertEqual(merge_step.count("statuses?per_page=100"), 1)
        self.assertEqual(merge_step.count("gh api --method PUT"), 1)

    def test_final_gate_scopes_source_reader_to_exact_owner_repositories(self) -> None:
        workflow = FINAL_WORKFLOW.read_text(encoding="utf-8")
        source_token = workflow.split("- name: Create a narrowly scoped read-only Source App token", 1)[1].split(
            "- name: Authenticate each registered source branch before final merge", 1
        )[0]

        self.assertIn("one Factory candidate cannot span multiple source owners", workflow)
        self.assertIn("repositories:($repositories | map(split(\"/\")[1]) | unique | join(\",\"))", workflow)
        self.assertIn("owner: ${{ steps.publication.outputs.source_owner }}", source_token)
        self.assertIn("repositories: ${{ steps.publication.outputs.source_repositories }}", source_token)
        self.assertIn("permission-contents: read", source_token)
        self.assertNotIn("permission-contents: write", source_token)

    def test_beta_source_gate_rechecks_both_registered_branch_heads(self) -> None:
        workflow = FINAL_WORKFLOW.read_text(encoding="utf-8")
        freshness = (ROOT / ".github" / "workflows" / "verify-generated-marketplace-publication.yml").read_text(encoding="utf-8")

        # Beta provenance alone is insufficient: each generated Beta candidate
        # binds the compared source-main head, and both unprotected early gate
        # and protected finalizer read it as an independently exact source ref.
        self.assertIn("(.main_source // empty)", workflow)
        self.assertIn("(.main_source // empty)", freshness)

    def test_finalizer_requires_the_exact_pr_source_gate(self) -> None:
        workflow = FINAL_WORKFLOW.read_text(encoding="utf-8")

        # The candidate source gate runs on pull_request. Accepting a
        # workflow_dispatch run would not prove that the exact PR content
        # received the reviewed Factory gate.
        self.assertIn(
            "actions/workflows/validate.yml/runs?head_sha=${",
            workflow,
        )
        self.assertIn("&event=pull_request&per_page=100", workflow)
        self.assertNotIn("&event=workflow_dispatch&per_page=100", workflow)

        # The Finalizer runs while the candidate remains open, when GitHub
        # returns its pull_requests association.
        self.assertIn("--argjson pull_number", workflow)
        self.assertIn("any(.pull_requests[]?; .number == $pull_number)", workflow)

    def test_finalizer_uses_source_gates_without_review_state(self) -> None:
        workflow = FINAL_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Require a current source gate", workflow)
        self.assertIn("Require source-gated automatic finalization", workflow)
        self.assertIn("require_current_review_state() {\n            :", workflow)

    def test_protected_finalizer_runs_after_the_unprivileged_selector(self) -> None:
        selector = (ROOT / ".github" / "workflows" / "auto-finalize-generated-marketplace-pr.yml").read_text(encoding="utf-8")
        workflow = SELECTED_FINALIZER_WORKFLOW.read_text(encoding="utf-8")

        # The selector has no reusable final-merge job; a workflow_run from
        # protected default-branch configuration finds one current-baseline
        # candidate before handing it to the production finalizer.
        self.assertNotIn("final-revalidate-and-merge:", selector)
        self.assertIn("workflows: [Automatically finalize generated Marketplace PR]", workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertNotIn("github.event.workflow_run.head_branch", workflow)
        self.assertIn("Require the preceding unprivileged selector to have run", workflow)
        self.assertIn("actions/runs/${UPSTREAM_RUN_ID}/jobs?per_page=100", workflow)
        self.assertIn('git/ref/heads/main" --jq .object.sha', workflow)
        self.assertIn('.base.sha == $main_sha', workflow)
        self.assertIn('test("^xsec-marketplace/(publish-|batch-|default-set-|external-beta-', workflow)
        self.assertIn("ready_matches='[]'", workflow)
        self.assertIn("done < <(printf '%s' \"$matches\" | jq -rc '.[]')", workflow)
        self.assertIn("expected one ready current-baseline generated PR", workflow)
        self.assertIn("refs/heads/main", FINAL_WORKFLOW.read_text(encoding="utf-8"))
        self.assertIn("source-freshness-gate", workflow)


if __name__ == "__main__":
    unittest.main()
