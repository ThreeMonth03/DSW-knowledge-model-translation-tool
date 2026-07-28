"""Structured data-model exports grouped by translation-tooling concern."""

from .knowledge_model import KnowledgeModelPackageIdentityMapping, ModelInfo, TreeNode
from .po import (
    PoBlock,
    PoDiffReviewResult,
    PoEntry,
    PoReference,
    PoReferenceSection,
    PoTranslationGroup,
)
from .sync import SharedStringCandidate, SharedStringConflict, SharedStringSyncResult
from .tree import (
    OutlineBuildResult,
    SharedBlocksDirectoryBuildResult,
    SharedBlocksOutlineBuildResult,
    TranslationFieldState,
    TranslationStatusFolder,
    TranslationStatusReport,
    TranslationStatusSummary,
    TreeFolderSnapshot,
    TreeScanResult,
    TreeValidationResult,
)
from .workflow import KmBuildResult, PoBuildResult, WorkflowContext

__all__ = [
    "ModelInfo",
    "KnowledgeModelPackageIdentityMapping",
    "KmBuildResult",
    "OutlineBuildResult",
    "PoBlock",
    "PoBuildResult",
    "PoDiffReviewResult",
    "PoEntry",
    "PoReference",
    "PoReferenceSection",
    "PoTranslationGroup",
    "SharedStringCandidate",
    "SharedStringConflict",
    "SharedStringSyncResult",
    "SharedBlocksDirectoryBuildResult",
    "SharedBlocksOutlineBuildResult",
    "TranslationFieldState",
    "TranslationStatusFolder",
    "TranslationStatusReport",
    "TranslationStatusSummary",
    "TreeFolderSnapshot",
    "TreeNode",
    "TreeScanResult",
    "TreeValidationResult",
    "WorkflowContext",
]
