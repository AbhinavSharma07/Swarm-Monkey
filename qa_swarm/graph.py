from __future__ import annotations

import random
from pathlib import Path

from langgraph.graph import END, StateGraph

from qa_swarm.agents import aggressor, detective, surgeon
from qa_swarm.config import Settings
from qa_swarm.cost import TokenUsage
from qa_swarm.sandbox import Sandbox
from qa_swarm.state import SwarmState


def aggressor_node(state: SwarmState) -> dict:
    mutation = aggressor.mutate(
        state["app_root"],
        state["rng"],
        exclude=state["tried_mutations"],
        exclude_files=state.get("exclude_files"),
    )
    log = state["log"] + []

    if mutation is None:
        log.append("Aggressor: no remaining mutation candidates in the target.")
        return {"mutation": None, "log": log}

    sandbox = state["sandbox"]
    commit_sha = sandbox.commit(f"aggressor: inject {mutation.operator} in {mutation.function}()")
    log.append(f"Aggressor: {mutation.description}")

    return {
        "mutation": mutation,
        "mutation_commit": commit_sha,
        "aggressor_attempts": state.get("aggressor_attempts", 0) + 1,
        "log": log,
    }


def route_after_aggressor(state: SwarmState) -> str:
    return "give_up" if state["mutation"] is None else "detective"


def detective_node(state: SwarmState) -> dict:
    sandbox = state["sandbox"]
    mutation = state["mutation"]
    log = state["log"] + []

    usage = state["token_usage"]
    result = detective.investigate(
        worktree_root=sandbox.worktree_path,
        test_target=state["test_target"],
        regression_dir=state["regression_dir"],
        mutation=mutation,
        run_id=state["run_id"],
        telemetry_config=state.get("telemetry_config"),
        usage=usage,
    )

    if not result.mutant_caught:
        log.append(
            f"Detective: mutation at {mutation.file.name}:{mutation.lineno} was silent "
            "(no test caught it) — discarding and retrying."
        )
        sandbox.reset_hard(sandbox.base_commit)
        return {
            "detective_result": result,
            "tried_mutations": state["tried_mutations"] | {aggressor.mutation_key(mutation)},
            "token_usage": usage,
            "log": log,
        }

    log.append(
        f"Detective: mutation caught via {result.caught_via}. "
        f"Regression test written to {result.regression_test.path}"
    )
    return {"detective_result": result, "token_usage": usage, "log": log}


def route_after_detective(state: SwarmState) -> str:
    if state["detective_result"].mutant_caught:
        return "surgeon"
    if state["aggressor_attempts"] >= state["max_aggressor_retries"]:
        return "give_up"
    return "aggressor"


def surgeon_node(state: SwarmState) -> dict:
    sandbox = state["sandbox"]
    mutation = state["mutation"]
    detective_result = state["detective_result"]
    log = state["log"] + []

    usage = state["token_usage"]
    attempt = surgeon.heal(
        worktree_root=sandbox.worktree_path,
        mutation=mutation,
        test_target=state["test_target"],
        test_report=detective_result.test_report,
        regression_test=detective_result.regression_test,
        max_retries=state["max_surgeon_retries"],
        max_change_ratio=state["max_patch_change_ratio"],
        usage=usage,
    )

    if attempt.validated:
        sandbox.commit(
            f"surgeon: fix {mutation.operator} in {mutation.function}() + add regression test"
        )
        log.append("Surgeon: patch validated and committed.")
        return {"surgeon_attempt": attempt, "token_usage": usage, "status": "healed", "log": log}

    log.append("Surgeon: exhausted retries without a validated patch.")
    return {"surgeon_attempt": attempt, "token_usage": usage, "status": "unresolved", "log": log}


def give_up_node(state: SwarmState) -> dict:
    log = state["log"] + ["Cycle ended without a validated fix."]
    return {"status": "unresolved", "log": log}


def build_graph():
    graph = StateGraph(SwarmState)
    graph.add_node("aggressor", aggressor_node)
    graph.add_node("detective", detective_node)
    graph.add_node("surgeon", surgeon_node)
    graph.add_node("give_up", give_up_node)

    graph.set_entry_point("aggressor")
    graph.add_conditional_edges(
        "aggressor", route_after_aggressor, {"detective": "detective", "give_up": "give_up"}
    )
    graph.add_conditional_edges(
        "detective",
        route_after_detective,
        {"surgeon": "surgeon", "aggressor": "aggressor", "give_up": "give_up"},
    )
    graph.add_edge("surgeon", END)
    graph.add_edge("give_up", END)

    return graph.compile()


def run_cycle(
    sandbox: Sandbox,
    app_root: Path,
    test_target: str,
    regression_dir: Path,
    settings: Settings,
    exclude_files: frozenset[str] | None = None,
    telemetry_config=None,
) -> SwarmState:
    initial_state: SwarmState = {
        "run_id": sandbox.run_id,
        "sandbox": sandbox,
        "rng": random.Random(sandbox.run_id),
        "app_root": app_root,
        "test_target": test_target,
        "regression_dir": regression_dir,
        "exclude_files": exclude_files,
        "telemetry_config": telemetry_config,
        "token_usage": TokenUsage(),
        "max_aggressor_retries": settings.max_aggressor_retries,
        "max_surgeon_retries": settings.max_surgeon_retries,
        "max_patch_change_ratio": settings.max_patch_change_ratio,
        "tried_mutations": frozenset(),
        "aggressor_attempts": 0,
        "mutation": None,
        "mutation_commit": None,
        "detective_result": None,
        "surgeon_attempt": None,
        "status": "running",
        "log": [],
    }
    app = build_graph()
    return app.invoke(initial_state)
