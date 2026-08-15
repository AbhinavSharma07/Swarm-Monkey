import ast
import random
import textwrap
from pathlib import Path

import libcst as cst

from qa_swarm.agents import aggressor


SAMPLE_MODULE = textwrap.dedent(
    """
    def classify(quantity):
        if quantity >= 10:
            return "bulk"
        return "single"


    def is_eligible(is_member, quantity):
        return is_member and quantity > 0
    """
).strip() + "\n"

FORMAT_SAMPLE = textwrap.dedent(
    """
    def classify(quantity):
        threshold = 10
        if quantity >= threshold:
            return 'bulk'
        return 'single'
    """
).strip() + "\n"


def _write_module(tmp_path: Path, name: str = "target.py") -> Path:
    path = tmp_path / name
    path.write_text(SAMPLE_MODULE, encoding="utf-8")
    return path


def test_apply_random_mutation_produces_valid_python(tmp_path):
    module_path = _write_module(tmp_path)
    mutation = aggressor.apply_random_mutation(module_path, random.Random(1))

    assert mutation is not None
    ast.parse(mutation.mutated_source)
    assert mutation.mutated_source != mutation.original_source
    assert module_path.read_text(encoding="utf-8") == mutation.mutated_source


def test_mutation_preserves_surrounding_formatting(tmp_path):
    module_path = tmp_path / "target.py"
    module_path.write_text(FORMAT_SAMPLE, encoding="utf-8")

    mutation = aggressor.apply_random_mutation(module_path, random.Random(5))

    assert mutation is not None
    original_lines = mutation.original_source.splitlines()
    mutated_lines = mutation.mutated_source.splitlines()
    assert len(original_lines) == len(mutated_lines)
    changed = [i for i, (a, b) in enumerate(zip(original_lines, mutated_lines)) if a != b]
    assert len(changed) == 1
    assert "'bulk'" in mutation.mutated_source
    assert "'single'" in mutation.mutated_source


def test_boundary_shift_description_matches_actual_mutation(tmp_path):
    module_path = tmp_path / "target.py"
    module_path.write_text("VALUE = 10\n", encoding="utf-8")

    mutation = aggressor.apply_random_mutation(module_path, random.Random(9))

    assert mutation is not None
    assert mutation.operator == "boundary_shift"
    after_text = mutation.description.split("-> `")[1].rstrip("`")
    assert after_text in mutation.mutated_source


def test_apply_random_mutation_respects_exclude_set(tmp_path):
    module_path = _write_module(tmp_path)
    original = module_path.read_text(encoding="utf-8")

    first = aggressor.apply_random_mutation(module_path, random.Random(2))
    module_path.write_text(original, encoding="utf-8")

    exclude = frozenset({aggressor.mutation_key(first)})
    second = aggressor.apply_random_mutation(module_path, random.Random(2), exclude=exclude)

    assert second is not None
    assert aggressor.mutation_key(second) != aggressor.mutation_key(first)


def test_discoverable_files_excludes_wiring_and_tests(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (app_dir / "main.py").write_text("x = 1\n", encoding="utf-8")
    (app_dir / "logic.py").write_text(SAMPLE_MODULE, encoding="utf-8")
    tests_dir = app_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_logic.py").write_text("def test_x(): assert True\n", encoding="utf-8")

    files = aggressor.discoverable_files(app_dir)

    assert files == [app_dir / "logic.py"]


def test_relational_operator_replacement_flips_boundary():
    module = cst.parse_module("quantity >= 10\n")
    compare = module.body[0].body[0].value
    op = aggressor.RelationalOperatorReplacement()

    assert op.is_candidate(compare)
    mutated = op.apply(compare)

    assert isinstance(mutated.comparisons[0].operator, cst.GreaterThan)


def test_boolean_operator_swap():
    module = cst.parse_module("a and b\n")
    bool_op = module.body[0].body[0].value
    op = aggressor.BooleanOperatorSwap()

    assert op.is_candidate(bool_op)
    mutated = op.apply(bool_op)

    assert isinstance(mutated.operator, cst.Or)


def test_arithmetic_operator_replacement_binop():
    module = cst.parse_module("a * b\n")
    binop = module.body[0].body[0].value
    op = aggressor.ArithmeticOperatorReplacement()

    assert op.is_candidate(binop)
    mutated = op.apply(binop)

    assert isinstance(mutated.operator, cst.Divide)


def test_arithmetic_operator_replacement_augassign():
    module = cst.parse_module("rate += 1\n")
    augassign = module.body[0].body[0]
    op = aggressor.ArithmeticOperatorReplacement()

    assert op.is_candidate(augassign)
    mutated = op.apply(augassign)

    assert isinstance(mutated.operator, cst.SubtractAssign)


def test_unary_operator_removal_drops_not():
    module = cst.parse_module("not is_member\n")
    unary = module.body[0].body[0].value
    op = aggressor.UnaryOperatorRemoval()

    assert op.is_candidate(unary)
    mutated = op.apply(unary)

    assert isinstance(mutated, cst.Name)
    assert mutated.value == "is_member"


def test_unary_operator_removal_drops_minus():
    module = cst.parse_module("-value\n")
    unary = module.body[0].body[0].value
    op = aggressor.UnaryOperatorRemoval()

    assert op.is_candidate(unary)
    mutated = op.apply(unary)

    assert isinstance(mutated, cst.Name)
    assert mutated.value == "value"


def test_unary_operator_removal_ignores_plus():
    module = cst.parse_module("+value\n")
    unary = module.body[0].body[0].value
    op = aggressor.UnaryOperatorRemoval()

    assert not op.is_candidate(unary)


def test_mutate_returns_none_when_no_candidates(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "main.py").write_text("x = 1\n", encoding="utf-8")

    mutation = aggressor.mutate(app_dir, random.Random(3))

    assert mutation is None
