import os
import subprocess
import sys

import pytest


def test_help_does_not_open_camera():
    result = subprocess.run(
        [sys.executable, "-m", "look_to_ask", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 0
    assert "--probe-camera" in result.stdout


def test_speech_check_failure_does_not_echo_private_model_path(monkeypatch, tmp_path, capsys):
    from look_to_ask import __main__ as cli

    private = "C:/PRIVATE-MODEL-DIRECTORY/never-log-this"
    monkeypatch.setattr(
        "look_to_ask.speech.load_model",
        lambda _name, **_kwargs: (_ for _ in ()).throw(ValueError(private)),
    )
    report = tmp_path / "report.json"
    assert cli.main(["--check-speech", "--speech-model", private, "--report", str(report)]) == 1
    captured = capsys.readouterr()
    assert "PRIVATE-MODEL" not in captured.err + captured.out + report.read_text("utf-8")
    assert "ValueError" in captured.err


def test_speech_check_reports_actual_backend_without_model_path(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace

    from look_to_ask import __main__ as cli

    selected = []

    def load(name, *, device="auto"):
        selected.append(device)
        return SimpleNamespace(device="cuda", compute_type="float16", fallback_reason="")

    monkeypatch.setattr("look_to_ask.speech.load_model", load)
    monkeypatch.setattr("faster_whisper.vad.get_vad_model", lambda: None)
    report = tmp_path / "backend.json"
    assert cli.main(["--check-speech", "--speech-device", "cuda", "--report", str(report)]) == 0
    result = json.loads(report.read_text("utf-8"))
    assert selected == ["cuda"] and result["speech_device"] == "cuda"
    assert result["speech_compute"] == "float16" and result["speech_fallback"] == ""


def test_fixture_report_tracks_inference_fallback_without_logging_transcript(monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace

    from look_to_ask import __main__ as cli

    model = SimpleNamespace(
        device="cuda", compute_type="float16", fallback_reason="", close=lambda: None
    )
    monkeypatch.setattr("look_to_ask.speech.load_model", lambda *args, **kwargs: model)
    monkeypatch.setattr("faster_whisper.vad.get_vad_model", lambda: None)
    monkeypatch.setattr("faster_whisper.audio.decode_audio", lambda stream: object())

    def decode(*args):
        model.device, model.compute_type, model.fallback_reason = (
            "cpu",
            "int8",
            "gpu_inference_failed",
        )
        return "PRIVATE-TRANSCRIPT-TEST-FIXTURE"

    monkeypatch.setattr("look_to_ask.speech.transcribe_audio", decode)
    fixture = tmp_path / "fixture.wav"
    fixture.write_bytes(b"TEST FILE FOR MOCK DECODER")
    report = tmp_path / "report.json"
    assert (
        cli.main(["--check-speech", "--speech-fixture", str(fixture), "--report", str(report)]) == 0
    )
    data = json.loads(report.read_text())
    assert (data["speech_device"], data["speech_compute"], data["speech_fallback"]) == (
        "cpu",
        "int8",
        "gpu_inference_failed",
    )
    assert len(data["inference_turns"]) == 3
    assert "PRIVATE-TRANSCRIPT" not in report.read_text()


def test_ui_smoke_exits_without_starting_camera_or_gaze_engine():
    result = subprocess.run(
        [sys.executable, "-m", "look_to_ask", "--smoke-ui"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONUTF8": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert "UI_SMOKE_OK" in result.stdout


@pytest.mark.parametrize("resolution", [(1280, 720), (1920, 1080)])
def test_hd_camera_option_reaches_explicit_probe_without_starting_ui(monkeypatch, resolution):
    from look_to_ask import __main__ as cli

    requested = []
    monkeypatch.setattr(
        cli, "probe_camera", lambda index, resolution: requested.append((index, resolution))
    )
    label = f"{resolution[0]}x{resolution[1]}"
    assert cli.main(["--probe-camera", "--camera-resolution", label]) == 0
    assert requested == [(0, resolution)]
