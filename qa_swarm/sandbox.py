from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return result.stdout


@dataclass
class Sandbox:
    repo_root: Path
    run_id: str
    branch: str
    worktree_path: Path
    base_commit: str

    @classmethod
    def create(cls, repo_root: Path, run_id: str, runs_dir: Path) -> "Sandbox":
        branch = f"qa-swarm/fix-{run_id}"
        worktree_path = (runs_dir / run_id / "worktree").resolve()
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        base_commit = _run_git(["rev-parse", "HEAD"], cwd=repo_root).strip()
        _run_git(
            ["worktree", "add", "-b", branch, str(worktree_path), base_commit],
            cwd=repo_root,
        )
        return cls(
            repo_root=repo_root,
            run_id=run_id,
            branch=branch,
            worktree_path=worktree_path,
            base_commit=base_commit,
        )

    def path_for(self, relative_to_repo: Path | str) -> Path:
        return self.worktree_path / relative_to_repo

    def has_uncommitted_changes(self) -> bool:
        status = _run_git(["status", "--porcelain"], cwd=self.worktree_path)
        return bool(status.strip())

    def commit(self, message: str) -> str:
        _run_git(["add", "-A"], cwd=self.worktree_path)
        _run_git(["commit", "-m", message], cwd=self.worktree_path)
        return _run_git(["rev-parse", "HEAD"], cwd=self.worktree_path).strip()

    def diff_since(self, base_sha: str) -> str:
        return _run_git(["diff", base_sha, "HEAD"], cwd=self.worktree_path)

    def export_diff(self, diff_text: str, dest_path: Path) -> Path:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(diff_text, encoding="utf-8")
        return dest_path

    def reset_hard(self, sha: str) -> None:
        _run_git(["reset", "--hard", sha], cwd=self.worktree_path)
        _run_git(["clean", "-fd"], cwd=self.worktree_path)

    def cleanup(self, remove_branch: bool = False) -> None:
        _run_git(["worktree", "remove", "--force", str(self.worktree_path)], cwd=self.repo_root)
        if remove_branch:
            _run_git(["branch", "-D", self.branch], cwd=self.repo_root)
