"""Small read-only planning/export CLI; no mission authorization or executor."""

from __future__ import annotations

import shlex
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from foreshadow.decision.adapters import (
    local_opportunity,
    local_repository,
    stored_opportunity,
)
from foreshadow.decision.models import Validation
from foreshadow.decision.pipeline import export_work_order, validate_opportunity
from foreshadow.paths import resolve_data_dir
from foreshadow.work_order import dumps, timestamp

app = typer.Typer(
    no_args_is_help=True,
    help="Prepare bounded Engineering Work Orders v1. Does not execute them.",
)


def _clock() -> datetime:
    return datetime.now(UTC)


def _checks(commands: list[str]) -> tuple[Validation, ...]:
    checks = []
    for command in commands:
        tokens = shlex.split(command)
        if not tokens or any(
            c in command for c in (";", "|", "&", ">", "<", "`", "$", "\n", "\x00")
        ):
            raise ValueError(
                "checks require structured argv; shell operators are not supported"
            )
        checks.append(Validation(tuple(tokens), "Declared check exits zero"))
    if not checks:
        raise ValueError("at least one --check is required")
    return tuple(checks)


def _emit(
    opportunity,
    observations,
    *,
    decision_at: datetime,
    output: Path | None,
    dry_run: bool,
    freshness_at: datetime | None = None,
):
    valid = validate_opportunity(opportunity, observations, now=decision_at)
    order = export_work_order(valid, now=freshness_at or decision_at)
    text = dumps(order)
    if output is not None and not dry_run:
        # Exclusive creation refuses an existing file and symlink. No overwrite.
        with output.expanduser().open("x", encoding="utf-8") as handle:
            handle.write(text)
    sys.stdout.write(text)


@app.command("plan")
def plan(
    repository: Path,
    identity: Annotated[str, typer.Option("--identity")],
    title: Annotated[str, typer.Option("--title")],
    objective: Annotated[str, typer.Option("--objective")],
    rationale: Annotated[str, typer.Option("--rationale")],
    source_file: Annotated[list[str], typer.Option("--source-file")],
    check: Annotated[list[str], typer.Option("--check")],
    acceptance: Annotated[list[str], typer.Option("--acceptance")],
    constraint: Annotated[list[str] | None, typer.Option("--constraint")] = None,
    as_of: Annotated[
        str | None,
        typer.Option(
            "--as-of",
            help="Decision time for replay; never changes actual observation timestamps.",
        ),
    ] = None,
    output: Annotated[Path | None, typer.Option("--export-work-order")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
):
    """Assess a human-defined local task against real source blobs at HEAD."""
    try:
        observed_at = _clock()
        now = timestamp(as_of, "as-of") if as_of else observed_at
        repo = local_repository(repository, identity)
        opportunity, observations = local_opportunity(
            repo,
            title=title,
            objective=objective,
            rationale=rationale,
            files=tuple(source_file),
            checks=_checks(check),
            acceptance=tuple(acceptance),
            constraints=tuple(constraint or ()),
            now=observed_at,
        )
        _emit(
            opportunity, observations, decision_at=now, output=output, dry_run=dry_run
        )
    except (ValueError, OSError) as exc:
        print(f"cannot prepare work order: {exc}", file=sys.stderr)
        raise typer.Exit(2) from exc


@app.command("export")
def export(
    identity: str,
    repository: Annotated[Path, typer.Option("--repository")],
    check: Annotated[list[str], typer.Option("--check")],
    output: Annotated[Path | None, typer.Option("--export-work-order")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
):
    """Export an existing entry recommendation with its actual retained observation dates."""
    conn = None
    try:
        repo = local_repository(repository, identity)
        path = resolve_data_dir() / "foreshadow.sqlite3"
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        opportunity, observations = stored_opportunity(
            conn, repo, checks=_checks(check)
        )
        # Use the stored decision time so unchanged exports are byte-identical.
        from foreshadow.entry import load_entry

        rid = conn.execute(
            "SELECT id FROM repos WHERE full_name=?", (identity,)
        ).fetchone()[0]
        strategy = load_entry(conn, rid)
        _emit(
            opportunity,
            observations,
            decision_at=timestamp(strategy.analyzed_at, "analyzed_at"),
            freshness_at=_clock(),
            output=output,
            dry_run=dry_run,
        )
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"cannot export work order: {exc}", file=sys.stderr)
        raise typer.Exit(2) from exc
    finally:
        if conn is not None:
            conn.close()
