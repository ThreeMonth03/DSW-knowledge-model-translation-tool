VENV_DIR ?= .venv
VENV_PYTHON := $(VENV_DIR)/bin/python
VENV_BIN := $(VENV_DIR)/bin
BOOTSTRAP_PYTHON ?= python3
PYTHON ?= $(VENV_PYTHON)
PIP := $(PYTHON) -m pip
DSW_KM_DISCOVER_VERSIONS := $(VENV_BIN)/dsw-km-discover-versions
DSW_KM_BUILD_TRANSLATION_REPO := $(VENV_BIN)/dsw-km-build-translation-repo
DSW_KM_BUILD_LEGAL_DRAFT := $(VENV_BIN)/dsw-km-build-legal-draft
DSW_KM_CATALOG_FROM_KM := $(VENV_BIN)/dsw-km-catalog-from-km
DSW_KM_EXPORT_TREE := $(VENV_BIN)/dsw-km-export-tree
DSW_KM_INIT_SOURCE_REPO := $(VENV_BIN)/dsw-km-init-source-repo
DSW_KM_INIT_TRANSLATION_REPO := $(VENV_BIN)/dsw-km-init-translation-repo
DSW_KM_IMPORT_GITHUB_TRANSLATIONS := $(VENV_BIN)/dsw-km-import-github-translations
DSW_KM_PO_TO_KM := $(VENV_BIN)/dsw-km-po-to-km
DSW_KM_PREPARE_RELEASE := $(VENV_BIN)/dsw-km-prepare-release
DSW_KM_PULL_BUNDLE := $(VENV_BIN)/dsw-km-pull-bundle
DSW_KM_PULL_LOCALIZE_PO := $(VENV_BIN)/dsw-km-pull-localize-po
DSW_KM_REPORT_ALIGNMENT := $(VENV_BIN)/dsw-km-report-alignment
DSW_KM_REPORT_GITHUB_TRANSLATIONS := $(VENV_BIN)/dsw-km-report-github-translations
DSW_KM_REPORT_LOCALIZE_STATUS := $(VENV_BIN)/dsw-km-report-localize-status
DSW_KM_REPORT_WEBLATE_CHECKS := $(VENV_BIN)/dsw-km-report-weblate-checks
DSW_KM_REVIEW_PO := $(VENV_BIN)/dsw-km-review-po
DSW_KM_SCAFFOLD := $(VENV_BIN)/dsw-km-scaffold
DSW_KM_STATUS := $(VENV_BIN)/dsw-km-status
DSW_KM_SYNC_LATEST_KM := $(VENV_BIN)/dsw-km-sync-latest-km
DSW_KM_SYNC_GITHUB_RELEASE := $(VENV_BIN)/dsw-km-sync-github-release
DSW_KM_SYNC_GIT_SOURCE := $(VENV_BIN)/dsw-km-sync-git-source
DSW_KM_SYNC_LOCALIZE := $(VENV_BIN)/dsw-km-sync-localize
DSW_KM_SYNC_REPOSITORY_SHARED_STRINGS := $(VENV_BIN)/dsw-km-sync-repository-shared-strings
DSW_KM_SYNC_SHARED_STRINGS := $(VENV_BIN)/dsw-km-sync-shared-strings
DSW_KM_TREE_TO_PO := $(VENV_BIN)/dsw-km-tree-to-po
DSW_KM_UPSTREAM_SMOKE := $(VENV_BIN)/dsw-km-upstream-smoke
DSW_KM_VALIDATE_CONFIG := $(VENV_BIN)/dsw-km-validate-config
DSW_KM_VALIDATE_RELEASE := $(VENV_BIN)/dsw-km-validate-release
DSW_KM_WORKFLOW := $(VENV_BIN)/dsw-km-workflow

PO ?= tests/fixtures/source_inputs/common_dsw_zh_Hant.po
MODEL ?= tests/fixtures/source_inputs/dsw_root_2.7.0.km
SOURCE_LANG ?= en
TARGET_LANG ?= zh_Hant
OUTPUT_ROOT ?= translation/$(TARGET_LANG)
TREE_DIR ?= $(OUTPUT_ROOT)/tree
FINAL_PO ?= $(OUTPUT_ROOT)/builds/final_translated.po
FINAL_KM ?= $(OUTPUT_ROOT)/builds/final_translated.km
REPORT ?= $(OUTPUT_ROOT)/reports/final_report.json
TREE_JSON ?= $(OUTPUT_ROOT)/reports/tree_snapshot.json
REVIEW_DIFF ?= $(OUTPUT_ROOT)/reviews/final_translated.diff
OUTLINE_MD ?= $(TREE_DIR)/outline.md
SHARED_BLOCKS_OUTLINE_MD ?= $(TREE_DIR)/shared_blocks_outline.md
REVIEW_FLAGS ?=
PO_TO_KM_FLAGS ?=
STATUS_LIMIT ?= 5
SYNC_GROUP ?= shared-block
LOCALIZE_PO ?= sources/localize/zh_Hant/latest.po
LOCALIZE_STATUS_JSON ?= reviews/localize_status_report.json
LOCALIZE_STATUS_MD ?= reviews/localize_status_report.md
WEBLATE_CHECK_QUERY ?= has:check
WEBLATE_CHECKS_JSON ?= reviews/weblate_checks_report.json
WEBLATE_CHECKS_MD ?= reviews/weblate_checks_report.md
ALIGNMENT_JSON ?= reviews/localize_alignment_report.json
ALIGNMENT_MD ?= reviews/localize_alignment_report.md
ALIGNMENT_ARTIFACT_DIR ?= reviews/localize_alignment_artifacts
KM_DISCOVERY_JSON ?= reviews/km_version_discovery.json
KM_DISCOVERY_MD ?= reviews/km_version_discovery.md
KM_AUTO_UPDATE_JSON ?= reviews/km_auto_update_report.json
KM_AUTO_UPDATE_MD ?= reviews/km_auto_update_report.md
GITHUB_TRANSLATIONS_JSON ?= reviews/github_translation_report.json
GITHUB_TRANSLATIONS_MD ?= reviews/github_translation_report.md
GITHUB_TRANSLATION_BASE_REF ?= origin/$(TRACKING_BRANCH)
GITHUB_TRANSLATION_HEAD_REF ?= HEAD
UPSTREAM_SMOKE_DIR ?= .cache/upstream-smoke
UPSTREAM_SMOKE_JSON ?= $(UPSTREAM_SMOKE_DIR)/upstream_smoke_report.json
UPSTREAM_SMOKE_MD ?= $(UPSTREAM_SMOKE_DIR)/upstream_smoke_report.md
TRANSLATION_REPO_DIR ?=
NEW_TRANSLATION_REPO_DIR ?=
NEW_SOURCE_REPO_DIR ?=
SOURCE_ORGANIZATION_ID ?=
SOURCE_KM_ID ?=
SOURCE_KM_NAME ?=
SOURCE_INITIAL_PARENT_PACKAGE_ID ?=
SOURCE_TOOLING_REPOSITORY ?= ThreeMonth03/dsw-km-translation-tool
SOURCE_TOOLING_REF ?= master
TRANSLATION_CONFIG ?= translation-config.yml
TRANSLATION_CONFIG_TEMPLATE ?= examples/translation-config.yml
TRACKING_BRANCH ?= master
TARGET_BRANCH ?=
RESTORE_SOURCE_REF ?= origin/$(TRACKING_BRANCH)
SPHINXBUILD ?= $(PYTHON) -m sphinx
SPHINXOPTS ?= -W --keep-going
DOCS_SOURCE ?= docs/sphinx
DOCS_BUILD ?= docs/sphinx/_build/html

.PHONY: help help-all require-translation-repo require-new-translation-repo require-source-repo-dir require-new-source-repo require-target-branch
.PHONY: venv install-dev install-hooks check compile format format-check lint
.PHONY: test test-infra test-translation docs docs-clean
.PHONY: repo-validate repo-pull-po repo-status repo-checks repo-align
.PHONY: source-repo-init source-repo-prepare source-repo-validate
.PHONY: repo-github-source-check repo-github-source-sync
.PHONY: repo-scaffold-check repo-scaffold-sync repo-sync-shared-strings
.PHONY: repo-github-translations repo-import-github-translations
.PHONY: repo-init repo-sync repo-sync-branch repo-km-status repo-km-pull repo-km-update upstream-smoke
.PHONY: export-tree export-tree-force status localize-status sync sync-watch
.PHONY: tree-to-po po-to-km review-po validate workflow

venv: $(VENV_PYTHON)

$(VENV_PYTHON):
	$(BOOTSTRAP_PYTHON) -m venv $(VENV_DIR)

help:
	@printf '%s\n' \
	'Common maintainer targets:' \
	'  install-dev        Create $(VENV_DIR) and install dev dependencies' \
	'  check              Run format check, lint, compile, tests, docs, and git diff --check' \
	'  docs               Build Sphinx docs into $(DOCS_BUILD)' \
	'  format             Auto-fix imports/style and format Python files' \
	'' \
	'Translation repository targets; set TRANSLATION_REPO_DIR=/path/to/repo:' \
	'  repo-validate      Validate translation-config.yml' \
	'  repo-status        Report checked-in Weblate PO health' \
	'  repo-checks        Query Weblate quality checks' \
	'  repo-align         Verify Weblate/tree/final PO/final KM alignment' \
	'  repo-scaffold-check Verify managed docs and workflows match their templates' \
	'  repo-scaffold-sync Writer: refresh managed docs and workflows only' \
	'  repo-sync-shared-strings Writer: expand canonical shared translations into the tree' \
	'  repo-github-translations Report GitHub translation changes against Weblate' \
	'  repo-init          Initialize a new translation repo; set NEW_TRANSLATION_REPO_DIR=/path' \
	'  source-repo-init   Initialize a source KM repo; use the packaged CLI for identity arguments' \
	'  source-repo-prepare Generate release-manifest.yml from an exported KM' \
	'  source-repo-validate Validate a source KM release repository' \
	'  repo-github-source-sync Writer: fetch the pinned GitHub KM release and rebuild' \
	'  repo-sync          Writer: pull Weblate, rebuild outputs, commit/push if changed' \
	'  repo-import-github-translations Writer: import accepted GitHub translations to Weblate' \
	'  repo-km-status     Report whether the Registry has a newer KM' \
	'  repo-km-update     Writer: update to latest KM only after validation passes' \
	'  upstream-smoke     Integration check against current upstream KM and Weblate PO' \
	'' \
	'Local translation-tree development targets:' \
	'  export-tree        Export PO + model into $(TREE_DIR)' \
	'  sync               Sync shared strings and rebuild $(FINAL_PO)' \
	'  status             Show untranslated fields from $(TREE_DIR)' \
	'  workflow           Run the optional end-to-end smoke workflow' \
	'' \
	'Run `make help-all` for lower-level targets and variables.'

help-all:
	@printf '%s\n' \
	'All targets:' \
	'  venv               Create $(VENV_DIR) when it does not exist' \
	'  install-dev        Install local dev dependencies from config/requirements.txt' \
	'  install-hooks      Install local git pre-commit hooks' \
	'  check              Run all local quality gates' \
	'  compile            Run Python syntax compilation checks' \
	'  format             Auto-fix imports/style and format Python files' \
	'  format-check       Check formatting without modifying files' \
	'  lint               Run ruff lint checks' \
	'  test               Run all pytest suites' \
	'  test-infra         Run infrastructure/CLI pytest suites' \
	'  test-translation   Run translation consistency pytest suites' \
	'  docs               Build Sphinx docs into $(DOCS_BUILD)' \
	'  docs-clean         Remove generated Sphinx docs' \
	'  repo-validate      Validate translation-config.yml in TRANSLATION_REPO_DIR' \
	'  repo-pull-po       Refresh sources/localize/ in TRANSLATION_REPO_DIR' \
	'  repo-status        Report checked-in Weblate PO health in TRANSLATION_REPO_DIR' \
	'  repo-checks        Query Weblate quality checks for TRANSLATION_REPO_DIR' \
	'  repo-align         Verify output alignment in TRANSLATION_REPO_DIR' \
	'  repo-scaffold-check Verify managed docs and workflows in TRANSLATION_REPO_DIR' \
	'  repo-scaffold-sync Writer: refresh managed docs and workflows in TRANSLATION_REPO_DIR' \
	'  repo-sync-shared-strings Writer: expand canonical shared translations into the tree' \
	'  repo-github-translations Report GitHub translation changes against Weblate' \
	'  repo-init          Initialize NEW_TRANSLATION_REPO_DIR from templates and upstream inputs' \
	'  source-repo-init   Initialize NEW_SOURCE_REPO_DIR from source KM templates' \
	'  source-repo-prepare Generate release-manifest.yml in NEW_SOURCE_REPO_DIR' \
	'  source-repo-validate Validate KM history and release metadata in NEW_SOURCE_REPO_DIR' \
	'  repo-github-source-check Verify a checked-in GitHub source release' \
	'  repo-github-source-sync Writer: fetch a pinned GitHub release and rebuild outputs' \
	'  repo-sync          Writer: sync Weblate to Git in TRANSLATION_REPO_DIR' \
	'  repo-sync-branch   Writer: sync Weblate to TARGET_BRANCH for PR repair' \
	'  repo-import-github-translations Writer: import merged GitHub translations to Weblate' \
	'  repo-km-status     Discover KM Registry versions for TRANSLATION_REPO_DIR' \
	'  repo-km-pull       Writer: refresh the configured source KM bundle' \
	'  repo-km-update     Writer: guarded latest-KM update for TRANSLATION_REPO_DIR' \
	'  upstream-smoke     Integration check against current upstream KM and Weblate PO' \
	'  export-tree        Export PO + model into $(TREE_DIR) and refresh shared-block files' \
	'  export-tree-force  Force rebuild $(TREE_DIR)' \
	'  status             Show untranslated fields from $(TREE_DIR)' \
	'  localize-status    Report Localize/Weblate PO status from $(LOCALIZE_PO)' \
	'  sync               Sync shared strings and refresh $(FINAL_PO)' \
	'  sync-watch         Watch editable inputs with watchdog' \
	'  tree-to-po         Build $(FINAL_PO) from $(TREE_DIR)' \
	'  po-to-km           Build $(FINAL_KM) from $(FINAL_PO) + $(MODEL)' \
	'  review-po          Review how $(FINAL_PO) differs from $(PO)' \
	'  validate           Validate $(FINAL_PO) against $(MODEL)' \
	'  workflow           Run the optional end-to-end smoke workflow'

require-translation-repo:
	@if [ -z "$(TRANSLATION_REPO_DIR)" ]; then \
		printf '%s\n' 'Set TRANSLATION_REPO_DIR=/path/to/dsw-root-locales-zh_Hant' >&2; \
		exit 2; \
	fi

require-new-translation-repo:
	@if [ -z "$(NEW_TRANSLATION_REPO_DIR)" ]; then \
		printf '%s\n' 'Set NEW_TRANSLATION_REPO_DIR=/path/to/new-translation-repo' >&2; \
		exit 2; \
	fi

require-new-source-repo:
	@if [ -z "$(NEW_SOURCE_REPO_DIR)" ] || \
		[ -z "$(SOURCE_ORGANIZATION_ID)" ] || \
		[ -z "$(SOURCE_KM_ID)" ] || \
		[ -z "$(SOURCE_KM_NAME)" ] || \
		[ -z "$(SOURCE_INITIAL_PARENT_PACKAGE_ID)" ]; then \
		printf '%s\n' \
			'Set NEW_SOURCE_REPO_DIR, SOURCE_ORGANIZATION_ID, SOURCE_KM_ID,' \
			'SOURCE_KM_NAME, and SOURCE_INITIAL_PARENT_PACKAGE_ID.' >&2; \
		exit 2; \
	fi

require-source-repo-dir:
	@if [ -z "$(NEW_SOURCE_REPO_DIR)" ]; then \
		printf '%s\n' 'Set NEW_SOURCE_REPO_DIR=/path/to/source-km-repository' >&2; \
		exit 2; \
	fi

require-target-branch:
	@if [ -z "$(TARGET_BRANCH)" ]; then \
		printf '%s\n' 'Set TARGET_BRANCH=<same-repository-branch-name>' >&2; \
		exit 2; \
	fi

install-dev: venv
	$(PIP) install -r config/requirements.txt

install-hooks: venv
	$(PYTHON) -m pre_commit install

check: format-check lint compile test docs
	git diff --check

compile: venv
	$(PYTHON) -m compileall -q src tests

format: venv
	$(PYTHON) -m ruff check --config config/ruff.toml --fix src tests
	$(PYTHON) -m ruff format --config config/ruff.toml src tests

format-check: venv
	$(PYTHON) -m ruff format --check --config config/ruff.toml src tests

lint: venv
	$(PYTHON) -m ruff check --config config/ruff.toml src tests

test: test-infra test-translation

test-infra: venv
	$(PYTHON) -m pytest tests/infra

test-translation: venv
	$(PYTHON) -m pytest tests/translation

docs: venv
	rm -rf $(DOCS_BUILD)
	$(SPHINXBUILD) $(SPHINXOPTS) -b html $(DOCS_SOURCE) $(DOCS_BUILD)

docs-clean:
	rm -rf docs/sphinx/_build

repo-validate: venv require-translation-repo
	$(DSW_KM_VALIDATE_CONFIG) \
		--config "$(TRANSLATION_REPO_DIR)/$(TRANSLATION_CONFIG)"

repo-pull-po: venv require-translation-repo
	$(DSW_KM_PULL_LOCALIZE_PO) \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--config "$(TRANSLATION_CONFIG)"

repo-status: venv require-translation-repo
	$(DSW_KM_REPORT_LOCALIZE_STATUS) \
		--po "$(TRANSLATION_REPO_DIR)/$(LOCALIZE_PO)" \
		--json-out "$(TRANSLATION_REPO_DIR)/$(LOCALIZE_STATUS_JSON)" \
		--details-out "$(TRANSLATION_REPO_DIR)/$(LOCALIZE_STATUS_MD)"

repo-checks: venv require-translation-repo
	$(DSW_KM_REPORT_WEBLATE_CHECKS) \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--config "$(TRANSLATION_CONFIG)" \
		--query "$(WEBLATE_CHECK_QUERY)" \
		--json-out "$(TRANSLATION_REPO_DIR)/$(WEBLATE_CHECKS_JSON)" \
		--details-out "$(TRANSLATION_REPO_DIR)/$(WEBLATE_CHECKS_MD)" \
		--allow-api-failure

repo-align: venv require-translation-repo
	$(DSW_KM_REPORT_ALIGNMENT) \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--config "$(TRANSLATION_CONFIG)" \
		--json-out "$(TRANSLATION_REPO_DIR)/$(ALIGNMENT_JSON)" \
		--details-out "$(TRANSLATION_REPO_DIR)/$(ALIGNMENT_MD)" \
		--artifact-dir "$(TRANSLATION_REPO_DIR)/$(ALIGNMENT_ARTIFACT_DIR)" \
		--fail-on-mismatch

repo-scaffold-check: venv require-translation-repo
	$(DSW_KM_SCAFFOLD) check \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--tooling-repo "$(CURDIR)" \
		--config "$(TRANSLATION_CONFIG)"

repo-scaffold-sync: venv require-translation-repo
	$(DSW_KM_SCAFFOLD) sync \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--tooling-repo "$(CURDIR)" \
		--config "$(TRANSLATION_CONFIG)"

repo-sync-shared-strings: venv require-translation-repo
	$(DSW_KM_SYNC_REPOSITORY_SHARED_STRINGS) \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--config "$(TRANSLATION_CONFIG)"

repo-github-translations: venv require-translation-repo
	$(DSW_KM_REPORT_GITHUB_TRANSLATIONS) \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--config "$(TRANSLATION_CONFIG)" \
		--base-ref "$(GITHUB_TRANSLATION_BASE_REF)" \
		--head-ref "$(GITHUB_TRANSLATION_HEAD_REF)" \
		--json-out "$(TRANSLATION_REPO_DIR)/$(GITHUB_TRANSLATIONS_JSON)" \
		--details-out "$(TRANSLATION_REPO_DIR)/$(GITHUB_TRANSLATIONS_MD)"

repo-import-github-translations: venv require-translation-repo
	$(DSW_KM_IMPORT_GITHUB_TRANSLATIONS) \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--config "$(TRANSLATION_CONFIG)" \
		--base-ref "$(GITHUB_TRANSLATION_BASE_REF)" \
		--head-ref "$(GITHUB_TRANSLATION_HEAD_REF)" \
		--json-out "$(TRANSLATION_REPO_DIR)/$(GITHUB_TRANSLATIONS_JSON)" \
		--details-out "$(TRANSLATION_REPO_DIR)/$(GITHUB_TRANSLATIONS_MD)"

repo-init: venv require-new-translation-repo
	$(DSW_KM_INIT_TRANSLATION_REPO) \
		--repo-root "$(NEW_TRANSLATION_REPO_DIR)" \
		--tooling-repo "$(CURDIR)" \
		--config-template "$(TRANSLATION_CONFIG_TEMPLATE)"

source-repo-validate: venv require-source-repo-dir
	$(DSW_KM_VALIDATE_RELEASE) \
		--repo-root "$(NEW_SOURCE_REPO_DIR)" \
		--allow-unreleased

source-repo-prepare: venv require-source-repo-dir
	$(DSW_KM_PREPARE_RELEASE) \
		--repo-root "$(NEW_SOURCE_REPO_DIR)"

source-repo-init: venv require-new-source-repo
	$(DSW_KM_INIT_SOURCE_REPO) \
		--repo-root "$(NEW_SOURCE_REPO_DIR)" \
		--tooling-repo "$(CURDIR)" \
		--organization-id "$(SOURCE_ORGANIZATION_ID)" \
		--km-id "$(SOURCE_KM_ID)" \
		--name "$(SOURCE_KM_NAME)" \
		--initial-parent-package-id "$(SOURCE_INITIAL_PARENT_PACKAGE_ID)" \
		--tooling-repository "$(SOURCE_TOOLING_REPOSITORY)" \
		--tooling-ref "$(SOURCE_TOOLING_REF)"

repo-github-source-check: venv require-translation-repo
	$(DSW_KM_SYNC_GITHUB_RELEASE) \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--config "$(TRANSLATION_CONFIG)" \
		--check \
		--allow-unreleased

repo-github-source-sync: venv require-translation-repo
	$(DSW_KM_SYNC_GITHUB_RELEASE) \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--config "$(TRANSLATION_CONFIG)"

repo-sync: venv require-translation-repo
	$(DSW_KM_SYNC_LOCALIZE) \
		--host-repo "$(TRANSLATION_REPO_DIR)" \
		--tooling-repo "$(CURDIR)" \
		--config "$(TRANSLATION_CONFIG)" \
		--translation-root . \
		--target-ref "$(TRACKING_BRANCH)" \
		--mode schedule

repo-sync-branch: venv require-translation-repo require-target-branch
	$(DSW_KM_SYNC_LOCALIZE) \
		--host-repo "$(TRANSLATION_REPO_DIR)" \
		--tooling-repo "$(CURDIR)" \
		--config "$(TRANSLATION_CONFIG)" \
		--translation-root . \
		--target-ref "$(TARGET_BRANCH)" \
		--restore-source-ref "$(RESTORE_SOURCE_REF)" \
		--mode pull_request

repo-km-status: venv require-translation-repo
	$(DSW_KM_DISCOVER_VERSIONS) \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--config "$(TRANSLATION_CONFIG)" \
		--report "$(KM_DISCOVERY_JSON)" \
		--details-out "$(KM_DISCOVERY_MD)"

repo-km-pull: venv require-translation-repo
	$(DSW_KM_PULL_BUNDLE) \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--config "$(TRANSLATION_CONFIG)"

repo-km-update: venv require-translation-repo
	$(DSW_KM_SYNC_LATEST_KM) \
		--repo-root "$(TRANSLATION_REPO_DIR)" \
		--tooling-repo "$(CURDIR)" \
		--config "$(TRANSLATION_CONFIG)" \
		--target-ref "$(TRACKING_BRANCH)" \
		--report "$(TRANSLATION_REPO_DIR)/$(KM_AUTO_UPDATE_JSON)" \
		--details-out "$(TRANSLATION_REPO_DIR)/$(KM_AUTO_UPDATE_MD)" \
		--skip-without-token

upstream-smoke: venv
	$(DSW_KM_UPSTREAM_SMOKE) \
		--work-dir "$(UPSTREAM_SMOKE_DIR)" \
		--config examples/translation-config.yml \
		--report "$(UPSTREAM_SMOKE_JSON)" \
		--details-out "$(UPSTREAM_SMOKE_MD)"

export-tree: venv
	$(DSW_KM_EXPORT_TREE) \
		--po $(PO) \
		--json $(MODEL) \
		--out-dir $(TREE_DIR) \
		--shared-blocks-dir-out $(TREE_DIR)/shared_blocks \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)

export-tree-force: venv
	$(DSW_KM_EXPORT_TREE) \
		--po $(PO) \
		--json $(MODEL) \
		--out-dir $(TREE_DIR) \
		--shared-blocks-dir-out $(TREE_DIR)/shared_blocks \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		--force

status: venv
	$(DSW_KM_STATUS) \
		--tree-dir $(TREE_DIR) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		-k $(STATUS_LIMIT)

localize-status: venv
	$(DSW_KM_REPORT_LOCALIZE_STATUS) \
		--po $(LOCALIZE_PO) \
		--json-out $(LOCALIZE_STATUS_JSON)

sync: venv
	$(DSW_KM_SYNC_SHARED_STRINGS) \
		--tree-dir $(TREE_DIR) \
		--original-po $(PO) \
		--out-po $(FINAL_PO) \
		--diff-out $(REVIEW_DIFF) \
		--outline-out $(OUTLINE_MD) \
		--shared-blocks-dir-out $(TREE_DIR)/shared_blocks \
		--shared-blocks-outline-out $(SHARED_BLOCKS_OUTLINE_MD) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		--group-by $(SYNC_GROUP)

sync-watch: venv
	$(DSW_KM_SYNC_SHARED_STRINGS) \
		--tree-dir $(TREE_DIR) \
		--original-po $(PO) \
		--out-po $(FINAL_PO) \
		--diff-out $(REVIEW_DIFF) \
		--outline-out $(OUTLINE_MD) \
		--shared-blocks-dir-out $(TREE_DIR)/shared_blocks \
		--shared-blocks-outline-out $(SHARED_BLOCKS_OUTLINE_MD) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		--group-by $(SYNC_GROUP) \
		--watch

tree-to-po: venv
	$(DSW_KM_TREE_TO_PO) \
		--tree-dir $(TREE_DIR) \
		--original-po $(PO) \
		--out-po $(FINAL_PO) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)

po-to-km: venv
	$(DSW_KM_PO_TO_KM) \
		--translated-po $(FINAL_PO) \
		--original-km $(MODEL) \
		--out-km $(FINAL_KM) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG) \
		$(PO_TO_KM_FLAGS)

review-po: venv
	$(DSW_KM_REVIEW_PO) \
		--original-po $(PO) \
		--generated-po $(FINAL_PO) \
		--diff-out $(REVIEW_DIFF) \
		$(REVIEW_FLAGS) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)

validate: venv
	$(DSW_KM_EXPORT_TREE) \
		--po $(FINAL_PO) \
		--json $(MODEL) \
		--report-out $(REPORT) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)

workflow: venv
	$(DSW_KM_WORKFLOW) \
		--po $(PO) \
		--json $(MODEL) \
		--tree-dir $(TREE_DIR) \
		--final-po $(FINAL_PO) \
		--report-out $(REPORT) \
		--source-lang $(SOURCE_LANG) \
		--target-lang $(TARGET_LANG)
