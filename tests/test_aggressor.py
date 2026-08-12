import ast
import random
import textwrap
from pathlib import Path

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
    tree = ast.parse("quantity >= 10")
    compare = tree.body[0].value
    op = aggressor.RelationalOperatorReplacement()

    assert op.is_candidate(compare)
    op.apply(compare)

    assert isinstance(compare.ops[0], ast.Gt)


def test_boolean_operator_swap():
    tree = ast.parse("a and b")
    bool_op = tree.body[0].value
    op = aggressor.BooleanOperatorSwap()

    assert op.is_candidate(bool_op)
    op.apply(bool_op)

    assert isinstance(bool_op.op, ast.Or)


def test_mutate_returns_none_when_no_candidates(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "main.py").write_text("x = 1\n", encoding="utf-8")

    mutation = aggressor.mutate(app_dir, random.Random(3))

    assert mutation is None
