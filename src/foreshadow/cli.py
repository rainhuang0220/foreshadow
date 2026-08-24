from __future__ import annotations

import sys
from datetime import UTC, date, datetime

import typer

from foreshadow.clock import Clock
from foreshadow.db import connect, migrate
from foreshadow.paths import resolve_data_dir
from foreshadow.pipeline import run_pipeline, show_repo
from foreshadow.reviews import (
    ACTIONS,
    ReviewError,
    apply_review,
    current_stances,
    format_stances,
)

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def run(
    force: bool = False,
    date: str | None = None,
    llm: bool = False,
) -> None:
    clock = _clock(date)
    try:
        result = run_pipeline(clock=clock, force=force, llm=llm)
    except SystemExit:
        raise
    except Exception as exc:
        from foreshadow.github.client import redact

        print(redact(str(exc)), file=sys.stderr)
        raise SystemExit(1) from exc
    text = result.summary or ""
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


@app.command()
def report(
    date: str | None = None,
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    clock = _clock(date)
    day = _resolve_report_date(clock, date)
    if day is None:
        print("no report", file=sys.stderr)
        raise SystemExit(2)
    path = resolve_data_dir() / "reports" / f"{day}{'.json' if as_json else '.md'}"
    if not path.is_file():
        print(f"no report for {day}", file=sys.stderr)
        raise SystemExit(2)
    sys.stdout.write(path.read_text(encoding="utf-8"))


@app.command()
def show(repo: str) -> None:
    text = show_repo(repo)
    if text is None:
        print(f"unknown repo: {repo}", file=sys.stderr)
        raise SystemExit(2)
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


@app.command()
def review(
    repo: str,
    action: str,
    m: str | None = typer.Option(None, "-m", help="Note"),
) -> None:
    action_n = action.strip().lower()
    if action_n not in ACTIONS:
        print(f"unknown action: {action} ({', '.join(ACTIONS)})", file=sys.stderr)
        raise SystemExit(2)
    clock = Clock()
    conn = connect(resolve_data_dir() / "foreshadow.sqlite3")
    migrate(conn)
    from foreshadow.config import load_config
    from foreshadow.github.client import GitHubClient, resolve_token

    settings = load_config()
    client = GitHubClient(
        token=resolve_token(),
        settings=settings.github,
        clock=clock,
    )
    try:
        apply_review(conn, client, repo, action_n, m, clock)
    except ReviewError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    except Exception as exc:
        from foreshadow.github.client import redact

        print(redact(str(exc)), file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        if hasattr(client, "close"):
            client.close()
    sys.stdout.write(f"recorded {action_n} for {repo}\n")


@app.command()
def watchlist(
    action: str | None = typer.Option(None, "--action", help="Filter by stance"),
) -> None:
    action_n = action.strip().lower() if action else None
    if action_n is not None and action_n not in ACTIONS:
        print(f"unknown action: {action} ({', '.join(ACTIONS)})", file=sys.stderr)
        raise SystemExit(2)
    db_path = resolve_data_dir() / "foreshadow.sqlite3"
    if not db_path.is_file():
        sys.stdout.write("no reviews\n")
        return
    conn = connect(db_path)
    migrate(conn)
    try:
        rows = current_stances(conn, action=action_n)
    except ReviewError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    sys.stdout.write(format_stances(rows, action=action_n))


def _clock(date_str: str | None) -> Clock:
    if not date_str:
        return Clock()
    day = date.fromisoformat(date_str)
    return Clock(now=datetime(day.year, day.month, day.day, 0, 5, tzinfo=UTC))


def _resolve_report_date(clock: Clock, date_arg: str | None) -> str | None:
    if date_arg:
        return date_arg
    db_path = resolve_data_dir() / "foreshadow.sqlite3"
    today = clock.today().isoformat()
    reports = resolve_data_dir() / "reports"
    today_file = reports / f"{today}.md"
    if today_file.is_file():
        return today
    if not db_path.is_file():
        return None
    conn = connect(db_path)
    migrate(conn)
    row = conn.execute(
        """
        SELECT run_date FROM daily_runs
        WHERE status IN ('complete', 'degraded')
        ORDER BY run_date DESC LIMIT 1
        """
    ).fetchone()
    return str(row[0]) if row else None
