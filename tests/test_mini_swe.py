"""mini-SWE executor contract. Fake agent — no live LLM in CI."""

from __future__ import annotations

from pathlib import Path

from foreshadow.contribution.executor import (
    ContributionJob,
    JobStatus,
    run_contribution,
)
from foreshadow.contribution.mini_swe import (
    DEFAULT_IMAGE,
    MiniSweExecutor,
    sandbox_env_for_container,
)
from foreshadow.contribution.package import build_package
from foreshadow.contribution.task import StructuredTask
from foreshadow.db import connect, migrate

BUGGY = """def handle(req):
    rid = req.get("id")
    return rid
"""

FIXED = """def handle(req):
    if not isinstance(req, dict):
        return {"error": "body must be a JSON object"}
    rid = req.get("id")
    return rid
"""

TEST = """from serve import handle

def test_list_body_is_client_error():
    out = handle([])
    assert out["error"] == "body must be a JSON object"

def test_object_still_works():
    assert handle({"id": 1}) == 1
"""


class _FixAgent:
    def __init__(self, sandbox: Path):
        self.sandbox = sandbox

    def run(self, prompt: str) -> dict:
        assert "git push" in prompt
        assert "#7" in prompt or "#" in prompt
        (self.sandbox / "serve.py").write_text(FIXED, encoding="utf-8")
        return {"exit_status": "submitted", "steps": 3, "cost": 0.0}


def _tiny_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "serve.py").write_text(BUGGY, encoding="utf-8")
    (root / "test_serve.py").write_text(TEST, encoding="utf-8")
    return root


def test_mini_swe_fake_agent_fixes_real_tree_without_tokens(
    tmp_home, tmp_path, monkeypatch
):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-ant-fake")
    src = _tiny_repo(tmp_path / "src")
    conn = connect(tmp_home / "foreshadow.sqlite3")
    migrate(conn)
    uid = conn.execute("SELECT id FROM users WHERE is_local=1").fetchone()[0]
    structured = StructuredTask(
        repository="acme/sidecar",
        task="JSON non-object must not crash handle()",
        issue_number=7,
        evidence=["issue 7 documents AttributeError on req.get"],
        expected_behavior="list body returns a client error object",
        acceptance_criteria=["test_list_body_is_client_error passes"],
        relevant_files=["serve.py", "test_serve.py"],
        test_commands=["python -m pytest test_serve.py -q"],
        forbidden_actions=["git push"],
        why="real crash on non-object JSON",
    )

    def factory(*, job, sandbox):
        return _FixAgent(sandbox)

    job = ContributionJob(
        user_id=uid,
        full_name="acme/sidecar",
        backend="mini_swe_agent",
        source_dir=src,
        work_dir=tmp_path / "work",
        task={"structured": structured.as_dict(), "why": structured.why},
        why=structured.why,
    )
    executor = MiniSweExecutor(agent_factory=factory, docker=False)
    artifact = run_contribution(job, executor=executor, conn=conn)
    assert job.status is JobStatus.ready
    assert artifact.tests_passed is True
    assert artifact.qa_ok is True
    assert "isinstance" in artifact.diff
    assert job.sandbox_path is not None
    remotes = (job.sandbox_path / ".git").exists()
    assert remotes
    env = sandbox_env_for_container()
    assert "GITHUB_TOKEN" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "sk-ant-fake" not in " ".join(env.values())
    pkg = build_package(job, artifact, structured=structured, qa_ok=True)
    assert pkg["remote_writes"] == 0
    assert pkg["related_issue"] == "#7"
    assert pkg["qa"] == "PASS"
    assert any(step.get("step") == "baseline_tests" for step in job.log)
    assert any(step.get("step") == "selected_task" for step in job.log)
    assert any(step.get("step") == "analyzing_repository" for step in job.log)
    assert pkg["remote_status"] == "WAITING_USER_APPROVAL"


def test_default_sandbox_image_is_published_tag():
    assert "slim-bookworm" in DEFAULT_IMAGE
    env = sandbox_env_for_container()
    assert "GITHUB_TOKEN" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env


def test_deepseek_anthropic_compat_rewrites_to_openai_tools(monkeypatch):
    from foreshadow.contribution.mini_swe import _model_setup

    monkeypatch.setenv("ANTHROPIC_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-test")
    monkeypatch.delenv("MSWEA_MODEL_NAME", raising=False)
    monkeypatch.delenv("FORESHADOW_MINISWE_MODEL", raising=False)
    name, kwargs = _model_setup()
    assert name == "openai/deepseek-v4-pro"
    assert kwargs["api_base"] == "https://api.deepseek.com"
    assert "anthropic" not in kwargs["api_base"]
