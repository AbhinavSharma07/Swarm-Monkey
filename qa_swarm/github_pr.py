from __future__ import annotations

import shutil
import subprocess

from qa_swarm.agents.aggressor import Mutation
from qa_swarm.sandbox import Sandbox

NETWORK_TIMEOUT_SECONDS = 30


def gh_available() -> bool:
    return shutil.which("gh") is not None


def push_branch(sandbox: Sandbox) -> bool:
    try:
        result = subprocess.run(
            ["git", "push", "-u", "origin", sandbox.branch],
            cwd=sandbox.worktree_path,
            capture_output=True,
            text=True,
            timeout=NETWORK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False
    return result.returncode == 0


def open_pull_request(sandbox: Sandbox, mutation: Mutation, base: str = "main") -> str | None:
    title = f"qa-swarm: fix {mutation.operator} in {mutation.function}()"
    body = (
        "Automated fix from qa-swarm.\n\n"
        f"**Mutation caught:** {mutation.description}\n\n"
        f"**Run:** {sandbox.run_id}\n"
    )
    try:
        result = subprocess.run(
            ["gh", "pr", "create", "--title", title, "--body", body, "--base", base, "--head", sandbox.branch],
            cwd=sandbox.worktree_path,
            capture_output=True,
            text=True,
            timeout=NETWORK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def push_and_open_pr(sandbox: Sandbox, mutation: Mutation, base: str = "main") -> str | None:
    if not gh_available():
        return None
    if not push_branch(sandbox):
        return None
    return open_pull_request(sandbox, mutation, base=base)
