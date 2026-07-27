# Architecture

This document maps the repository to the maintenance problems it solves. Use it
when deciding where a change belongs.

## Top-Level Shape

- [`readme.md`][readme] is the quick-start entry point for this tooling repo.
- [`pyproject.toml`][pyproject] defines the installable package and the
  `dsw-km-*` command-line tools.
- [`Makefile`][makefile] wraps local development checks and the in-repository
  translation-tree workflow.
- [`src/dsw_km_translation_tool/cli/`][cli-dir] contains packaged command-line
  entry points used by Make targets and GitHub Actions.
- [`src/dsw_km_translation_tool/`][package-dir] contains reusable package code.
- [`examples/`][examples-dir] contains workflow templates, translation
  repository docs templates, and an example translation repository config.
- [`docs/sphinx/`][sphinx-dir] contains Sphinx source for the published docs site
  and package reference. The files under `docs/sphinx/maintainer/` are
  include wrappers; edit the maintainer Markdown files under `docs/`.
- [`tests/fixtures/source_inputs/`][source-inputs-fixture-dir] contains offline
  PO/KM inputs for deterministic local tests.
- [`tests/fixtures/translation_tree/`][translation-fixture-dir] contains the checked-in tree, final PO, and
  review diff used by translation round-trip tests.
- [`tests/infra/`][tests-infra-dir] covers tooling, CLI, config, and automation behavior.
- [`tests/translation/`][tests-translation-dir] covers translation-tree and PO/KM round trips.

External production translation repositories usually contain:

```text
translation-config.yml
sources/localize/
sources/knowledge-models/
tree/
builds/
reviews/
```

The tooling repo should be able to run against that layout without keeping
production translation state in the repository root.

## PO, KM, and Tree Layer

These modules handle the local representation of translation data:

- [`po.py`][po-py]: reads and writes PO entries.
- [`dsw_models_adapter.py`][dsw-models-adapter-py]: adapts DSW KM JSON events into a structure the tools
  can inspect.
- [`tree.py`][tree-py], [`outline.py`][outline-py], [`workflow.py`][workflow-py]: export and inspect the
  translator-facing folder tree.
- [`shared_blocks/`][shared-blocks-dir], [`sync.py`][sync-py], [`review.py`][review-py]: synchronize repeated strings,
  rebuild generated PO files, and produce review diffs.
- [`knowledge_model_service.py`][knowledge-model-service-py]: applies translated PO content back into a KM
  bundle.

Keep translator-facing Markdown stable. If a parser change affects field order,
folder names, or shared-block behavior, add focused tests before updating
fixtures.

## Localize/Weblate Sync Layer

These modules connect the translation repository to the Weblate website:

- [`translation_repository_config.py`][translation-repository-config-py]: loads `translation-config.yml` and
  computes repository paths.
- [`localize_sync.py`][localize-sync-py]: downloads the current Weblate PO
  snapshot into the translation repository.
- [`localize_status.py`][localize-status-py]: reports PO completion, empty strings, and Weblate
  review-state counts without modifying translations.
- [`weblate_checks.py`][weblate-checks-py]: reports Weblate units matching quality-check queries
  such as `has:check` without changing translations.
- [`alignment_status.py`][alignment-status-py]: verifies that Weblate, the checked-in Localize PO,
  the translation tree, the final PO, and the final KM are mutually aligned.
- [`localize_tree_sync.py`][localize-tree-sync-py]: force-refreshes `tree/` from the latest Weblate PO.
- [`github_translation_contributions.py`][github-translation-contributions-py] and
  [`weblate_upload.py`][weblate-upload-py]: report reviewed GitHub translation
  edits and upload safe post-merge imports to Weblate.
- [`translation_format.py`][translation-format-py]: compares source and
  translated Markdown structure before GitHub contributions can be imported.
- [`ci_sync.py`][ci-sync-py], [`repository_ci_sync.py`][repository-ci-sync-py]: rebuild the translation tree, final PO,
  and final KM, then make Git sync commits.
- [`translation_repository_bootstrap.py`][translation-repository-bootstrap-py]: scaffolds a new translation
  repository and hydrates it from Registry/Weblate inputs without committing or
  pushing.
- `km_catalog.py` generates a deterministic Git-managed catalog directly from a
  source KM, carrying translations only when UUID, field, and source text remain
  unchanged.
- `github_release.py` verifies versioned KM GitHub Release assets against their
  checksum sidecars and expected DSW package identity.
- `github_translation_source.py` checks or synchronizes the pinned release for a
  Git-authoritative translation repository, then rebuilds derived outputs.
- `km_release.py` validates append-only source KM history, release manifests,
  checksums, and Git tag/version alignment.
- `km_release_history.py` resolves and downloads the previous GitHub Release,
  then delegates immutable-history validation to `km_release.py`.
- `km_source_repository_scaffold.py` renders a source KM repository whose
  branches are mutable but whose tags and published KM packages are immutable.
- `translation_repository_build.py` rebuilds Git-authoritative translation
  outputs without network or Weblate access.
- [`translation_repository_scaffold.py`][translation-repository-scaffold-py]: renders, checks, and
  refreshes managed translation repository docs and workflows without changing
  repository config or translations.
- [`km_bundle_sync.py`][km-bundle-sync-py], [`km_latest_sync.py`][km-latest-sync-py], [`km_registry.py`][km-registry-py]: support KM bundle
  discovery and update operations.
- [`command.py`][command-py]: shared subprocess and Git identity helpers used by automation
  writers.

This layer supports the Weblate-to-Git production sync flow. Operational steps
belong in [Localize Sync Runbook](localize-sync-runbook.md).

## GitHub Actions Layer

- [`.github/workflows/unittest.yml`][unittest-workflow] validates this tooling repository.
- [`.github/workflows/upstream_smoke.yml`][upstream-smoke-workflow] checks the current
  upstream Registry KM and Weblate PO without writing to a translation repo.
- [`examples/github-actions/localize_auto_sync_template.yml`][localize-auto-sync-template] is the
  rendered sync workflow template for dedicated translation repositories.
- [`examples/github-actions/github_translation_import_template.yml`][github-import-template] is the
  guarded post-merge workflow for importing reviewed GitHub translation edits
  to Weblate.
- [`examples/github-actions/localize_status_report_template.yml`][localize-status-template] is the
  read-only status workflow for scheduled Localize/Weblate health reports.
- [`examples/github-actions/localize_alignment_report_template.yml`][localize-alignment-template] is the
  read-only output alignment workflow.
- [`examples/github-actions/km_version_auto_update_template.yml`][km-auto-update-template] is the guarded
  KM Registry writer. Its safety checks are documented in
  [KM Update Runbook](km-update-runbook.md).
- [`examples/github-actions/validate_translation_config_template.yml`][validate-config-template] is the
  read-only config validation workflow for dedicated translation repositories.
- `examples/github-actions-github/` contains the Weblate-free translation CI
  profile.
- `examples/km-source-repository/` contains source KM validation and tag-release
  workflows.

Keep GitHub Actions as orchestration. Branch selection, recovery, GitHub
translation import decisions, KM generation, and commit decisions belong in
Python helpers. Use
[Workflow Templates](workflow-templates.md) when rendering or updating templates
in translation repositories. Workflows that write the tracking branch or
Weblate share one concurrency group with a retained queue. Post-merge imports
still revalidate Weblate before upload because external website edits are not
controlled by the GitHub queue.

## Ownership Rules

- If a change affects Localize/Weblate download or GitHub import conflict
  policy, it belongs in the Localize sync layer and must be reflected in the
  runbook.
- If a change affects tree format, shared strings, generated PO, or KM output,
  it belongs in the PO/KM/tree layer and needs round-trip tests.
- If a translation repository needs a new workflow behavior, add it to the
  external template first, then use scaffold sync to render it into the target
  repo.
- If a new translation repository needs different default docs or scaffolded
  files, update `examples/translation-repository/` and the bootstrap tests.
- After changing a workflow or repository template, run scaffold check against
  the production translation repository.
- If a command changes, update [Command Reference](command-reference.md).

[alignment-status-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/alignment_status.py
[ci-sync-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/ci_sync.py
[command-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/command.py
[dsw-models-adapter-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/dsw_models_adapter.py
[examples-dir]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/examples
[github-import-template]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/examples/github-actions/github_translation_import_template.yml
[github-translation-contributions-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/github_translation_contributions.py
[km-auto-update-template]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/examples/github-actions/km_version_auto_update_template.yml
[km-bundle-sync-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/km_bundle_sync.py
[km-latest-sync-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/km_latest_sync.py
[km-registry-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/km_registry.py
[knowledge-model-service-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/knowledge_model_service.py
[localize-alignment-template]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/examples/github-actions/localize_alignment_report_template.yml
[localize-auto-sync-template]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/examples/github-actions/localize_auto_sync_template.yml
[localize-status-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/localize_status.py
[localize-status-template]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/examples/github-actions/localize_status_report_template.yml
[localize-sync-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/localize_sync.py
[localize-tree-sync-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/localize_tree_sync.py
[makefile]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/Makefile
[outline-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/outline.py
[package-dir]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/src/dsw_km_translation_tool
[po-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/po.py
[pyproject]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/pyproject.toml
[readme]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/readme.md
[repository-ci-sync-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/repository_ci_sync.py
[review-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/review.py
[shared-blocks-dir]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/src/dsw_km_translation_tool/shared_blocks
[sphinx-dir]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/docs/sphinx
[source-inputs-fixture-dir]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/tests/fixtures/source_inputs
[cli-dir]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/src/dsw_km_translation_tool/cli
[sync-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/sync.py
[tests-infra-dir]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/tests/infra
[tests-translation-dir]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/tests/translation
[translation-fixture-dir]: https://github.com/ThreeMonth03/dsw-km-translation-tool/tree/master/tests/fixtures/translation_tree
[translation-repository-bootstrap-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/translation_repository_bootstrap.py
[translation-repository-scaffold-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/translation_repository_scaffold.py
[translation-repository-config-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/translation_repository_config.py
[translation-format-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/translation_format.py
[tree-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/tree.py
[unittest-workflow]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/.github/workflows/unittest.yml
[upstream-smoke-workflow]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/.github/workflows/upstream_smoke.yml
[validate-config-template]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/examples/github-actions/validate_translation_config_template.yml
[weblate-checks-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/weblate_checks.py
[weblate-upload-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/weblate_upload.py
[workflow-py]: https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/src/dsw_km_translation_tool/workflow.py
