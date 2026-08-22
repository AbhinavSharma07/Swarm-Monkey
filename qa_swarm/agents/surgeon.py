from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from qa_swarm.agents.aggressor import Mutation
from qa_swarm.agents.detective import RegressionTest, TestReport, run_pytest
from qa_swarm.llm import get_llm, invoke_with_retry


@dataclass
class PatchAttempt:
    patched_source: str
    validated: bool
    test_report: TestReport


SURGEON_SYSTEM_PROMPT = """You are the Surgeon agent in an automated mutation-testing swarm.
A logical bug was injected into the function below and is now failing tests. Rewrite the
ENTIRE file with the bug fixed, preserving all other logic and structure exactly. Return
ONLY the complete corrected Python source for the file, no prose, no markdown fences."""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip() + "\n"


def generate_patch(
    mutation: Mutation,
    test_report: TestReport,
    regression_test: RegressionTest,
    previous_attempt: PatchAttempt | None = None,
    usage=None,
) -> str:
    llm = get_llm()
    context = (
        f"Original (pre-mutation) source:\n```python\n{mutation.original_source}\n```\n\n"
        f"Current (buggy) source:\n```python\n{mutation.mutated_source}\n```\n\n"
        f"Mutation applied: {mutation.description}\n\n"
        f"pytest failure output:\n```\n{test_report.output}\n```\n\n"
        f"Regression test that must pass:\n```python\n{regression_test.content}\n```\n"
    )
    if previous_attempt is not None:
        context += (
            "\nA previous fix attempt still failed validation:\n"
            f"```python\n{previous_attempt.patched_source}\n```\n"
            f"Failure after that attempt:\n```\n{previous_attempt.test_report.output}\n```\n"
        )
    response = invoke_with_retry(
        llm, [SystemMessage(content=SURGEON_SYSTEM_PROMPT), HumanMessage(content=context)], usage=usage
    )
    return _strip_code_fences(response.content)


def change_ratio(before: str, after: str) -> float:
    matcher = difflib.SequenceMatcher(a=before.splitlines(), b=after.splitlines())
    return 1 - matcher.ratio()


def apply_and_validate(
    worktree_root: Path,
    mutation: Mutation,
    test_target: str,
    regression_test: RegressionTest,
    patched_source: str,
    max_change_ratio: float = 0.5,
) -> PatchAttempt:
    ratio = change_ratio(mutation.mutated_source, patched_source)
    if ratio > max_change_ratio:
        rejected_report = TestReport(
            passed=False,
            output=(
                f"Patch rejected before testing: changed {ratio:.0%} of the file, "
                f"exceeding the {max_change_ratio:.0%} safety limit."
            ),
        )
        return PatchAttempt(patched_source=patched_source, validated=False, test_report=rejected_report)

    mutation.file.write_text(patched_source, encoding="utf-8")
    suite_report = run_pytest(worktree_root, test_target)
    regression_report = run_pytest(
        worktree_root, str(regression_test.path.relative_to(worktree_root))
    )
    validated = suite_report.passed and regression_report.passed
    return PatchAttempt(
        patched_source=patched_source,
        validated=validated,
        test_report=TestReport(passed=validated, output=suite_report.output + "\n" + regression_report.output),
    )


def heal(
    worktree_root: Path,
    mutation: Mutation,
    test_target: str,
    test_report: TestReport,
    regression_test: RegressionTest,
    max_retries: int,
    max_change_ratio: float = 0.5,
    usage=None,
) -> PatchAttempt:
    attempt: PatchAttempt | None = None
    current_report = test_report
    for _ in range(max_retries):
        patched_source = generate_patch(mutation, current_report, regression_test, attempt, usage=usage)
        attempt = apply_and_validate(
            worktree_root, mutation, test_target, regression_test, patched_source, max_change_ratio
        )
        if attempt.validated:
            return attempt
        current_report = attempt.test_report
    return attempt
