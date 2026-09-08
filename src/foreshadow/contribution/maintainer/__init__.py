"""Maintainer-facing output: deny-by-default projection, lint, and remote gate.

Internal discovery, ranking, and executor metadata must not reach a third-party
GitHub PR. Callers pass a MaintainerDraftContext — never a raw StructuredTask.
"""

from foreshadow.contribution.maintainer.context import (
    MaintainerDraftContext,
    project_maintainer_context,
)
from foreshadow.contribution.maintainer.draft import (
    MaintainerDraft,
    compose_and_gate,
    compose_maintainer_draft,
)
from foreshadow.contribution.maintainer.gate import (
    GateResult,
    assert_remote_submission_allowed,
    evaluate_maintainer_output,
    evaluate_remote_submission,
    prepare_remote_submission,
)
from foreshadow.contribution.maintainer.revise import revise_package_draft

__all__ = [
    "GateResult",
    "MaintainerDraft",
    "MaintainerDraftContext",
    "assert_remote_submission_allowed",
    "compose_and_gate",
    "compose_maintainer_draft",
    "evaluate_maintainer_output",
    "evaluate_remote_submission",
    "prepare_remote_submission",
    "project_maintainer_context",
    "revise_package_draft",
]
