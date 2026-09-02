"""Optional OpenHands backend. Not vendored; extra must be installed."""

from __future__ import annotations

import importlib.util

from foreshadow.contribution.executor import (
    BackendNotInstalled,
    ContributionJob,
    PatchArtifact,
)

_EXTRA_NAMES = ("openhands", "openhands_sdk")


def _extra_available() -> bool:
    return any(importlib.util.find_spec(name) is not None for name in _EXTRA_NAMES)


def _require() -> None:
    if _extra_available():
        return
    raise BackendNotInstalled(
        "openhands backend is not installed. "
        "Install the extra to enable it; Foreshadow does not vendor OpenHands."
    )


class OpenHandsExecutor:
    name = "openhands"

    def __init__(self) -> None:
        _require()

    def prepare(self, job: ContributionJob) -> None:
        _require()
        raise BackendNotInstalled("openhands adapter is not wired in this build")

    def analyze(self, job: ContributionJob) -> None:
        _require()
        raise BackendNotInstalled("openhands adapter is not wired in this build")

    def implement(self, job: ContributionJob) -> None:
        _require()
        raise BackendNotInstalled("openhands adapter is not wired in this build")

    def test(self, job: ContributionJob) -> None:
        _require()
        raise BackendNotInstalled("openhands adapter is not wired in this build")

    def iterate(self, job: ContributionJob) -> None:
        _require()
        raise BackendNotInstalled("openhands adapter is not wired in this build")

    def produce_patch(self, job: ContributionJob) -> PatchArtifact:
        _require()
        raise BackendNotInstalled("openhands adapter is not wired in this build")
