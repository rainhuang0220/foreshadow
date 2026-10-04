"""Small growth command group. It does not execute an experiment."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from foreshadow.growth_intel.casebook import load_casebook, packaged_casebook
from foreshadow.growth_intel.export import export_work_order
from foreshadow.growth_intel.plan import build_plan
from foreshadow.growth_intel.render import dumps, render_plan
from foreshadow.work_order import dumps as dump_order
from foreshadow.work_order import timestamp

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Plan a bounded project-growth experiment. Does not score contributions or execute work.",
)


def _book(path: Path | None) -> dict:
    if path is None:
        return packaged_casebook()
    return load_casebook(json.loads(path.expanduser().read_text(encoding="utf-8")))


def _as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return timestamp(value, "as-of")


@app.command("study")
def study(
    casebook: Annotated[Path | None, typer.Option("--casebook")] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
):
    """Show what the benchmark casebook can and cannot support."""
    plan = build_plan(_book(casebook), as_of=_as_of(as_of))
    sys.stdout.write(dumps(plan["study"]) if as_json else render_plan(plan))


@app.command("portfolio")
def portfolio(
    casebook: Annotated[Path | None, typer.Option("--casebook")] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
):
    """Rank owned repositories. A release block stays ineligible."""
    plan = build_plan(_book(casebook), as_of=_as_of(as_of))
    if as_json:
        sys.stdout.write(dumps({"portfolio": plan["portfolio"]}))
        return
    for row in plan["portfolio"]:
        score = "none" if row["score"] is None else str(row["score"])
        print(f"{row['identity']}\teligible={row['eligible']}\treason={row['reason']}\tscore={score}")


@app.command("plan")
def plan(
    casebook: Annotated[Path | None, typer.Option("--casebook")] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    as_json: Annotated[bool, typer.Option("--json")] = False,
):
    """Print the recommended experiment, or say that none is supported."""
    built = build_plan(_book(casebook), as_of=_as_of(as_of))
    sys.stdout.write(dumps(built) if as_json else render_plan(built))


@app.command("export")
def export(
    casebook: Annotated[Path | None, typer.Option("--casebook")] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    repository: Annotated[Path | None, typer.Option("--repository")] = None,
    output: Annotated[Path | None, typer.Option("--export")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
):
    """Write one generic Engineering Work Order v1. Does not run it."""
    try:
        now = _as_of(as_of)
        built = build_plan(_book(casebook), as_of=now)
        order = export_work_order(built, now=now, repository_path=repository)
    except (ValueError, OSError) as exc:
        print(f"cannot export growth experiment: {exc}", file=sys.stderr)
        raise typer.Exit(2) from exc
    text = dump_order(order)
    if output is not None and not dry_run:
        with output.expanduser().open("x", encoding="utf-8") as handle:
            handle.write(text)
    sys.stdout.write(text)
