# Localize Sync Runbook

Use this runbook for production zh-Hant sync.

## Operating Model

The latest translation state is governed by Localize/Weblate. The Git
translation repository mirrors that state so maintainers can review generated
trees, build translated KM bundles, and keep reproducible history.

Normal scheduled automation is one-way:

```text
Localize/Weblate -> GitHub translation repository
```

GitHub pull requests can also contribute translation edits. That path is
guarded:

```text
GitHub PR -> reviewed merge -> Weblate import -> Weblate-to-Git sync
```

## Secrets

Scheduled sync and alignment do not need Weblate write access. Configure
`LOCALIZE_API_TOKEN` in the production translation repository when enabling the
post-merge GitHub translation import workflow or when the read-only status
workflow should use authenticated Weblate checks. If it is not configured for
the status report, the check report uses anonymous access. See
[Security and Permissions](security-and-permissions.md).

## Scheduled Pull Sync

The external translation workflow should run:

- on a schedule, usually twice per day
- on pull requests targeting `master`

The workflow runs the `dsw-km-sync-localize` command. That command:

1. Downloads the current Weblate PO to `sources/localize/zh_Hant/latest.po`.
2. Force-refreshes `tree/` from the latest Weblate PO.
3. Rebuilds `builds/final_translated.po`.
4. Rebuilds `builds/final_translated.km`.
5. Refreshes review outputs.
6. Commits and pushes only when tracked files changed.

Scheduled runs commit directly to `master` when repository policy allows it.
Pull request runs always produce a read-only GitHub translation report. Writer
sync runs only for same-repository pull requests that do not edit translation
text. Fork pull requests never receive writer commits from this workflow.

When a pull request edits `tree/**/translation.md`, the workflow reports those
GitHub translation changes, validates that source Markdown formatting is
preserved, including leading and trailing whitespace, and skips Weblate-to-Git
writer sync for that PR. Invalid formatting fails the pull-request check with
field-level details. Skipping writer sync
prevents unmerged GitHub translation work from being replaced by the latest
Weblate mirror before review.

For a local maintainer run against a checked-out translation repository, use:

```shell
make repo-sync TRANSLATION_REPO_DIR=/path/to/dsw-root-locales-zh_Hant
```

Set `TRANSLATION_REPO_DIR` as described in the
[Command Reference](command-reference.md). The target is
declared in the [`Makefile`][makefile].

## Read-Only Status and Alignment Reports

Use the status report workflow to inspect Weblate PO health without changing
Git or Weblate. It:

1. Checks out the translation repository.
2. Pulls the latest Weblate PO into the ephemeral workflow checkout.
3. Runs `dsw-km-report-localize-status`.
4. Writes a GitHub step summary and uploads
   `reviews/localize_status_report.json` and
   `reviews/localize_status_report.md` as artifacts.

The status report includes Weblate review-state counts from the PO export as
part of current translation health.

The same workflow can also run `dsw-km-report-weblate-checks` with the Weblate
query `has:check`. That catches website-side quality-check warnings that are
not always visible from PO state alone. The check report is diagnostic and uses
`--allow-api-failure` so Weblate API rate limits are captured in the report
while Git sync monitoring continues.

It requires only `contents: read`.

Use the alignment report workflow to verify output consistency without
changing Git or Weblate. It:

1. Downloads the latest Weblate PO into a temporary file.
2. Compares it with `sources/localize/zh_Hant/latest.po`.
3. Rebuilds `builds/final_translated.po` from `tree/`.
4. Rebuilds `builds/final_translated.km` from the final PO and configured KM
   metadata.
5. Uploads JSON, Markdown, and generated comparison artifacts.

The alignment report is allowed to fail when drift is detected. That failure
means a pull sync, tree rebuild, or KM rebuild should run before maintainers
trust the repository outputs. It also requires only `contents: read` and does
not change translations.

To run the same alignment check from your machine, use:

```shell
make repo-align TRANSLATION_REPO_DIR=/path/to/dsw-root-locales-zh_Hant
```

## PR Gate and Post-Merge Import

Before a same-repository branch reaches `master`, the pull request writer pulls
Weblate again and refreshes the branch when the PR does not edit translation
text. This makes infra/config/doc PRs include the latest website translation
state.

For PRs that do edit translation text, the writer is skipped. After the PR is
merged, the GitHub translation import workflow compares the accepted GitHub
edits with the latest Weblate PO and repeats all PR checks before any upload.
The PR check fails before merge when Weblate already conflicts, source Markdown
formatting is lost, or canonical `shared_blocks/` edits were not expanded into
their referenced `translation.md` fields. Post-merge validation catches Weblate
changes that land after the PR check:

- GitHub changed an entry and Weblate still matches the base: import GitHub to
  Weblate.
- GitHub and Weblate already match: no import is needed.
- GitHub and Weblate changed the same entry differently: fail and write a
  conflict report.
- The translated Markdown lost source formatting: fail and write a format
  report.

After upload, the workflow downloads Weblate again and verifies every imported
entry. It fails if Weblate did not apply the expected content. A verified
import then runs normal Weblate-to-Git sync so the repository returns to being
a Weblate mirror.

Use forward commits for sync and workflow corrections on public branches.

## Conflict Policy

Normal sync is Weblate-first:

- Weblate entries that are ready for use win.
- Checked-in tree translations that differ from Weblate are replaced during
  force-refresh.
- Entries marked for review stay in Weblate for translators to resolve on the
  website.

GitHub translation import is not last-write-wins. It imports only entries that
are safe against the current Weblate state. Conflicts require human review.

Writer workflows use the same retained concurrency queue. This prevents a later
push or scheduled run from replacing an import that is already waiting.

## KM Updates

The current production policy is latest-only. Use
[KM Update Runbook](km-update-runbook.md) when the DSW Registry publishes a new
Common DSW KM.

## Troubleshooting

- If sync commits nothing, Weblate and Git outputs are already aligned.
- If `translation-config.yml` fails validation, fix config before running sync.
- If tree parsing fails in CI, the writer may restore malformed files from the
  tracking branch once and retry.
- If Weblate has untranslated strings after sync, check whether they are empty,
  marked for review, or missing from the current KM source.

[makefile]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/Makefile
