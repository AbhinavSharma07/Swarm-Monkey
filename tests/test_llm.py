import pytest
from langchain_core.messages import HumanMessage

from qa_swarm.llm import invoke_with_retry


class _Response:
    def __init__(self, content):
        self.content = content


class _FlakyLLM:
    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("transient failure")
        return _Response("ok")


def test_invoke_with_retry_succeeds_after_transient_failures():
    llm = _FlakyLLM(fail_times=2)
    sleeps = []

    result = invoke_with_retry(
        llm, [HumanMessage(content="hi")], max_attempts=3, base_delay=1.0, sleep=sleeps.append
    )

    assert result.content == "ok"
    assert llm.calls == 3
    assert sleeps == [1.0, 2.0]


def test_invoke_with_retry_raises_after_exhausting_attempts():
    llm = _FlakyLLM(fail_times=10)
    sleeps = []

    with pytest.raises(RuntimeError, match="transient failure"):
        invoke_with_retry(
            llm, [HumanMessage(content="hi")], max_attempts=3, base_delay=1.0, sleep=sleeps.append
        )

    assert llm.calls == 3
    assert sleeps == [1.0, 2.0]


def test_invoke_with_retry_succeeds_first_try_never_sleeps():
    llm = _FlakyLLM(fail_times=0)
    sleeps = []

    result = invoke_with_retry(llm, [HumanMessage(content="hi")], sleep=sleeps.append)

    assert result.content == "ok"
    assert llm.calls == 1
    assert sleeps == []
