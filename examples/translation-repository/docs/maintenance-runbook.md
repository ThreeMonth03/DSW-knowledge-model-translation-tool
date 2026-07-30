# Maintenance Runbook

Use this runbook for routine operation of a Common DSW Knowledge Model
translation repository.

## Daily Health Check

Check the latest scheduled Weblate-to-Git sync:

```shell
gh run list --workflow localize_auto_sync.yml --branch master --limit 5
```

Healthy outcomes:

- Git was already aligned with Weblate.
- The workflow committed a Weblate sync update to `master`.

Check read-only reports:

```shell
gh run list --workflow localize_status_report.yml --branch master --limit 5
gh run list --workflow localize_alignment_report.yml --branch master --limit 5
```

Check KM auto-update:

```shell
gh run list --workflow km_version_auto_update.yml --branch master --limit 5
```

Check post-merge GitHub translation imports:

```shell
gh run list --workflow github_translation_import.yml --branch master --limit 5
```

## Manual Triggers

Trigger Weblate-to-Git sync after a translation batch lands in Weblate:

```shell
gh workflow run localize_auto_sync.yml --ref master
```

Trigger read-only reports:

```shell
gh workflow run localize_status_report.yml --ref master
gh workflow run localize_alignment_report.yml --ref master
```

Trigger KM auto-update immediately:

```shell
gh workflow run km_version_auto_update.yml --ref master
```

Trigger a GitHub translation import for a known commit range:

```shell
gh workflow run github_translation_import.yml \
  --ref master \
  -f base_ref=BASE_COMMIT \
  -f head_ref=HEAD_COMMIT
```

Use this only after reviewed translation changes have landed in the tracking
branch.

## KM and Config Updates

Normal Weblate sync does not refresh `translation-config.yml`. The KM
auto-update workflow may update only the active KM version and bundle path after
the newer KM bundle, Weblate mirror, rebuild, validation, and alignment checks
all pass. Other settings, such as branch names, Weblate URLs, and tooling refs,
are maintained manually.

## Local Checks

Use the tooling repository for local checks:

```shell
TOOL_REPO_DIR=/path/to/dsw-km-translation-tool
TRANSLATION_REPO_DIR=/path/to/translation-repo

cd "$TOOL_REPO_DIR"
make install-dev
make repo-validate TRANSLATION_REPO_DIR="$TRANSLATION_REPO_DIR"
make repo-scaffold-check TRANSLATION_REPO_DIR="$TRANSLATION_REPO_DIR"
make repo-sync-shared-strings TRANSLATION_REPO_DIR="$TRANSLATION_REPO_DIR"
make repo-align TRANSLATION_REPO_DIR="$TRANSLATION_REPO_DIR"
```

After the tooling repository changes its managed docs or workflow templates,
refresh them with `make repo-scaffold-sync`. This command reads but never
changes `translation-config.yml` or translation artifacts.

`make repo-sync-shared-strings` updates only canonical shared-block context
files and their referenced `tree/**/translation.md` fields. It does not commit
or push. Other writer targets such as `make repo-sync` and
`make repo-km-update` may commit and push from the checkout where they run. Use
them only from a disposable checkout or when you intentionally want a Git
update.

## Troubleshooting

- Sync created no commit: Git is already aligned with Weblate.
- Alignment failed: download `localize-alignment-report` and compare the
  generated files with the checked-in files.
- Generated KM changed unexpectedly: compare `sources/localize/*/latest.po`
  with `builds/final_translated.po`.
- KM auto-update failed before downloading a bundle: check `DSW_REGISTRY_TOKEN`.
- KM auto-update failed after rebuilding: inspect the validation or alignment
  error.
- A translation PR failed Markdown validation: open the GitHub translation
  report and restore the missing emphasis, link, list, or code formatting.
- A same-repository translation PR failed shared-block validation: inspect the
  shared-sync step first. To reproduce it locally, run
  `make repo-sync-shared-strings TRANSLATION_REPO_DIR=/path/to/repo`.
- A fork translation PR failed shared-block validation: run the same command
  locally and commit its `tree/` changes to the fork branch; Actions never
  writes to forks.
- A translation PR conflicts with Weblate: resolve the reported entries before
  merging; the workflow does not choose a winner automatically.
