#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


def request_json(method: str, url: str, payload: dict[str, Any] | None = None, token: str = "") -> tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body) if body else {}
        except ValueError:
            return exc.code, body


def main() -> int:
    parser = argparse.ArgumentParser(description="Velez bot smoke/readiness check")
    parser.add_argument("--base-url", default=os.getenv("VELEZ_BASE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--token", default=os.getenv("VELEZ_OPS_TOKEN", ""))
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    checks: list[tuple[str, bool, str]] = []

    status, body = request_json("GET", f"{base}/health")
    checks.append(("/health", status == 200 and bool(body.get("ok")), f"status={status}"))

    status, body = request_json("GET", f"{base}/api/ops/uptime")
    checks.append(("/api/ops/uptime", status == 200 and body.get("status") in {"ok", "degraded"}, f"status={status} state={body.get('status')}"))

    status, body = request_json("GET", f"{base}/api/ops/whoami", token=args.token)
    checks.append(("/api/ops/whoami", status == 200, f"status={status} role={body.get('role') if isinstance(body, dict) else 'unknown'}"))

    if args.token:
        for path in ["/api/safety/state", "/api/burn-in/status", "/api/ops/readiness", "/api/ops/audit"]:
            status, body = request_json("GET", f"{base}{path}", token=args.token)
            checks.append((path, status == 200, f"status={status}"))

    failures = 0
    print(f"[velez-smoke] base={base}")
    for path, ok, detail in checks:
        failures += 0 if ok else 1
        print(f" - {path:<24} {'PASS' if ok else 'FAIL'} {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
