"""On-demand microphone and reusable local Whisper worker; audio stays in RAM."""

import math
import os
import queue
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QThread, Signal
from scipy.signal import resample_poly

from look_to_ask.cuda_runtime import prepare_cuda_libraries
from look_to_ask.i18n import tr

SPEECH_BEAM_SIZE = 5


class SpeechError(ValueError):
    pass


class PushToTalkRecorder:
    MAX_SECONDS = 30

    def __init__(self, *, device=sd):
        self.device = device
        self._stream = None
        self._chunks = []
        self._frames = 0
        self._bad = False
        self._lock = threading.Lock()
        self.rate = 16000
        self.signal_stats = None

    @property
    def active(self):
        return self._stream is not None

    @property
    def buffered_frames(self):
        return self._frames

    @property
    def fault(self):
        with self._lock:
            return self._bad

    def start(self):
        if self.active:
            raise SpeechError(tr("麦克风已在录音。"))
        self.cancel()
        try:
            self.rate = round(self.device.query_devices(kind="input")["default_samplerate"])
            if not 8000 <= self.rate <= 192000:
                raise SpeechError(tr("麦克风采样率不受支持。"))
            self._stream = self.device.InputStream(
                samplerate=self.rate,
                channels=1,
                dtype="float32",
                callback=self._receive,
            )
            self._stream.start()
            if self.fault:
                raise SpeechError(tr("录音设备溢出。"))
        except Exception as exc:
            self.cancel()
            raise SpeechError(tr("无法打开默认麦克风；检查设备、Windows 隐私权限或占用。")) from exc

    def _receive(self, data, frames, _time_info, status):
        with self._lock:
            if status or self._frames + frames > self.rate * self.MAX_SECONDS:
                self._bad = True
                # PortAudio stops collection immediately; the GUI releases the device.
                raise sd.CallbackAbort
            self._chunks.append(data[:, 0].copy())
            self._frames += frames

    def _close(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.abort()
            finally:
                stream.close()

    def cancel(self):
        try:
            self._close()
        except Exception:
            # A disconnected device may fail abort/close; both are attempted by _close.
            pass
        finally:
            with self._lock:
                self._chunks.clear()
                self._frames = 0
                self._bad = False
                self.signal_stats = None

    def stop(self):
        stats = None
        try:
            self._close()  # Close hardware before any concatenation/resampling.
            with self._lock:
                chunks, self._chunks = self._chunks, []
                frames, self._frames = self._frames, 0
                bad, self._bad = self._bad, False
            if bad:
                raise SpeechError(tr("录音溢出或超过 30 秒；本次已取消，请缩短问题重试。"))
            duration = frames / self.rate
            if duration < 0.35 or not chunks:
                raise SpeechError(tr("录音太短；按住说完问题再松开。"))
            audio = np.concatenate(chunks)
            if not np.isfinite(audio).all():
                raise SpeechError(tr("麦克风返回无效音频；本次没有发送。"))
            # Raw capture metadata only; resampling overshoot must not look like input clipping.
            rms = float(np.sqrt(np.square(audio, dtype=np.float64).mean()))
            peak = float(np.max(np.abs(audio)))
            stats = {
                "input_rate": self.rate,
                "rms_dbfs": round(20 * math.log10(max(rms, 1e-6)), 1),
                "peak_dbfs": round(20 * math.log10(max(peak, 1e-6)), 1),
                "full_scale_fraction": round(float(np.mean(np.abs(audio) >= 0.999)), 6),
            }
            divisor = math.gcd(self.rate, 16000)
            audio = resample_poly(audio, 16000 // divisor, self.rate // divisor)
            return np.ascontiguousarray(audio, dtype=np.float32), duration
        except SpeechError:
            raise
        except Exception as exc:
            raise SpeechError(tr("无法结束录音；请重新连接麦克风后重试。")) from exc
        finally:
            self.cancel()
            self.signal_stats = stats


class LocalWhisperModel:
    """Reuse one local model; retry a failed GPU turn once on CPU, without partial text."""

    def __init__(self, name, device="auto"):
        if device not in ("auto", "cpu", "cuda"):
            raise ValueError("Unsupported speech device")
        self.name, self.requested_device = name, device
        self.device, self.compute_type, self.fallback_reason = "cpu", "int8", ""
        self._model = None
        if device != "cpu":
            try:
                import ctranslate2

                if ctranslate2.get_cuda_device_count() < 1:
                    self.fallback_reason = "cuda_unavailable"
                    if device == "cuda":
                        raise RuntimeError("No CUDA device")
                else:
                    prepare_cuda_libraries()
                    self._load("cuda")
            except (RuntimeError, OSError, ValueError):
                if device == "cuda":
                    raise
                self.fallback_reason = "gpu_load_failed"
        if self._model is None:
            self._load("cpu")

    def _load(self, device):
        from faster_whisper import WhisperModel

        compute_type = "float16" if device == "cuda" else "int8"
        self._model = WhisperModel(
            self.name,
            device=device,
            compute_type=compute_type,
            cpu_threads=min(4, os.cpu_count() or 1),
            num_workers=1,
            download_root=str(Path.home() / ".cache" / "look-to-ask" / "whisper"),
        )
        self.device, self.compute_type = device, compute_type

    def close(self):
        model, self._model = self._model, None
        self.device, self.compute_type = "unknown", "unknown"
        if model is not None:
            try:
                model.model.unload_model()
            except (RuntimeError, OSError):
                pass  # Release the Python reference even when the CUDA context has failed.

    def _decode(self, audio, options):
        segments, info = self._model.transcribe(audio, **options)
        # Native inference is lazy. Finish it here so a late CUDA error can be retried safely.
        return list(segments), info

    def transcribe(self, audio, **options):
        try:
            return self._decode(audio, options)
        except (RuntimeError, OSError):
            if self.device != "cuda" or self.requested_device != "auto":
                raise
            self.close()
            self.fallback_reason = "gpu_inference_failed"
            self._load("cpu")
        return self._decode(audio, options)


def load_model(name, *, device="auto"):
    return LocalWhisperModel(name, device)


def transcribe_audio(model, audio, language):
    segments, _info = model.transcribe(
        audio,
        language=None if language == "auto" else language,
        beam_size=SPEECH_BEAM_SIZE,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    # faster-whisper is lazy: iteration performs actual recognition.
    text = "".join(segment.text for segment in segments).strip()
    if not text:
        raise SpeechError(tr("没有识别到语音；本次没有发送，请检查麦克风后重试。"))
    if len(text) > 8000:
        raise SpeechError(tr("转写过长；请缩短问题重试。"))
    return text


class SpeechWorker(QThread):
    """One worker retains the general model across turns; it never opens a microphone."""

    prepared = Signal(str, int)
    transcribed = Signal(int, str, int)
    failed = Signal(int, str, str)

    def __init__(self, parent=None, *, model_factory=load_model):
        super().__init__(parent)
        self.model_factory = model_factory
        self.loaded_name = None
        self.device = "unknown"
        self.compute_type = "unknown"
        self.fallback_reason = ""
        self.busy = False
        self._jobs = queue.Queue(maxsize=1)

    def _submit(self, job):
        if self.busy or self.isInterruptionRequested():
            raise SpeechError(tr("语音引擎仍在处理上一项任务，请稍后重试。"))
        self.busy = True
        self._jobs.put_nowait(job)
        if not self.isRunning():
            self.start()

    def prepare(self, name):
        self._submit(("prepare", name.strip()))

    def transcribe(self, identity, audio, language):
        self._submit(("transcribe", identity, audio, language))

    def shutdown(self):
        self.requestInterruption()
        # Wake an idle worker. Active native inference/download finishes safely.
        try:
            self._jobs.put_nowait(("quit",))
        except queue.Full:
            pass

    def run(self):
        model = None
        while not self.isInterruptionRequested():
            job = self._jobs.get()
            if job[0] == "quit" or self.isInterruptionRequested():
                break
            started = time.monotonic()
            identity = 0 if job[0] == "prepare" else job[1]
            try:
                if job[0] == "prepare":
                    if not job[1]:
                        raise SpeechError(
                            tr("请填写语音模型名（准确优先 medium，较快 small）或本地目录。")
                        )
                    if self.loaded_name != job[1]:
                        if isinstance(model, LocalWhisperModel):
                            model.close()
                        model = self.model_factory(job[1])
                        self.loaded_name = job[1]
                    self._backend(model)
                    self.busy = False
                    if not self.isInterruptionRequested():
                        self.prepared.emit(
                            self.loaded_name, round((time.monotonic() - started) * 1000)
                        )
                else:
                    if model is None:
                        raise SpeechError(tr("请先准备语音模型。"))
                    text = transcribe_audio(model, job[2], job[3])
                    self._backend(model)
                    self.busy = False
                    if not self.isInterruptionRequested():
                        self.transcribed.emit(
                            identity, text, round((time.monotonic() - started) * 1000)
                        )
            except Exception as exc:
                self.busy = False
                if job[0] == "prepare" or (
                    isinstance(model, LocalWhisperModel) and model._model is None
                ):
                    model, self.loaded_name = None, None
                    self.device, self.compute_type, self.fallback_reason = "unknown", "unknown", ""
                elif model is not None:
                    self._backend(model)
                if not self.isInterruptionRequested():
                    self.failed.emit(
                        identity,
                        str(exc)
                        if isinstance(exc, SpeechError)
                        else (
                            tr("语音模型加载失败；检查网络、本地路径及磁盘空间。")
                            if job[0] == "prepare"
                            else tr("本地语音识别失败；请重试或改用文字提问。")
                        ),
                        "model_failed" if job[0] == "prepare" else "asr_failed",
                    )
            finally:
                job = None  # Drop the per-turn audio reference immediately.
        self.busy = False
        self.loaded_name = None
        if isinstance(model, LocalWhisperModel):
            model.close()
        while not self._jobs.empty():
            self._jobs.get_nowait()

    def _backend(self, model):
        self.device = getattr(model, "device", "unknown")
        self.compute_type = getattr(model, "compute_type", "unknown")
        self.fallback_reason = getattr(model, "fallback_reason", "")
