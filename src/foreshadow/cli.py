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

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_SKIPPED = 3

APP_HELP = """Find what the future has already foreshadowed.

A local daily short-list of GitHub repos you might still be able to help.
Nothing is posted to GitHub unless you say so.

Start here:
  foreshadow init
  foreshadow run
  foreshadow board"""

APP_EPILOG = """GitHub token (read-only, this machine only):
  export GITHUB_TOKEN=ghp_...     classic PAT, no scopes
  or  export GH_TOKEN=...
  or  gh auth login

Exit codes: 0 ok, 1 failure, 2 usage, 3 already ran today (use --force to debug)"""

GIT_MISSING = (
    "git is not installed, so the repo was not cloned.\n"
    "Install git (macOS: xcode-select --install) then run the same command again.\n"
    "https://git-scm.com/downloads"
)

app = typer.Typer(
    name="foreshadow",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
    help=APP_HELP,
    epilog=APP_EPILOG,
    context_settings={"help_option_names": ["-h", "--help"]},
)
schedule_app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Install a daily local job (optional). Does not depend on the current directory.",
)
app.add_typer(schedule_app, name="schedule", rich_help_panel="Setup")


def _show_version(value: bool) -> None:
    if value:
        from foreshadow import __version__

        sys.stdout.write(f"foreshadow {__version__}\n")
        raise typer.Exit(EXIT_OK)


@app.callback()
def _root(
    show_version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Print version and exit.",
        callback=_show_version,
        is_eager=True,
    ),
) -> None:
    """Find what the future has already foreshadowed.

    A local daily short-list of GitHub repos you might still be able to help.
    Nothing is posted to GitHub unless you say so.

    Start here:
      foreshadow init
      foreshadow run
      foreshadow board
    """


@app.command(rich_help_panel="Setup")
def version() -> None:
    """Print the installed version."""
    from foreshadow import __version__

    sys.stdout.write(f"foreshadow {__version__}\n")


@app.command(rich_help_panel="Start here")
def init(
    schedule: bool = typer.Option(
        False, "--schedule", help="Also install the daily scheduler"
    ),
) -> None:
    """Create local data and default config. Safe to run more than once."""
    from foreshadow.doctor import format_init, initialize

    info = initialize()
    sys.stdout.write(format_init(info))
    if schedule:
        from foreshadow.schedule import ScheduleError, format_install, install_schedule

        try:
            sched = install_schedule()
        except (ScheduleError, RuntimeError) as exc:
            print(f"scheduler install failed: {exc}", file=sys.stderr)
            print("next: foreshadow doctor", file=sys.stderr)
            raise SystemExit(EXIT_FAIL) from exc
        sys.stdout.write(format_install(sched))
    if not info.get("token_ok"):
        raise SystemExit(EXIT_OK)


@app.command(rich_help_panel="Setup")
def doctor() -> None:
    """Check token, git, data dir, last run, and scheduler."""
    from foreshadow.doctor import collect_doctor, format_doctor

    info = collect_doctor()
    sys.stdout.write(format_doctor(info))
    if not info.get("ok"):
        raise SystemExit(EXIT_FAIL)


@app.command(rich_help_panel="Setup")
def status() -> None:
    """Show last Official run, observation panel, and scheduler."""
    from foreshadow.doctor import collect_status, format_status

    sys.stdout.write(format_status(collect_status()))


def _execute_run(*, force: bool, date: str | None, llm: bool) -> None:
    clock = _clock(date)
    try:
        result = run_pipeline(clock=clock, force=force, llm=llm)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else EXIT_FAIL
        if code == EXIT_USAGE:
            print(
                "GitHub credentials unavailable.\n"
                "next: export GITHUB_TOKEN=… then foreshadow doctor",
                file=sys.stderr,
            )
        raise
    except Exception as exc:
        from foreshadow.github.client import GitHubError, redact

        print("Foreshadow daily run failed", file=sys.stderr)
        print(f"Reason: {redact(str(exc))}", file=sys.stderr)
        if isinstance(exc, GitHubError) and exc.status == 401:
            from foreshadow.github.client import missing_token_message

            print(missing_token_message(), file=sys.stderr, end="")
        _print_recovery()
        raise SystemExit(EXIT_FAIL) from exc
    if result.skipped and result.status == "locked":
        print("Foreshadow daily run already in progress", file=sys.stderr)
        _print_recovery()
        raise SystemExit(EXIT_FAIL)
    text = result.summary or ""
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    if result.skipped and result.skip_reason == "same_day":
        raise SystemExit(EXIT_SKIPPED)


@app.command(rich_help_panel="Start here")
def run(
    force: bool = typer.Option(
        False, "--force", help="Re-run today's completed scan (debug)."
    ),
    date: str | None = typer.Option(None, "--date", help="UTC date override (debug)."),
    llm: bool = typer.Option(
        False, "--llm", help="Optional narrative. Never changes scores."
    ),
) -> None:
    """Scan public GitHub once for today (UTC). Empty Top 5 is OK."""
    _execute_run(force=force, date=date, llm=llm)


@app.command(rich_help_panel="Daily")
def report(
    date: str | None = None,
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Print the latest daily report."""
    clock = _clock(date)
    day = _resolve_report_date(clock, date)
    if day is None:
        print(
            "no report yet.\nStart here:\n  foreshadow init\n  foreshadow run",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)
    path = resolve_data_dir() / "reports" / f"{day}{'.json' if as_json else '.md'}"
    if not path.is_file():
        print(
            f"no report for {day}\nRun:  foreshadow run",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)
    sys.stdout.write(path.read_text(encoding="utf-8"))


@app.command(rich_help_panel="Daily")
def show(repo: str) -> None:
    """Show the latest local score card for a repo."""
    text = show_repo(repo)
    if text is None:
        print(
            f"unknown repo: {repo}\n"
            "Run `foreshadow run` first, then use a name from the report.",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)
    sys.stdout.write(text if text.endswith("\n") else text + "\n")


@app.command(rich_help_panel="Daily")
def review(
    repo: str,
    action: str,
    m: str | None = typer.Option(None, "-m", help="Note"),
) -> None:
    """Record a stance: watch, interested, reject, investigate, enter, later."""
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


@app.command(rich_help_panel="Start here")
def board(
    date: str | None = None,
    preview: bool = False,
    no_open: bool = typer.Option(False, "--no-open"),
    export_html: bool = typer.Option(False, "--export-html"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Open the Daily Board in your browser (localhost only)."""
    from foreshadow.board.pipeline import build_board_from_db, write_board
    from foreshadow.board.server import port_in_use_message, serve_board, validate_host

    db_path = resolve_data_dir() / "foreshadow.sqlite3"
    if not db_path.is_file():
        print(
            "No daily data yet. Start here:\n"
            "  foreshadow init\n"
            "  foreshadow run\n"
            "  foreshadow board",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)
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
    try:
        serve_board(
            host=host,
            port=port,
            date=day,
            preview=preview,
            clock=clock,
            open_browser=not no_open,
        )
    except OSError:
        print(port_in_use_message(host, port), file=sys.stderr)
        raise SystemExit(EXIT_FAIL)


@app.command(rich_help_panel="Enter")
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
    if clone_status == "no_git":
        lines.append("")
        lines.append(GIT_MISSING)
    sys.stdout.write("\n".join(lines) + "\n")


@app.command(rich_help_panel="Enter")
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


@app.command(rich_help_panel="Advanced")
def sample_access() -> None:
    """Fetch extra access signals (advanced). Does not change Official scores."""
    from foreshadow.config import load_config
    from foreshadow.github.client import GitHubClient, resolve_token
    from foreshadow.pipeline.access_sample import sample_medium_access

    path = resolve_data_dir() / "foreshadow.sqlite3"
    if not path.is_file():
        print(
            "No daily data yet. Start here:\n  foreshadow init\n  foreshadow run",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_USAGE)
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


@app.command("missions", rich_help_panel="Enter")
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


@app.command(rich_help_panel="Daily")
def watchlist(
    action: str | None = typer.Option(None, "--action", help="Filter by stance"),
) -> None:
    """List current review stances."""
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


@schedule_app.command("install")
def schedule_install(
    at: str = typer.Option("07:00", "--at", help="Local time HH:MM"),
) -> None:
    """Install the daily job. Idempotent. Refuses Desktop/worktree paths."""
    from foreshadow.schedule import ScheduleError, install, scheduler_status
    from foreshadow.schedule import format_status as format_sched

    try:
        _spec, notes = install(at=at)
    except ScheduleError as exc:
        print(f"scheduler install failed: {exc}", file=sys.stderr)
        print("next: foreshadow doctor", file=sys.stderr)
        raise SystemExit(1) from exc
    for note in notes:
        sys.stdout.write(note + "\n")
    sys.stdout.write(format_sched(scheduler_status()))


@schedule_app.command("status")
def schedule_status_cmd() -> None:
    """Show whether the daily job is installed."""
    from foreshadow.schedule import format_status as format_sched
    from foreshadow.schedule import scheduler_status

    sys.stdout.write(format_sched(scheduler_status()))


@schedule_app.command("run-now")
def schedule_run_now(
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Run today's Official job the same way the scheduler would."""
    from foreshadow.schedule import ScheduleError, run_now

    try:
        code = run_now(force=force)
    except ScheduleError:
        _execute_run(force=force, date=None, llm=False)
        return
    raise SystemExit(code)


@schedule_app.command("uninstall")
def schedule_uninstall() -> None:
    """Remove the daily job. Does not delete your database."""
    from foreshadow.schedule import uninstall

    for note in uninstall():
        sys.stdout.write(note + "\n")


def _print_recovery() -> None:
    from foreshadow.doctor import last_successful_run

    last = last_successful_run()
    print(f"last successful run: {last or 'none'}", file=sys.stderr)
    print("next: foreshadow doctor", file=sys.stderr)


def _clock(date_str: str | None) -> Clock:
    if not date_str:
        return Clock()
    try:
        day = date.fromisoformat(date_str)
    except ValueError:
        print(f"invalid date {date_str!r} (use YYYY-MM-DD)", file=sys.stderr)
        raise SystemExit(EXIT_USAGE) from None
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
