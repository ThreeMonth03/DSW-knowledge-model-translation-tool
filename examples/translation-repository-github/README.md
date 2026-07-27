# {{TARGET_LANGUAGE_LABEL}} translation of {{SOURCE_KM_ID}}

This repository is the Git-authoritative {{TARGET_LANGUAGE_LABEL}} translation
of `{{SOURCE_KM_ID}}`. It intentionally has no Weblate dependency.

Current source:

- repository: `{{SOURCE_REPOSITORY}}`
- ref: `{{SOURCE_REF}}`
- planned KM version: `{{SOURCE_VERSION}}`

The repository may remain uninitialized until the first source KM is released.
Once initialized, translators edit only Translation blocks in
`tree/**/translation.md`. `sources/`, `builds/`, and generated tree metadata are
maintained by the DSW KM Translation Tool.

CI verifies that the checked-in source KM is byte-for-byte identical to the
pinned GitHub Release asset.

See [docs/maintenance.md](docs/maintenance.md) for bootstrap, update, and release
commands.
