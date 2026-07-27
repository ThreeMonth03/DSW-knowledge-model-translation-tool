# GitHub-only translation maintenance

## Authority

Git is the only translation authority. There is no active Weblate component.
Do not add a Localize URL as a placeholder.

The source KM is pinned by `knowledge_model.upstream_ref` in
`translation-config.yml`. The tooling is also pinned. Update either dependency
through a reviewed pull request.

## First bootstrap

After the first source KM release is available:

```shell
git clone https://github.com/{{TOOLING_REPOSITORY}} tooling-repo
git -C tooling-repo checkout {{TOOLING_REF}}
make -C tooling-repo install-dev
tooling-repo/.venv/bin/dsw-km-sync-github-release --repo-root .
```

The command downloads the exact `knowledge_model.upstream_ref` GitHub Release,
verifies its `.sha256` sidecar and package ID, creates an empty Git-managed
catalog, and builds the editable tree. No manual asset download is needed.

For a source KM update, change `upstream_ref`, `version`, and `bundle_path`
together in a pull-request branch, then run the same command. Translations are
carried only when the UUID, field, and English source text are unchanged.

## Routine edits

Edit only the Translation fenced blocks under `tree/`, then rebuild:

```shell
tooling-repo/.venv/bin/dsw-km-build-translation-repo --repo-root .
```

Commit the tree, catalog, review report, and build outputs together. Pull
requests rebuild them and fail if the checkout is not reproducible.

## Future Weblate cutover

If the DSW team later creates an official component, import the checked-in PO
once and switch authority in a dedicated cutover pull request. Never run Git
and Weblate as simultaneous writers.
