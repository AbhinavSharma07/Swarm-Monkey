import subprocess
import textwrap
from pathlib import Path

from qa_swarm.telemetry import (
    TelemetryConfig,
    discover_telemetry_config,
    generate_telemetry_test,
    run_telemetry_check,
)

GOOD_CALC = textwrap.dedent(
    """
    def calc(n):
        if n < 0:
            raise ValueError("n must be non-negative")
        return n * 2
    """
).strip() + "\n"

BROKEN_CALC = textwrap.dedent(
    """
    def calc(n):
        return n * 2
    """
).strip() + "\n"

MAIN_SOURCE = textwrap.dedent(
    """
    from fastapi import FastAPI, HTTPException
    from demo_app.calc import calc

    app = FastAPI()


    @app.get("/calc/{n}")
    def get_calc(n: int):
        try:
            return {"result": calc(n)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    """
).strip() + "\n"

NARROW_TEST_SOURCE = textwrap.dedent(
    """
    from demo_app.calc import calc


    def test_positive():
        assert calc(5) == 10
    """
).strip() + "\n"

REQUESTS = [
    {"method": "GET", "path": "/calc/5", "expect_status": 200},
    {"method": "GET", "path": "/calc/-1", "expect_status": 400},
]


def _build_demo_app(tmp_path: Path, calc_source: str) -> Path:
    app_dir = tmp_path / "demo_app"
    app_dir.mkdir()
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (app_dir / "calc.py").write_text(calc_source, encoding="utf-8")
    (app_dir / "main.py").write_text(MAIN_SOURCE, encoding="utf-8")
    tests_dir = app_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (tests_dir / "test_calc.py").write_text(NARROW_TEST_SOURCE, encoding="utf-8")
    return tmp_path


def test_generate_telemetry_test_produces_valid_assertions():
    code = generate_telemetry_test("demo_app.main", REQUESTS)

    assert "from demo_app.main import app" in code
    assert "client.get('/calc/5')" in code
    assert "== 200" in code
    assert "== 400" in code


def test_discover_telemetry_config_finds_file_and_computes_import_path(tmp_path):
    worktree_root = _build_demo_app(tmp_path, GOOD_CALC)
    (worktree_root / "demo_app" / "telemetry_requests.json").write_text(
        '[{"method": "GET", "path": "/calc/5", "expect_status": 200}]', encoding="utf-8"
    )

    config = discover_telemetry_config(worktree_root, Path("demo_app"), app_dir=".", app_module="main")

    assert config is not None
    assert config.app_import_path == "demo_app.main"
    assert config.requests == [{"method": "GET", "path": "/calc/5", "expect_status": 200}]


def test_discover_telemetry_config_returns_none_when_file_absent(tmp_path):
    worktree_root = _build_demo_app(tmp_path, GOOD_CALC)

    config = discover_telemetry_config(worktree_root, Path("demo_app"), app_dir=".", app_module="main")

    assert config is None


def test_run_telemetry_check_passes_on_correct_app(tmp_path):
    worktree_root = _build_demo_app(tmp_path, GOOD_CALC)
    config = TelemetryConfig(requests=REQUESTS, app_import_path="demo_app.main")

    report = run_telemetry_check(worktree_root, worktree_root / "demo_app", config)

    assert report.passed is True


def test_run_telemetry_check_catches_regression_the_apps_own_narrow_suite_misses(tmp_path):
    worktree_root = _build_demo_app(tmp_path, BROKEN_CALC)
    config = TelemetryConfig(requests=REQUESTS, app_import_path="demo_app.main")

    narrow_result = subprocess.run(
        ["python", "-m", "pytest", "demo_app/tests", "-q"],
        cwd=worktree_root,
        capture_output=True,
        text=True,
    )
    assert narrow_result.returncode == 0

    report = run_telemetry_check(worktree_root, worktree_root / "demo_app", config)

    assert report.passed is False
