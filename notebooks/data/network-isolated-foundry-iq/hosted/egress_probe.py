"""Harmless egress probe for the hosted runtime and the outside positive control.

Never pass tokens, document text, user questions or arbitrary URLs. Supply only a
separately approved, task-owned HTTPS canary origin and a random UUID nonce.
"""
import json
import os
import uuid
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def probe(origin: str, nonce: str) -> dict:
    u = urlsplit(origin)
    if u.scheme != "https" or not u.hostname or u.path not in ("", "/") or u.query or u.fragment or u.username or u.password:
        raise ValueError("Expected an approved HTTPS canary origin without path, credentials or query")
    nonce = str(uuid.UUID(nonce))
    request = Request(origin.rstrip("/") + "/canary/" + nonce, method="GET")
    try:
        with urlopen(request, timeout=10) as response:
            return {"nonce": nonce, "status_code": response.status, "classification": "UNREVIEWED"}
    except HTTPError as error:
        return {"nonce": nonce, "status_code": error.code, "classification": "INCONCLUSIVE"}
    except (URLError, TimeoutError):
        return {"nonce": nonce, "status_code": None, "classification": "INCONCLUSIVE"}


if __name__ == "__main__":
    if os.environ.get("LAB_EGRESS_PROBE_APPROVAL") != "approved-task-owned-canary":
        raise PermissionError("Separate task-owned canary approval required")
    print(json.dumps(probe(os.environ["LAB_CANARY_ORIGIN"], os.environ["LAB_CANARY_NONCE"])))
