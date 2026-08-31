import pytest

from foreshadow.auth import (
    AuthError,
    authenticate,
    create_session,
    ensure_local_user,
    hash_password,
    lookup_session,
    register_user,
    revoke_session,
    verify_password,
)
from foreshadow.db import connect, migrate
from foreshadow.reviews import apply_review, current_stances, latest_action_map


def test_password_is_hashed_not_plaintext():
    stored = hash_password("correct horse")
    assert "correct horse" not in stored
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong", stored)


def test_register_login_and_session(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    user = register_user(conn, "rain", "rain@example.com", "password1")
    assert user["username"] == "rain"
    row = conn.execute(
        "SELECT password_hash FROM users WHERE username='rain'"
    ).fetchone()
    assert "password1" not in row[0]
    again = authenticate(conn, "rain", "password1")
    assert again["id"] == user["id"]
    via_email = authenticate(conn, "rain@example.com", "password1")
    assert via_email["id"] == user["id"]
    token = create_session(conn, user["id"])
    assert lookup_session(conn, token)["username"] == "rain"
    revoke_session(conn, token)
    assert lookup_session(conn, token) is None


def test_duplicate_and_reserved_usernames(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    register_user(conn, "rain", "rain@example.com", "password1")
    with pytest.raises(AuthError):
        register_user(conn, "rain", "other@example.com", "password1")
    with pytest.raises(AuthError):
        register_user(conn, "local", "x@example.com", "password1")
    with pytest.raises(AuthError):
        authenticate(conn, "rain", "nope-nope")


def test_local_user_cannot_web_login(tmp_home):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = ensure_local_user(conn)
    assert uid >= 1
    with pytest.raises(AuthError):
        authenticate(conn, "local", "anything1")
    token = create_session(conn, uid)
    assert lookup_session(conn, token) is None


def test_reviews_are_isolated_per_user(tmp_home, frozen_clock, fake_github):
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    a = register_user(conn, "alice", "a@example.com", "password1")
    b = register_user(conn, "bob", "b@example.com", "password1")
    apply_review(
        conn,
        fake_github,
        "acme/memkit",
        "interested",
        None,
        frozen_clock,
        user_id=a["id"],
    )
    apply_review(
        conn,
        fake_github,
        "acme/memkit",
        "reject",
        None,
        frozen_clock,
        user_id=b["id"],
    )
    assert latest_action_map(conn, user_id=a["id"])["acme/memkit"] == "interested"
    assert latest_action_map(conn, user_id=b["id"])["acme/memkit"] == "reject"
    alice_rows = current_stances(conn, None, user_id=a["id"])
    bob_rows = current_stances(conn, None, user_id=b["id"])
    assert {r["action"] for r in alice_rows} == {"interested"}
    assert {r["action"] for r in bob_rows} == {"reject"}
    n = conn.execute("SELECT count(*) FROM reviews").fetchone()[0]
    assert n == 2
