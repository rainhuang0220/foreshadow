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
    ReviewFetchError,
    apply_review,
    current_stances,
    format_stances,
    needs_hydrate,
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

    settings = load_config()
    client = None
    if needs_hydrate(conn, repo, action_n, clock):
        from foreshadow.github.client import GitHubClient, resolve_token

        client = GitHubClient(
            token=resolve_token(),
            settings=settings.github,
            clock=clock,
        )
    try:
        apply_review(conn, client, repo, action_n, m, clock, settings=settings)
    except ReviewError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    except ReviewFetchError as exc:
        from foreshadow.github.client import redact

        print(redact(str(exc)), file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        from foreshadow.github.client import redact

        print(redact(str(exc)), file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()
    sys.stdout.write(f"recorded {action_n} for {repo}\n")


@app.command()
def board(
    date: str | None = None,
    preview: bool = False,
    no_open: bool = typer.Option(False, "--no-open"),
    export_html: bool = typer.Option(False, "--export-html"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Open the interactive Daily Board on localhost. --export-html writes a static file."""
    from foreshadow.board.pipeline import build_board_from_db, write_board
    from foreshadow.board.server import serve_board, validate_host

    db_path = resolve_data_dir() / "foreshadow.sqlite3"
    if not db_path.is_file():
        print("no database — run `foreshadow run` first", file=sys.stderr)
        raise SystemExit(2)
    clock = _clock(date)
    day = date or clock.today().isoformat()
    if not date:
        resolved = _resolve_report_date(clock, None)
        if resolved:
            day = resolved
    if export_html:
        doc, before, after = build_board_from_db(date=day, preview=preview, clock=clock)
        if before != after:
            print("board run mutated snapshots — aborting", file=sys.stderr)
            raise SystemExit(1)
        _json_path, html_path = write_board(doc, preview=preview)
        sys.stdout.write(
            f"Foreshadow board {doc.date}  mode={doc.mode}  "
            f"discovered={doc.discovered} shortlisted={doc.shortlisted} "
            f"deep={doc.deep_reviewed} official={doc.official_top5} "
            f"provisional={doc.provisional_count}\n"
            f"{html_path}\n"
        )
        if not no_open:
            import webbrowser

            webbrowser.open(html_path.resolve().as_uri())
        return
    try:
        validate_host(host)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    serve_board(
        host=host,
        port=port,
        date=day,
        preview=preview,
        clock=clock,
        open_browser=not no_open,
    )


@app.command()
def enter(
    repo: str = typer.Argument(..., help="owner/repo"),
) -> None:
    """Create a local Entry Mission. Never posts to GitHub."""
    from foreshadow.auth import resolve_cli_user
    from foreshadow.mission import create_for_user, parse_repo_name

    try:
        repo = parse_repo_name(repo)
    except ValueError:
        print("need owner/repo", file=sys.stderr)
        raise SystemExit(2)
    path = resolve_data_dir() / "foreshadow.sqlite3"
    conn = connect(path)
    migrate(conn)
    try:
        uid = resolve_cli_user(conn)
        mission = create_for_user(
            conn, user_id=uid, full_name=repo, data_dir=resolve_data_dir()
        )
        from foreshadow.mission import setup_local_environment

        setup = setup_local_environment(conn, mission.id or 0, uid, resolve_data_dir())
        mission_status = setup["mission"].get("status") or mission.status
        clone_status = (setup.get("clone") or {}).get("status")
        local_path = setup["mission"].get("local_path") or mission.local_path
        steps = setup["mission"].get("steps_zh") or mission.strategy.steps_zh
    finally:
        conn.close()
    lines = [
        (
            f"entry mission {mission.id} {mission.full_name} "
            f"path={mission.strategy.path} status={mission_status} "
            f"clone={clone_status}"
        ),
        mission.strategy.summary_zh,
        f"local {local_path}",
        f"read {local_path}/FORESHADOW.md and {local_path}/ISSUE_DRAFT.md",
    ]
    for step in steps or []:
        text = str(step).strip()
        if text:
            lines.append(text)
    lines.append("remote GitHub writes are blocked until you approve them.")
    sys.stdout.write("\n".join(lines) + "\n")


@app.command()
def outcome(
    repo: str = typer.Argument(..., help="owner/repo"),
    event: str = typer.Option(
        ...,
        "--event",
        help="maintainer_replied / pr_merged / abandoned / …",
    ),
) -> None:
    """Record a manual contribution outcome. Never talks to GitHub."""
    from foreshadow.auth import resolve_cli_user
    from foreshadow.mission import USER_MARKED_EVENTS, list_missions, record_user_event

    if event not in USER_MARKED_EVENTS:
        print(f"unknown event {event}", file=sys.stderr)
        raise SystemExit(2)
    path = resolve_data_dir() / "foreshadow.sqlite3"
    conn = connect(path)
    migrate(conn)
    try:
        uid = resolve_cli_user(conn)
        items = list_missions(conn, uid)
        found = next((m for m in items if m.get("full_name") == repo), None)
        if found is None:
            print(
                "no mission for that repo — run foreshadow enter first", file=sys.stderr
            )
            raise SystemExit(2)
        plan = record_user_event(
            conn, user_id=uid, mission_id=int(found["id"]), event=event
        )
    finally:
        conn.close()
    sys.stdout.write(
        f"recorded {event} on {repo} status={plan.get('status')}\n"
        "this does not post to GitHub.\n"
    )


@app.command()
def sample_access() -> None:
    """GET closed PRs for medium-tier snapshots. Does not change official v1 scores."""
    from foreshadow.config import load_config
    from foreshadow.github.client import GitHubClient, resolve_token
    from foreshadow.pipeline.access_sample import sample_medium_access

    path = resolve_data_dir() / "foreshadow.sqlite3"
    if not path.is_file():
        print("no database — run `foreshadow run` first", file=sys.stderr)
        raise SystemExit(2)
    conn = connect(path)
    migrate(conn)
    try:
        client = GitHubClient(resolve_token(), settings=load_config().github)
        out = sample_medium_access(conn, client)
    finally:
        conn.close()
    sys.stdout.write(
        f"medium access sample updated={out['updated']} "
        f"skipped={out['skipped']} failed={out['failed']}\n"
        f"{out['note']}\n"
    )


@app.command("missions")
def missions_cmd() -> None:
    """List local Entry Missions. Never talks to GitHub."""
    from foreshadow.auth import resolve_cli_user
    from foreshadow.mission import list_missions, status_zh

    path = resolve_data_dir() / "foreshadow.sqlite3"
    conn = connect(path)
    migrate(conn)
    try:
        uid = resolve_cli_user(conn)
        items = list_missions(conn, uid)
    finally:
        conn.close()
    if not items:
        sys.stdout.write("no missions. run foreshadow enter owner/repo\n")
        return
    for row in items:
        st = str(row.get("status") or "")
        sys.stdout.write(
            f"{row.get('id')} {row.get('full_name')} "
            f"{st} ({status_zh(st)}) {row.get('next_step_zh') or ''} "
            f"{row.get('local_path') or ''}\n"
        )


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
