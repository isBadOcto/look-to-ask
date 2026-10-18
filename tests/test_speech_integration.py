"""Real Whisper decoding of a locally generated test fixture; never records people."""

import json
import os
import time
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtGui import QColor, QImage, QPainter
from scipy.io import wavfile
from scipy.signal import resample_poly
from test_ask import dispose, prepare
from test_vision import service, wait_until  # noqa: F401 -- pytest fixture imported explicitly
from test_voice import stable

from look_to_ask.context import build_context
from look_to_ask.speech import SpeechError, load_model, transcribe_audio

REAL_LOCAL_APP_DATA = os.environ.get("LOCALAPPDATA")


@pytest.fixture(autouse=True)
def optional_real_cuda_libraries(monkeypatch):
    # Preference writes stay isolated. Only the explicit GPU test run reads real generic DLLs.
    if os.environ.get("LOOK_TO_ASK_TEST_CUDA") == "1" and REAL_LOCAL_APP_DATA:
        from look_to_ask import cuda_runtime

        paths = cuda_runtime.sysconfig.get_paths()
        paths["purelib"] = str(Path(REAL_LOCAL_APP_DATA) / "LookToAsk/gpu")
        monkeypatch.setattr(cuda_runtime.sysconfig, "get_paths", lambda: paths)


def local_fixture(name="base"):
    fixture = Path(__file__).parent / "fixtures" / "local-voice-zh.wav"
    cache = Path.home() / f".cache/look-to-ask/whisper/models--Systran--faster-whisper-{name}"
    reference = cache / "refs/main"
    if not fixture.exists() or not reference.exists():
        pytest.skip(f"需先准备 {name} 模型并运行 tests/manual/create_voice_fixture.ps1；测试不下载")
    model_path = cache / "snapshots" / reference.read_text().strip()
    rate, samples = wavfile.read(fixture)
    audio = np.asarray(resample_poly(samples.astype(np.float32) / 32768, 16000, rate), np.float32)
    return model_path, audio


def test_cached_whisper_repeated_chinese_recognition_and_silence():
    model_path, audio = local_fixture()
    started = time.perf_counter()
    model = load_model(
        str(model_path), device="cpu"
    )  # Preserve the original CPU accuracy baseline.
    metrics = {"cached_model_load_ms": round((time.perf_counter() - started) * 1000), "asr_ms": []}
    for _ in range(3):
        started = time.perf_counter()
        text = transcribe_audio(model, audio, "zh")
        metrics["asr_ms"].append(round((time.perf_counter() - started) * 1000))
        assert "什么意思" in text and "报错" in text
    with pytest.raises(SpeechError, match="没有识别到语音"):
        transcribe_audio(model, np.zeros(16000, np.float32), "zh")
    print("REAL_LOCAL_ASR", json.dumps(metrics))


@pytest.mark.skipif(
    os.environ.get("LOOK_TO_ASK_TEST_CUDA") != "1",
    reason="Optional real CUDA test; explicitly opt in",
)
def test_real_cuda_medium_three_turns_no_fallback_and_silence():
    model_path, audio = local_fixture("medium")
    model = load_model(str(model_path), device="cuda")
    try:
        for _ in range(3):
            text = transcribe_audio(model, audio, "zh")
            assert "什么意思" in text and "为什么" in text
            assert model.device == "cuda" and model.fallback_reason == ""
        with pytest.raises(SpeechError, match="没有识别到语音"):
            transcribe_audio(model, np.zeros(16000, np.float32), "zh")
    finally:
        model.close()


def test_real_cpu_recognition_after_missing_gpu_runtime(monkeypatch):
    model_path, audio = local_fixture()
    monkeypatch.setattr("ctranslate2.get_cuda_device_count", lambda: 1)

    def missing():
        raise OSError("injected missing NVIDIA DLL, not real audio")

    monkeypatch.setattr("look_to_ask.speech.prepare_cuda_libraries", missing)
    model = load_model(str(model_path))
    try:
        text = transcribe_audio(model, audio, "zh")
        assert "什么意思" in text and model.device == "cpu"
        assert model.fallback_reason == "gpu_load_failed"
    finally:
        model.close()


@pytest.mark.parametrize("name", ["small", "medium"])
def test_larger_cached_models_decode_and_reject_silence_without_claiming_perfect_accuracy(name):
    model_path, audio = local_fixture(name)
    model = load_model(str(model_path))
    for _ in range(3):
        text = transcribe_audio(model, audio, "zh")
        assert "什么意思" in text and "为什么" in text
    # This fixture still has homophone errors (报错/爆错); do not hide them by text replacement.
    with pytest.raises(SpeechError, match="没有识别到语音"):
        transcribe_audio(model, np.zeros(16000, np.float32), "zh")


@pytest.mark.parametrize("name", ["base", "small", "medium"])
def test_real_asr_worker_to_real_local_http_three_turns(service, name):  # noqa: F811
    """Synthetic audio/screen + real ASR/thread/HTTP. The HTTP answer is explicitly a fixture."""
    model_path, audio = local_fixture(name)
    app, window = prepare()
    voice = window.voice
    url, server = service
    server["delay"] = 0.05
    dialog = window.ask.dialog
    dialog.base_url_edit.setText(url)
    dialog.model_edit.setText("local-http-fixture-not-ai")
    dialog.speech_model_edit.setText(str(model_path))

    class AudioFixture:
        MAX_SECONDS = 30
        active = False
        fault = False

        def start(self):
            self.active = True

        def stop(self):
            self.active = False
            return audio.copy(), len(audio) / 16000

        def cancel(self):
            self.active = False

    voice.recorder = AudioFixture()
    image = QImage(1000, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    painter = QPainter(image)
    painter.fillRect(500, 0, 500, 800, QColor("blue"))
    painter.end()
    captures, transcripts = [], []
    voice.engine.transcribed.connect(lambda _identity, text, _ms: transcripts.append(text))

    def capture(screen, point):
        captures.append(point)
        return build_context(image, screen, point)

    window.ask.capture_factory = capture
    try:
        voice.prepare()
        wait_until(lambda: voice.engine.loaded_name is not None, timeout=10)
        for x in (200, 800, 300):
            stable(window, x)
            assert voice.press()
            window._on_gaze(900, 700, time.monotonic())
            voice.release()
            wait_until(lambda: not voice.active, timeout=10)
            assert "HTTP 测试响应" in dialog.answer_view.toPlainText()
        assert captures == [(200, 400), (800, 400), (300, 400)]
        assert len(server["received"]) == 3
        contents = [item[1]["messages"][1]["content"] for item in server["received"]]
        # Model/device changes may produce simplified/traditional variants or homophone errors.
        # This integration contract is to send the actual, unmodified ASR text with its locked crop.
        assert len(transcripts) == 3 and all(transcripts)
        assert all(
            text in content[0]["text"] for text, content in zip(transcripts, contents, strict=True)
        )
        pictures = [
            [part["image_url"]["url"] for part in c if part["type"] == "image_url"]
            for c in contents
        ]
        assert pictures[0] != pictures[1]
        metrics = [json.loads(line) for line in window.ask.log.records if "voice_completed" in line]
        assert len(metrics) == 3 and all(m["code"] == "ok" for m in metrics)
        if os.environ.get("LOOK_TO_ASK_TEST_CUDA") == "1":
            events = [
                json.loads(line)
                for line in window.ask.log.records
                if '"event": "asr_completed"' in line
            ]
            assert len(events) == 3 and all(e["speech_device"] == "cuda" for e in events)
        print("REAL_ASR_LOCAL_HTTP", json.dumps([m["after_release_ms"] for m in metrics]))
    finally:
        dispose(window)
        assert voice.engine.wait(5000)
        app.processEvents()
