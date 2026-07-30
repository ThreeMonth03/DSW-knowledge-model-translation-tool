# Sync Policy

This repository uses a Weblate-first synchronization policy.

## Authority

The latest translation state is governed by Localize/Weblate.

GitHub mirrors the website state. Direct changes to `tree/` outside the
reviewed pull-request path may be overwritten by the next sync.

## Direction

Scheduled automation is one-way:

```text
Localize/Weblate -> GitHub
```

The sync writer:

1. Downloads the latest Weblate PO.
2. Refreshes `tree/` from that PO.
3. Rebuilds `builds/final_translated.po`.
4. Rebuilds `builds/final_translated.km`.
5. Refreshes review outputs.
6. Commits and pushes only when tracked artifacts changed.

Scheduled sync does not upload translations to Weblate.

Reviewed GitHub translation pull requests use a guarded reverse path:

```text
GitHub PR -> reviewed merge -> Weblate import -> Weblate-to-Git sync
```

Only entries that are safe against the current Weblate state are imported. If
GitHub and Weblate changed the same entry differently, the import workflow
fails and writes a conflict report. It does not use timestamps or a
last-writer-wins rule to choose between reviewers. Pull-request and post-merge
checks also reject translations that do not preserve source Markdown formatting
and boundary whitespace. For same-repository pull requests, canonical
`tree/shared_blocks/*/context.md` edits are expanded into every referenced
`translation.md` field and committed to the pull-request branch before that
report runs. The reporter still rejects any inconsistency the deterministic
sync cannot resolve. After upload, the workflow downloads Weblate again and
fails unless every expected entry is present.

## Writer Workflows

- `localize_auto_sync.yml` commits directly to the tracking branch on scheduled
  runs when tracked files changed.
- Same-repository pull requests first receive a deterministic shared-translation
  expansion commit when needed, followed by the GitHub translation and Markdown
  format report.
- Fork pull requests receive the same report but remain read-only.
- Same-repository pull requests that do not edit translation text can also
  receive a Weblate sync commit before merge.
- Delayed pull-request runs compare against the pull request base commit and
  skip writer sync if the head branch no longer exists.
- `github_translation_import.yml` imports accepted GitHub translation edits to
  Weblate after merge, then syncs Weblate back to Git when an upload occurred.
- `km_version_auto_update.yml` updates to a newer published KM only after the
  bundle download, Weblate mirror, rebuild, validation, and alignment checks
  pass.

These writer workflows share a retained concurrency queue so pending imports,
syncs, and KM updates are not replaced by later runs.

## Read-Only Reports

- `localize_status_report.yml` reports empty entries, review-state counts, and
  Weblate `has:check` items.
- `localize_alignment_report.yml` verifies that Weblate PO, checked-in PO,
  `tree/`, final PO, and final KM match.

## Translation Quality States

Resolve review-marked strings in Weblate. Git mirrors those states in reports.
