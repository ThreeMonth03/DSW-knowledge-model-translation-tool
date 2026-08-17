# KM Update Runbook

Use this runbook when the DSW Registry publishes a new Common DSW Knowledge
Model. The production translation repository tracks the current published KM.

## When to Start

Start after the KM version is published and available from the DSW Registry or
another official upstream source.

## Required Secret

Configure `DSW_REGISTRY_TOKEN` in the production translation repository under
GitHub Actions repository secrets before enabling the scheduled KM update
workflow. Local runs read the same token from the shell environment. See
[Security and Permissions](security-and-permissions.md).

The scheduled KM version auto-update workflow is the normal update mechanism.
It runs `dsw-km-sync-latest-km`, no-ops when the configured KM is current, and
only pushes to Git when every safety check passes. When the Registry has a newer
published KM, the workflow:

- downloads the new KM bundle using `DSW_REGISTRY_TOKEN`;
- updates `translation-config.yml` and the conventional source KM path;
- downloads the current Weblate PO without uploading anything to Weblate;
- rebuilds `tree/`, `builds/final_translated.po`, and
  `builds/final_translated.km`;
- validates config, runs translation tests, and checks repository alignment;
- commits and pushes to the tracking branch only after those steps pass.

If the token is missing or any validation step fails, no Git commit is pushed.
The next scheduled run will retry.

For a local maintainer run, use:

```shell
export TOOL_REPO_DIR=/path/to/dsw-km-translation-tool
make -C "$TOOL_REPO_DIR" repo-km-update \
  TRANSLATION_REPO_DIR=/path/to/dsw-root-locales-zh_Hant
```

Set `TRANSLATION_REPO_DIR` as described in the
[Command Reference](command-reference.md). Override `TRACKING_BRANCH` only when
the production repository does not use `master`. The targets are declared in
the [`Makefile`][makefile].

## Manual Test or Repair Path

Use this path only when the scheduled update fails, or when you want to test a
new KM update in a disposable branch or local clone.

1. Create and check out a disposable branch in a clean translation repository.

2. Discover available versions:

   ```shell
   make -C "$TOOL_REPO_DIR" repo-km-status \
     TRANSLATION_REPO_DIR=/path/to/dsw-root-locales-zh_Hant
   ```

3. Run the same guarded updater against the disposable branch:

   ```shell
   export DSW_REGISTRY_TOKEN=...
   make -C "$TOOL_REPO_DIR" repo-km-update \
     TRANSLATION_REPO_DIR="$TRANSLATION_REPO_DIR" \
     TRACKING_BRANCH="$BRANCH_NAME"
   ```

4. Validate config and alignment if you are diagnosing a failed update:

   ```shell
   make -C "$TOOL_REPO_DIR" repo-validate \
     TRANSLATION_REPO_DIR="$TRANSLATION_REPO_DIR"
   make -C "$TOOL_REPO_DIR" repo-align \
     TRANSLATION_REPO_DIR="$TRANSLATION_REPO_DIR"
   ```

## Review Manual Branch Outputs

Review these generated files before merging:

```text
sources/knowledge-models/
sources/localize/zh_Hant/latest.po
tree/
builds/final_translated.po
builds/final_translated.km
reviews/
```

Pay special attention to:

- source mismatches, which may indicate changed English strings;
- missing entries, which may indicate new KM fields or removed old fields;
- newly empty translations;
- newly review-marked translations reported by Weblate.

Merge a manual branch only after it produces aligned outputs. After merge,
trigger the scheduled sync and alignment report once manually to verify the
production branch.

[makefile]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/Makefile
