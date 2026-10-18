"""Explicit audio/device fixtures; never used by the running application."""

from types import SimpleNamespace

import numpy as np
import pytest
import sounddevice as sd
from test_vision import wait_until

from look_to_ask.speech import PushToTalkRecorder, SpeechError, SpeechWorker, transcribe_audio


class Device:
    def __init__(self, *, fail=False, overflow=False):
        self.fail, self.overflow = fail, overflow
        self.closed = self.aborted = False

    def query_devices(self, **_kwargs):
        return {"default_samplerate": 48000}

    def InputStream(self, **kwargs):
        self.callback = kwargs["callback"]
        return self

    def start(self):
        if self.fail:
            raise RuntimeError("private device failure")
        self.callback(np.ones((48000, 1), dtype=np.float32) * 0.02, 48000, None, self.overflow)

    def abort(self):
        self.aborted = True

    def close(self):
        self.closed = True


def test_audio_diagnostics_are_numeric_raw_input_metadata_and_clear_on_next_press():
    device = Device()
    recorder = PushToTalkRecorder(device=device)
    recorder.start()
    recorder.stop()
    stats = recorder.signal_stats
    assert stats["input_rate"] == 48000
    assert stats["rms_dbfs"] == pytest.approx(-34, abs=0.1)
    assert stats["peak_dbfs"] == pytest.approx(-34, abs=0.1)
    assert stats["full_scale_fraction"] == 0
    assert all(type(value) in (int, float) for value in stats.values())
    recorder.start()
    assert recorder.signal_stats is None
    recorder.cancel()


def test_audio_diagnostics_detect_full_scale_before_resampling_and_cleanup_on_failure():
    recorder = PushToTalkRecorder(device=Device())
    recorder.start()
    recorder._chunks = [np.ones(48000, np.float32)]
    recorder.stop()
    assert recorder.signal_stats["full_scale_fraction"] == 1
    assert recorder.signal_stats["peak_dbfs"] == 0
    recorder.start()
    recorder._bad = True
    with pytest.raises(SpeechError):
        recorder.stop()
    assert recorder.signal_stats is None and not recorder.active


def test_44100_hz_resampling_preserves_real_signal_pitch_and_duration():
    device = Device()
    device.query_devices = lambda **_kwargs: {"default_samplerate": 44100}
    recorder = PushToTalkRecorder(device=device)
    recorder.start()
    recorder._chunks = [np.sin(2 * np.pi * 440 * np.arange(44100) / 44100).astype(np.float32) * 0.1]
    recorder._frames = 44100
    audio, duration = recorder.stop()
    assert duration == 1 and len(audio) == 16000
    peak_hz = np.argmax(np.abs(np.fft.rfft(audio)))
    assert peak_hz == 440


def test_default_mic_opens_only_on_press_and_closes_before_resampling(monkeypatch):
    from look_to_ask import speech

    device = Device()
    original_resample = speech.resample_poly

    def checked_resample(*args, **kwargs):
        assert device.closed and device.aborted
        return original_resample(*args, **kwargs)

    monkeypatch.setattr(speech, "resample_poly", checked_resample)
    recorder = PushToTalkRecorder(device=device)
    assert not hasattr(device, "callback")
    recorder.start()
    audio, duration = recorder.stop()
    assert device.closed and device.aborted and not recorder.active
    assert audio.shape == (16000,) and audio.dtype == np.float32 and duration == 1
    assert recorder.buffered_frames == 0
    recorder.start()
    recorder.cancel()
    assert not recorder.active and recorder.buffered_frames == 0


@pytest.mark.parametrize("failure", ["open", "overflow", "short", "invalid"])
def test_recorder_errors_release_device_and_clear_audio(failure):
    device = Device(fail=failure == "open", overflow=failure == "overflow")
    recorder = PushToTalkRecorder(device=device)
    with pytest.raises(SpeechError):
        recorder.start()
        if failure in ("short", "invalid"):
            recorder._chunks.clear()
            recorder._frames = 48000 if failure == "invalid" else 100
            recorder._chunks.append(
                np.full(recorder._frames, np.nan if failure == "invalid" else 0.0)
            )
        recorder.stop()
    assert device.closed and not recorder.active and recorder.buffered_frames == 0


def test_real_transcription_options_and_empty_vad_result():
    calls = []

    class Model:
        def transcribe(self, audio, **kwargs):
            calls.append(kwargs)
            return iter([SimpleNamespace(text=" 这个是什么？ ")]), None

    assert transcribe_audio(Model(), np.zeros(16000, np.float32), "zh") == "这个是什么？"
    assert calls[0]["vad_filter"] and calls[0]["beam_size"] == 5
    assert calls[0]["language"] == "zh"
    assert calls[0]["condition_on_previous_text"] is False

    class Empty:
        def transcribe(self, *_args, **_kwargs):
            return iter([]), None

    with pytest.raises(SpeechError, match="语音"):
        transcribe_audio(Empty(), np.zeros(16000, np.float32), "auto")


def test_callback_overflow_aborts_collection_and_device_close_error_is_safe():
    device = Device()
    recorder = PushToTalkRecorder(device=device)
    recorder.start()
    with pytest.raises(sd.CallbackAbort):
        device.callback(np.zeros((480, 1), np.float32), 480, None, True)
    assert recorder.fault
    recorder.cancel()
    assert device.closed and not recorder.active and recorder.buffered_frames == 0

    def fail_abort():
        raise RuntimeError("device unplugged")

    device.abort = fail_abort
    recorder.start()
    recorder.cancel()
    assert device.closed and not recorder.active and recorder.buffered_frames == 0


def test_worker_reuses_model_handles_failure_and_exits_without_destroying_running_thread():
    calls, prepared, results, errors = [], [], [], []

    class Model:
        def transcribe(self, audio, **_kwargs):
            return iter([] if audio[0] == 0 else [SimpleNamespace(text=" words ")]), None

    def factory(name):
        calls.append(name)
        if name == "bad":
            raise RuntimeError("private path/token")
        return Model()

    worker = SpeechWorker(model_factory=factory)
    worker.prepared.connect(lambda *args: prepared.append(args))
    worker.transcribed.connect(lambda *args: results.append(args))
    worker.failed.connect(lambda *args: errors.append(args))
    try:
        worker.prepare("base")
        wait_until(lambda: prepared)
        worker.transcribe(1, np.ones(16000, np.float32), "en")
        wait_until(lambda: results)
        worker.transcribe(2, np.zeros(16000, np.float32), "zh")
        wait_until(lambda: errors)
        worker.prepare("base")
        wait_until(lambda: len(prepared) == 2)
        assert calls == ["base"] and results[0][:2] == (1, "words")
        worker.prepare("bad")
        wait_until(lambda: len(errors) == 2)
        assert "private" not in str(errors) and worker.loaded_name is None
    finally:
        worker.shutdown()
        assert worker.wait(2000)
