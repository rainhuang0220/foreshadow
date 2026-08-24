"""Pipeline stages. Orchestration (`run_pipeline`) is a later task."""

from foreshadow.pipeline.discover import discover_hydrate_snapshot, is_degraded

__all__ = ["discover_hydrate_snapshot", "is_degraded"]
