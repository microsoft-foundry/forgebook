import ast
import base64
import contextlib
import io
import json
import socket
import ssl
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SOURCE_REF = "c06549384f52c0dd8e11399b41d1d4b271c82c7a"
SOURCE_PATH = "notebooks/network-isolated-foundry-iq.ipynb"


def original_classifier():
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/microsoft-foundry/forgebook/contents/{SOURCE_PATH}?ref={SOURCE_REF}",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    notebook = json.loads(base64.b64decode(json.loads(result.stdout)["content"]))
    source = "".join(notebook["cells"][33]["source"])
    definition = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "call"
    )
    namespace = {
        "socket": socket,
        "urllib": urllib,
        "cred": SimpleNamespace(
            get_token=lambda scope: SimpleNamespace(token="offline-dummy-not-a-token")
        ),
    }
    exec(
        compile(ast.Module(body=[definition], type_ignores=[]), SOURCE_PATH, "exec"),
        namespace,
    )
    return namespace["call"]


def main():
    classifier = original_classifier()
    url = "https://example.invalid/knowledgebases/offline-test/retrieve?api-version=2025-11-01-preview"
    cases = [
        ("expired-or-invalid-credential", 401, "Unauthorized"),
        ("missing-RBAC-permission", 403, "Caller does not have permission"),
        ("unknown-resource", 404, "Not found"),
        ("wrong-http-method", 405, "Method not allowed"),
        ("service-failure", 500, "Internal error"),
        ("DNS-failure", None, urllib.error.URLError(socket.gaierror("offline DNS failure"))),
        ("TLS-failure", None, ssl.SSLError("offline certificate failure")),
        ("request-timeout", None, TimeoutError("offline request timeout")),
    ]
    observations = []
    for name, status, detail in cases:
        failure = detail
        if status is not None:
            failure = urllib.error.HTTPError(
                url, status, detail, {}, io.BytesIO(detail.encode("utf-8"))
            )
        requests = []

        def fail(request, timeout):
            requests.append({"method": request.get_method(), "bodyPresent": request.data is not None})
            raise failure

        with (
            patch.object(socket, "gethostbyname", return_value="192.0.2.1"),
            patch.object(urllib.request, "urlopen", side_effect=fail),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = classifier(name, url)
        observations.append(
            {
                "case": name,
                "status": status,
                "expectedIsolationProof": False,
                "originalClassifiesIsolated": result,
                "falsePositive": result is True,
                "requests": requests,
            }
        )

    report = {
        "scope": "Offline reproduction with mocked DNS, HTTP and credentials; not Azure network evidence",
        "sourceRepository": "microsoft-foundry/forgebook",
        "sourceRef": SOURCE_REF,
        "sourcePath": SOURCE_PATH,
        "cellIndexZeroBased": 33,
        "sourceFetchedFromGitHub": True,
        "azureDataPlaneCallsExecuted": 0,
        "credentialAcquisitionExecuted": False,
        "cases": observations,
        "falsePositiveCount": sum(case["falsePositive"] for case in observations),
        "observedRetrieveMethods": sorted(
            {request["method"] for case in observations for request in case["requests"]}
        ),
    }
    assert report["falsePositiveCount"] == 5, report
    assert report["observedRetrieveMethods"] == ["GET"], report
    destination = Path(__file__).with_name("original-classifier-reproduction.json")
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
