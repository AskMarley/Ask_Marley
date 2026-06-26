from __future__ import annotations

import argparse
from http.cookiejar import CookieJar
import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

DEFAULT_PATHS = [
    "/",
    "/health",
    "/consumer/chat",
]

AUTH_TARGET_DASHBOARD_PATHS = {
    "provider": "/provider/dashboard",
    "admin": "/admin/dashboard",
}


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    if path == "/":
        return "/"
    return path.rstrip("/")


def _request_url(url: str, timeout: float, request: Request, opener=None):
    if opener is not None:
        return opener.open(request, timeout=timeout)
    return urlopen(request, timeout=timeout)


def check_endpoint(base_url: str, path: str, timeout: float, allow_redirect: bool = False, opener=None) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    request = Request(url, method="GET")
    started = datetime.now(timezone.utc)
    try:
        with _request_url(url, timeout, request, opener=opener) as response:
            latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            status = int(response.getcode() or 0)
            final_url = response.geturl()
            final_path = urlsplit(final_url).path
            redirected = _normalize_path(final_path) != _normalize_path(path)
            ok = 200 <= status < 400 and (allow_redirect or not redirected)
            return {
                "path": path,
                "status": status,
                "ok": ok,
                "latency_ms": latency_ms,
                "redirected": redirected,
                "final_path": final_path,
            }
    except HTTPError as exc:
        latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        status = int(exc.code or 0)
        return {
            "path": path,
            "status": status,
            "ok": False,
            "latency_ms": latency_ms,
            "error": str(exc),
        }
    except URLError as exc:
        latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {
            "path": path,
            "status": 0,
            "ok": False,
            "latency_ms": latency_ms,
            "error": str(exc.reason),
        }


def login_demo_session(base_url: str, timeout: float, target: str):
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    login_page_url = f"{base_url.rstrip('/')}/auth/login"
    login_page_request = Request(login_page_url, method="GET")

    csrf_token = None
    try:
        with opener.open(login_page_request, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="ignore")
            match = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', html)
            if match:
                csrf_token = match.group(1)
    except Exception as exc:  # pragma: no cover - broad to keep smoke script resilient
        return None, f"failed to fetch CSRF token: {exc}"

    if not csrf_token:
        return None, "failed to fetch CSRF token"

    login_path = "/auth/demo-login"
    url = f"{base_url.rstrip('/')}{login_path}"
    payload = urlencode({"target": target, "csrf_token": csrf_token}).encode("utf-8")
    request = Request(url, data=payload, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")

    expected_path = AUTH_TARGET_DASHBOARD_PATHS[target]
    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(response.getcode() or 0)
            final_path = urlsplit(response.geturl()).path
            if status >= 400:
                return None, f"demo login for {target} returned {status}"
            if _normalize_path(final_path) != _normalize_path(expected_path):
                return None, f"demo login for {target} redirected to {final_path} instead of {expected_path}"
            return opener, None
    except Exception as exc:  # pragma: no cover - broad to keep smoke script resilient
        return None, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AskMarley smoke route checks.")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Base URL of the app")
    parser.add_argument("--timeout", type=float, default=4.0, help="Timeout per request in seconds")
    parser.add_argument(
        "--paths",
        nargs="*",
        default=DEFAULT_PATHS,
        help="Route paths to check",
    )
    parser.add_argument(
        "--allow-redirect-paths",
        nargs="*",
        default=[],
        help="Paths allowed to redirect without failing the check",
    )
    parser.add_argument(
        "--auth-demo-targets",
        nargs="*",
        choices=sorted(AUTH_TARGET_DASHBOARD_PATHS.keys()),
        default=[],
        help="Run additional authenticated dashboard checks using demo login",
    )
    parser.add_argument("--json", action="store_true", help="Print output as JSON")
    args = parser.parse_args()

    allow_redirect_set = {value.strip() for value in args.allow_redirect_paths if value.strip()}
    results = [
        check_endpoint(
            args.base_url,
            path,
            args.timeout,
            allow_redirect=path in allow_redirect_set,
        )
        for path in args.paths
    ]

    for target in args.auth_demo_targets:
        dashboard_path = AUTH_TARGET_DASHBOARD_PATHS[target]
        opener, login_error = login_demo_session(args.base_url, args.timeout, target)
        if login_error:
            results.append(
                {
                    "path": dashboard_path,
                    "status": 0,
                    "ok": False,
                    "latency_ms": 0,
                    "error": f"Auth bootstrap failed: {login_error}",
                    "auth_target": target,
                    "mode": "auth-demo",
                }
            )
            continue

        auth_result = check_endpoint(
            args.base_url,
            dashboard_path,
            args.timeout,
            allow_redirect=False,
            opener=opener,
        )
        auth_result["auth_target"] = target
        auth_result["mode"] = "auth-demo"
        results.append(auth_result)

    failures = [result for result in results if not result["ok"]]

    if args.json:
        print(json.dumps({"results": results, "failed": len(failures)}, indent=2))
    else:
        print(f"Smoke check target: {args.base_url}")
        for result in results:
            label = "PASS" if result["ok"] else "FAIL"
            extra = f" ({result.get('error')})" if result.get("error") else ""
            if result.get("redirected") and not result.get("error"):
                extra = f" (redirected to {result.get('final_path')})"
            if result.get("mode") == "auth-demo":
                print(
                    f"[{label}] {result['path']} [{result['mode']}:{result.get('auth_target')}] -> "
                    f"{result['status']} in {result['latency_ms']}ms{extra}"
                )
            else:
                print(f"[{label}] {result['path']} -> {result['status']} in {result['latency_ms']}ms{extra}")
        print(f"Summary: {len(results) - len(failures)}/{len(results)} routes healthy")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
