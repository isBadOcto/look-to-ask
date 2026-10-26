"""Protocol-boundary tests; no desktop messages, credentials or subprocesses."""

import base64
import importlib
import json
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QProcess, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication
from shiboken6 import delete, isValid

from look_to_ask.calibration import ScreenRect
from look_to_ask.screen_context import build_screen_context

THREAD = "11111111-1111-4111-8111-111111111111"
QUEUE = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def module():
    assert importlib.util.find_spec("look_to_ask.codex_handoff") is not None
    return importlib.import_module("look_to_ask.codex_handoff")


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def snapshot(app):
    image = QImage(900, 700, QImage.Format.Format_RGB32)
    image.fill(QColor("#396cb5"))
    return build_screen_context(image, ScreenRect(0, 0, 900, 700), (450, 350))


class FakeProcess(QObject):
    started = Signal()
    readyReadStandardOutput = Signal()
    readyReadStandardError = Signal()
    errorOccurred = Signal(object)
    finished = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.output = bytearray()
        self.stderr = bytearray()
        self.sent = []
        self.arguments = None
        self.process_state = QProcess.ProcessState.NotRunning
        self.killed = False

    def setProcessChannelMode(self, mode):
        pass

    def start(self, executable, arguments):
        self.arguments = [executable, *arguments]
        self.process_state = QProcess.ProcessState.Running
        self.started.emit()

    def state(self):
        return self.process_state

    def write(self, data):
        self.sent.append(json.loads(bytes(data)))
        return len(data)

    def readAllStandardOutput(self):
        data = bytes(self.output)
        self.output.clear()
        return data

    def readAllStandardError(self):
        data = bytes(self.stderr)
        self.stderr.clear()
        return data

    def closeWriteChannel(self):
        pass

    def kill(self):
        self.killed = True
        self.process_state = QProcess.ProcessState.NotRunning

    def reply(self, value):
        self.feed(json.dumps(value).encode() + b"\n")

    def feed(self, data):
        self.output.extend(data)
        self.readyReadStandardOutput.emit()


@pytest.fixture
def harness(module, app, tmp_path):
    executable = tmp_path / "codex.exe"
    executable.touch()
    process = FakeProcess()
    wakes, completed, failed, checked = [], [], [], []
    client = module.CodexClient(
        process_factory=lambda parent: process,
        wake=lambda thread: wakes.append(thread) or True,
    )
    client.completed.connect(completed.append)
    client.failed.connect(lambda message, code: failed.append((message, code)))
    client.checked.connect(checked.append)
    config = module.CodexConfig(THREAD, str(executable))
    yield client, process, config, wakes, completed, failed, checked
    client.cancel()
    app.processEvents()


def handshake(process, thread=THREAD, name="测试对话"):
    process.reply({"id": 1, "result": {"userAgent": "codex/0.164.0"}})
    process.reply({"id": 2, "result": {"thread": {"id": thread, "name": name}}})


def ack(process, **changes):
    params = process.sent[-1]["params"]
    submission = {
        "id": QUEUE,
        "threadId": THREAD,
        "clientUserMessageId": params["clientUserMessageId"],
        "input": params["input"],
    }
    submission.update(changes)
    process.reply({"id": 3, "result": {"queuedSubmission": submission}})


@pytest.mark.parametrize("value", [THREAD, THREAD.upper(), f"codex://threads/{THREAD}"])
def test_thread_parser_accepts_only_receiver_identifiers(module, value):
    assert module.parse_thread_id(value) == THREAD


@pytest.mark.parametrize(
    "value",
    [
        "", "SECRET", f"codex://threads/{THREAD}?prompt=SECRET",
        f"codex://threads/{THREAD}#SECRET", f"codex://threads/wake/{THREAD}",
        f"https://chatgpt.com/{THREAD}", "{" + THREAD + "}", THREAD.replace("-", ""),
    ],
)
def test_invalid_receiver_errors_do_not_echo_input(module, value):
    with pytest.raises(ValueError) as error:
        module.parse_thread_id(value)
    assert "SECRET" not in str(error.value)


def test_locator_selects_newest_desktop_binary_and_never_npm(module, monkeypatch, tmp_path):
    root = tmp_path / "OpenAI" / "Codex" / "bin"
    old, new = root / "old" / "codex.exe", root / "new" / "codex.exe"
    for path, timestamp in [(old, 100), (new, 200)]:
        path.parent.mkdir(parents=True)
        path.touch()
        os.utime(path, (timestamp, timestamp))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert module.locate_codex() == str(new.resolve())
    new.unlink()
    old.unlink()
    with pytest.raises(ValueError):
        module.locate_codex()


def test_config_normalizes_receiver_and_requires_real_absolute_executable(module, tmp_path):
    executable = tmp_path / "codex.exe"
    executable.touch()
    config = module.CodexConfig(f"codex://threads/{THREAD}", str(executable)).validate()
    assert config.thread_id == THREAD
    assert Path(config.executable) == executable.resolve()
    with pytest.raises(ValueError):
        module.CodexConfig(THREAD, "codex.exe").validate()


def test_input_contains_annotated_overview_and_unchanged_focus(module, snapshot):
    content = module.build_codex_input(snapshot, "  这里是什么？  ")
    assert [part["type"] for part in content] == ["text", "image", "image"]
    assert "这里是什么？" in content[0]["text"]
    assert "(450, 350)" in content[0]["text"]
    assert "(170, 170, 560, 360)" in content[0]["text"]
    images = []
    for part in content[1:]:
        assert part["url"].startswith("data:image/png;base64,")
        image = QImage.fromData(base64.b64decode(part["url"].split(",", 1)[1]), "PNG")
        assert not image.isNull()
        images.append(image)
    assert images[0].size() == snapshot.roi.size()
    assert images[0] != snapshot.roi
    assert images[1] == snapshot.focus


def test_prompt_explicitly_describes_shared_primary_screen(module, app):
    image = QImage(300, 200, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    screen = ScreenRect(0, 0, 300, 200)
    snapshot = build_screen_context(image, screen, (150, 100))
    text = module.build_codex_input(snapshot, "what is shown?")[0]["text"]
    assert "Image 1 is an overview of the entire primary screen" in text
    assert text.isascii()


@pytest.mark.parametrize("question", ["", " \n", "x" * 8001])
def test_input_rejects_invalid_questions(module, snapshot, question):
    with pytest.raises(ValueError):
        module.build_codex_input(snapshot, question)


def test_input_size_limit_rejects_before_process_start(module, snapshot, monkeypatch):
    monkeypatch.setattr(module, "MAX_INPUT_BYTES", 100)
    with pytest.raises(ValueError):
        module.build_codex_input(snapshot, "question")


def test_check_uses_initialize_and_read_only_then_emits_receiver_title(harness):
    client, process, config, wakes, completed, failed, checked = harness
    client.check(config)
    assert client.busy
    assert process.sent == [{
        "id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "look_to_ask", "version": "1"},
            "capabilities": {"experimentalApi": True},
        },
    }]
    handshake(process)
    assert [message["method"] for message in process.sent] == [
        "initialize", "initialized", "thread/read",
    ]
    assert process.sent[-1]["params"] == {"threadId": THREAD, "includeTurns": False}
    assert checked == ["测试对话"]
    assert not client.busy
    assert not completed and not failed and not wakes


def test_send_only_enqueues_and_wakes_after_verified_ack(harness, snapshot):
    client, process, config, wakes, completed, failed, checked = harness
    client.send(config, snapshot, "question")
    handshake(process)
    assert [message["method"] for message in process.sent] == [
        "initialize", "initialized", "thread/read", "thread/queue/add",
    ]
    params = process.sent[-1]["params"]
    assert params["threadId"] == THREAD
    assert [part["type"] for part in params["input"]] == ["text", "image", "image"]
    assert not wakes and not completed
    ack(process)
    assert wakes == [THREAD]
    assert completed == [QUEUE]
    assert not client.busy and not failed and not checked
    assert process.killed


def test_target_mismatch_never_enqueues(harness, snapshot):
    client, process, config, wakes, completed, failed, _ = harness
    client.send(config, snapshot, "question")
    handshake(process, thread=QUEUE)
    assert all(message["method"] != "thread/queue/add" for message in process.sent)
    assert failed[-1][1] == "invalid_receiver"
    assert not wakes and not completed


def test_unsupported_protocol_fails_without_fallback_or_raw_error(harness, snapshot):
    client, process, config, wakes, completed, failed, _ = harness
    client.send(config, snapshot, "PRIVATE QUESTION")
    process.reply({"id": 1, "error": {"code": -32601, "message": "SECRET ERROR"}})
    assert failed[-1][1] == "compatibility"
    assert "SECRET" not in failed[-1][0] and "PRIVATE" not in failed[-1][0]
    assert len(process.sent) == 1 and not wakes and not completed


@pytest.mark.parametrize("field", ["clientUserMessageId", "input", "id", "threadId"])
def test_unverified_ack_is_unknown_delivery_and_never_wakes(harness, snapshot, field):
    client, process, config, wakes, completed, failed, _ = harness
    client.send(config, snapshot, "question")
    handshake(process)
    changes = {
        "clientUserMessageId": "wrong", "input": [{"type": "text", "text": "wrong"}],
        "id": "not-a-uuid", "threadId": QUEUE,
    }
    ack(process, **{field: changes[field]})
    assert failed[-1][1] == "delivery_unknown"
    assert not wakes and not completed


def test_cancellation_before_enqueue_prevents_late_submission(harness, snapshot):
    client, process, config, wakes, completed, failed, _ = harness
    client.send(config, snapshot, "question")
    client.cancel()
    handshake(process)
    assert failed[-1][1] == "cancelled"
    assert all(message["method"] != "thread/queue/add" for message in process.sent)
    assert not wakes and not completed and not client.busy


def test_cancellation_after_enqueue_warns_unknown_and_ignores_late_ack(harness, snapshot):
    client, process, config, wakes, completed, failed, _ = harness
    client.send(config, snapshot, "question")
    handshake(process)
    client.cancel()
    ack(process)
    assert failed[-1][1] == "delivery_unknown"
    assert not wakes and not completed


@pytest.mark.parametrize("after_enqueue", [False, True])
def test_timeout_never_retries_and_distinguishes_unknown_delivery(harness, snapshot, after_enqueue):
    client, process, config, wakes, completed, failed, _ = harness
    client.send(config, snapshot, "question")
    if after_enqueue:
        handshake(process)
    client._timer.timeout.emit()
    assert failed[-1][1] == ("delivery_unknown" if after_enqueue else "timeout")
    assert not client.busy and not wakes and not completed


def test_acknowledged_queue_with_failed_wake_is_not_reported_complete(harness, snapshot):
    client, process, config, wakes, completed, failed, _ = harness
    client._wake = lambda thread: False
    client.send(config, snapshot, "question")
    handshake(process)
    ack(process)
    assert failed[-1][1] == "queued_not_woken"
    assert not completed and not client.busy


def test_buffer_limit_and_malformed_json_never_expose_body(harness, module, monkeypatch):
    client, process, config, _, completed, failed, _ = harness
    monkeypatch.setattr(module, "MAX_BUFFER_BYTES", 30)
    client.check(config)
    process.feed(b"SECRET" * 10)
    assert failed[-1][1] == "response_too_large"
    assert "SECRET" not in failed[-1][0] and not completed


def test_fragmented_responses_notifications_and_stderr_are_handled(harness):
    client, process, config, _, completed, failed, checked = harness
    client.check(config)
    process.stderr.extend(b"SECRET STDERR")
    process.readyReadStandardError.emit()
    process.feed(b'{"method":"warning","params":{"message":"SECRET"}}\n{"id":1,"res')
    process.feed(b'ult":{}}\n')
    process.reply({"id": 2, "result": {"thread": {"id": THREAD, "name": "Receiver"}}})
    assert checked == ["Receiver"] and not completed and not failed
    assert not process.stderr


def test_process_failure_after_enqueue_is_unknown_delivery(harness, snapshot):
    client, process, config, wakes, completed, failed, _ = harness
    client.send(config, snapshot, "question")
    handshake(process)
    process.errorOccurred.emit(QProcess.ProcessError.Crashed)
    assert failed[-1][1] == "delivery_unknown"
    assert not completed and not wakes and not client.busy


def test_server_error_after_enqueue_is_unknown_delivery(harness, snapshot):
    client, process, config, wakes, completed, failed, _ = harness
    client.send(config, snapshot, "question")
    handshake(process)
    process.reply({"id": 3, "error": {"code": -32603, "message": "SECRET ERROR"}})
    assert failed[-1][1] == "delivery_unknown"
    assert "SECRET" not in failed[-1][0] and not completed and not wakes


def test_receipt_id_cannot_be_a_deep_link(harness, snapshot):
    client, process, config, wakes, completed, failed, _ = harness
    client.send(config, snapshot, "question")
    handshake(process)
    ack(process, id=f"codex://threads/{QUEUE}")
    assert failed[-1][1] == "delivery_unknown"
    assert not completed and not wakes


def test_malformed_response_is_sanitized(harness):
    client, process, config, _, completed, failed, _ = harness
    client.check(config)
    process.feed(b"SECRET NOT JSON\n")
    assert failed[-1][1] == "invalid_response"
    assert "SECRET" not in failed[-1][0] and not completed


def test_busy_client_rejects_second_operation(harness):
    client, process, config, *_ = harness
    client.check(config)
    with pytest.raises(ValueError):
        client.check(config)
    assert len(process.sent) == 1


def test_wake_uses_only_nonactivating_queue_uri(module, monkeypatch):
    calls = []

    class Execute:
        def __call__(self, *arguments):
            calls.append(arguments)
            return 33

    class Shell:
        ShellExecuteW = Execute()

    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.ctypes, "WinDLL", lambda *args, **kwargs: Shell())
    assert module.wake_codex_thread(THREAD)
    assert calls == [(None, "open", f"codex://threads/wake/{THREAD}", None, None, 4)]
    assert not module.wake_codex_thread(f"codex://threads/{THREAD}")
    assert len(calls) == 1


def test_native_wake_failure_is_reported_without_navigation_fallback(module, monkeypatch):
    class Execute:
        def __call__(self, *arguments):
            return 31

    class Shell:
        ShellExecuteW = Execute()

    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.ctypes, "WinDLL", lambda *args, **kwargs: Shell())
    assert not module.wake_codex_thread(THREAD)


def test_same_type_receipt_with_changed_image_cannot_wake(harness, snapshot):
    client, process, config, wakes, completed, failed, _ = harness
    client.send(config, snapshot, "question")
    handshake(process)
    content = [dict(part) for part in process.sent[-1]["params"]["input"]]
    content[1]["url"] = "data:image/png;base64,ALTERED"
    ack(process, input=content)
    assert failed[-1][1] == "delivery_unknown"
    assert not wakes and not completed


def test_check_cancellation_and_process_exit_never_emit_completion(harness):
    client, process, config, _, completed, failed, checked = harness
    client.check(config)
    client.cancel()
    process.finished.emit(0, QProcess.ExitStatus.NormalExit)
    assert failed[-1][1] == "cancelled"
    assert not completed and not checked


def test_startup_failure_is_sanitized_and_releases_busy_state(harness):
    client, process, config, _, completed, failed, _ = harness
    client.check(config)
    process.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
    assert failed[-1][1] == "process_error"
    assert not completed and not client.busy


def test_late_finished_callback_ignores_deleted_native_process(module, app):
    client = module.CodexClient()
    process = QProcess()
    delete(process)
    assert not isValid(process)
    client._finished(process)
    assert not client.busy


def test_finished_callback_rechecks_native_lifetime_after_completion(harness, snapshot):
    client, process, config, _, completed, failed, _ = harness
    client.send(config, snapshot, "question")
    handshake(process)
    params = process.sent[-1]["params"]
    message = {"id": 3, "result": {"queuedSubmission": {
        "id": QUEUE, "threadId": THREAD,
        "clientUserMessageId": params["clientUserMessageId"], "input": params["input"],
    }}}
    process.output.extend(json.dumps(message).encode() + b"\n")
    client.completed.connect(lambda _queue: delete(process))
    client._finished(process)
    assert completed == [QUEUE] and not failed
    assert not isValid(process) and not client.busy


def test_parent_destruction_makes_late_callbacks_inert(module, app):
    parent = QObject()
    client = module.CodexClient(parent)
    process = QProcess(client)
    client._process = process
    delete(parent)
    assert not isValid(client) and not isValid(process)
    client._finished(process)
    client._started(process)
    client._consume(process)
    client._process_error(process)
    client._discard_stderr(process)
    client._timeout()
    client.cancel()


@pytest.mark.parametrize("after_enqueue", [False, True])
def test_unexpected_native_destruction_still_reports_delivery_state(
    harness, snapshot, after_enqueue
):
    client, process, config, wakes, completed, failed, _ = harness
    client.send(config, snapshot, "question")
    if after_enqueue:
        handshake(process)
    delete(process)
    assert failed[-1][1] == ("delivery_unknown" if after_enqueue else "process_error")
    assert len(failed) == 1 and not completed and not wakes and not client.busy
