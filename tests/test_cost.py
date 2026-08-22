from qa_swarm.cost import TokenUsage


class _Response:
    def __init__(self, usage_metadata=None):
        self.usage_metadata = usage_metadata


def test_add_from_response_accumulates_tokens():
    usage = TokenUsage()

    usage.add_from_response(_Response({"input_tokens": 100, "output_tokens": 40}))
    usage.add_from_response(_Response({"input_tokens": 50, "output_tokens": 10}))

    assert usage.input_tokens == 150
    assert usage.output_tokens == 50
    assert usage.total_tokens == 200


def test_add_from_response_ignores_missing_usage_metadata():
    usage = TokenUsage()

    usage.add_from_response(_Response(None))
    usage.add_from_response(object())

    assert usage.total_tokens == 0


def test_add_merges_two_usage_objects():
    a = TokenUsage(input_tokens=10, output_tokens=5)
    b = TokenUsage(input_tokens=3, output_tokens=2)

    a.add(b)

    assert a.input_tokens == 13
    assert a.output_tokens == 7
