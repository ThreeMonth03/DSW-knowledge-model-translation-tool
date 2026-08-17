# Repository Transfer Checklist

Use this checklist when moving the tooling repository to another GitHub owner or
organization. The goal is to keep translation automation working without
changing translation text or uploading anything to Weblate.

Set `TOOL_REPO_DIR` to the trusted tooling checkout before running this
checklist:

```shell
export TOOL_REPO_DIR=/path/to/dsw-km-translation-tool
```

## Before Transfer

1. Confirm the current default branch is green in GitHub Actions.
2. Confirm the production translation repository is aligned with Weblate:

   ```shell
   make -C "$TOOL_REPO_DIR" repo-align \
     TRANSLATION_REPO_DIR="$TRANSLATION_REPO_DIR"
   ```

   Set `TRANSLATION_REPO_DIR` as described in the
   [Command Reference](command-reference.md).

3. Record the target tooling repository owner/name and branch policy.

## Update Tooling References

After the tooling repository is transferred, update every translation repository
that checks out the tooling:

- [`translation-config.yml`][example-translation-config]
  - `tooling.repository`
  - `tooling.ref`, if the branch or tag policy changed
- [`.github/workflows/*.yml`][github-actions-templates]
  - `TOOLING_REPOSITORY`
  - `TOOLING_REF`, if the branch or tag policy changed

In this tooling repository, update:

- [`examples/translation-config.yml`][example-translation-config]
- [`examples/github-actions/*_template.yml`][github-actions-templates]
- [`tests/infra/test_github_workflows.py`][test-github-workflows]
- Source links in maintainer docs, if GitHub redirects will not cover the new
  location.

## GitHub Settings

Verify these settings after transfer:

- Actions are enabled for the tooling repository.
- GitHub Pages is enabled with the `Deploy Documentation` workflow.
- The repository homepage points to the active docs site.
- Required repository secrets are present in each production translation
  repository that needs them. See
  [Security and Permissions](security-and-permissions.md) for
  `LOCALIZE_API_TOKEN` and `DSW_REGISTRY_TOKEN`.

Secrets are repository settings, not files. Verify them in GitHub after the
move rather than documenting token values.

## Smoke Test

Run these checks after updating references:

```shell
make -C "$TOOL_REPO_DIR" install-dev
make -C "$TOOL_REPO_DIR" check
make -C "$TOOL_REPO_DIR" repo-validate \
  TRANSLATION_REPO_DIR="$TRANSLATION_REPO_DIR"
make -C "$TOOL_REPO_DIR" repo-align \
  TRANSLATION_REPO_DIR="$TRANSLATION_REPO_DIR"
```

Then trigger the read-only status and alignment workflows manually in the
production translation repository. Trigger writer workflows only after read-only
checks are green.

[example-translation-config]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/examples/translation-config.yml
[github-actions-templates]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/examples/github-actions
[test-github-workflows]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/tests/infra/test_github_workflows.py
