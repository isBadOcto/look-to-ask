"""Local HTTP fixtures verify transport, never claim genuine multimodal accuracy."""

import base64
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from look_to_ask.calibration import ScreenRect  # noqa: E402
from look_to_ask.context import build_context  # noqa: E402
from look_to_ask.vision import ApiConfig, VisionClient, build_payload  # noqa: E402


@pytest.fixture
def snapshot():
    image = QImage(1000, 800, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    return build_context(image, ScreenRect(0, 0, 1000, 800), (500, 400))


@pytest.fixture
def service():
    state = {
        "received": [],
        "status": 200,
        "delay": 0,
        "headers": {},
        "body": {"choices": [{"message": {"content": "HTTP 测试响应，非真实 AI"}}]},
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            state["received"].append(
                (self.path, json.loads(body), self.headers.get("Authorization"))
            )
            time.sleep(state["delay"])
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            for name, value in state["headers"].items():
                self.send_header(name, value)
            self.end_headers()
            try:
                self.wfile.write(json.dumps(state["body"]).encode())
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1", state
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def wait_until(predicate, timeout=3):
    app = QApplication.instance() or QApplication([])
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate(), "Local HTTP/Qt event loop did not finish"


def test_payload_contains_only_two_unmarked_crops_and_explicit_gaze_coordinates(snapshot):
    payload = build_payload(
        ApiConfig("https://example.test/v1", "vision-test", "SECRET"), snapshot, "这个是什么？"
    )
    content = payload["messages"][1]["content"]
    assert "(280, 180)" in content[0]["text"]
    assert "(80, 60)" in content[0]["text"]
    images = [part["image_url"]["url"] for part in content if part["type"] == "image_url"]
    assert len(images) == 2
    decoded = [QImage.fromData(base64.b64decode(value.split(",", 1)[1])) for value in images]
    assert [(image.width(), image.height()) for image in decoded] == [(560, 360), (160, 120)]
    assert decoded[0].pixelColor(280, 180) == QColor(
        "red"
    )  # Preview crosshair must not be uploaded.
    assert "SECRET" not in json.dumps(payload)


def test_real_http_request_and_response_use_custom_endpoint_and_model(service, snapshot):
    app = QApplication.instance() or QApplication([])
    url, state = service
    client = VisionClient()
    answers, errors = [], []
    client.completed.connect(answers.append)
    client.failed.connect(lambda message, code: errors.append((message, code)))
    client.send(ApiConfig(url, "custom-vision", "LOCAL-SECRET"), snapshot, "读出对象")
    wait_until(lambda: answers or errors)
    assert not errors
    assert answers == ["HTTP 测试响应，非真实 AI"]
    path, payload, auth = state["received"][0]
    assert path == "/v1/chat/completions"
    assert payload["model"] == "custom-vision"
    assert auth == "Bearer LOCAL-SECRET"
    assert not client.busy
    app.processEvents()


def test_http_errors_never_echo_provider_body_or_key(service, snapshot):
    app = QApplication.instance() or QApplication([])
    url, state = service
    state.update(status=401, body={"error": "SECRET-KEY private screenshot text"})
    client = VisionClient()
    failures = []
    client.failed.connect(lambda message, code: failures.append((message, code)))
    client.send(ApiConfig(url, "vision-test", "SECRET-KEY"), snapshot, "private question")
    wait_until(lambda: failures)
    assert failures[0][1] == "http_401"
    assert "SECRET" not in str(failures) and "screenshot" not in str(failures)
    app.processEvents()


@pytest.mark.parametrize("cancel", [False, True])
def test_requests_can_timeout_or_be_cancelled_without_late_answers(service, snapshot, cancel):
    app = QApplication.instance() or QApplication([])
    url, state = service
    state["delay"] = 0.4
    client = VisionClient()
    failures, answers = [], []
    client.failed.connect(lambda message, code: failures.append((message, code)))
    client.completed.connect(answers.append)
    client.send(
        ApiConfig(url, "vision-test", "", timeout_ms=80 if not cancel else 1000), snapshot, "test"
    )
    if cancel:
        client.cancel()
    wait_until(lambda: failures)
    assert failures[0][1] == ("cancelled" if cancel else "timeout")
    assert not answers and not client.busy
    app.processEvents()


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.test/v1",
        "https://user:secret@example.test/v1",
        "https://example.test/v1?key=secret",
    ],
)
def test_unsafe_or_secret_bearing_endpoint_is_rejected_before_network(url):
    with pytest.raises(ValueError):
        _ = ApiConfig(url, "vision-test", "SECRET").endpoint


def test_redirect_does_not_forward_images_or_credentials(service, snapshot):
    app = QApplication.instance() or QApplication([])
    url, state = service
    state.update(status=302, headers={"Location": url + "/forward"})
    client = VisionClient()
    failures = []
    client.failed.connect(lambda message, code: failures.append((message, code)))
    client.send(ApiConfig(url, "vision-test", "SECRET"), snapshot, "test")
    wait_until(lambda: failures)
    assert failures[0][1] == "http_302"
    assert len(state["received"]) == 1
    app.processEvents()


@pytest.mark.parametrize(
    "body,code",
    [
        ({"choices": []}, "invalid_response"),
        ({"data": "x" * (2 * 1024 * 1024)}, "response_too_large"),
    ],
)
def test_invalid_and_oversized_responses_are_bounded_failures(service, snapshot, body, code):
    app = QApplication.instance() or QApplication([])
    url, state = service
    state["body"] = body
    client = VisionClient()
    failures = []
    client.failed.connect(lambda message, result: failures.append((message, result)))
    client.send(ApiConfig(url, "vision-test"), snapshot, "test")
    wait_until(lambda: failures)
    assert failures[0][1] == code
    assert not client.busy
    app.processEvents()
