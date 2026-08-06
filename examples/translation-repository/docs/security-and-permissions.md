# Security and Permissions

Use this page when configuring GitHub Actions, secrets, and workflow
permissions for this repository.

## Workflow Permission Matrix

| Workflow | Permission | Secret | Writes |
| --- | --- | --- | --- |
| `localize_auto_sync.yml` | `contents: write` | none | tracking branch from trusted scheduled runs |
| `github_translation_import.yml` | `contents: write` | `LOCALIZE_API_TOKEN` | Weblate after merge; Git only when sync changes follow |
| `localize_status_report.yml` | `contents: read` | optional `LOCALIZE_API_TOKEN` | nothing |
| `localize_alignment_report.yml` | `contents: read` | none | nothing |
| `km_version_auto_update.yml` | `contents: write` | `DSW_REGISTRY_TOKEN` only when a newer KM exists | tracking branch only after validation |
| `validate_translation_config.yml` | `contents: read` | none | nothing |

The workflows that write `master` or Weblate share the
`translation-state-master` concurrency group with `queue: max`. Keep both
settings aligned so later runs do not replace pending writer jobs.

On pull requests, `localize_auto_sync.yml` writes only when the head branch
belongs to this repository and still exists. Its shared-translation step
commits only canonical `tree/shared_blocks/*/context.md` files and referenced
`tree/**/translation.md` files. Fork pull requests remain read-only.

## Actions Secrets

Configure these Actions repository secrets:

```text
LOCALIZE_API_TOKEN
DSW_REGISTRY_TOKEN
```

`LOCALIZE_API_TOKEN` is required by the post-merge GitHub translation import
workflow. It is also used by the status report for read-only Weblate checks;
that report falls back to anonymous access if the token is unavailable, but API
limits may be stricter.

`DSW_REGISTRY_TOKEN` is used only by KM auto-update when it needs to download a
newly published source KM bundle.

## Token Hygiene

- Keep tokens out of `translation-config.yml`, workflow YAML, logs, and
  generated reports.
