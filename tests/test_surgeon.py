import subprocess
import textwrap
from pathlib import Path

import pytest

from qa_swarm.agents.aggressor import Mutation
from qa_swarm.agents.surgeon import apply_and_validate, change_ratio


def _run(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_change_ratio_identical_is_zero():
    text = "a\nb\nc\n"
    assert change_ratio(text, text) == 0.0


def test_change_ratio_completely_different_is_near_one():
    assert change_ratio("a\nb\nc\n", "x\ny\nz\n") == pytest.approx(1.0)


def test_change_ratio_small_edit_is_low():
    before = "\n".join(f"line{i}" for i in range(20)) + "\n"
    after = before.replace("line5", "line5_fixed")
    assert change_ratio(before, after) < 0.2


@pytest.fixture
def worktree(tmp_path) -> Path:
    repo = tmp_path / "worktree"
    repo.mkdir()
    _run(["init", "-q"], cwd=repo)
    _run(["config", "user.email", "test@example.com"], cwd=repo)
    _run(["config", "user.name", "Test"], cwd=repo)
    return repo


def _make_mutation(target_file: Path, mutated_source: str) -> Mutation:
    target_file.write_text(mutated_source, encoding="utf-8")
    return Mutation(
        operator="boundary_shift",
        file=target_file,
        function="calc",
        lineno=1,
        description="test mutation",
        original_source=mutated_source,
        mutated_source=mutated_source,
    )


def test_apply_and_validate_rejects_oversized_rewrite_without_touching_file(worktree):
    target = worktree / "calc.py"
    buggy_source = textwrap.dedent(
        """
        def calc(n):
            return n + 1
        """
    ).strip() + "\n"
    mutation = _make_mutation(target, buggy_source)

    wildly_different_source = textwrap.dedent(
        """
        class SomethingElseEntirely:
            def unrelated_method(self, a, b, c):
                total = 0
                for value in (a, b, c):
                    total += value * 2
                return total

            def another_method(self):
                return "nothing to do with calc"
        """
    ).strip() + "\n"

    dummy_regression_test = type("RT", (), {"path": worktree / "test_x.py", "content": ""})()
    (worktree / "test_x.py").write_text("def test_x():\n    pass\n", encoding="utf-8")

    attempt = apply_and_validate(
        worktree_root=worktree,
        mutation=mutation,
        test_target="test_x.py",
        regression_test=dummy_regression_test,
        patched_source=wildly_different_source,
        max_change_ratio=0.3,
    )

    assert attempt.validated is False
    assert "rejected" in attempt.test_report.output
    assert "30%" in attempt.test_report.output
    assert target.read_text(encoding="utf-8") == buggy_source
