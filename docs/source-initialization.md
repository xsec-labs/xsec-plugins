# Source initialization

The Factory source is maintained under `xsec-labs/xsec-plugins`. The registry
contains the twelve first-party packages. The external `io.xsec.project-files`
package was never published and has been withdrawn from the allowlist (the Go
desktop does not provide a native view for it). The root package marker and
submodule Gitlinks identify the new source repositories and their initial
immutable revisions.

The initial marketplace index has an empty `plugins` list. Each package must
complete source materialization, adoption, artifact construction, provenance,
and protected publication before discovery can advertise it. The snapshots
directory is initialized for that workflow; its placeholder is not a package.

JWT Analysis retains its registered first-party trust tier and `AVAILABLE`
installation policy. Its static source mapping is exactly
`xsec-labs/xsec-plugin-jwt-analysis`. Registry edits cannot authorize any other
repository or introduce an arbitrary first-party plugin.

The historical root-layout transition verifier retains the package set for
that one-time transition. Current registry validation checks the current root
package marker, registered source paths, Gitlinks, and submodule URLs.

Source validation does not establish marketplace availability or native
artifact acceptance. Publication requires fresh evidence from the new
repositories and workflows. Existing immutable releases remain in the private
migration audit backup and are not represented as new publication evidence.

Until the first protected publication, the source gate runs with `--allow-pending-publication`. That flag accepts an empty marketplace index only while no package snapshot is retained. Unit tests that read unpublished snapshots are skipped by `tests/publication_gate.py` and run again once snapshots exist. Three tests need first-party submodules (`plugins/<id>`), and all three need the `binary-analysis` submodule. They run only in a checkout that includes it. No CI job does that today, so they stay skipped in CI until a CI job checks out that submodule. Owner: Claude (gate-fix session for PR #6), assigned by the project coordinator.

First-publication checklist: remove `--allow-pending-publication` from `validate.yml`. Also remove the `requires_publication` decorators and the `skip: awaitingPublication` options, so the publication tests run unconditionally, and confirm the unit run reports no publication skips. Until then, a PR that deletes every snapshot and empties the index passes the source gate. Owner: Claude (gate-fix session for PR #6), assigned by the project coordinator.
