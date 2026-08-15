import re
import subprocess
import textwrap
from pathlib import Path

import pytest

import qa_swarm.agents.detective as detective_mod
import qa_swarm.agents.surgeon as surgeon_mod
from qa_swarm import cli


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

BOOTSTRAP_SOURCE = textwrap.dedent(
    """
    def ping(n):
        if n >= 10:
            return "reachable"
        return "unreachable"
    """
).strip() + "\n"

SPEC_SOURCE = textwrap.dedent(
    """
    from src.calc import classify


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
def custom_layout_repo(tmp_path) -> Path:
    repo = tmp_path / "custom_repo"
    (repo / "src").mkdir(parents=True)
    (repo / "spec").mkdir()
    (repo / "src" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "calc.py").write_text(CALC_SOURCE, encoding="utf-8")
    (repo / "src" / "bootstrap.py").write_text(BOOTSTRAP_SOURCE, encoding="utf-8")
    (repo / "spec" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "spec" / "test_calc.py").write_text(SPEC_SOURCE, encoding="utf-8")

    _run_git(["init", "-q"], cwd=repo)
    _run_git(["config", "user.email", "test@example.com"], cwd=repo)
    _run_git(["config", "user.name", "Test"], cwd=repo)
    _run_git(["add", "-A"], cwd=repo)
    _run_git(["commit", "-q", "-m", "initial"], cwd=repo)
    return repo


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeDetectiveLLM:
    def invoke(self, messages):
        prompt = messages[-1].content
        match = re.search(r"import the mutated module as `([\w.]+)`", prompt, re.IGNORECASE)
        import_path = match.group(1) if match else "src.calc"
        return FakeMessage(REGRESSION_TEST_TEMPLATE.format(import_path=import_path))


class FakeSurgeonLLM:
    def invoke(self, messages):
        return FakeMessage(CALC_SOURCE)


def test_generic_layout_and_exclude_files(custom_layout_repo, monkeypatch, capsys):
    monkeypatch.chdir(custom_layout_repo)
    monkeypatch.setattr(detective_mod, "get_llm", lambda temperature=0.0: FakeDetectiveLLM())
    monkeypatch.setattr(surgeon_mod, "get_llm", lambda temperature=0.0: FakeSurgeonLLM())

    cli.run_command(
        target=".",
        cycles=4,
        app_dir="src",
        tests_dir="spec",
        exclude_files=frozenset({"__init__.py", "bootstrap.py"}),
    )

    output = capsys.readouterr().out
    assert "bootstrap.py" not in output
    assert "HEALED" in output
