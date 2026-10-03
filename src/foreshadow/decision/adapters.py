"""Read-only Git and retained entry adapters. No coding agent or execution store."""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from foreshadow.decision.models import (
    Evidence,
    Observation,
    Opportunity,
    Repository,
    Validation,
)
from foreshadow.decision.task import StructuredTask, from_entry
from foreshadow.repository_identity import github_repository_name
from foreshadow.work_order import timestamp


def _git(path: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
            env=__import__("os").environ | {"GIT_OPTIONAL_LOCKS": "0"},
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Git inspection timed out") from exc
    except OSError as exc:
        raise ValueError("git is required for a local work order") from exc
    if result.returncode:
        raise ValueError(f"cannot inspect repository: {result.stderr.strip()}")
    return result.stdout.strip()


def local_repository(path: Path, identity: str) -> Repository:
    path = path.expanduser().resolve()
    if (
        not path.is_dir()
        or Path(_git(path, "rev-parse", "--show-toplevel")).resolve() != path
    ):
        raise ValueError("repository must be an existing Git checkout root")
    _verify_repository_identity(path, identity)
    return Repository(
        identity=identity,
        path=str(path),
        base_revision=_git(path, "rev-parse", "--verify", "HEAD^{commit}"),
    )


def _verify_repository_identity(path: Path, identity: str) -> None:
    remotes = _git(path, "remote").splitlines()
    names = {
        name: github_repository_name(
            _git(path, "config", "--get", f"remote.{name}.url")
        )
        for name in ("origin", "upstream")
        if name in remotes
    }
    origin, upstream = names.get("origin"), names.get("upstream")
    if upstream and upstream.casefold() != identity.casefold():
        raise ValueError(
            f"repository identity mismatch: upstream={upstream}; expected={identity}"
        )
    if origin and origin.casefold() != identity.casefold() and not upstream:
        raise ValueError(
            f"repository identity mismatch: origin={origin}; expected={identity}"
        )


def observe_files(
    repository: Repository, files: tuple[str, ...], *, now: datetime
) -> tuple[Observation, ...]:
    if repository.path is None or repository.base_revision is None or not files:
        raise ValueError(
            "local observations require a pinned repository and source files"
        )
    observations = []
    for name in sorted(set(files)):
        relative = PurePosixPath(name)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not name
            or name.startswith("-")
        ):
            raise ValueError("source-file must be a repository-relative path")
        # Read retained Git blobs, never substitute the current dirty worktree.
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    repository.path,
                    "show",
                    f"{repository.base_revision}:{name}",
                ],
                timeout=30,
                capture_output=True,
                check=False,
                env=__import__("os").environ | {"GIT_OPTIONAL_LOCKS": "0"},
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"source-file observation timed out: {name}") from exc
        except OSError as exc:
            raise ValueError("git is required for source-file observation") from exc
        if result.returncode:
            raise ValueError(
                f"cannot observe source-file {name} at the pinned revision"
            )
        blob = result.stdout
        digest = hashlib.sha256(blob).hexdigest()
        observations.append(
            Observation(
                id="blob-" + hashlib.sha256((name + digest).encode()).hexdigest()[:24],
                repository_identity=repository.identity,
                observed_at=now,
                source=f"git:{repository.base_revision}:{name}",
                summary=f"Retained source {name}; sha256={digest}",
            )
        )
    return tuple(observations)


def local_opportunity(
    repository: Repository,
    *,
    title: str,
    objective: str,
    rationale: str,
    files: tuple[str, ...],
    checks: tuple[Validation, ...],
    acceptance: tuple[str, ...],
    constraints: tuple[str, ...],
    now: datetime,
) -> tuple[Opportunity, tuple[Observation, ...]]:
    observations = observe_files(repository, files, now=now)
    expires = now + timedelta(days=3)
    evidence = tuple(Evidence.observed(obs, expires_at=expires) for obs in observations)
    # The operator's diagnosis is explicitly an inference, not a measured fact.
    inference = Evidence.inferred(
        id="reason-" + hashlib.sha256(rationale.encode()).hexdigest()[:24],
        summary=rationale,
        source="operator:local-review",
        observations=observations,
        expires_at=expires,
    )
    task = StructuredTask(
        repository=repository.identity,
        task=title,
        expected_behavior=objective,
        acceptance_criteria=list(acceptance),
        constraints=list(constraints),
        relevant_files=list(files),
    )
    identifier = (
        "local-"
        + hashlib.sha256(
            (repository.identity + repository.base_revision + title).encode()
        ).hexdigest()[:24]
    )
    return Opportunity(
        identifier,
        repository,
        title,
        objective,
        rationale,
        task,
        evidence + (inference,),
        0.8,
        checks,
    ), observations


def stored_opportunity(
    conn: sqlite3.Connection, repository: Repository, *, checks: tuple[Validation, ...]
) -> tuple[Opportunity, tuple[Observation, ...]]:
    from foreshadow.entry import load_entry

    if repository.path is not None:
        _verify_repository_identity(Path(repository.path), repository.identity)

    row = conn.execute(
        "SELECT id FROM repos WHERE full_name=?", (repository.identity,)
    ).fetchone()
    if row is None:
        raise ValueError("repository has no retained radar observations")
    rid = int(row[0])
    strategy = load_entry(conn, rid)
    source = conn.execute(
        "SELECT source_snapshot_date FROM entry_analyses WHERE repo_id=?", (rid,)
    ).fetchone()
    if strategy is None or source is None or not source[0]:
        raise ValueError("no entry recommendation with a retained source snapshot")
    snapshot = conn.execute(
        "SELECT captured_at, stars, open_issues, open_prs FROM snapshots WHERE repo_id=? AND snapshot_date=?",
        (rid, source[0]),
    ).fetchone()
    if snapshot is None:
        raise ValueError("entry source snapshot is missing")
    captured = timestamp(snapshot[0], "snapshot.captured_at")
    analyzed = timestamp(strategy.analyzed_at, "entry.analyzed_at")
    if captured > analyzed:
        raise ValueError(
            "snapshot was replaced after entry analysis; refresh the recommendation"
        )
    expires = min(
        captured + timedelta(days=3),
        timestamp(strategy.stale_after, "entry.stale_after"),
    )
    obs = Observation(
        id=f"snapshot-{rid}-{source[0]}",
        repository_identity=repository.identity,
        observed_at=captured,
        source=f"sqlite:snapshots/{rid}/{source[0]}",
        summary=f"Retained snapshot: stars={snapshot[1]}, open_issues={snapshot[2]}, open_prs={snapshot[3]}",
    )
    task = from_entry(repository.identity, strategy.as_dict())
    if not task.issue_number or strategy.recommended.route not in {
        "ISSUE",
        "REPRO",
        "FIX",
        "DOCS",
    }:
        raise ValueError(
            "entry has no bounded issue target; choose a defined local task"
        )
    task.expected_behavior = strategy.recommended.summary_zh
    task.acceptance_criteria = [strategy.recommended.summary_zh]
    rationale = "; ".join(strategy.recommended.why)
    inference = Evidence.inferred(
        id="entry-" + strategy.as_dict()["revision"][:24],
        summary=rationale,
        source="entry:" + strategy.as_dict()["revision"],
        observations=(obs,),
        expires_at=expires,
    )
    return Opportunity(
        "entry-" + strategy.as_dict()["revision"][:24],
        repository,
        task.task,
        task.expected_behavior,
        rationale,
        task,
        (Evidence.observed(obs, expires_at=expires), inference),
        strategy.recommended.confidence,
        checks,
    ), (obs,)
