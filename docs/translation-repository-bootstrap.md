# Translation Repository Bootstrap

Use this page when creating a new dedicated translation repository from the
tooling repository.

## What Bootstrap Does

The bootstrap command turns an empty checkout into a working translation
repository:

- writes `translation-config.yml` from a template;
- renders repository docs and GitHub Actions workflows from the config;
- downloads the configured KM bundle from the DSW Registry;
- downloads the current Localize/Weblate PO;
- expands the PO/KM pair into `tree/`;
- builds `builds/final_translated.po` and `builds/final_translated.km`;
- writes review output under `reviews/`.

It does not commit, push, configure GitHub secrets, or upload translations to
Weblate.

## GitHub-only bootstrap

Set `workflow.mode: github`, omit `localize`, add
`translation.catalog_path`, and pin `knowledge_model.upstream_ref`. Scaffold
without a source release:

```shell
.venv/bin/dsw-km-init-translation-repo \
  --repo-root /path/to/translation-repo \
  --tooling-repo . \
  --config-template examples/translation-config-github.yml \
  --scaffold-only
```

After the source KM is released, pin its GitHub tag in
`knowledge_model.upstream_ref` and hydrate without Registry or Weblate access:

```shell
.venv/bin/dsw-km-sync-github-release \
  --repo-root /path/to/translation-repo
```

The tool downloads the exact GitHub Release asset, checks its `.sha256` sidecar
and package ID, and generates an empty catalog from the KM. Later catalog
updates carry a translation only when its UUID, field, and source text are
unchanged. `dsw-km-init-translation-repo --source-km` remains available for
offline or migration bootstraps.

## Fields Missing from Weblate

Use supplemental translations only when the source KM contains a user-facing
field that is absent from the upstream PO catalog. Add its directory to
`translation-config.yml`:

```yaml
translation:
  supplemental_directory: supplemental
```

Store each entry at `supplemental/<entity-uuid>/translation.md`. The file uses
the same Source and Translation blocks as files under `tree/`. Translators edit
only the Translation block.

Supplemental forms are not copied into Weblate or the generated PO. Every KM
build validates their UUID, field, and source text against the current KM, then
applies them after the Weblate translations. A field that later appears in the
upstream PO is rejected as a duplicate so it can be moved back to the normal
Weblate workflow.

Use bootstrap only to create a repository. To refresh docs and workflows in an
existing repository, use the scaffold commands below.

## Command

From the tooling repository:

```shell
export DSW_REGISTRY_TOKEN=...
make repo-init NEW_TRANSLATION_REPO_DIR=/path/to/new-translation-repo
```

By default this uses [`examples/translation-config.yml`][example-config]. For a
custom repository, copy that file, edit the KM/language/Weblate/tooling values,
and pass it explicitly:

```shell
make repo-init \
  NEW_TRANSLATION_REPO_DIR=/path/to/new-translation-repo \
  TRANSLATION_CONFIG_TEMPLATE=/path/to/translation-config.yml
```

Use scaffold-only mode when you want to review config/docs/workflows before any
network downloads:

```shell
.venv/bin/dsw-km-init-translation-repo \
  --repo-root /path/to/new-translation-repo \
  --tooling-repo . \
  --config-template /path/to/translation-config.yml \
  --scaffold-only
```

## After Bootstrap

1. Review generated files.
2. Create the GitHub repository and push the first commit.
3. Configure repository secrets:
   - `LOCALIZE_API_TOKEN`
   - `DSW_REGISTRY_TOKEN`
4. Run `localize_alignment_report.yml`.
5. Run `localize_auto_sync.yml` and confirm it creates no unexpected changes.

## Existing Repositories

Check whether managed docs and workflows still match their tooling templates:

```shell
make repo-scaffold-check TRANSLATION_REPO_DIR=/path/to/translation-repo
```

Refresh only those managed files:

```shell
make repo-scaffold-sync TRANSLATION_REPO_DIR=/path/to/translation-repo
```

Scaffold sync reads `translation-config.yml` to render repository-specific
values, but never modifies that config or any translation artifact.

## Template Ownership

- Translation repository docs are rendered from
  [`examples/translation-repository/`][translation-repo-template]. Language and
  tooling values come from `translation-config.yml`.
- GitHub Actions workflows are copied from
  [`examples/github-actions/`][github-actions-templates].
- Workflow `TOOLING_REPOSITORY`, `TOOLING_REF`, and tracking branch values are
  rendered from `translation-config.yml`.
- Unknown template placeholders fail the command instead of being copied into
  the target repository.

[example-config]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/examples/translation-config.yml
[github-actions-templates]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/examples/github-actions
[translation-repo-template]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/examples/translation-repository
