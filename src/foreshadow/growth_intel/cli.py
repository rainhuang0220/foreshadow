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
        priority = (
            "none"
            if row["intervention_priority"] is None
            else str(row["intervention_priority"])
        )
        print(
            f"{row['identity']}\teligible={row['eligible']}\treason={row['reason']}\t"
            f"intervention_priority={priority}\tmeaning={row['priority_meaning']}"
        )


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


@app.command("observe")
def observe(
    identity: Annotated[str, typer.Argument()],
    casebook: Annotated[Path | None, typer.Option("--casebook")] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    database: Annotated[Path | None, typer.Option("--database")] = None,
):
    """Record read-only traffic for one owned repository. Does not post or execute."""
    from foreshadow.growth_intel.owner_traffic import TOKEN_ENV, record_owner_traffic, token_from_env

    token = token_from_env()
    if not token:
        print(
            f"cannot observe owner traffic: {TOKEN_ENV} is not set. "
            "Create a fine-grained personal access token limited to the selected repositories, "
            "with Administration repository permission Read. "
            "Do not use a classic repo token. Public GITHUB_TOKEN is not read.",
            file=sys.stderr,
        )
        raise typer.Exit(2)
    try:
        book = _book(casebook)
        allowed = {row["identity"] for row in book["repositories"] if row.get("role") == "owned"}
        if identity not in allowed:
            raise ValueError("repository is not an owned casebook repository")
        from foreshadow.db import connect, migrate

        if database is None:
            from foreshadow.paths import resolve_data_dir

            database = resolve_data_dir() / "foreshadow.sqlite3"
        conn = connect(database)
        migrate(conn)
        record_owner_traffic(
            conn,
            identity=identity,
            token=token,
            as_of=_as_of(as_of),
            allowed=allowed,
        )
    except (ValueError, OSError) as exc:
        print(f"cannot observe owner traffic: {exc}", file=sys.stderr)
        raise typer.Exit(2) from exc
    print(f"recorded owner traffic for {identity}")
