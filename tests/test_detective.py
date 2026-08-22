import subprocess
from pathlib import Path

from qa_swarm.agents import detective


def test_run_pytest_passes_on_a_healthy_suite(tmp_path):
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    report = detective.run_pytest(tmp_path, "test_ok.py")

    assert report.passed is True


def test_run_pytest_fails_on_a_failing_suite(tmp_path):
    (tmp_path / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")

    report = detective.run_pytest(tmp_path, "test_bad.py")

    assert report.passed is False


def test_run_pytest_handles_timeout_gracefully(tmp_path, monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=kwargs.get("timeout"))

    monkeypatch.setattr(detective.subprocess, "run", fake_run)

    report = detective.run_pytest(tmp_path, "test_whatever.py", timeout=5)

    assert report.passed is False
    assert "timed out after 5s" in report.output


def test_run_pytest_passes_configured_timeout_to_subprocess(tmp_path, monkeypatch):
    captured = {}

    def fake_run(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(detective.subprocess, "run", fake_run)

    detective.run_pytest(tmp_path, "test_whatever.py", timeout=42)

    assert captured["timeout"] == 42
