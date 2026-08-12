from __future__ import annotations

import argparse
import subprocess
import uuid
from pathlib import Path

from qa_swarm.config import settings
from qa_swarm.graph import run_cycle
from qa_swarm.sandbox import Sandbox


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    )
    return Path(result.stdout.strip())


def run_command(target: str, cycles: int) -> None:
    repo_root = _repo_root()
    target_path = Path(target)
    if not target_path.is_absolute():
        target_path = (Path.cwd() / target_path).resolve()
    target_rel = target_path.relative_to(repo_root)

    for i in range(cycles):
        run_id = uuid.uuid4().hex[:8]
        print(f"\n=== qa-swarm cycle {i + 1}/{cycles} (run {run_id}) ===")

        sandbox = Sandbox.create(
            repo_root=repo_root, run_id=run_id, runs_dir=repo_root / settings.runs_dir
        )
        app_root = sandbox.path_for(target_rel / "app")
        test_target = (target_rel / "tests").as_posix()
        regression_dir = sandbox.path_for(target_rel / "tests")

        try:
            final_state = run_cycle(sandbox, app_root, test_target, regression_dir, settings)
        except Exception:
            sandbox.cleanup(remove_branch=True)
            raise

        for line in final_state["log"]:
            print(f"  {line}")

        if final_state["status"] == "healed":
            diff_text = sandbox.diff_since(final_state["mutation_commit"])
            diff_path = sandbox.export_diff(
                diff_text, repo_root / settings.runs_dir / run_id / "patch.diff"
            )
            print(f"  -> HEALED. Branch: {sandbox.branch}  Diff: {diff_path}")
            sandbox.cleanup(remove_branch=False)
        else:
            print(f"  -> UNRESOLVED for run {run_id}.")
            sandbox.cleanup(remove_branch=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="qa-swarm")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Run one or more Aggressor/Detective/Surgeon cycles against a target app"
    )
    run_parser.add_argument(
        "--target", required=True, help="Path to the target app (containing app/ and tests/ dirs)"
    )
    run_parser.add_argument("--cycles", type=int, default=1, help="Number of mutation cycles to run")

    args = parser.parse_args()

    if args.command == "run":
        run_command(args.target, args.cycles)


if __name__ == "__main__":
    main()
