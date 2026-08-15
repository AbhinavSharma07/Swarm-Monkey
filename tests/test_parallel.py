import re
import subprocess
import textwrap
from pathlib import Path

import pytest

import qa_swarm.agents.detective as detective_mod
import qa_swarm.agents.surgeon as surgeon_mod
from qa_swarm import cli, report


def _run_git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


CALC_SOURCE = textwrap.dedent(
    """
    def classify(n):
        if n >= 10:
            return "big"
        return "small"
    """
).strip() + "\n"

SPEC_SOURCE = textwrap.dedent(
    """
    from app.calc import classify


    def test_boundary():
        assert classify(9) == "small"
        assert classify(10) == "big"
    """
).strip() + "\n"

REGRESSION_TEST_TEMPLATE = textwrap.dedent(
    """
    from {import_path} import classify


    def test_qa_swarm_regression_boundary():
        assert classify(9) == "small"
        assert classify(10) == "big"
    """
).strip() + "\n"


@pytest.fixture
def repo(tmp_path) -> Path:
    r = tmp_path / "repo"
    (r / "app").mkdir(parents=True)
    (r / "tests").mkdir()
    (r / "app" / "__init__.py").write_text("", encoding="utf-8")
    (r / "app" / "calc.py").write_text(CALC_SOURCE, encoding="utf-8")
    (r / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (r / "tests" / "test_calc.py").write_text(SPEC_SOURCE, encoding="utf-8")

    _run_git(["init", "-q"], cwd=r)
    _run_git(["config", "user.email", "test@example.com"], cwd=r)
    _run_git(["config", "user.name", "Test"], cwd=r)
    _run_git(["add", "-A"], cwd=r)
    _run_git(["commit", "-q", "-m", "initial"], cwd=r)
    return r


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeDetectiveLLM:
    def invoke(self, messages):
        prompt = messages[-1].content
        match = re.search(r"import the mutated module as `([\w.]+)`", prompt, re.IGNORECASE)
        import_path = match.group(1) if match else "app.calc"
        return FakeMessage(REGRESSION_TEST_TEMPLATE.format(import_path=import_path))


class FakeSurgeonLLM:
    def invoke(self, messages):
        return FakeMessage(CALC_SOURCE)


def test_parallel_cycles_all_complete_and_record_history(repo, monkeypatch):
    monkeypatch.chdir(repo)
    monkeypatch.setattr(detective_mod, "get_llm", lambda temperature=0.0: FakeDetectiveLLM())
    monkeypatch.setattr(surgeon_mod, "get_llm", lambda temperature=0.0: FakeSurgeonLLM())

    cli.run_command(target=".", cycles=4, parallel=2)

    history_path = repo / "runs" / "history.jsonl"
    records = report.load_history(history_path)
    assert len(records) == 4
    assert len({r.run_id for r in records}) == 4

    result = subprocess.run(
        ["git", "worktree", "list"], cwd=repo, capture_output=True, text=True, check=True
    )
    assert result.stdout.strip().count("\n") == 0
