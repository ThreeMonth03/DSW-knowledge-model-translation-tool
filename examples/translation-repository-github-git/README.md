# {{TARGET_LANGUAGE_LABEL}} translation of {{SOURCE_KM_ID}}

This repository is the Git-authoritative {{TARGET_LANGUAGE_LABEL}} translation
of `{{SOURCE_KM_ID}}`. It intentionally has no Weblate dependency.

Current source:

- repository: `{{SOURCE_REPOSITORY}}`
- commit: `{{SOURCE_REF}}`
- bundle: `{{SOURCE_BUNDLE_PATH}}`
- KM version: `{{SOURCE_VERSION}}`

The complete source commit and bundle path are pinned in
`translation-config.yml`. Translators edit only Translation blocks in
`tree/**/translation.md`. `sources/`, `builds/`, and generated tree metadata are
maintained by the DSW KM Translation Tool.

CI checks out the exact source commit, synchronizes its KM, rebuilds every
derived artifact, and requires a clean Git diff. Use this mode for a mutable
review branch; switch to an immutable GitHub Release dependency when the source
KM is formally released.

See [docs/maintenance.md](docs/maintenance.md) for bootstrap, update, and
release-cutover commands.
