from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CycleRecord:
    run_id: str
    status: str
    operator: str | None
    function: str | None
    file: str | None
    description: str | None


def append_record(history_path: Path, record: CycleRecord) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record)) + "\n")


def load_history(history_path: Path) -> list[CycleRecord]:
    if not history_path.exists():
        return []
    records = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(CycleRecord(**json.loads(line)))
    return records


def summarize(records: list[CycleRecord]) -> dict:
    total = len(records)
    healed = sum(1 for r in records if r.status == "healed")
    unresolved = total - healed

    by_operator: dict[str, dict[str, int]] = {}
    for r in records:
        if r.operator is None:
            continue
        stats = by_operator.setdefault(r.operator, {"healed": 0, "unresolved": 0})
        stats["healed" if r.status == "healed" else "unresolved"] += 1

    return {
        "total_cycles": total,
        "healed": healed,
        "unresolved": unresolved,
        "mutation_score": (healed / total) if total else 0.0,
        "by_operator": by_operator,
    }


def format_summary(summary: dict) -> str:
    lines = [
        f"Total cycles: {summary['total_cycles']}",
        f"Healed: {summary['healed']}  Unresolved: {summary['unresolved']}",
        f"Mutation score: {summary['mutation_score']:.0%}",
    ]
    if summary["by_operator"]:
        lines.append("By operator:")
        for operator, stats in sorted(summary["by_operator"].items()):
            lines.append(f"  {operator}: healed={stats['healed']} unresolved={stats['unresolved']}")
    return "\n".join(lines)
