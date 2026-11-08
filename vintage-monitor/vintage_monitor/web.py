"""Minimal HTTP layer on the standard library.

Every outside call goes through `request()`, so tests can swap in a fake
transport with the same signature.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import __version__

# Discord (behind Cloudflare) rejects Python's default "Python-urllib" agent.
USER_AGENT = f"VintageMonitor/{__version__}"
DEFAULT_TIMEOUT = 20


class NetworkError(Exception):
    """The request never got an HTTP response (DNS, refused, timeout...)."""


@dataclass
class Response:
    status: int
    body: bytes = b""
    headers: dict = field(default_factory=dict)  # keys lower-cased

    def json(self):
        return json.loads(self.body.decode("utf-8")) if self.body else None


Transport = Callable[..., Response]


def request(
    method: str,
    url: str,
    headers: Optional[dict] = None,
    body: Optional[bytes] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Response:
    all_headers = {"User-Agent": USER_AGENT}
    all_headers.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=all_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return Response(
                resp.status,
                resp.read(),
                {k.lower(): v for k, v in resp.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        try:
            data = exc.read()
        except Exception:  # pragma: no cover - defensive
            data = b""
        hdrs = {k.lower(): v for k, v in (exc.headers or {}).items()}
        return Response(exc.code, data, hdrs)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise NetworkError(str(reason)) from exc
