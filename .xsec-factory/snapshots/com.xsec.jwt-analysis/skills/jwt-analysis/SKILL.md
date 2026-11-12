---
name: jwt-analysis
description: Create and interpret project-scoped JWT security analysis jobs in XSEC Desktop.
---

# XSEC JWT Analysis

Use this skill when an authorized assessment discovers a JWT in a response, request, cookie, browser storage, local file, or user-provided input. The existing `xsec-jwt-security` skill remains the testing methodology; this skill handles XSEC job creation, evidence, and workspace presentation.

## Create a job

1. Confirm the token or traffic belongs to the active authorized project. Never infer a target from token claims or an untrusted `jku`, `jwk`, or `kid` value.
2. Call `jwt_analysis_create` with one of `token`, `traffic_ref`, `request_file`, `project_file`, or `batch`. Use `profile: "full"` when a supplied, authorized HTTP baseline is present; otherwise use `passive`. Active probes run only against that explicit baseline.
3. For a `traffic_ref`, pass only the captured `flow_id`; Desktop checks its project, scope, and task binding. For a project file, pass a workspace-relative path; Desktop resolves it within the bound project.
4. Call core `xsec_workspace_reveal` with `plugin_id: "jwt-analysis"`, the active `project_id` as `entity_id`, and `dock: "side"` so the project dashboard opens.
5. Poll `jwt_analysis_get` and `jwt_analysis_events` until completion, cancellation, or an explicit error. Do not automatically retry; call `jwt_analysis_retry` only when asked to retry a failed job.

## Interpret results

- `vulnerable`: the supplied baseline marker was present in a successful anomalous-token response, or a signing key was verified against the JWT signature.
- `candidate`: the variant response differed from the baseline but no user-supplied canary confirmed acceptance.
- `not_vulnerable`: the tested dictionary did not match or the server rejected the tested variant.
- `not_applicable`: the token algorithm does not meet the test's applicability conditions.
- `not_run`: a prerequisite is missing, such as an explicit baseline or disabled listener.
- `blocked`: a baseline failure prevented dependent active tests.
- `error`: a concrete parsing, dictionary, network, or Sidecar failure occurred.

Do not report a CVE solely because a test is `candidate`. Review the exact request/response evidence using `jwt_analysis_evidence_get`; evidence is redacted by default. Preserve the test variant, baseline comparison, and evidence ID in conclusions.

## Promote a finding

Keep findings as plugin candidates. After validating the evidence and confirming severity, call core `xsec_finding_upsert` with the project context and evidence references. Do not create a formal finding for a `candidate`, `not_run`, `blocked`, or `error` result without independent confirmation.

## Scope and secrets

The Sidecar never accepts caller-supplied project IDs. Traffic and project-file references are resolved by Desktop Host. Active requests are bounded to the supplied origin, do not follow redirects, validate TLS by default, use the configured request rate, and stop on explicit cancellation. External JWKS listeners are disabled by default. Do not expose full JWTs, cookies, or recovered secrets in chat; the dashboard masks secrets and evidence retrieval redacts them unless the user explicitly requests sensitive evidence.
