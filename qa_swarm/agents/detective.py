from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from qa_swarm.agents.aggressor import Mutation
from qa_swarm.llm import get_llm, invoke_with_retry


@dataclass
class TestReport:
    passed: bool
    output: str


@dataclass
class RegressionTest:
    path: Path
    content: str


@dataclass
class DetectiveResult:
    mutant_caught: bool
    test_report: TestReport
    regression_test: RegressionTest | None
    caught_via: str | None = None


def run_pytest(cwd: Path, target: str) -> TestReport:
    result = subprocess.run(
        ["python", "-m", "pytest", target, "-q"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return TestReport(passed=result.returncode == 0, output=result.stdout + result.stderr)


def module_import_path(worktree_root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(worktree_root).with_suffix("")
    return ".".join(rel.parts)


REGRESSION_TEST_SYSTEM_PROMPT = """You are the Detective agent in an automated mutation-testing swarm.
A logical bug was just injected into a Python function. Given the original source, the
mutated source, and the pytest failure output, write ONE new pytest test function that
pins down the specific incorrect behavior the mutation introduced (asserting the CORRECT
behavior, matching the original function's intent). Return ONLY the Python code for the
test function (plus any needed imports), no prose, no markdown fences."""


def synthesize_regression_test(mutation: Mutation, test_report: TestReport, import_path: str) -> str:
    llm = get_llm()
    prompt = (
        f"Original source:\n```python\n{mutation.original_source}\n```\n\n"
        f"Mutated source:\n```python\n{mutation.mutated_source}\n```\n\n"
        f"Mutation applied: {mutation.description}\n\n"
        f"pytest failure output:\n```\n{test_report.output}\n```\n\n"
        f"Import the mutated module as `{import_path}`. Write the new test function now."
    )
    response = invoke_with_retry(
        llm, [SystemMessage(content=REGRESSION_TEST_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    return _strip_code_fences(response.content)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip() + "\n"


def write_regression_test(regression_dir: Path, run_id: str, code: str) -> RegressionTest:
    regression_dir.mkdir(parents=True, exist_ok=True)
    path = regression_dir / f"test_qa_swarm_regression_{run_id}.py"
    path.write_text(code, encoding="utf-8")
    return RegressionTest(path=path, content=code)


def investigate(
    worktree_root: Path,
    test_target: str,
    regression_dir: Path,
    mutation: Mutation,
    run_id: str,
    telemetry_config=None,
) -> DetectiveResult:
    report = run_pytest(worktree_root, test_target)
    caught_via = "pytest"

    if report.passed and telemetry_config is not None:
        from qa_swarm.telemetry import run_telemetry_check

        telemetry_report = run_telemetry_check(worktree_root, regression_dir, telemetry_config)
        if not telemetry_report.passed:
            report = telemetry_report
            caught_via = "telemetry"

    if report.passed:
        return DetectiveResult(mutant_caught=False, test_report=report, regression_test=None)

    import_path = module_import_path(worktree_root, mutation.file)
    code = synthesize_regression_test(mutation, report, import_path)
    regression_test = write_regression_test(regression_dir, run_id, code)

    confirm = run_pytest(worktree_root, str(regression_test.path.relative_to(worktree_root)))
    if confirm.passed:
        regression_test.path.unlink(missing_ok=True)
        return DetectiveResult(mutant_caught=False, test_report=report, regression_test=None)

    return DetectiveResult(
        mutant_caught=True, test_report=report, regression_test=regression_test, caught_via=caught_via
    )
