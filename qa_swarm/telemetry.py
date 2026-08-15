from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from qa_swarm.agents.detective import TestReport, module_import_path, run_pytest


@dataclass
class TelemetryConfig:
    requests: list[dict]
    app_import_path: str


def discover_telemetry_config(
    worktree_root: Path,
    target_rel: Path,
    app_dir: str,
    app_module: str = "main",
) -> TelemetryConfig | None:
    requests_path = worktree_root / target_rel / "telemetry_requests.json"
    if not requests_path.exists():
        return None

    requests = json.loads(requests_path.read_text(encoding="utf-8"))
    app_file = worktree_root / target_rel / app_dir / f"{app_module}.py"
    if not app_file.exists():
        return None

    return TelemetryConfig(
        requests=requests,
        app_import_path=module_import_path(worktree_root, app_file),
    )


def generate_telemetry_test(app_import_path: str, requests: list[dict]) -> str:
    lines = [
        "from fastapi.testclient import TestClient",
        f"from {app_import_path} import app",
        "",
        "client = TestClient(app)",
        "",
    ]
    for i, req in enumerate(requests):
        method = req["method"].lower()
        path = req["path"]
        json_body = req.get("json")
        expect_status = req["expect_status"]

        lines.append(f"def test_telemetry_scenario_{i}():")
        if json_body is not None:
            lines.append(f"    response = client.{method}({path!r}, json={json_body!r})")
        else:
            lines.append(f"    response = client.{method}({path!r})")
        lines.append(f"    assert response.status_code == {expect_status!r}, response.text")
        lines.append("")
    return "\n".join(lines)


def run_telemetry_check(
    worktree_root: Path,
    regression_dir: Path,
    telemetry_config: TelemetryConfig,
) -> TestReport:
    test_code = generate_telemetry_test(telemetry_config.app_import_path, telemetry_config.requests)
    regression_dir.mkdir(parents=True, exist_ok=True)
    test_path = regression_dir / "test_qa_swarm_telemetry_check.py"
    test_path.write_text(test_code, encoding="utf-8")

    try:
        return run_pytest(worktree_root, str(test_path.relative_to(worktree_root)))
    finally:
        test_path.unlink(missing_ok=True)
