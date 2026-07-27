# KM release process

## Mutable work

Use one pull-request branch for a release. Amend and force-push with
`--force-with-lease` as needed. The branch and pull-request checks are mutable.

## Immutable boundary

1. Review `legal-mapping.yml` and the proposed questionnaire behavior.
2. Implement the approved change in the existing DSW Knowledge Model Editor.
3. Publish a new numeric KM version.
4. Export the exact bundle to `km/{{KM_ID}}.km`.
5. Generate the manifest from the exported bundle:
   `dsw-km-prepare-release --repo-root .`. For a replacement manifest that has
   not been merged or tagged, add `--overwrite`.
6. Run `dsw-km-validate-release --repo-root .`.
7. Squash-merge the release pull request.
8. Create the immutable `v<version>` tag on that merge commit.

Never move a published tag or replace an existing DSW version. Corrections get
a new patch version. Pull-request and tag CI download the previous GitHub
Release asset and reject rewritten historical packages.
