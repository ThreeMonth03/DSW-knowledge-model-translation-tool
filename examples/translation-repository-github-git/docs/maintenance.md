# Pinned-Git translation maintenance

## Authority

Git is the only translation authority. There is no active Weblate component.
Do not add a Localize URL as a placeholder.

The source KM is pinned by full commit SHA and bundle path in
`translation-config.yml`. The tooling is also pinned. Update either dependency
through paired source and translation pull-request branches.

## First bootstrap

Check out the exact source and tooling commits recorded in
`translation-config.yml`. To seed unchanged strings from an earlier catalog:

```shell
tooling-repo/.venv/bin/dsw-km-sync-git-source \
  --repo-root . \
  --source-repo ../source-repo \
  --seed-po ../previous-translation/sources/catalog.po
```

The command rejects a source checkout whose HEAD differs from the pinned SHA,
validates the official KM schema and package identity, carries only unchanged
translations, and builds the editable tree and translated KM.

For review feedback, amend the source commit first, update `upstream_ref`, rerun
the command, update changed translations, and amend this repository's commit.

## Routine edits

Edit only the Translation fenced blocks under `tree/`, then rebuild:

```shell
tooling-repo/.venv/bin/dsw-km-build-translation-repo --repo-root .
```

Commit the tree, catalog, review report, and build outputs together. Pull
requests rebuild them and fail if the checkout is not reproducible.

Pull-request CI uploads a 14-day review artifact named
`{{TRANSLATED_ASSET_STEM}}-<commit SHA>`. An immutable `v<version>` tag creates
a GitHub Release containing the versioned KM and PO, a stable
`{{TRANSLATED_ASSET_STEM}}.km` alias, checksums, and the pinned
`translation-config.yml` provenance record. Releases below `1.0.0` are marked
as pre-releases. Workflow artifacts are for review; GitHub Releases are the
long-term archive.

## Release cutover

After the source version is approved and published, change
`workflow.source` from `git` to `release`, remove
`knowledge_model.upstream_bundle_path`, replace `upstream_ref` with the
immutable release ref, synchronize with `dsw-km-sync-github-release`, and
refresh the managed scaffold. Do not keep both source modes active.

## Future Weblate cutover

If the DSW team later creates an official component, import the checked-in PO
once and switch authority in a dedicated cutover pull request. Never run Git
and Weblate as simultaneous writers.
