# Source initialization

The Factory source is maintained under `xsec-labs/xsec-plugins`. The registry
contains twelve first-party packages and the external `io.xsec.project-files`
package. The root package marker and submodule Gitlinks identify the new source
repositories and their initial immutable revisions.

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
