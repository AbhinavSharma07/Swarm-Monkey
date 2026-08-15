from qa_swarm import report


def _record(run_id, status, operator=None):
    return report.CycleRecord(
        run_id=run_id,
        status=status,
        operator=operator,
        function="calc" if operator else None,
        file="calc.py" if operator else None,
        description="desc" if operator else None,
    )


def test_append_and_load_history_roundtrip(tmp_path):
    history_path = tmp_path / "history.jsonl"
    r1 = _record("run1", "healed", "boundary_shift")
    r2 = _record("run2", "unresolved", "condition_negation")

    report.append_record(history_path, r1)
    report.append_record(history_path, r2)

    loaded = report.load_history(history_path)

    assert loaded == [r1, r2]


def test_load_history_missing_file_returns_empty(tmp_path):
    assert report.load_history(tmp_path / "nope.jsonl") == []


def test_summarize_computes_mutation_score_and_breakdown():
    records = [
        _record("a", "healed", "boundary_shift"),
        _record("b", "healed", "boundary_shift"),
        _record("c", "unresolved", "boundary_shift"),
        _record("d", "healed", "condition_negation"),
        _record("e", "unresolved", None),
    ]

    summary = report.summarize(records)

    assert summary["total_cycles"] == 5
    assert summary["healed"] == 3
    assert summary["unresolved"] == 2
    assert summary["mutation_score"] == 3 / 5
    assert summary["by_operator"] == {
        "boundary_shift": {"healed": 2, "unresolved": 1},
        "condition_negation": {"healed": 1, "unresolved": 0},
    }


def test_summarize_empty_history_is_zero_not_division_error():
    summary = report.summarize([])
    assert summary["total_cycles"] == 0
    assert summary["mutation_score"] == 0.0


def test_format_summary_contains_key_numbers():
    summary = report.summarize([_record("a", "healed", "boundary_shift")])
    text = report.format_summary(summary)

    assert "Total cycles: 1" in text
    assert "Mutation score: 100%" in text
    assert "boundary_shift" in text
