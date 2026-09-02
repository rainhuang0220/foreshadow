from foreshadow.contribution.clone import clone_from_url, git_env_without_tokens
from foreshadow.contribution.executor import ContributionJob, JobStatus, PatchArtifact
from foreshadow.contribution.package import build_package
from foreshadow.contribution.task import StructuredTask, from_entry


def test_structured_task_prompt_contains_issue_and_forbids_push():
    task = StructuredTask(
        repository="Cyrax321/CONTINUUM",
        task="Fix stdio crash on JSON non-object",
        issue_number=582,
        evidence=["https://github.com/Cyrax321/CONTINUUM/issues/582"],
        expected_behavior="stdio answers bad_request and keeps the loop",
        acceptance_criteria=["echo '[]' does not AttributeError"],
        relevant_files=["src/continuum/serve/server.py"],
        test_commands=["pytest tests/test_serve.py -o addopts="],
        forbidden_actions=["git push"],
        why="Issue #582 documents a crash on main",
    )
    prompt = task.to_prompt()
    assert "Cyrax321/CONTINUUM" in prompt
    assert "#582" in prompt
    assert "git push" in prompt
    assert "fix repo" not in prompt.lower() or "Task:" in prompt


def test_from_entry_stringifies_issue_evidence_urls():
    task = from_entry(
        "acme/x",
        {
            "recommended": {
                "title": "Follow issue 582",
                "issue_number": 582,
                "why": ["crash"],
                "evidence": [
                    {
                        "kind": "issue",
                        "id": 582,
                        "url": "https://github.com/acme/x/issues/582",
                    }
                ],
            }
        },
    )
    assert task.issue_number == 582
    assert task.evidence == ["https://github.com/acme/x/issues/582"]


def test_from_entry_does_not_invent_issue_numbers():
    task = from_entry(
        "acme/x",
        {
            "recommended": {
                "title": "File an issue first",
                "route": "ISSUE_FIRST",
                "issue_number": None,
                "why": ["thin evidence"],
            }
        },
    )
    assert task.issue_number is None
    assert "ISSUE" in task.task or "issue" in task.task.lower() or task.task


def test_clone_from_local_git_strips_remote_and_tokens(tmp_path, monkeypatch):
    import subprocess

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken_not_a_real_secret")
    src = tmp_path / "src"
    src.mkdir()
    env = git_env_without_tokens()
    subprocess.run(["git", "init"], cwd=src, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=src, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=src, check=True)
    (src / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "README"], cwd=src, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=src,
        check=True,
        env={
            **env,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "a@b.c",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "a@b.c",
        },
    )
    dest = tmp_path / "dest"
    clone_from_url(str(src), dest)
    remotes = subprocess.run(
        ["git", "-C", str(dest), "remote"], capture_output=True, text=True, check=True
    )
    assert remotes.stdout.strip() == ""
    env_used = git_env_without_tokens()
    assert "GITHUB_TOKEN" not in env_used
    assert "ghp_testtoken_not_a_real_secret" not in " ".join(env_used.values())


def test_package_records_zero_remote_writes():
    job = ContributionJob(
        full_name="acme/x",
        backend="mini_swe_agent",
        status=JobStatus.ready,
        why="issue 1",
        task={"structured": {"repository": "acme/x", "task": "fix", "issue_number": 1}},
    )
    artifact = PatchArtifact(
        diff="diff --git a/a.py b/a.py\n",
        why="issue 1",
        tests_passed=True,
        qa_ok=True,
        files=["a.py"],
        title="Fix a.py",
    )
    pkg = build_package(job, artifact, qa_ok=True)
    assert pkg["remote_writes"] == 0
    assert pkg["related_issue"] == "#1"
    assert pkg["qa"] == "PASS"
    assert pkg["files_changed_n"] == 1
    assert pkg["remote_status"] == "WAITING_USER_APPROVAL"
