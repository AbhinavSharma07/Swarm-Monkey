from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from qa_swarm.config import settings


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
