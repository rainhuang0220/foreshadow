"""Optional mini-SWE-agent backend. Not vendored; extra must be installed."""

from __future__ import annotations

import importlib.util

from foreshadow.contribution.executor import (
    BackendNotInstalled,
    ContributionJob,
    PatchArtifact,
)

_EXTRA_NAMES = ("minisweagent", "mini_swe_agent", "mini_swe")


def _extra_available() -> bool:
    return any(importlib.util.find_spec(name) is not None for name in _EXTRA_NAMES)


def _require() -> None:
    if _extra_available():
        return
    raise BackendNotInstalled(
        "mini_swe_agent backend is not installed. "
        "Install the extra to enable it; Foreshadow does not vendor mini-SWE-agent."
    )


class MiniSweExecutor:
    name = "mini_swe_agent"

    def __init__(self) -> None:
        _require()

    def prepare(self, job: ContributionJob) -> None:
        _require()
        raise BackendNotInstalled("mini_swe_agent adapter is not wired in this build")

    def analyze(self, job: ContributionJob) -> None:
        _require()
        raise BackendNotInstalled("mini_swe_agent adapter is not wired in this build")

    def implement(self, job: ContributionJob) -> None:
        _require()
        raise BackendNotInstalled("mini_swe_agent adapter is not wired in this build")

    def test(self, job: ContributionJob) -> None:
        _require()
        raise BackendNotInstalled("mini_swe_agent adapter is not wired in this build")

    def iterate(self, job: ContributionJob) -> None:
        _require()
        raise BackendNotInstalled("mini_swe_agent adapter is not wired in this build")

    def produce_patch(self, job: ContributionJob) -> PatchArtifact:
        _require()
        raise BackendNotInstalled("mini_swe_agent adapter is not wired in this build")
