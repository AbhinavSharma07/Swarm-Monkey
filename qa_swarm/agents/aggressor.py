from __future__ import annotations

import ast
import random
from dataclasses import dataclass
from pathlib import Path

EXCLUDE_DIRS = {"tests", "__pycache__"}
EXCLUDE_FILES = {"__init__.py", "main.py"}


@dataclass
class Mutation:
    operator: str
    file: Path
    function: str
    lineno: int
    description: str
    original_source: str
    mutated_source: str


def mutation_key(mutation: "Mutation") -> tuple[str, int, str]:
    return (str(mutation.file), mutation.lineno, mutation.operator)


class RelationalOperatorReplacement:
    name = "relational_operator_replacement"

    _SWAPS = {
        ast.Gt: ast.GtE,
        ast.GtE: ast.Gt,
        ast.Lt: ast.LtE,
        ast.LtE: ast.Lt,
        ast.Eq: ast.NotEq,
        ast.NotEq: ast.Eq,
    }

    def is_candidate(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and type(node.ops[0]) in self._SWAPS
        )

    def apply(self, node: ast.Compare) -> None:
        node.ops[0] = self._SWAPS[type(node.ops[0])]()


class BoundaryShift:
    name = "boundary_shift"

    def is_candidate(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        )

    def apply(self, node: ast.Constant) -> None:
        delta = 1 if isinstance(node.value, int) else (0.01 if abs(node.value) < 1 else 1.0)
        node.value = node.value + random.choice([delta, -delta])


class BooleanOperatorSwap:
    name = "boolean_operator_swap"

    def is_candidate(self, node: ast.AST) -> bool:
        return isinstance(node, ast.BoolOp)

    def apply(self, node: ast.BoolOp) -> None:
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()


class ConditionNegation:
    name = "condition_negation"

    def is_candidate(self, node: ast.AST) -> bool:
        return isinstance(node, ast.If)

    def apply(self, node: ast.If) -> None:
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)


OPERATORS = [
    RelationalOperatorReplacement(),
    BoundaryShift(),
    BooleanOperatorSwap(),
    ConditionNegation(),
]


def _walk_with_function_context(node: ast.AST, function_name: str = "<module>"):
    yield node, function_name
    next_name = node.name if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else function_name
    for child in ast.iter_child_nodes(node):
        yield from _walk_with_function_context(child, next_name)


def discoverable_files(app_root: Path) -> list[Path]:
    return [
        p
        for p in sorted(app_root.rglob("*.py"))
        if p.name not in EXCLUDE_FILES and not any(part in EXCLUDE_DIRS for part in p.parts)
    ]


def apply_random_mutation(
    source_path: Path,
    rng: random.Random,
    exclude: frozenset[tuple[str, int, str]] = frozenset(),
) -> Mutation | None:
    original_source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(original_source)

    candidates: list[tuple[object, ast.AST, str]] = []
    for node, function_name in _walk_with_function_context(tree):
        for operator in OPERATORS:
            if operator.is_candidate(node):
                key = (str(source_path), getattr(node, "lineno", -1), operator.name)
                if key not in exclude:
                    candidates.append((operator, node, function_name))

    if not candidates:
        return None

    operator, node, function_name = rng.choice(candidates)
    before_text = ast.get_source_segment(original_source, node) or ast.unparse(node)
    operator.apply(node)
    after_text = ast.unparse(node)

    ast.fix_missing_locations(tree)
    mutated_source = ast.unparse(tree)
    source_path.write_text(mutated_source, encoding="utf-8")

    return Mutation(
        operator=operator.name,
        file=source_path,
        function=function_name,
        lineno=getattr(node, "lineno", 0),
        description=f"{operator.name} in {function_name}(): `{before_text}` -> `{after_text}`",
        original_source=original_source,
        mutated_source=mutated_source,
    )


def mutate(
    app_root: Path,
    rng: random.Random,
    exclude: frozenset[tuple[str, int, str]] = frozenset(),
) -> Mutation | None:
    files = discoverable_files(app_root)
    rng.shuffle(files)
    for file in files:
        mutation = apply_random_mutation(file, rng, exclude=exclude)
        if mutation is not None:
            return mutation
    return None
