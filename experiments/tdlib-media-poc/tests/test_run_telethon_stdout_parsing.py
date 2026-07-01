from benchmark.run_telethon import extract_json_envelope


def test_extract_json_envelope_strips_leading_progress_lines():
    stdout = (
        "PROGRESS 0/46MB 0.3%\n"
        "PROGRESS 46/46MB 100.0%\n"
        '{\n  "ok": true,\n  "payload": {"path": "/tmp/x.mp4", "size_bytes": 123}\n}\n'
    )
    envelope = extract_json_envelope(stdout)
    assert envelope == {"ok": True, "payload": {"path": "/tmp/x.mp4", "size_bytes": 123}}


def test_extract_json_envelope_handles_pure_json_with_no_progress_lines():
    stdout = '{"ok": false, "error": "boom"}'
    envelope = extract_json_envelope(stdout)
    assert envelope == {"ok": False, "error": "boom"}


def test_extract_json_envelope_raises_on_no_json_present():
    import json
    import pytest

    with pytest.raises(json.JSONDecodeError):
        extract_json_envelope("PROGRESS 0/1MB 0.0%\nsome error text, no braces")
