"""Contribution executor: sandbox, patch, quality gate. Never pushes or opens PRs."""

from foreshadow.contribution.executor import (
    BackendNotInstalled,
    ContributionError,
    ContributionExecutor,
    ContributionJob,
    JobStatus,
    PatchArtifact,
    RemoteWriteRefused,
    get_executor,
    refuse_remote,
    run_contribution,
)
from foreshadow.contribution.native import NativeExecutor
from foreshadow.contribution.package import build_package
from foreshadow.contribution.qa import gate
from foreshadow.contribution.task import StructuredTask, from_entry

__all__ = [
    "BackendNotInstalled",
    "ContributionError",
    "ContributionExecutor",
    "ContributionJob",
    "JobStatus",
    "NativeExecutor",
    "PatchArtifact",
    "RemoteWriteRefused",
    "StructuredTask",
    "build_package",
    "from_entry",
    "gate",
    "get_executor",
    "refuse_remote",
    "run_contribution",
]
