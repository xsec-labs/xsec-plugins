# com.xsec.asset-discovery

This is the public source repository for `com.xsec.asset-discovery`. It was materialized from
the immutable signed XSEC Marketplace release during the first-party source
migration. Develop on `beta`; merge reviewed, tested changes to `main` for the
Stable source line.

Marketplace artifacts, release indexes, signatures, and Factory adoption proof
remain in [xsec-labs/xsec-plugins](https://github.com/xsec-labs/xsec-plugins).
This source repository never stores Factory credentials or KMS material.

Source repository: <https://github.com/xsec-labs/xsec-plugin-asset-discovery>

## Collector prompts

`prompts/collector-system.md` is the collector agent's system prompt and `prompts/collector-goal.md` is its goal template (the single `{scope}` placeholder is replaced with the collection scope). xSec Desktop reads both files from the installed plugin when a collection starts and refuses to start when either is missing or invalid; it has no built-in copy. Keep the host tool names `xsec_asset_import`, `xsec_collection_finalize` and `xsec_product_issue_submit` in the system prompt; the manifest test checks them. The prompts are read again at the start of every collection, so a plugin upgrade changes the next collection without restarting Desktop. Prompt changes ship as a new plugin version; Desktop never edits the installed files. A prompt that fails to load is reported in the collection's error message, naming the file.
