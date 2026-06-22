from telegram_control_plane.regression_loop import (
    DEFAULT_STEPS,
    RegressionStep,
    _json_gate_status,
    run_regression_loop,
)


def test_regression_loop_skips_live_steps(monkeypatch):
    seen = []

    def fake_run_step(step, *, timeout):
        seen.append(step.id)
        return {"id": step.id, "status": "ok", "elapsed_seconds": 0.01}

    monkeypatch.setattr("telegram_control_plane.regression_loop._run_step", fake_run_step)

    report = run_regression_loop(include_live=False, timeout=1)

    assert report["status"] == "ok"
    assert seen == [step.id for step in DEFAULT_STEPS if not step.live]
    assert any(item["status"] == "skipped" for item in report["steps"])


def test_regression_loop_stops_on_first_failure(monkeypatch):
    def fake_run_step(step, *, timeout):
        status = "fail" if step.id == "runtime-tests" else "ok"
        return {"id": step.id, "status": status, "elapsed_seconds": 0.01}

    monkeypatch.setattr("telegram_control_plane.regression_loop._run_step", fake_run_step)

    report = run_regression_loop(include_live=True, timeout=1)

    assert report["status"] == "fail"
    assert [item["id"] for item in report["steps"]] == ["control-plane-tests", "runtime-tests"]


def test_json_gate_fails_on_warn_doctor_payload():
    step = RegressionStep(
        "maintenance-doctor",
        "/tmp",
        ("telegram-maintenance-doctor", "--json"),
        live=True,
    )

    status, reason = _json_gate_status(step, '{"status":"warn"}', "ok")

    assert status == "fail"
    assert reason == "json_status=warn"


def test_json_gate_fails_on_stale_feature_status():
    step = RegressionStep("feature-status-dry-run", "/tmp", ("telegram-feature-status", "--json"), live=True)

    status, reason = _json_gate_status(step, '{"status":"ok","changed_count":2}', "ok")

    assert status == "fail"
    assert reason == "changed_count=2"
