from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

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
        cst.GreaterThan: cst.GreaterThanEqual,
        cst.GreaterThanEqual: cst.GreaterThan,
        cst.LessThan: cst.LessThanEqual,
        cst.LessThanEqual: cst.LessThan,
        cst.Equal: cst.NotEqual,
        cst.NotEqual: cst.Equal,
    }

    def is_candidate(self, node: cst.CSTNode) -> bool:
        return (
            isinstance(node, cst.Comparison)
            and len(node.comparisons) == 1
            and type(node.comparisons[0].operator) in self._SWAPS
        )

    def apply(self, node: cst.Comparison) -> cst.Comparison:
        target = node.comparisons[0]
        new_operator = self._SWAPS[type(target.operator)]()
        return node.with_changes(comparisons=[target.with_changes(operator=new_operator)])


class BoundaryShift:
    name = "boundary_shift"

    def is_candidate(self, node: cst.CSTNode) -> bool:
        return isinstance(node, (cst.Integer, cst.Float))

    def apply(self, node: cst.BaseNumber) -> cst.BaseNumber:
        if isinstance(node, cst.Integer):
            current = int(node.value)
            new_value = current + random.choice([1, -1])
            return node.with_changes(value=str(new_value))

        current = float(node.value)
        delta = 0.01 if abs(current) < 1 else 1.0
        new_value = current + random.choice([delta, -delta])
        return node.with_changes(value=repr(new_value))


class BooleanOperatorSwap:
    name = "boolean_operator_swap"

    def is_candidate(self, node: cst.CSTNode) -> bool:
        return isinstance(node, cst.BooleanOperation)

    def apply(self, node: cst.BooleanOperation) -> cst.BooleanOperation:
        new_operator = cst.Or() if isinstance(node.operator, cst.And) else cst.And()
        return node.with_changes(operator=new_operator)


class ConditionNegation:
    name = "condition_negation"

    def is_candidate(self, node: cst.CSTNode) -> bool:
        return isinstance(node, cst.If)

    def apply(self, node: cst.If) -> cst.If:
        return node.with_changes(test=cst.UnaryOperation(operator=cst.Not(), expression=node.test))


class ArithmeticOperatorReplacement:
    name = "arithmetic_operator_replacement"

    _BINOP_SWAPS = {
        cst.Add: cst.Subtract,
        cst.Subtract: cst.Add,
        cst.Multiply: cst.Divide,
        cst.Divide: cst.Multiply,
    }
    _AUGASSIGN_SWAPS = {
        cst.AddAssign: cst.SubtractAssign,
        cst.SubtractAssign: cst.AddAssign,
        cst.MultiplyAssign: cst.DivideAssign,
        cst.DivideAssign: cst.MultiplyAssign,
    }

    def is_candidate(self, node: cst.CSTNode) -> bool:
        if isinstance(node, cst.BinaryOperation):
            return type(node.operator) in self._BINOP_SWAPS
        if isinstance(node, cst.AugAssign):
            return type(node.operator) in self._AUGASSIGN_SWAPS
        return False

    def apply(self, node: cst.CSTNode) -> cst.CSTNode:
        if isinstance(node, cst.BinaryOperation):
            new_operator = self._BINOP_SWAPS[type(node.operator)]()
        else:
            new_operator = self._AUGASSIGN_SWAPS[type(node.operator)]()
        return node.with_changes(operator=new_operator)


OPERATORS = [
    RelationalOperatorReplacement(),
    BoundaryShift(),
    BooleanOperatorSwap(),
    ConditionNegation(),
    ArithmeticOperatorReplacement(),
]


class _CandidateCollector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, source_path: Path, exclude: frozenset[tuple[str, int, str]]):
        super().__init__()
        self.source_path = source_path
        self.exclude = exclude
        self.function_stack = ["<module>"]
        self.candidates: list[tuple[object, cst.CSTNode, str, tuple[str, int, str]]] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        self.function_stack.append(node.name.value)

    def leave_FunctionDef(self, original_node: cst.FunctionDef) -> None:
        self.function_stack.pop()

    def on_visit(self, node: cst.CSTNode) -> bool:
        function_name = self.function_stack[-1]
        for operator in OPERATORS:
            if operator.is_candidate(node):
                position = self.get_metadata(PositionProvider, node)
                key = (str(self.source_path), position.start.line, operator.name)
                if key not in self.exclude:
                    self.candidates.append((operator, node, function_name, key))
        return super().on_visit(node)


class _SingleNodeMutator(cst.CSTTransformer):
    def __init__(self, target_node: cst.CSTNode, replacement_node: cst.CSTNode):
        super().__init__()
        self.target_node = target_node
        self.replacement_node = replacement_node

    def on_leave(self, original_node: cst.CSTNode, updated_node: cst.CSTNode) -> cst.CSTNode:
        updated_node = super().on_leave(original_node, updated_node)
        if original_node is self.target_node:
            return self.replacement_node
        return updated_node


def discoverable_files(app_root: Path, exclude_files: frozenset[str] | None = None) -> list[Path]:
    exclude_files = EXCLUDE_FILES if exclude_files is None else exclude_files
    return [
        p
        for p in sorted(app_root.rglob("*.py"))
        if p.name not in exclude_files and not any(part in EXCLUDE_DIRS for part in p.parts)
    ]


def apply_random_mutation(
    source_path: Path,
    rng: random.Random,
    exclude: frozenset[tuple[str, int, str]] = frozenset(),
) -> Mutation | None:
    original_source = source_path.read_text(encoding="utf-8")
    module = cst.parse_module(original_source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)

    collector = _CandidateCollector(source_path, exclude)
    wrapper.visit(collector)

    if not collector.candidates:
        return None

    operator, node, function_name, key = rng.choice(collector.candidates)
    before_text = module.code_for_node(node).strip()
    replacement_node = operator.apply(node)
    after_text = module.code_for_node(replacement_node).strip()

    new_module = module.visit(_SingleNodeMutator(node, replacement_node))
    mutated_source = new_module.code
    source_path.write_text(mutated_source, encoding="utf-8")

    return Mutation(
        operator=operator.name,
        file=source_path,
        function=function_name,
        lineno=key[1],
        description=f"{operator.name} in {function_name}(): `{before_text}` -> `{after_text}`",
        original_source=original_source,
        mutated_source=mutated_source,
    )


def mutate(
    app_root: Path,
    rng: random.Random,
    exclude: frozenset[tuple[str, int, str]] = frozenset(),
    exclude_files: frozenset[str] | None = None,
) -> Mutation | None:
    files = discoverable_files(app_root, exclude_files=exclude_files)
    rng.shuffle(files)
    for file in files:
        mutation = apply_random_mutation(file, rng, exclude=exclude)
        if mutation is not None:
            return mutation
    return None
