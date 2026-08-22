from __future__ import annotations

import argparse
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from qa_swarm import github_pr, report
from qa_swarm.config import settings
from qa_swarm.graph import run_cycle
from qa_swarm.sandbox import Sandbox
from qa_swarm.telemetry import discover_telemetry_config


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True, timeout=30
    )
    return Path(result.stdout.strip())


def _run_one_cycle(
    repo_root: Path,
    target_rel: Path,
    index: int,
    cycles: int,
    app_dir: str,
    tests_dir: str,
    exclude_files: frozenset[str] | None,
    open_pr: bool,
    pr_base: str,
    app_module: str = "main",
) -> None:
    run_id = uuid.uuid4().hex[:8]
    lines = [f"\n=== qa-swarm cycle {index + 1}/{cycles} (run {run_id}) ==="]

    sandbox = Sandbox.create(repo_root=repo_root, run_id=run_id, runs_dir=repo_root / settings.runs_dir)
    app_root = sandbox.path_for(target_rel / app_dir)
    test_target = (target_rel / tests_dir).as_posix()
    regression_dir = sandbox.path_for(target_rel / tests_dir)
    telemetry_config = discover_telemetry_config(sandbox.worktree_path, target_rel, app_dir, app_module)
    if telemetry_config is not None:
        lines.append(f"  (telemetry: {len(telemetry_config.requests)} request scenarios active)")

    try:
        final_state = run_cycle(
            sandbox,
            app_root,
            test_target,
            regression_dir,
            settings,
            exclude_files=exclude_files,
            telemetry_config=telemetry_config,
        )
    except Exception:
        sandbox.cleanup(remove_branch=True)
        raise

    for line in final_state["log"]:
        lines.append(f"  {line}")

    mutation = final_state.get("mutation")
    usage = final_state.get("token_usage")
    history_path = repo_root / settings.runs_dir / "history.jsonl"
    report.append_record(
        history_path,
        report.CycleRecord(
            run_id=run_id,
            status=final_state["status"],
            operator=mutation.operator if mutation else None,
            function=mutation.function if mutation else None,
            file=str(mutation.file) if mutation else None,
            description=mutation.description if mutation else None,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        ),
    )

    if final_state["status"] == "healed":
        diff_text = sandbox.diff_since(final_state["mutation_commit"])
        diff_path = sandbox.export_diff(diff_text, repo_root / settings.runs_dir / run_id / "patch.diff")
        lines.append(f"  -> HEALED. Branch: {sandbox.branch}  Diff: {diff_path}")

        if open_pr:
            pr_url = github_pr.push_and_open_pr(sandbox, mutation, base=pr_base)
            if pr_url:
                lines.append(f"  -> PR opened: {pr_url}")
            else:
                lines.append("  -> PR automation skipped (gh unavailable, or push/create failed).")

        sandbox.cleanup(remove_branch=False)
    else:
        lines.append(f"  -> UNRESOLVED for run {run_id}.")
        sandbox.cleanup(remove_branch=True)

    print("\n".join(lines))


def run_command(
    target: str,
    cycles: int,
    app_dir: str = "app",
    tests_dir: str = "tests",
    exclude_files: frozenset[str] | None = None,
    parallel: int = 1,
    open_pr: bool = False,
    pr_base: str = "main",
    app_module: str = "main",
) -> None:
    repo_root = _repo_root()
    target_path = Path(target)
    if not target_path.is_absolute():
        target_path = (Path.cwd() / target_path).resolve()
    target_rel = target_path.relative_to(repo_root)

    if parallel <= 1:
        for i in range(cycles):
            _run_one_cycle(
                repo_root,
                target_rel,
                i,
                cycles,
                app_dir,
                tests_dir,
                exclude_files,
                open_pr,
                pr_base,
                app_module,
            )
    else:
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = [
                executor.submit(
                    _run_one_cycle,
                    repo_root,
                    target_rel,
                    i,
                    cycles,
                    app_dir,
                    tests_dir,
                    exclude_files,
                    open_pr,
                    pr_base,
                    app_module,
                )
                for i in range(cycles)
            ]
            for future in futures:
                future.result()

    history_path = repo_root / settings.runs_dir / "history.jsonl"
    print("\n" + report.format_summary(report.summarize(report.load_history(history_path))))


def report_command() -> None:
    repo_root = _repo_root()
    history_path = repo_root / settings.runs_dir / "history.jsonl"
    print(report.format_summary(report.summarize(report.load_history(history_path))))


def main() -> None:
    parser = argparse.ArgumentParser(prog="qa-swarm")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Run one or more Aggressor/Detective/Surgeon cycles against a target app"
    )
    run_parser.add_argument(
        "--target", required=True, help="Path to the target repo/app to mutate and test"
    )
    run_parser.add_argument("--cycles", type=int, default=1, help="Number of mutation cycles to run")
    run_parser.add_argument(
        "--app-dir", default="app", help="Path (relative to --target) containing the source to mutate"
    )
    run_parser.add_argument(
        "--tests-dir", default="tests", help="Path (relative to --target) containing the test suite"
    )
    run_parser.add_argument(
        "--exclude-files",
        default=None,
        help="Comma-separated filenames to never mutate (default: __init__.py,main.py)",
    )
    run_parser.add_argument(
        "--parallel", type=int, default=1, help="Number of cycles to run concurrently (default: 1, sequential)"
    )
    run_parser.add_argument(
        "--open-pr",
        action="store_true",
        help="Push healed branches and open a real GitHub PR via `gh` (requires gh installed and authenticated)",
    )
    run_parser.add_argument("--pr-base", default="main", help="Base branch for --open-pr (default: main)")
    run_parser.add_argument(
        "--app-module",
        default="main",
        help="Module name (without .py) inside --app-dir holding the FastAPI `app` object, "
        "used only if the target defines telemetry_requests.json (default: main)",
    )

    subparsers.add_parser("report", help="Print aggregate mutation-score stats from past runs")

    args = parser.parse_args()

    if args.command == "run":
        exclude_files = (
            frozenset(name.strip() for name in args.exclude_files.split(","))
            if args.exclude_files
            else None
        )
        run_command(
            args.target,
            args.cycles,
            args.app_dir,
            args.tests_dir,
            exclude_files,
            args.parallel,
            args.open_pr,
            args.pr_base,
            args.app_module,
        )
    elif args.command == "report":
        report_command()


if __name__ == "__main__":
    main()
