from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs


def _load_smoke_routes_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_routes.py"
    spec = importlib.util.spec_from_file_location("smoke_routes", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, status=200, final_url="http://127.0.0.1:5000/", body=""):
        self._status = status
        self._final_url = final_url
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return self._status

    def geturl(self):
        return self._final_url

    def read(self):
        return self._body.encode("utf-8")


def test_check_endpoint_fails_when_path_redirects(monkeypatch):
    smoke_routes = _load_smoke_routes_module()

    def _fake_request(_url, _timeout, _request, opener=None):
        return _FakeResponse(status=200, final_url="http://127.0.0.1:5000/auth/login")

    monkeypatch.setattr(smoke_routes, "_request_url", _fake_request)

    result = smoke_routes.check_endpoint("http://127.0.0.1:5000", "/provider/dashboard", timeout=1.0)

    assert result["status"] == 200
    assert result["redirected"] is True
    assert result["final_path"] == "/auth/login"
    assert result["ok"] is False


def test_check_endpoint_allows_redirect_when_explicit(monkeypatch):
    smoke_routes = _load_smoke_routes_module()

    def _fake_request(_url, _timeout, _request, opener=None):
        return _FakeResponse(status=200, final_url="http://127.0.0.1:5000/auth/login")

    monkeypatch.setattr(smoke_routes, "_request_url", _fake_request)

    result = smoke_routes.check_endpoint(
        "http://127.0.0.1:5000",
        "/provider/dashboard",
        timeout=1.0,
        allow_redirect=True,
    )

    assert result["redirected"] is True
    assert result["ok"] is True


def test_login_demo_session_returns_error_when_csrf_missing():
    smoke_routes = _load_smoke_routes_module()

    class _Opener:
        def open(self, request, timeout=0):
            return _FakeResponse(status=200, final_url=request.full_url, body="<html>No token</html>")

    def _fake_build_opener(_processor):
        return _Opener()

    smoke_routes.build_opener = _fake_build_opener

    opener, error = smoke_routes.login_demo_session("http://127.0.0.1:5000", timeout=1.0, target="provider")

    assert opener is None
    assert error == "failed to fetch CSRF token"


def test_login_demo_session_posts_target_and_csrf():
    smoke_routes = _load_smoke_routes_module()

    class _Opener:
        def __init__(self):
            self.post_payload = None

        def open(self, request, timeout=0):
            if request.method == "GET":
                html = '<input type="hidden" name="csrf_token" value="token-123">'
                return _FakeResponse(status=200, final_url=request.full_url, body=html)

            self.post_payload = request.data.decode("utf-8")
            return _FakeResponse(status=200, final_url="http://127.0.0.1:5000/provider/dashboard")

    opener_instance = _Opener()

    def _fake_build_opener(_processor):
        return opener_instance

    smoke_routes.build_opener = _fake_build_opener

    opener, error = smoke_routes.login_demo_session("http://127.0.0.1:5000", timeout=1.0, target="provider")

    assert error is None
    assert opener is opener_instance
    parsed = parse_qs(opener_instance.post_payload)
    assert parsed["target"] == ["provider"]
    assert parsed["csrf_token"] == ["token-123"]


def test_main_returns_nonzero_when_auth_demo_bootstrap_fails(monkeypatch, capsys):
    smoke_routes = _load_smoke_routes_module()

    def _fake_check_endpoint(base_url, path, timeout, allow_redirect=False, opener=None):
        return {
            "path": path,
            "status": 200,
            "ok": True,
            "latency_ms": 1,
            "redirected": False,
            "final_path": path,
        }

    def _fake_login_demo_session(base_url, timeout, target):
        return None, "boom"

    monkeypatch.setattr(smoke_routes, "check_endpoint", _fake_check_endpoint)
    monkeypatch.setattr(smoke_routes, "login_demo_session", _fake_login_demo_session)
    monkeypatch.setattr(
        smoke_routes.sys,
        "argv",
        [
            "smoke_routes.py",
            "--base-url",
            "http://127.0.0.1:5000",
            "--auth-demo-targets",
            "provider",
            "--json",
        ],
    )

    exit_code = smoke_routes.main()
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert exit_code == 1
    assert payload["failed"] == 1
    assert any(
        result.get("mode") == "auth-demo" and "Auth bootstrap failed" in result.get("error", "")
        for result in payload["results"]
    )