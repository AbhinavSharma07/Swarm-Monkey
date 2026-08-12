from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic")
    llm_model: str = os.getenv("LLM_MODEL", "claude-sonnet-5")
    max_surgeon_retries: int = int(os.getenv("MAX_SURGEON_RETRIES", "3"))
    max_aggressor_retries: int = int(os.getenv("MAX_AGGRESSOR_RETRIES", "5"))
    runs_dir: str = os.getenv("QA_SWARM_RUNS_DIR", "runs")


settings = Settings()
