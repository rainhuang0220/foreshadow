"""Human sections and canonical JSON. Facts stay separated from the experiment."""

from __future__ import annotations

import json


def dumps(plan: dict) -> str:
    visible = {key: value for key, value in plan.items() if key != "target_record"}
    return json.dumps(visible, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def render_plan(plan: dict) -> str:
    sections = plan["sections"]
    experiment = plan["recommended_experiment"]
    lines = [
        "Fact:",
        sections["fact"],
        "",
        "Interpretation:",
        sections["interpretation"],
        "",
        "Hypothesis:",
        sections["hypothesis"],
        "",
        "Recommended experiment:",
        sections["experiment"] if experiment is None else (
            f"{experiment['title']} on {experiment['target']}. "
            f"Check: {experiment.get('implementation_metric') or experiment.get('outcome_metric')}. "
            f"State: {experiment.get('state', 'PLANNED')}. "
            f"Evidence: {experiment['evidence_strength']}."
        ),
        "",
    ]
    growth = plan.get("growth_experiment")
    if growth:
        lines.extend(
            [
                "Outcome measurement:",
                (
                    f"{growth['id']} on {growth['target']}. "
                    f"State: {growth['state']}. "
                    f"Metric: {growth['outcome_metric']}. "
                    f"Evidence: {growth['evidence_strength']}."
                ),
                "",
            ]
        )
    return "\n".join(lines)
