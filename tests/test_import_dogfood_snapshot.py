"""Surgical dogfood mission import: remap, reuse, never clobber."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from foreshadow.auth import ensure_local_user
from foreshadow.contribution.review import active_contribution, history_for_repo
from foreshadow.db import connect, migrate

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import_dogfood_snapshot.py"


def _load_importer():
    spec = importlib.util.spec_from_file_location("import_dogfood_snapshot", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


imp = _load_importer()

NOW = datetime.now(UTC).isoformat()
DIFF_1828 = """diff --git a/cmd/deja/doctor.go b/cmd/deja/doctor.go
--- a/cmd/deja/doctor.go
+++ b/cmd/deja/doctor.go
@@ -1,1 +1,2 @@
 keep
+grok plugin
"""
DIFF_1551 = """diff --git a/internal/index/friction.go b/internal/index/friction.go
--- a/internal/index/friction.go
+++ b/internal/index/friction.go
@@ -1,2 +1,3 @@
 keep
+undefined symbol
diff --git a/internal/index/friction_phrases_test.go b/internal/index/friction_phrases_test.go
--- a/internal/index/friction_phrases_test.go
+++ b/internal/index/friction_phrases_test.go
@@ -1,1 +1,2 @@
 keep
+undefined reference to
"""


def _pkg(issue: int, title: str, diff: str, files: list[str], body: str) -> dict:
    return {
        "related_issue": f"#{issue}",
        "issue_url": f"https://github.com/vshulcz/deja-vu/issues/{issue}",
        "pr_title": title,
        "pr_body": body,
        "diff": diff,
        "files_changed": files,
        "files_changed_n": len(files),
        "tests": {"ok": True, "commands": [{"command": "go test ./...", "ok": True}]},
        "qa": "PASS",
        "qa_ok": True,
        "remote_writes": 0,
        "remote_status": "WAITING_USER_APPROVAL",
        "status": "WAITING_USER_APPROVAL",
        "implementation": {
            "mode": "autonomous_executor",
            "clean_before": True,
            "backend": "mini_swe_agent",
        },
    }


def _insert_user(conn, *, username, email, github_id=None, github_login=None) -> int:
    cur = conn.execute(
        """
        INSERT INTO users(username, email, password_hash, created_at, is_local, github_id, github_login)
        VALUES (?,?,?,?,0,?,?)
        """,
        (username, email, "x", NOW, github_id, github_login),
    )
    conn.commit()
    return int(cur.lastrowid)


def _insert_repo(
    conn,
    *,
    repo_id=None,
    full_name="vshulcz/deja-vu",
    node_id="R_kgDOTX8R2w",
    database_id=1300173275,
) -> int:
    owner, name = full_name.split("/", 1)
    if repo_id is None:
        cur = conn.execute(
            """
            INSERT INTO repos(node_id, database_id, full_name, owner, name, first_seen_at, last_seen_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (node_id, database_id, full_name, owner, name, NOW, NOW),
        )
        conn.commit()
        return int(cur.lastrowid)
    conn.execute(
        """
        INSERT INTO repos(id, node_id, database_id, full_name, owner, name, first_seen_at, last_seen_at)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (repo_id, node_id, database_id, full_name, owner, name, NOW, NOW),
    )
    conn.commit()
    return int(repo_id)


def _insert_mission(
    conn, *, mid=None, user_id, repo_id, issue, created, extra=None
) -> int:
    plan = {
        "id": mid,
        "full_name": "vshulcz/deja-vu",
        "preferred_issue": issue,
        "cited_issue": {"number": issue, "title": f"issue {issue}"},
        "entry_source": "HUMAN_CONFIRM",
        "entry_strategy": {"recommended": {"issue_number": issue}},
        "status": "WAITING_USER_APPROVAL",
    }
    if extra:
        plan.update(extra)
    cols = "user_id, repo_id, full_name, status, entry_path, difficulty, effort, plan_json, local_path, created_at, updated_at"
    vals = (
        user_id,
        repo_id,
        "vshulcz/deja-vu",
        "WAITING_USER_APPROVAL",
        "ISSUE",
        "Medium",
        "4h",
        json.dumps(plan),
        "/tmp/local-deja",
        created,
        created,
    )
    if mid is None:
        cur = conn.execute(
            f"INSERT INTO entry_missions({cols}) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            vals,
        )
        conn.commit()
        return int(cur.lastrowid)
    conn.execute(
        f"INSERT INTO entry_missions(id, {cols}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (mid, *vals),
    )
    conn.commit()
    return int(mid)


def _insert_job(
    conn, *, jid=None, user_id, repo_id, issue, created, backend="workspace"
) -> int:
    task = {"structured": {"repository": "vshulcz/deja-vu", "issue_number": issue}}
    cols = "user_id, repo_id, full_name, status, backend, task_json, log_json, created_at, updated_at"
    vals = (
        user_id,
        repo_id,
        "vshulcz/deja-vu",
        "ready",
        backend,
        json.dumps(task),
        "[]",
        created,
        created,
    )
    if jid is None:
        cur = conn.execute(
            f"INSERT INTO contribution_jobs({cols}) VALUES (?,?,?,?,?,?,?,?,?)",
            vals,
        )
        conn.commit()
        return int(cur.lastrowid)
    conn.execute(
        f"INSERT INTO contribution_jobs(id, {cols}) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (jid, *vals),
    )
    conn.commit()
    return int(jid)


def _insert_artifact(conn, *, aid=None, job_id, kind, body, created=NOW) -> int:
    if aid is None:
        cur = conn.execute(
            """
            INSERT INTO contribution_artifacts(job_id, kind, path, body, meta_json, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (job_id, kind, None, body, "{}", created),
        )
        conn.commit()
        return int(cur.lastrowid)
    conn.execute(
        """
        INSERT INTO contribution_artifacts(id, job_id, kind, path, body, meta_json, created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (aid, job_id, kind, None, body, "{}", created),
    )
    conn.commit()
    return int(aid)


def _source_db(path: Path) -> Path:
    conn = connect(path)
    migrate(conn)
    ensure_local_user(conn)
    uid = _insert_user(conn, username="pocboard", email="pocboard@example.com")
    assert uid == 2
    rid = _insert_repo(conn, repo_id=86)
    _insert_mission(
        conn,
        mid=1,
        user_id=uid,
        repo_id=rid,
        issue=1828,
        created="2026-09-08T03:54:35+00:00",
    )
    _insert_mission(
        conn,
        mid=2,
        user_id=uid,
        repo_id=rid,
        issue=1551,
        created="2026-09-08T08:35:13+00:00",
        extra={"active_entry_target": {"issue_number": 1551}},
    )
    _insert_job(
        conn,
        jid=1,
        user_id=uid,
        repo_id=None,
        issue=582,
        created="2026-09-02T17:53:04+00:00",
    )
    conn.execute(
        "UPDATE contribution_jobs SET full_name='Cyrax321/CONTINUUM' WHERE id=1"
    )
    _insert_job(
        conn,
        jid=2,
        user_id=uid,
        repo_id=rid,
        issue=1828,
        created="2026-09-08T04:05:44+00:00",
    )
    _insert_job(
        conn,
        jid=6,
        user_id=uid,
        repo_id=rid,
        issue=1551,
        created="2026-09-08T09:24:24+00:00",
        backend="mini_swe_agent",
    )
    pkg8 = json.dumps(
        _pkg(
            1828,
            "fix(doctor): report a stale Grok plugin (#1828)",
            DIFF_1828,
            ["cmd/deja/doctor.go", "cmd/deja/grok_plugin.go"],
            "Closes #1828.\n",
        ),
        ensure_ascii=False,
    )
    pkg16 = json.dumps(
        _pkg(
            1551,
            'Fix "undefined symbol" is not friction (#1551)',
            DIFF_1551,
            ["internal/index/friction.go", "internal/index/friction_phrases_test.go"],
            "Closes #1551.\n",
        ),
        ensure_ascii=False,
    )
    _insert_artifact(conn, aid=8, job_id=2, kind="package", body=pkg8)
    _insert_artifact(conn, aid=16, job_id=6, kind="package", body=pkg16)
    _insert_artifact(conn, aid=5, job_id=2, kind="diff", body=DIFF_1828)
    _insert_artifact(conn, aid=13, job_id=6, kind="diff", body=DIFF_1551)
    conn.execute(
        """
        INSERT INTO contribution_events(id, user_id, mission_id, full_name, event, detail_json, created_at)
        VALUES (1, ?, 1, 'vshulcz/deja-vu', 'entered', '{}', ?)
        """,
        (uid, NOW),
    )
    conn.commit()
    conn.close()
    return path


def _target_db(path: Path) -> tuple[sqlite3.Connection, int, int]:
    conn = connect(path)
    migrate(conn)
    ensure_local_user(conn)
    rain = _insert_user(conn, username="rain", email="rain@example.com")
    assert rain == 2
    prod = _insert_user(
        conn,
        username="rainhuang0220",
        email="rainhuang0220@users.noreply.github.com",
        github_id=424242,
        github_login="rainhuang0220",
    )
    assert prod != 2
    deja = _insert_repo(conn, repo_id=224)
    other = _insert_repo(
        conn,
        full_name="Prescott-Data/jarviscore-framework",
        node_id="R_jarvis",
        database_id=999001,
    )
    conn.execute(
        """
        INSERT INTO entry_missions(
          user_id, repo_id, full_name, status, entry_path, difficulty, effort,
          plan_json, local_path, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            prod,
            other,
            "Prescott-Data/jarviscore-framework",
            "WAITING_USER_APPROVAL",
            "ISSUE",
            "Medium",
            "4h",
            json.dumps({"preferred_issue": 1}),
            None,
            NOW,
            NOW,
        ),
    )
    cur = conn.execute(
        """
        INSERT INTO contribution_jobs(user_id, repo_id, full_name, status, backend, task_json, log_json, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            rain,
            None,
            "Cyrax321/CONTINUUM",
            "ready",
            "mini_swe_agent",
            "{}",
            "[]",
            NOW,
            NOW,
        ),
    )
    job_id = int(cur.lastrowid)
    for kind in ("diff", "test_log", "qa", "package"):
        conn.execute(
            """
            INSERT INTO contribution_artifacts(job_id, kind, path, body, meta_json, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (job_id, kind, None, f"old-{kind}", "{}", NOW),
        )
    conn.commit()
    return conn, prod, deja


def test_dry_run_does_not_write(tmp_path):
    source = _source_db(tmp_path / "source.sqlite3")
    target = tmp_path / "target.sqlite3"
    tconn, prod_uid, _ = _target_db(target)
    before = tconn.execute("SELECT COUNT(*) FROM entry_missions").fetchone()[0]
    tconn.close()
    plan = imp.plan_import(
        source,
        target,
        github_login="rainhuang0220",
    )
    assert plan["dry_run"] is True
    assert plan["prod_user"]["id"] == prod_uid
    assert plan["prod_user"]["id"] != plan["source_user_id"]
    assert plan["repo"]["resolution"] == "reused"
    assert plan["repo"]["source_id"] == 86
    assert plan["repo"]["target_id"] == 224
    after = (
        sqlite3.connect(target)
        .execute("SELECT COUNT(*) FROM entry_missions")
        .fetchone()[0]
    )
    assert after == before


def test_refuses_ambiguous_github_identity(tmp_path):
    source = _source_db(tmp_path / "source.sqlite3")
    target = tmp_path / "target.sqlite3"
    tconn, _, _ = _target_db(target)
    tconn.execute(
        "UPDATE users SET github_login=NULL, github_id=NULL WHERE github_login='rainhuang0220'"
    )
    tconn.commit()
    tconn.close()
    with pytest.raises(imp.ImportBlocked):
        imp.plan_import(source, target, github_login="rainhuang0220")


def test_apply_remaps_preserves_old_rows_and_selects_active(tmp_path):
    source = _source_db(tmp_path / "source.sqlite3")
    target = tmp_path / "target.sqlite3"
    tconn, prod_uid, _ = _target_db(target)
    old_missions = [
        r[0] for r in tconn.execute("SELECT id FROM entry_missions ORDER BY id")
    ]
    old_jobs = [
        r[0] for r in tconn.execute("SELECT id FROM contribution_jobs ORDER BY id")
    ]
    old_arts = list(
        tconn.execute("SELECT id, kind, body FROM contribution_artifacts ORDER BY id")
    )
    tconn.close()

    result = imp.apply_import(source, target, github_login="rainhuang0220")
    assert result["dry_run"] is False
    mapping = result["id_mapping"]
    assert mapping["missions"][1] not in old_missions
    assert mapping["missions"][2] not in old_missions
    assert mapping["jobs"][2] not in old_jobs
    assert mapping["jobs"][6] not in old_jobs
    assert 8 not in mapping["artifacts"] or mapping["artifacts"][8] != 8
    assert mapping["artifacts"][16] != 16

    conn = connect(target)
    preserved = list(
        conn.execute(
            "SELECT id FROM entry_missions WHERE full_name='Prescott-Data/jarviscore-framework'"
        )
    )
    assert [r[0] for r in preserved] == old_missions
    for aid, kind, body in old_arts:
        row = conn.execute(
            "SELECT kind, body FROM contribution_artifacts WHERE id=?", (aid,)
        ).fetchone()
        assert row == (kind, body)

    assert (
        conn.execute(
            "SELECT user_id FROM entry_missions WHERE id=?", (mapping["missions"][2],)
        ).fetchone()[0]
        == prod_uid
    )
    assert (
        conn.execute(
            "SELECT user_id FROM contribution_jobs WHERE id=?", (mapping["jobs"][6],)
        ).fetchone()[0]
        == prod_uid
    )
    assert (
        conn.execute(
            "SELECT repo_id FROM entry_missions WHERE id=?", (mapping["missions"][2],)
        ).fetchone()[0]
        == 224
    )

    src = sqlite3.connect(source)
    src_pkg = src.execute(
        "SELECT body FROM contribution_artifacts WHERE id=16"
    ).fetchone()[0]
    dst_pkg = conn.execute(
        "SELECT body FROM contribution_artifacts WHERE id=?",
        (mapping["artifacts"][16],),
    ).fetchone()[0]
    assert dst_pkg == src_pkg
    assert (
        hashlib.sha256(dst_pkg.encode()).hexdigest()
        == hashlib.sha256(src_pkg.encode()).hexdigest()
    )

    active = active_contribution(conn, prod_uid, "vshulcz/deja-vu")
    assert active is not None
    assert active["issue_number"] == 1551
    assert "friction.go" in active["diff"]
    assert "doctor.go" not in active["diff"]
    hist = history_for_repo(conn, prod_uid, "vshulcz/deja-vu")
    assert [h["issue_number"] for h in hist] == [1551, 1828]
    old = next(h for h in hist if h["issue_number"] == 1828)
    assert old["role"] == "history"
    assert active["remote_writes"] == 0
    pkg = json.loads(dst_pkg)
    assert pkg["implementation"]["clean_before"] is True
    assert pkg["implementation"]["mode"] == "autonomous_executor"


def test_collision_skips_already_imported_issue(tmp_path):
    source = _source_db(tmp_path / "source.sqlite3")
    target = tmp_path / "target.sqlite3"
    tconn, _, _ = _target_db(target)
    tconn.close()
    first = imp.apply_import(source, target, github_login="rainhuang0220")
    second = imp.apply_import(source, target, github_login="rainhuang0220")
    assert second["inserts"]["entry_missions"] == 0
    assert second["inserts"]["contribution_jobs"] == 0
    assert first["id_mapping"]["missions"] == second["id_mapping"]["missions"]
    conn = connect(target)
    n = conn.execute(
        "SELECT COUNT(*) FROM entry_missions WHERE full_name='vshulcz/deja-vu'"
    ).fetchone()[0]
    assert n == 2


def test_mission_content_conflict_aborts_without_inserting_children(tmp_path):
    source = _source_db(tmp_path / "source.sqlite3")
    target = tmp_path / "target.sqlite3"
    tconn, prod_uid, deja = _target_db(target)
    _insert_mission(
        tconn,
        user_id=prod_uid,
        repo_id=deja,
        issue=1828,
        created="2026-09-08T03:54:35+00:00",
        extra={"note": "different production snapshot"},
    )
    before_jobs = tconn.execute("SELECT COUNT(*) FROM contribution_jobs").fetchone()[0]
    before_arts = tconn.execute(
        "SELECT COUNT(*) FROM contribution_artifacts"
    ).fetchone()[0]
    tconn.close()

    with pytest.raises(imp.ImportBlocked, match="ABORT_CONFLICT"):
        imp.apply_import(source, target, github_login="rainhuang0220")

    conn = sqlite3.connect(target)
    assert (
        conn.execute("SELECT COUNT(*) FROM contribution_jobs").fetchone()[0]
        == before_jobs
    )
    assert (
        conn.execute("SELECT COUNT(*) FROM contribution_artifacts").fetchone()[0]
        == before_arts
    )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM entry_missions WHERE full_name='vshulcz/deja-vu'"
        ).fetchone()[0]
        == 1
    )


def test_package_content_conflict_aborts_without_inserting_remaining(tmp_path):
    source = _source_db(tmp_path / "source.sqlite3")
    target = tmp_path / "target.sqlite3"
    tconn, prod_uid, deja = _target_db(target)
    _insert_mission(
        tconn,
        user_id=prod_uid,
        repo_id=deja,
        issue=1828,
        created="2026-09-08T03:54:35+00:00",
    )
    jid = _insert_job(
        tconn,
        user_id=prod_uid,
        repo_id=deja,
        issue=1828,
        created="2026-09-08T04:05:44+00:00",
    )
    _insert_artifact(tconn, job_id=jid, kind="diff", body=DIFF_1828)
    _insert_artifact(
        tconn, job_id=jid, kind="package", body='{"remote_writes":0,"qa":"DIFFERS"}'
    )
    before_missions = tconn.execute("SELECT COUNT(*) FROM entry_missions").fetchone()[0]
    before_jobs = tconn.execute("SELECT COUNT(*) FROM contribution_jobs").fetchone()[0]
    tconn.close()

    with pytest.raises(imp.ImportBlocked, match="ABORT_CONFLICT"):
        imp.apply_import(source, target, github_login="rainhuang0220")

    conn = sqlite3.connect(target)
    assert (
        conn.execute("SELECT COUNT(*) FROM entry_missions").fetchone()[0]
        == before_missions
    )
    assert (
        conn.execute("SELECT COUNT(*) FROM contribution_jobs").fetchone()[0]
        == before_jobs
    )
    bodies = [
        r[0]
        for r in conn.execute(
            "SELECT body FROM contribution_artifacts WHERE kind='package' ORDER BY id"
        )
    ]
    assert '{"remote_writes":0,"qa":"DIFFERS"}' in bodies
    assert not any("undefined symbol" in (body or "") for body in bodies)


def test_half_set_mission_skip_does_not_insert_jobs(tmp_path):
    source = _source_db(tmp_path / "source.sqlite3")
    target = tmp_path / "target.sqlite3"
    tconn, prod_uid, deja = _target_db(target)
    _insert_mission(
        tconn,
        user_id=prod_uid,
        repo_id=deja,
        issue=1828,
        created="2026-09-08T03:54:35+00:00",
    )
    before_jobs = tconn.execute("SELECT COUNT(*) FROM contribution_jobs").fetchone()[0]
    tconn.close()

    with pytest.raises(imp.ImportBlocked, match="ABORT_CONFLICT"):
        imp.apply_import(source, target, github_login="rainhuang0220")

    conn = sqlite3.connect(target)
    assert (
        conn.execute("SELECT COUNT(*) FROM contribution_jobs").fetchone()[0]
        == before_jobs
    )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM contribution_jobs WHERE full_name='vshulcz/deja-vu'"
        ).fetchone()[0]
        == 0
    )


def test_does_not_import_unrelated_continuum_job(tmp_path):

    source = _source_db(tmp_path / "source.sqlite3")
    target = tmp_path / "target.sqlite3"
    _target_db(target)
    result = imp.apply_import(source, target, github_login="rainhuang0220")
    assert 1 not in result["id_mapping"]["jobs"]
    conn = sqlite3.connect(target)
    names = [
        r[0] for r in conn.execute("SELECT DISTINCT full_name FROM contribution_jobs")
    ]
    assert "Cyrax321/CONTINUUM" in names
    imported = [
        r[0]
        for r in conn.execute(
            "SELECT full_name FROM contribution_jobs WHERE user_id=?",
            (result["prod_user"]["id"],),
        )
    ]
    assert imported.count("vshulcz/deja-vu") >= 2
    assert "Cyrax321/CONTINUUM" not in imported
