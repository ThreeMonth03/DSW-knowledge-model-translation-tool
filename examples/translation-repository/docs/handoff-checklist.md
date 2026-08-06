# Handoff Checklist

Use this page when handing repository maintenance to another maintainer.

## Operating Model

- Translate in Localize/Weblate.
- Let GitHub Actions mirror Weblate into this repository.
- Review generated `tree/`, `builds/`, and `reviews/` files in Git.
- Use workflow reports to diagnose drift before editing repository files.

## Repositories

| Repository | Purpose |
| --- | --- |
| This repository | Formal {{TARGET_LANGUAGE_LABEL}} translation mirror and build output |
| [`{{TOOLING_REPOSITORY}}`](https://github.com/{{TOOLING_REPOSITORY}}) | Tooling used by workflows and local maintenance commands |

## Required Access

- Write access to this translation repository.
- Access to repository Actions and workflow logs.
- Access to configure repository Actions secrets.
- Localize/Weblate account for translation review.

## Secrets

Configure these secrets in this repository:

| Secret | Used by | Purpose |
| --- | --- | --- |
| `LOCALIZE_API_TOKEN` | `github_translation_import.yml`, `localize_status_report.yml` | Import accepted GitHub translation edits and read Weblate quality-check units |
| `DSW_REGISTRY_TOKEN` | `km_version_auto_update.yml` | Download newer published KM bundles |

## Workflow Inventory

| Workflow | Schedule | Writes | Normal Result |
| --- | --- | --- | --- |
| `localize_auto_sync.yml` | Scheduled, PR | Git | Mirrors Weblate; commits only when tracked files changed |
| `github_translation_import.yml` | Push to the tracking branch, manual | Weblate, then Git if sync changes follow | Imports accepted GitHub translation edits after merge; fails on conflicts |
| `localize_status_report.yml` | Scheduled, manual | No | Reports empty translations, review-state counts, and Weblate checks |
| `localize_alignment_report.yml` | Scheduled, manual | No | Verifies Weblate PO, checked-in PO, tree, final PO, and final KM alignment |
| `km_version_auto_update.yml` | Scheduled, manual | Git | No-ops when current; updates only after validation passes |
| `validate_translation_config.yml` | Push, PR, manual | No | Validates config and checks managed docs/workflows for drift |

## Routine Check

1. Check the latest `localize_auto_sync.yml` run.
2. Check the latest `localize_alignment_report.yml` run.
3. Check the latest `localize_status_report.yml` run.
4. Check the latest `km_version_auto_update.yml` run.
5. If a report failed, download its artifact before changing files.

See [Maintenance Runbook](maintenance-runbook.md) for commands.

## Healthy Signals

- Sync reports Git and Weblate are already aligned, or creates one sync commit.
- Alignment report status is `aligned`.
- Status report has no empty translations unless new KM strings were introduced.
- KM auto-update reports `current`, or commits an update after validation passes.

## Failure Entry Points

| Symptom | First Place to Look |
| --- | --- |
| Sync failed | `localize_auto_sync.yml` log |
| Git and Weblate drifted | `localize-alignment-report` artifact |
| Weblate checks changed | `localize-status-report` artifact |
| KM update failed | `km-version-auto-update` artifact |
| Config validation failed | `translation-config.yml` and `validate_translation_config.yml` log |

## Local Maintenance

Use a disposable checkout for local sync or KM repair. The sync command can
commit and push from the checkout where it runs.

Use [Maintenance Runbook](maintenance-runbook.md#local-checks) for local
commands.
