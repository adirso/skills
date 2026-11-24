"""Model downloads resume after a dropped connection and are checksum-verified."""
import hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from wac import models_registry as mr

PAYLOAD = bytes(range(256)) * 4096  # 1 MiB


class FlakyHandler(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        rng = self.headers.get("Range")
        start = int(rng.split("=")[1].rstrip("-")) if rng else 0
        FlakyHandler.calls.append(start)
        body = PAYLOAD[start:]
        self.send_response(206 if rng else 200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if len(FlakyHandler.calls) == 1:  # first attempt: send half, then drop the connection
            self.wfile.write(body[: len(body) // 2])
            self.wfile.flush()
            self.connection.close()
            return
        self.wfile.write(body)


@pytest.fixture()
def server():
    FlakyHandler.calls = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FlakyHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/model.bin"
    srv.shutdown()


def _register(monkeypatch, url, sha):
    spec = mr.ModelSpec("testmodel", "t", "t", "testmodel.bin", url, sha, len(PAYLOAD), "MIT", "", "")
    monkeypatch.setitem(mr.MODELS, "testmodel", spec)
    monkeypatch.setattr(mr.time, "sleep", lambda s: None)


def test_resumes_after_dropped_connection(data_dir, server, monkeypatch):
    _register(monkeypatch, server, hashlib.sha256(PAYLOAD).hexdigest())
    dm = mr.DownloadManager()
    dm.progress["testmodel"] = {"state": "downloading"}
    dm._download("testmodel")
    assert dm.progress["testmodel"]["state"] == "done"
    assert mr.model_path("testmodel").read_bytes() == PAYLOAD
    assert len(FlakyHandler.calls) == 2 and FlakyHandler.calls[1] > 0  # second request resumed via Range


def test_checksum_mismatch_rejected(data_dir, server, monkeypatch):
    _register(monkeypatch, server, "0" * 64)
    dm = mr.DownloadManager()
    dm._download("testmodel")
    assert dm.progress["testmodel"]["state"] == "error"
    assert not mr.model_path("testmodel").exists()
