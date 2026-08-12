import subprocess
from pathlib import Path

import pytest

from qa_swarm.sandbox import Sandbox


def _run(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def scratch_repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _run(["init", "-q"], cwd=repo)
    _run(["config", "user.email", "test@example.com"], cwd=repo)
    _run(["config", "user.name", "Test"], cwd=repo)
    _run(["add", "-A"], cwd=repo)
    _run(["commit", "-q", "-m", "initial"], cwd=repo)
    return repo


def test_create_checks_out_worktree_on_new_branch(scratch_repo):
    sandbox = Sandbox.create(repo_root=scratch_repo, run_id="run1", runs_dir=scratch_repo / "runs")

    assert sandbox.worktree_path.exists()
    assert (sandbox.worktree_path / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert sandbox.branch == "qa-swarm/fix-run1"

    sandbox.cleanup(remove_branch=True)


def test_commit_and_diff_since_capture_changes(scratch_repo):
    sandbox = Sandbox.create(repo_root=scratch_repo, run_id="run2", runs_dir=scratch_repo / "runs")

    sandbox.path_for("app.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert sandbox.has_uncommitted_changes()

    sha = sandbox.commit("bump value")
    diff = sandbox.diff_since(sandbox.base_commit)

    assert "-VALUE = 1" in diff
    assert "+VALUE = 2" in diff
    assert sha != sandbox.base_commit

    sandbox.cleanup(remove_branch=True)


def test_export_diff_writes_file(scratch_repo):
    sandbox = Sandbox.create(repo_root=scratch_repo, run_id="run3", runs_dir=scratch_repo / "runs")
    sandbox.path_for("app.py").write_text("VALUE = 3\n", encoding="utf-8")
    sandbox.commit("bump value")

    dest = scratch_repo / "runs" / "run3" / "patch.diff"
    out = sandbox.export_diff(sandbox.diff_since(sandbox.base_commit), dest)

    assert out == dest
    assert "VALUE = 3" in dest.read_text(encoding="utf-8")

    sandbox.cleanup(remove_branch=True)


def test_reset_hard_discards_changes(scratch_repo):
    sandbox = Sandbox.create(repo_root=scratch_repo, run_id="run4", runs_dir=scratch_repo / "runs")
    sandbox.path_for("app.py").write_text("VALUE = 999\n", encoding="utf-8")
    sandbox.commit("bad mutation")

    sandbox.reset_hard(sandbox.base_commit)

    assert sandbox.path_for("app.py").read_text(encoding="utf-8") == "VALUE = 1\n"

    sandbox.cleanup(remove_branch=True)


def test_cleanup_removes_worktree_and_branch(scratch_repo):
    sandbox = Sandbox.create(repo_root=scratch_repo, run_id="run5", runs_dir=scratch_repo / "runs")
    sandbox.cleanup(remove_branch=True)

    assert not sandbox.worktree_path.exists()
    result = subprocess.run(
        ["git", "branch", "--list", sandbox.branch], cwd=scratch_repo, capture_output=True, text=True
    )
    assert sandbox.branch not in result.stdout
