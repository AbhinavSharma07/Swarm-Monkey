from __future__ import annotations

import random
from pathlib import Path
from typing import TypedDict

from qa_swarm.agents.aggressor import Mutation
from qa_swarm.agents.detective import DetectiveResult
from qa_swarm.agents.surgeon import PatchAttempt
from qa_swarm.sandbox import Sandbox
from qa_swarm.telemetry import TelemetryConfig


class SwarmState(TypedDict, total=False):
    run_id: str
    sandbox: Sandbox
    rng: random.Random
    app_root: Path
    test_target: str
    regression_dir: Path
    exclude_files: frozenset[str] | None
    telemetry_config: TelemetryConfig | None
    max_aggressor_retries: int
    max_surgeon_retries: int
    max_patch_change_ratio: float

    tried_mutations: frozenset
    aggressor_attempts: int
    mutation: Mutation | None
    mutation_commit: str | None
    detective_result: DetectiveResult | None
    surgeon_attempt: PatchAttempt | None

    status: str
    log: list[str]
