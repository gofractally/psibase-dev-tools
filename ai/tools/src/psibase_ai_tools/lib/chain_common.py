"""Shared helpers for psinode chain MCP tools."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse, urljoin


DEFAULT_API_HTTP_HOST = "psibase.localhost"


def default_api_url(*, http_host: str, port: int) -> str:
    host = (http_host or DEFAULT_API_HTTP_HOST).strip() or DEFAULT_API_HTTP_HOST
    base = f"http://{host}:{int(port)}/"
    return base if base.endswith("/") else base + "/"


def admin_status_url(api_base_url: str) -> str:
    base = api_base_url.rstrip("/") + "/"
    return urljoin(base, "native/admin/status")


def admin_status_probe_request(api_base_url: str) -> urllib.request.Request:
    """GET /native/admin/status on loopback with Host=x-admin.<roothost>:port.

    Why this shape:
      * Connect to 127.0.0.1 so TCP does not depend on DNS for names like
        ``psibase.localhost``.
      * psinode dispatches by Host subdomain. ``/native/...`` on the bare root
        host hits XHttp which emits 302/404 (see ``XHttp.cpp``); the integration
        test client uses ``service='x-admin'`` which prepends ``x-admin.`` to
        the host (see ``Node._make_url`` in ``programs/psinode/tests/psinode.py``).
        Only then does XHttp bail and the C++ native handler answer the status.
    """
    raw = api_base_url.strip()
    if "://" not in raw:
        raw = "http://" + raw
    p = urlparse(raw)
    port = p.port
    if port is None:
        port = 443 if (p.scheme or "http") == "https" else 80
    scheme = p.scheme or "http"
    loop_base = f"{scheme}://127.0.0.1:{port}/"
    url = admin_status_url(loop_base)
    host = (p.hostname or DEFAULT_API_HTTP_HOST).strip() or DEFAULT_API_HTTP_HOST
    if not host.startswith("x-admin."):
        host = "x-admin." + host
    netloc = f"{host}:{port}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Host", netloc)
    return req


def _admin_status_ready(body: str) -> tuple[bool, str | None]:
    """Match programs/psinode/tests/psinode.py Node._is_ready (HTTP 200 already assumed)."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        return False, f"invalid JSON from /native/admin/status: {exc}"
    # Upstream checks: 'startup' not in result.json()
    if "startup" in data:
        return False, None
    return True, None


def wait_for_admin_status(
    api_base_url: str,
    *,
    total_timeout_sec: float = 60.0,
    request_timeout_sec: float = 2.0,
    poll_interval_sec: float = 0.25,
) -> tuple[bool, str | None, int | None]:
    """Poll GET .../native/admin/status until HTTP 200 and node past startup, or timeout.

    /native/admin/status returns 200 with a JSON array while the server is still
    starting (e.g. ``[\"startup\"]``). Treat readiness like psinode's own tests:
    HTTP 200 and ``\"startup\"`` not in the decoded JSON.

    Returns (ok, response_body_or_error_message, http_status_or_none).
    """
    deadline = time.monotonic() + total_timeout_sec
    last_err: str | None = None
    last_status: int | None = None

    while time.monotonic() < deadline:
        try:
            req = admin_status_probe_request(api_base_url)
            with urllib.request.urlopen(req, timeout=request_timeout_sec) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                last_status = resp.status
                if resp.status == 200:
                    ready, parse_err = _admin_status_ready(body)
                    if ready:
                        return True, body, 200
                    last_err = parse_err or "status still reports startup"
                else:
                    last_err = f"HTTP {resp.status}"
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            last_err = f"HTTP {exc.code}: {exc.reason}"
        except Exception as exc:  # noqa: BLE001 — surface any probe failure
            last_err = str(exc) or type(exc).__name__

        time.sleep(poll_interval_sec)

    return False, last_err, last_status


def read_log_tail(path: Path, max_chars: int = 12000) -> str:
    if not path.is_file():
        return ""
    raw = path.read_text(encoding="utf-8", errors="replace")
    if len(raw) <= max_chars:
        return raw
    return raw[-max_chars:]
