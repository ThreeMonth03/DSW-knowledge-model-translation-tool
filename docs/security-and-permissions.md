# Security and Permissions

Use this page when configuring GitHub Actions, repository settings, or secrets
for a production translation repository.

## Source of Truth

Latest zh-Hant translation text is governed by Localize/Weblate. The Git
translation repository is a reproducible mirror for automation, review, and
visual inspection.

Scheduled automation pulls from Weblate into Git and uses download-only access.
The only Git-to-Weblate path is the guarded post-merge GitHub translation import
workflow.

## Required Workflow Permissions

| Workflow | GitHub permission | Secrets | Writes translations? |
| --- | --- | --- | --- |
| [Tooling upstream smoke][upstream-smoke-workflow] | `contents: read` | `DSW_REGISTRY_TOKEN` | No |
| [Localize auto sync][localize-auto-sync-template] | `contents: write` | none | Writes the tracking branch from trusted scheduled runs |
| [GitHub translation import][github-import-template] | `contents: write` | `LOCALIZE_API_TOKEN` | Writes Weblate after merge, then writes Git through sync |
| [Localize status report][localize-status-template] | `contents: read` | optional `LOCALIZE_API_TOKEN` | No |
| [Localize alignment report][localize-alignment-template] | `contents: read` | none | No |
| [KM version auto update][km-auto-update-template] | `contents: write` | `DSW_REGISTRY_TOKEN` only when a newer KM exists | Writes Git only after validation |

The workflows that write the tracking branch or Weblate share the
`translation-state-master` concurrency group with `queue: max`. Keep both
settings aligned so later runs do not replace pending writer jobs.

## Secret Placement

Configure secrets in the production translation repository:

```text
Settings -> Secrets and variables -> Actions -> Repository secrets
```

The tooling repository does not need these secrets for documentation builds or
unit tests. The tooling repository only needs `DSW_REGISTRY_TOKEN` if its
scheduled upstream smoke workflow is enabled. Local maintainer runs read the
same names from shell environment variables.

The workflow templates in [`examples/github-actions/`][github-actions-templates]
show where GitHub Actions injects these secrets.

The normal sync and alignment workflows use download-only Weblate access.

`LOCALIZE_API_TOKEN` is optional for the status report. It is required for the
post-merge GitHub translation import workflow because that workflow uploads
reviewed translation edits to Weblate. When absent from the status report, the
report falls back to anonymous access.

`DSW_REGISTRY_TOKEN` is required when the guarded KM version auto-update
workflow is enabled. It is used only to download a newly published source KM
bundle. The tooling repository upstream smoke workflow uses the same secret to
download the current source KM for integration testing. It is not used for
Weblate access.

## Token Handling

- Store tokens as GitHub Actions repository secrets.
- Keep tokens out of `translation-config.yml`, workflow files, logs, and
  generated reports.

## Public History

Use forward commits for workflow, build output, report, or documentation fixes
on public branches.

[km-auto-update-template]: ../examples/github-actions/km_version_auto_update_template.yml
[github-import-template]: ../examples/github-actions/github_translation_import_template.yml
[github-actions-templates]: ../examples/github-actions
[localize-alignment-template]: ../examples/github-actions/localize_alignment_report_template.yml
[localize-auto-sync-template]: ../examples/github-actions/localize_auto_sync_template.yml
[localize-status-template]: ../examples/github-actions/localize_status_report_template.yml
[upstream-smoke-workflow]: ../.github/workflows/upstream_smoke.yml
