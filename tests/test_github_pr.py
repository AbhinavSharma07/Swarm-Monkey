from dataclasses import dataclass
from pathlib import Path

from qa_swarm import github_pr
from qa_swarm.agents.aggressor import Mutation


@dataclass
class _FakeSandbox:
    branch: str
    worktree_path: Path
    run_id: str = "run1"


def _mutation(file: Path) -> Mutation:
    return Mutation(
        operator="boundary_shift",
        file=file,
        function="calc",
        lineno=1,
        description="boundary_shift in calc(): `1` -> `2`",
        original_source="",
        mutated_source="",
    )


class _FakeCompletedProcess:
    def __init__(self, returncode, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def test_gh_available_reflects_shutil_which(monkeypatch):
    monkeypatch.setattr(github_pr.shutil, "which", lambda name: "/usr/bin/gh")
    assert github_pr.gh_available() is True

    monkeypatch.setattr(github_pr.shutil, "which", lambda name: None)
    assert github_pr.gh_available() is False


def test_push_branch_returns_true_on_success(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, cwd, capture_output, text):
        calls.append((args, cwd))
        return _FakeCompletedProcess(returncode=0)

    monkeypatch.setattr(github_pr.subprocess, "run", fake_run)
    sandbox = _FakeSandbox(branch="qa-swarm/fix-run1", worktree_path=tmp_path)

    assert github_pr.push_branch(sandbox) is True
    assert calls[0][0] == ["git", "push", "-u", "origin", "qa-swarm/fix-run1"]
    assert calls[0][1] == tmp_path


def test_push_branch_returns_false_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        github_pr.subprocess, "run", lambda *a, **k: _FakeCompletedProcess(returncode=1)
    )
    sandbox = _FakeSandbox(branch="qa-swarm/fix-run1", worktree_path=tmp_path)

    assert github_pr.push_branch(sandbox) is False


def test_open_pull_request_returns_url_on_success(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, cwd, capture_output, text):
        calls.append(args)
        return _FakeCompletedProcess(returncode=0, stdout="https://github.com/x/y/pull/1\n")

    monkeypatch.setattr(github_pr.subprocess, "run", fake_run)
    sandbox = _FakeSandbox(branch="qa-swarm/fix-run1", worktree_path=tmp_path)

    url = github_pr.open_pull_request(sandbox, _mutation(tmp_path / "calc.py"), base="main")

    assert url == "https://github.com/x/y/pull/1"
    args = calls[0]
    assert args[:3] == ["gh", "pr", "create"]
    assert "--base" in args and args[args.index("--base") + 1] == "main"
    assert "--head" in args and args[args.index("--head") + 1] == "qa-swarm/fix-run1"


def test_open_pull_request_returns_none_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        github_pr.subprocess, "run", lambda *a, **k: _FakeCompletedProcess(returncode=1, stdout="")
    )
    sandbox = _FakeSandbox(branch="qa-swarm/fix-run1", worktree_path=tmp_path)

    assert github_pr.open_pull_request(sandbox, _mutation(tmp_path / "calc.py")) is None


def test_push_and_open_pr_short_circuits_when_gh_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(github_pr, "gh_available", lambda: False)

    def fail_if_called(*a, **k):
        raise AssertionError("subprocess.run should not be called when gh is unavailable")

    monkeypatch.setattr(github_pr.subprocess, "run", fail_if_called)
    sandbox = _FakeSandbox(branch="qa-swarm/fix-run1", worktree_path=tmp_path)

    assert github_pr.push_and_open_pr(sandbox, _mutation(tmp_path / "calc.py")) is None
