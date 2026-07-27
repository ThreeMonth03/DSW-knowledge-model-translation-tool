# DSW KM Translation Tool

Python tooling for DSW Knowledge Model source release and translation
maintenance.

For zh-Hant production work, the latest translation state is maintained in
Localize/Weblate. This repository provides automation and visualization around
that workflow:

- mirror Weblate PO exports into a Git translation tree
- rebuild final PO and KM bundles
- validate translation repository configuration
- report Weblate PO health and output alignment
- update to a newer published source KM after validation passes

GitHub-authoritative repositories are also supported without a Weblate
component:

- scaffold an append-only source KM release repository
- generate release manifests and validate immutable package history
- generate a deterministic PO catalog directly from a KM
- synchronize a pinned GitHub KM Release and rebuild a Git-managed translation tree

## Documentation

The documentation workflow publishes the maintainer docs and package API
reference when GitHub Pages is enabled for the repository.

Start here:

- [First-Time Maintainer Guide](docs/first-time-maintainer.md)
- [Maintainer Docs](docs/README.md)

Common references:

- [Architecture](docs/architecture.md)
- [Localize Sync Runbook](docs/localize-sync-runbook.md)
- [KM Update Runbook](docs/km-update-runbook.md)
- [Translation Repository Bootstrap](docs/translation-repository-bootstrap.md)
- [Command Reference](docs/command-reference.md)
- [Development Guidelines](docs/development-guidelines.md)

## Setup

```shell
make install-dev
```

This creates `.venv` and installs the package plus development dependencies
declared through `pyproject.toml` and `config/requirements.txt`.

## Common Commands

Run local checks before pushing tooling changes:

```shell
make check
```

Use `make help` for the common maintainer targets and `make help-all` for
lower-level repair helpers. The targets and Make variables are declared in the
[`Makefile`][makefile].

Read [Command Reference](docs/command-reference.md) before running targets that
rebuild translation output files or write Git commits. Configure workflow secrets
from [Security and Permissions](docs/security-and-permissions.md).

## Local Translation Tree Tools

Local tree commands are available for development, inspection, and repair. By
default they write to the ignored local workspace `translation/zh_Hant/`.
Production translation repositories use their own `translation-config.yml` and
repository layout; see [`examples/translation-config.yml`][example-translation-config].

Use `examples/translation-config-github.yml` when Git, rather than Weblate, is
the translation authority. `dsw-km-init-source-repo` creates the matching source
KM repository scaffold.

[example-translation-config]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/examples/translation-config.yml
[makefile]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/Makefile
