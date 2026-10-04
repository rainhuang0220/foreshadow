"""Project growth intelligence.

This package answers what bounded experiment to try on an owned repository.
It is not star-growth scoring, not Expected Entry Value, and not a contribution
Opportunity.
"""

from foreshadow.growth_intel.plan import build_plan

__all__ = ["build_plan"]
