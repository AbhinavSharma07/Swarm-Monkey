from __future__ import annotations

import time
from typing import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from qa_swarm.config import settings


def invoke_with_retry(
    llm: BaseChatModel,
    messages: list[BaseMessage],
    max_attempts: int = 3,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
):
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return llm.invoke(messages)
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                sleep(base_delay * (2**attempt))
    raise last_exc


def get_llm(temperature: float = 0.0) -> BaseChatModel:
    provider = settings.llm_provider.lower()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=settings.llm_model, temperature=temperature)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=settings.llm_model, temperature=temperature)

    raise ValueError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'; expected 'anthropic' or 'openai'"
    )
