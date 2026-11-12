"""scripts/wasm/app_dev_server.py answers only the page it serves."""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def server(tmp_path, monkeypatch):
    from pyaermod import browser

    monkeypatch.setattr(browser, "WORK_DIR", None)
    spec = importlib.util.spec_from_file_location(
        "app_dev_server", REPO / "scripts" / "wasm" / "app_dev_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    srv = module.serve(0, work_dir=tmp_path / "work")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def post(server, headers, body=b'{"op": "list_files"}'):
    port = server.server_port
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/call", data=body,
                                     method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, None


def test_the_page_itself_is_answered(server):
    port = server.server_port
    status, reply = post(server, {"Content-Type": "application/json",
                                  "Origin": f"http://127.0.0.1:{port}"})
    assert status == 200 and reply["ok"]


@pytest.mark.parametrize("headers", [
    {"Content-Type": "text/plain"},                                    # a "simple" request
    {"Content-Type": "application/json", "Host": "attacker.example"},  # DNS rebinding
    {"Content-Type": "application/json", "Origin": "https://evil.example"},
])
def test_other_pages_are_refused(server, headers):
    status, _ = post(server, headers)
    assert status == 403
