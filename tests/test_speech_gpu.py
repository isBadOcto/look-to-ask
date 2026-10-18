"""GPU failures are injected; no hardware, download or private audio in unit tests."""

from types import SimpleNamespace

import numpy as np
import pytest
from test_vision import wait_until

from look_to_ask import speech


def backend(monkeypatch, *, count=1, failure=None, cuda_prepare=None):
    import ctranslate2
    import faster_whisper

    calls, released = [], []

    def factory(name, **options):
        calls.append((name, options))
        if options["device"] == "cuda" and failure:
            raise failure
        return SimpleNamespace(
            model=SimpleNamespace(unload_model=lambda: released.append(True)),
            transcribe=lambda *_args, **_kwargs: (iter([SimpleNamespace(text="原始转写")]), None),
        )

    monkeypatch.setattr(ctranslate2, "get_cuda_device_count", lambda: count)
    monkeypatch.setattr(faster_whisper, "WhisperModel", factory)
    monkeypatch.setattr(
        speech, "prepare_cuda_libraries", cuda_prepare or (lambda: None), raising=False
    )
    return calls, released


def test_auto_uses_cuda_and_keeps_the_same_model_between_questions(monkeypatch):
    calls, _ = backend(monkeypatch)
    model = speech.load_model("medium")
    assert (model.device, model.compute_type, model.fallback_reason) == ("cuda", "float16", "")
    for _ in range(2):
        assert speech.transcribe_audio(model, np.zeros(16000, np.float32), "zh") == "原始转写"
    assert len(calls) == 1 and calls[0][1]["device"] == "cuda"


@pytest.mark.parametrize("failure", [RuntimeError("PRIVATE GPU memory"), OSError("PRIVATE DLL")])
def test_auto_cuda_load_failure_keeps_cpu_available_without_exposing_raw_errors(
    monkeypatch, failure
):
    calls, _ = backend(monkeypatch, failure=failure)
    model = speech.load_model("medium")
    assert (model.device, model.compute_type, model.fallback_reason) == (
        "cpu",
        "int8",
        "gpu_load_failed",
    )
    assert speech.transcribe_audio(model, np.zeros(16000, np.float32), "zh") == "原始转写"
    assert [options["device"] for _, options in calls] == ["cuda", "cpu"]


def test_auto_without_cuda_does_not_try_to_load_gpu_model(monkeypatch):
    calls, _ = backend(monkeypatch, count=0)
    model = speech.load_model("small")
    assert model.device == "cpu" and model.fallback_reason == "cuda_unavailable"
    assert len(calls) == 1 and calls[0][1]["device"] == "cpu"


def test_missing_optional_dlls_fall_back_before_loading_cuda_model(monkeypatch):
    def missing():
        raise OSError("PRIVATE DLL path")

    calls, _ = backend(monkeypatch, cuda_prepare=missing)
    model = speech.load_model("medium")
    assert model.device == "cpu" and model.fallback_reason == "gpu_load_failed"
    assert len(calls) == 1 and calls[0][1]["device"] == "cpu"


def test_lazy_cuda_failure_discards_partial_text_retries_once_and_reuses_cpu(monkeypatch):
    calls, released = backend(monkeypatch)
    model = speech.load_model("medium")

    def partial(*_args, **_kwargs):
        def segments():
            yield SimpleNamespace(text="不该拼入结果的片段")
            raise RuntimeError("PRIVATE CUDA out of memory")

        return segments(), None

    model._model.transcribe = partial
    for _ in range(2):
        assert speech.transcribe_audio(model, np.zeros(16000, np.float32), "zh") == "原始转写"
    assert model.device == "cpu" and model.fallback_reason == "gpu_inference_failed"
    assert released == [True] and [options["device"] for _, options in calls] == ["cuda", "cpu"]


def test_explicit_cpu_does_not_probe_or_initialize_gpu(monkeypatch):
    def forbidden():
        raise AssertionError("GPU must not be initialized")

    calls, _ = backend(monkeypatch, cuda_prepare=forbidden)
    monkeypatch.setattr("ctranslate2.get_cuda_device_count", forbidden)
    model = speech.load_model("medium", device="cpu")
    assert model.device == "cpu" and model.fallback_reason == ""
    assert len(calls) == 1


def test_explicit_cuda_diagnostic_does_not_hide_gpu_failure(monkeypatch):
    backend(monkeypatch, failure=RuntimeError("CUDA unavailable"))
    with pytest.raises(RuntimeError, match="CUDA unavailable"):
        speech.load_model("medium", device="cuda")


def test_cpu_failure_after_fallback_is_not_retried_indefinitely(monkeypatch):
    backend(monkeypatch, count=0)
    model = speech.load_model("medium")

    def broken(*_args, **_kwargs):
        raise RuntimeError("CPU failure")

    model._model.transcribe = broken
    with pytest.raises(RuntimeError, match="CPU failure"):
        speech.transcribe_audio(model, np.zeros(16000, np.float32), "zh")


def test_failed_cpu_reconstruction_clears_worker_readiness_and_same_name_can_recover(monkeypatch):
    import faster_whisper

    backend(monkeypatch)
    gpu_loads, prepared, failed, results = [], [], [], []

    def factory(_name, **options):
        if options["device"] == "cpu":
            raise RuntimeError("CPU load failure")
        gpu_loads.append(True)
        first = len(gpu_loads) == 1

        def decode(*_args, **_kwargs):
            if first:
                raise RuntimeError("CUDA failure")
            return iter([SimpleNamespace(text="恢复后的原始转写")]), None

        return SimpleNamespace(model=SimpleNamespace(unload_model=lambda: None), transcribe=decode)

    monkeypatch.setattr(faster_whisper, "WhisperModel", factory)
    worker = speech.SpeechWorker()
    worker.prepared.connect(lambda *args: prepared.append(args))
    worker.failed.connect(lambda *args: failed.append(args))
    worker.transcribed.connect(lambda *args: results.append(args))
    try:
        worker.prepare("medium")
        wait_until(lambda: prepared)
        worker.transcribe(1, np.zeros(16000, np.float32), "zh")
        wait_until(lambda: failed)
        assert worker.loaded_name is None and worker.device == "unknown"
        worker.prepare("medium")
        wait_until(lambda: len(prepared) == 2)
        worker.transcribe(2, np.zeros(16000, np.float32), "zh")
        wait_until(lambda: results)
        assert results[0][:2] == (2, "恢复后的原始转写") and len(gpu_loads) == 2
    finally:
        worker.shutdown()
        assert worker.wait(2000)


def test_windows_optional_runtime_uses_known_absolute_directories_and_retains_handles(
    monkeypatch, tmp_path
):
    from look_to_ask import cuda_runtime

    root = tmp_path / "LookToAsk/gpu/nvidia"
    for package, files in (
        ("cublas", ("cublasLt64_12.dll", "cublas64_12.dll")),
        ("cudnn", ("cudnn64_9.dll",)),
        ("cuda_runtime", ("cudart64_12.dll",)),
    ):
        folder = root / package / "bin"
        folder.mkdir(parents=True)
        for name in files:
            (folder / name).write_bytes(b"unit-test-only, never loaded")
    monkeypatch.setattr(cuda_runtime, "_directories", {})
    monkeypatch.setattr(cuda_runtime, "_libraries", {})
    monkeypatch.setattr(cuda_runtime.sys, "platform", "win32")
    monkeypatch.setattr(
        cuda_runtime.sysconfig, "get_paths", lambda: {"purelib": str(tmp_path / "empty")}
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("CUDA_PATH", raising=False)
    monkeypatch.delenv("CUDNN_PATH", raising=False)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(cuda_runtime.os, "add_dll_directory", lambda _path: object())
    loaded = []
    monkeypatch.setattr(
        cuda_runtime.ctypes,
        "WinDLL",
        lambda path, **kwargs: loaded.append((path, kwargs)) or object(),
    )
    cuda_runtime.prepare_cuda_libraries()
    cuda_runtime.prepare_cuda_libraries()
    assert len(loaded) == 3 and len(cuda_runtime._directories) == 3
    assert all(
        path.startswith(str(root)) and options["winmode"] == 0x1000 for path, options in loaded
    )
