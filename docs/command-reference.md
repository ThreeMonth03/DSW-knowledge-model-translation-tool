# Command Reference

Use `make` for normal maintenance. Use the packaged `dsw-km-*` commands only
when you are changing workflow wiring, debugging one helper, or reproducing a
GitHub Actions command exactly.

## Required Variables

These are Make variables declared in the repository [`Makefile`][makefile].
Commands that operate on a production-style translation repository need:

```shell
TRANSLATION_REPO_DIR=/path/to/dsw-root-locales-zh_Hant
```

Optional overrides:

```shell
TRANSLATION_CONFIG=translation-config.yml
TRACKING_BRANCH=master
GITHUB_TRANSLATION_BASE_REF=origin/master
GITHUB_TRANSLATION_HEAD_REF=HEAD
```

Workflow secrets are configured in the production translation repository. Local
commands read `LOCALIZE_API_TOKEN` and `DSW_REGISTRY_TOKEN` from the shell
environment when a target needs them. See
[Security and Permissions](security-and-permissions.md).

Translation repository behavior is configured in `translation-config.yml`; see
[`examples/translation-config.yml`][example-translation-config] for the expected
shape.

Set `workflow.mode: github` and omit `localize` for a Git-authoritative
repository. In that mode, set `translation.catalog_path` and pin
`knowledge_model.upstream_ref`.

## Local Tooling

| Target | Use |
| --- | --- |
| `make install-dev` | Create `.venv` and install development dependencies |
| `make check` | Run format check, lint, compile, tests, docs, and `git diff --check` |
| `make docs` | Build the Sphinx docs into `docs/sphinx/_build/html/` |
| `make format` | Auto-fix Python formatting and import ordering |
| `make help` | Show the common maintainer targets |
| `make help-all` | Show every target, including lower-level local tree helpers |
| `make upstream-smoke` | Check current upstream KM/Weblate inputs in `.cache/upstream-smoke/` |

## Translation Repository

Set `TRANSLATION_REPO_DIR` before running these targets.

| Target | Safety | Use |
| --- | --- | --- |
| `make repo-validate` | Read-only | Validate `translation-config.yml` |
| `make repo-status` | Report files only | Inspect the checked-in Weblate PO |
| `make repo-checks` | Report files only | Query Weblate quality checks such as `has:check` |
| `make repo-align` | Report files only | Compare Weblate, tree, final PO, and final KM outputs |
| `make repo-scaffold-check` | Read-only | Verify managed docs and workflows match the tooling templates |
| `make repo-scaffold-sync` | Filesystem writer | Refresh managed docs and workflows without changing config or translations |
| `make repo-github-translations` | Report files only | Compare GitHub translation edits with current Weblate |
| `make repo-init` | Writes files | Initialize a new translation repository from templates and upstream inputs |
| `make repo-pull-po` | Writes files | Refresh `sources/localize/` in the checkout |
| `make repo-sync` | Git writer | Pull Weblate, rebuild outputs, and commit/push when changed |
| `make repo-import-github-translations` | Weblate writer | Import accepted GitHub translation edits, failing on conflicts |
| `make repo-km-status` | Report files only | Check whether the Registry has a newer KM |
| `make repo-km-update` | Guarded Git writer | Update to a newer published KM after validation passes |

## GitHub-only source and translation repositories

Create an append-only source KM repository:

```shell
.venv/bin/dsw-km-init-source-repo \
  --repo-root /path/to/dsw-root-tw \
  --tooling-repo . \
  --organization-id tw \
  --km-id root-tw \
  --name "Taiwan DSW Knowledge Model" \
  --initial-parent-package-id dsw:root:2.7.0 \
  --tooling-repository ThreeMonth03/dsw-km-translation-tool \
  --tooling-ref <commit-sha>
```

Validate an unreleased scaffold or a completed release:

```shell
.venv/bin/dsw-km-validate-release --repo-root /path/to/dsw-root-tw --allow-unreleased
.venv/bin/dsw-km-validate-release --repo-root /path/to/dsw-root-tw --tag v0.1.0
```

Build legal-review candidates and validate a curated mapping against the exact
source bundle:

```shell
.venv/bin/dsw-km-build-legal-inventory \
  --km /path/to/dsw-root-2.7.0.km \
  --rules /path/to/legal-inventory-rules.yml \
  --out /path/to/legal-question-inventory.yml
.venv/bin/dsw-km-validate-legal-mapping \
  --km /path/to/dsw-root-2.7.0.km \
  --mapping /path/to/legal-mapping.yml
.venv/bin/dsw-km-build-legal-draft \
  --km /path/to/dsw-root-2.7.0.km \
  --mapping /path/to/legal-mapping.yml \
  --output /path/to/root-tw.km \
  --organization-id tw \
  --km-id root-tw \
  --version 0.1.0 \
  --name "Taiwan DSW Knowledge Model" \
  --description "Taiwan-focused research data management knowledge model." \
  --license Apache-2.0 \
  --readme-file /path/to/package-readme.md
```

The inventory is keyword-based triage, not a legal conclusion. The validator
binds every curated mapping to the package checksum, question UUID, current
question title, immutable GitHub source location, and declared official
sources. The draft builder preserves the complete parent history and appends one
child package containing deterministic title and guidance edit events. It
supports only `rewrite` and `replace`; structural actions must be authored and
reviewed in the DSW KM Editor.

After exporting from the DSW KM Editor, generate the manifest instead of
copying IDs and checksums by hand:

```shell
.venv/bin/dsw-km-prepare-release --repo-root /path/to/dsw-root-tw
```

Source-repository CI passes `--github-repository owner/repo`, so every release
after the first is compared with the previous GitHub Release bundle. Historical
packages that disappear or change are rejected.

Generate a Weblate-free catalog and rebuild a translation repository:

```shell
.venv/bin/dsw-km-catalog-from-km \
  --km /path/to/root-tw.km \
  --out sources/catalog/zh_Hant/catalog.po \
  --target-language zh_Hant
.venv/bin/dsw-km-build-translation-repo --repo-root .
```

`dsw-km-init-translation-repo --source-km /path/to/root-tw.km` combines these
steps for a GitHub-only config. Add `--source-po` to seed it from an existing
catalog.

For normal GitHub-only operation, avoid manual asset downloads. Pin
`knowledge_model.upstream_ref`, `version`, and `bundle_path`, then run:

```shell
.venv/bin/dsw-km-sync-github-release --repo-root /path/to/translation-repo
.venv/bin/dsw-km-sync-github-release \
  --repo-root /path/to/translation-repo \
  --check
```

The writer downloads the versioned `.km` and `.sha256` assets, verifies the KM
package ID, preserves translations whose UUID/field/source text did not change,
and rebuilds the repository. The read-only form is the CI dependency check.

Example:

```shell
make repo-align TRANSLATION_REPO_DIR=/path/to/dsw-root-locales-zh_Hant
```

After changing translation repository templates, check and refresh an existing
repository with:

```shell
make repo-scaffold-check TRANSLATION_REPO_DIR=/path/to/translation-repo
make repo-scaffold-sync TRANSLATION_REPO_DIR=/path/to/translation-repo
```

The sync target never writes `translation-config.yml`, `tree/`, `sources/`, or
`builds/`.

To create a new translation repository, set `NEW_TRANSLATION_REPO_DIR`:

```shell
export DSW_REGISTRY_TOKEN=...
make repo-init NEW_TRANSLATION_REPO_DIR=/path/to/new-translation-repo
```

See [Translation Repository Bootstrap](translation-repository-bootstrap.md) for
the full initialization flow.

## Local Translation Tree

These targets are for development, inspection, and repair in an ignored local
workspace. They default to `translation/zh_Hant/`.

| Target | Use |
| --- | --- |
| `make export-tree` | Export the sample PO/KM into a local translation tree |
| `make sync` | Sync shared strings and rebuild the local final PO |
| `make status` | Show untranslated fields in the local tree |
| `make workflow` | Run the optional end-to-end smoke workflow |

Run `make help-all` if you need lower-level helpers such as `tree-to-po`,
`po-to-km`, `repo-km-pull`, or `repo-sync-branch`.

`dsw-km-po-to-km` also accepts `--supplemental-translations-dir` for strict
Markdown forms representing source KM fields that do not exist in the upstream
PO. Production repositories should set `translation.supplemental_directory` in
`translation-config.yml` instead of passing this flag directly.

## Direct CLI Use

The targets above are thin wrappers around console scripts installed into
`.venv/bin/`. Those commands are declared in [`pyproject.toml`][pyproject] and
implemented under [`src/dsw_km_translation_tool/cli/`][cli-dir].

When changing implementation, use [Architecture](architecture.md) to find the
owning package module and tests.

## Local Tree Variables

The local tree targets accept these Make variable overrides from
[`Makefile`][makefile]:

```shell
PO=tests/fixtures/source_inputs/common_dsw_zh_Hant.po
MODEL=tests/fixtures/source_inputs/dsw_root_2.7.0.km
TARGET_LANG=zh_Hant
OUTPUT_ROOT=translation/zh_Hant
```

Production translation repositories should use `translation-config.yml` and the
`repo-*` targets instead.

[example-translation-config]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/examples/translation-config.yml
[cli-dir]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/src/dsw_km_translation_tool/cli
[makefile]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/Makefile
[pyproject]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/pyproject.toml
