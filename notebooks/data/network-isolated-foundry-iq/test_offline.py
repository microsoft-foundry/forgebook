"""Synthetic offline regressions. These tests do not demonstrate Azure isolation."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.message import Message
from io import BytesIO
import json
from pathlib import Path
from socket import gaierror
from ssl import SSLError
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import HTTPSHandler, build_opener
from urllib.response import addinfourl

from definitions import API, SAMPLE_FILES, digest, source_definition, kb_definition, prompt_definition, toolbox_definition
from lab import Client, approval, create_absent, ServiceFailure, wait_for_sync
from verify import Status, Result, REQUIRED, paired, ingestion, grounding, egress, public_bundle, exit_code

C = dict(source="grid-source", knowledge_base="grid-kb", storage_resource_id="fixture-storage",
         container="grid-policies", folder="fixtures", openai_endpoint="https://model.example.invalid",
         embedding_model="text-embedding-3-large", embedding_deployment="embeddings",
         chat_model="gpt-4.1-mini", chat_deployment="chat", search_endpoint="https://search.example.invalid",
         prompt_connection="prompt-mi", hosted_connection="hosted-identity", prompt_agent="grid-prompt")


def pair():
    request = dict(method="POST", path="/knowledgebases/grid-kb/retrieve", body_digest="fixture-body",
                   api_version=API, resource_alias="search", audience="search",
                   principal_alias="same-reader", permissions_digest="same-permissions")
    common = dict(request=request, service="search", identity_evidence="fixture-only",
                  route_evidence="fixture-only", server_request_id="fixture-id")
    return (dict(common, context="inside", status_code=200, content_validated=True),
            dict(deepcopy(common), context="outside", status_code=403, service="search",
                 denial_signature="publicNetworkAccess: Disabled", network_diagnostic_evidence="fixture-only",
                 network_diagnostic_correlated=True))


class ClassifierTests(unittest.TestCase):
    def test_correlated_search_denial(self):
        self.assertEqual(paired(*pair()).status, Status.PASS)

    def test_false_isolation_regressions(self):
        for code in (401, 403, 404, 405, 429, 500, 502, 503, 504, None):
            for error in (None, "DNS", "TLS", "timeout", "exception"):
                with self.subTest(code=code, error=error):
                    inside, outside = pair()
                    outside.update(status_code=code, error=error, denial_signature="RBAC or unknown")
                    self.assertNotEqual(paired(inside, outside).status, Status.PASS)

    def test_identity_and_request_equivalence(self):
        for key in pair()[0]["request"]:
            with self.subTest(key=key):
                inside, outside = pair()
                outside["request"][key] = "different"
                self.assertEqual(paired(inside, outside).status, Status.BLOCKED)

    def test_get_is_not_post_retrieve(self):
        inside, outside = pair()
        outside["request"]["method"] = "GET"
        self.assertEqual(paired(inside, outside).status, Status.BLOCKED)

    def test_matched_get_still_cannot_prove_retrieve(self):
        inside, outside = pair()
        inside["request"]["method"] = outside["request"]["method"] = "GET"
        self.assertEqual(paired(inside, outside).status, Status.BLOCKED)

    def test_retrieve_query_does_not_bypass_post_or_api_contract(self):
        for method, path, expected in (
            ("GET", f"/knowledgebases/grid-kb/retrieve?api-version={API}", Status.BLOCKED),
            ("POST", f"/knowledgebases/grid-kb/retrieve?api-version={API}", Status.PASS),
            ("POST", "/knowledgebases/grid-kb/retrieve?api-version=wrong", Status.BLOCKED),
            ("POST", f"/knowledgebases/grid-kb/retrieve?api-version={API}&extra=1", Status.BLOCKED),
            ("POST", "https://search.example.invalid/knowledgebases/grid-kb/retrieve", Status.BLOCKED),
        ):
            with self.subTest(method=method, path=path):
                inside, outside = pair()
                for receipt in (inside, outside):
                    receipt["request"].update(method=method, path=path)
                self.assertEqual(paired(inside, outside).status, expected)

    def test_both_service_provenances_must_be_search(self):
        for position in (0, 1):
            for service in (None, "foundry", "blob"):
                with self.subTest(position=position, service=service):
                    receipts = pair()
                    receipts[position]["service"] = service
                    self.assertEqual(paired(*receipts).status, Status.BLOCKED)

    def test_control_requires_matching_search_endpoint(self):
        inside, outside = pair()
        self.assertEqual(paired(inside, outside, control="paired-kb-mcp").status, Status.BLOCKED)
        for receipt in (inside, outside):
            receipt["request"]["path"] = f"/knowledgebases/grid-kb/mcp?api-version={API}"
        self.assertEqual(paired(inside, outside, control="paired-kb-mcp").status, Status.PASS)
        self.assertEqual(paired(inside, outside, control="paired-kb-retrieve").status, Status.BLOCKED)

    def test_search_pairs_cannot_pass_unimplemented_controls(self):
        for control in ("paired-hosted-ingress", "paired-prompt-ingress", "dependent-data-planes"):
            with self.subTest(control=control):
                inside, outside = pair()
                self.assertEqual(paired(inside, outside, control=control).status, Status.BLOCKED)
                with tempfile.TemporaryDirectory() as folder:
                    source, output = Path(folder)/"receipts.json", Path(folder)/"evidence.json"
                    source.write_text(json.dumps({"pairs": {control: {"inside": inside, "outside": outside}}}))
                    run = subprocess.run([sys.executable, str(Path(__file__).with_name("verify.py")),
                                          "--input", str(source), "--output", str(output)], capture_output=True)
                    self.assertEqual(run.returncode, 2)
                    results = {item["control"]: item["status"] for item in json.loads(output.read_text())["controls"]}
                    self.assertEqual(results[control], "BLOCKED")

    def test_original_eight_error_fixtures_no_longer_pass(self):
        baseline = json.loads(Path(__file__).with_name("original-classifier-reproduction.json").read_text())
        self.assertEqual(baseline["falsePositiveCount"], 5)
        for case in baseline["cases"]:
            inside, outside = pair()
            outside.update(status_code=case["status"], denial_signature=case["case"])
            self.assertNotEqual(paired(inside, outside).status, Status.PASS, case["case"])

    def test_positive_control_and_provenance_required(self):
        for key in ("content_validated", "identity_evidence", "route_evidence", "server_request_id"):
            inside, outside = pair()
            inside.pop(key)
            self.assertNotEqual(paired(inside, outside).status, Status.PASS)

    def test_public_success_is_failure(self):
        inside, outside = pair()
        outside["status_code"] = 200
        self.assertEqual(paired(inside, outside).status, Status.FAIL)

    def test_403_requires_specific_service_and_corroboration(self):
        for key in ("service", "denial_signature", "network_diagnostic_evidence", "network_diagnostic_correlated"):
            inside, outside = pair()
            outside.pop(key)
            self.assertNotEqual(paired(inside, outside).status, Status.PASS)

    def test_ingestion_stale_pending_and_failed(self):
        now = datetime.now(timezone.utc)
        observed = dict(source=source_definition(C), indexer={"executionEnvironment": "private"},
                        sku="standard2", source_content_evidence="fixture", embedding_evidence="fixture",
                        shared_links=[dict(groupId=g, target=g, status="Approved", provisioningState="Succeeded") for g in ("blob", "openai_account")],
                        expected_targets={g: g for g in ("blob", "openai_account")},
                        status={"lastSynchronizationState": {"endTime": now.isoformat(), "status": "success", "itemsUpdatesFailed": 0}})
        self.assertEqual(ingestion(observed, (now-timedelta(minutes=1)).isoformat()).status, Status.PASS)
        self.assertEqual(ingestion(observed, (now+timedelta(minutes=1)).isoformat()).status, Status.BLOCKED)
        for field, value in (("endTime", None), ("itemsUpdatesFailed", 1), ("status", "partialSuccess")):
            changed = deepcopy(observed)
            changed["status"]["lastSynchronizationState"][field] = value
            self.assertNotEqual(ingestion(changed, now.isoformat()).status, Status.PASS)
        observed["indexer"]["executionEnvironment"] = "public"
        self.assertEqual(ingestion(observed, now.isoformat()).status, Status.FAIL)

    def test_retrieval_errors_are_not_abstention(self):
        self.assertEqual(grounding({"tool_error": "failure", "answer": "I don't know."}, unsupported=True).status, Status.FAIL)
        self.assertEqual(grounding({"answer": "I don't know."}, unsupported=True).status, Status.BLOCKED)

    def test_grounding_needs_source_payload_and_review(self):
        r = dict(tool_name="knowledge_base_retrieve", tool_success=True, invocation_id="fixture", tool_call_id="fixture",
                 agent_version="1", runtime_principal_evidence="fixture", tool_payload_evidence="fixture", correlated=True,
                 answer="I don't know.", citations=[])
        self.assertEqual(grounding(r, unsupported=True).status, Status.PASS)
        r.update(answer="24 hours [1]", citations=[{"source_file": "policy.md"}], claims=[{"source_file": "policy.md"}])
        self.assertEqual(grounding(r, unsupported=False).status, Status.BLOCKED)
        r["citations"][0].update(source_version="fixture", source_text="revoke within 24 hours")
        r["claims"][0].update(supporting_quote="revoke within 24 hours", faithfulness_review="supported", review_evidence="fixture-review")
        self.assertEqual(grounding(r, unsupported=False).status, Status.PASS)

    def test_jumpbox_and_timeout_do_not_prove_runtime_egress(self):
        for context in ("jumpbox", "hosted-runtime", "prompt-tool-service"):
            self.assertNotEqual(egress({"context": context, "error": "timeout"}, "hosted-runtime").status, Status.PASS)

    def test_missing_controls_return_nonzero(self):
        self.assertEqual(exit_code({}), 2)
        self.assertEqual(exit_code({k: Result(Status.PASS, "synthetic") for k in REQUIRED}), 0)

    def test_public_projection_cannot_leak_raw_values(self):
        bundle = public_bundle({"configuration": Result(Status.BLOCKED, "https://tenant.invalid/?sig=SECRET")})
        self.assertNotIn("SECRET", json.dumps(bundle))
        self.assertFalse(bundle["publish_ready"])
        self.assertFalse(bundle["live_run"])
        self.assertEqual(set(bundle), {"schema_version", "run_alias", "live_run", "observed_at", "versions", "controls", "publish_ready"})

    def test_cli_missing_evidence_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"bundle.json"
            run = subprocess.run([sys.executable, str(Path(__file__).with_name("verify.py")), "--output", str(path)], capture_output=True)
            self.assertEqual(run.returncode, 2)
            self.assertTrue(all(x["status"] == "BLOCKED" for x in json.loads(path.read_text())["controls"]))


class DefinitionTests(unittest.TestCase):
    def test_source_directory_prefix_matches_uploaded_files_only(self):
        prefix = source_definition(C)["azureBlobParameters"]["folderPath"]
        self.assertEqual(prefix, f'{C["folder"]}/')
        for name in SAMPLE_FILES:
            self.assertTrue(f'{C["folder"]}/{name}'.startswith(prefix))
        self.assertFalse(f'{C["folder"]}-unrelated/policy.md'.startswith(prefix))

    def test_private_creation_and_shared_kb(self):
        s = source_definition(C)
        self.assertEqual(s["azureBlobParameters"]["ingestionParameters"]["networkAccessMode"], "private")
        self.assertNotIn("chatCompletionModel", s["azureBlobParameters"]["ingestionParameters"])
        self.assertEqual(kb_definition(C)["knowledgeSources"], [{"name": C["source"]}])
        prompt = prompt_definition(C)["definition"]["tools"][0]
        hosted = toolbox_definition(C)["tools"][0]
        self.assertEqual(prompt["server_url"], hosted["server_url"])
        self.assertEqual(prompt["allowed_tools"], ["knowledge_base_retrieve"])
        self.assertNotEqual(prompt["project_connection_id"], hosted["project_connection_id"])

    def test_no_approval_no_operations(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"approval.json"
            path.write_text('{"approved":false}')
            with self.assertRaises(PermissionError): approval(path, {"operation": "source"})

    def test_changed_plan_invalidates_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"approval.json"
            path.write_text(json.dumps(dict(approved=True, plan_digest=digest({"operation": "source"}), new_disposable_lab=True,
                                          cost_approval_reference="fixture", support_review_reference="fixture",
                                          expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())))
            with self.assertRaises(PermissionError): approval(path, {"operation": "upload"})

    def test_existing_source_is_not_mutated(self):
        class Existing:
            def request(self, method, *args, **kwargs):
                if method != "GET": raise AssertionError("Unexpected mutation")
                return {}
        with self.assertRaises(RuntimeError): create_absent(Existing(), "fixture", "scope", {})

    def test_rbac_error_does_not_trigger_creation(self):
        class Denied:
            def request(self, method, *args, **kwargs):
                if method != "GET": raise AssertionError("Unexpected mutation")
                raise ServiceFailure(403, "GET")
        with self.assertRaises(ServiceFailure): create_absent(Denied(), "fixture", "scope", {})

    def test_sync_poll_bound(self):
        class Pending:
            count = 0
            def request(self, *args):
                self.count += 1
                return {}
        client = Pending()
        with self.assertRaises(TimeoutError): wait_for_sync(client, C, attempts=2, delay=0)
        self.assertEqual(client.count, 2)

    def test_authenticated_redirects_do_not_replay_requests(self):
        class FixtureTransport(HTTPSHandler):
            def __init__(self, status):
                super().__init__()
                self.status = status
                self.requests = []

            def https_open(self, request):
                self.requests.append(request)
                headers = Message()
                headers["Location"] = "https://other.example.invalid/redirected"
                status = self.status if len(self.requests) == 1 else 200
                response = addinfourl(BytesIO(b'{"fixture":"redirect"}'), headers, request.full_url, status)
                response.msg = "Fixture response"
                return response

        credential = SimpleNamespace(get_token=lambda scope: SimpleNamespace(token="fixture-token-not-a-secret"))
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as folder:
                transport = FixtureTransport(status)
                with patch("lab.build_opener", side_effect=lambda *handlers: build_opener(*handlers, transport)):
                    client = Client(credential, Path(folder))
                with self.assertRaises(ServiceFailure) as failure:
                    client.request("POST", "https://search.example.invalid/retrieve", "fixture-scope", {"query": "fixture"})
                self.assertEqual(failure.exception.status, status)
                self.assertEqual(len(transport.requests), 1)
                self.assertEqual(transport.requests[0].get_method(), "POST")
                receipts = list(Path(folder).glob("*.json"))
                self.assertEqual(len(receipts), 1)
                content = receipts[0].read_text()
                self.assertEqual(json.loads(content)["status_code"], status)
                self.assertNotIn("fixture-token-not-a-secret", content)

    def test_transport_errors_preserve_one_safe_failure_receipt(self):
        credential = SimpleNamespace(get_token=lambda scope: SimpleNamespace(token="fixture-token-not-a-secret"))
        cases = (
            (URLError(gaierror(-2, "RAW_EXCEPTION_SECRET")), "dns"),
            (TimeoutError("RAW_EXCEPTION_SECRET"), "timeout"),
            (URLError(TimeoutError("RAW_EXCEPTION_SECRET")), "timeout"),
            (URLError(SSLError("RAW_EXCEPTION_SECRET")), "tls"),
            (URLError("RAW_EXCEPTION_SECRET"), "transport"),
        )
        for error, category in cases:
            with self.subTest(category=category), tempfile.TemporaryDirectory() as folder:
                client = Client(credential, Path(folder))
                with patch.object(client.opener, "open", side_effect=error) as request:
                    with self.assertRaises(ServiceFailure) as failure:
                        client.request("POST", "https://search.example.invalid/retrieve",
                                       "fixture-scope", {"query": "fixture"})
                    self.assertIsNone(failure.exception.status)
                    self.assertEqual(request.call_count, 1)
                receipts = list(Path(folder).glob("*.json"))
                self.assertEqual(len(receipts), 1)
                content = receipts[0].read_text()
                receipt = json.loads(content)
                self.assertEqual(receipt["transport_error"]["category"], category)
                self.assertEqual(receipt["method"], "POST")
                self.assertEqual(receipt["url"], "https://search.example.invalid/retrieve")
                self.assertEqual(receipt["request_digest"], digest({"query": "fixture"}))
                self.assertTrue(receipt["at"])
                self.assertIsNone(receipt["status_code"])
                self.assertNotIn("RAW_EXCEPTION_SECRET", content)
                self.assertNotIn("fixture-token-not-a-secret", content)
                self.assertNotIn("Authorization", content)
                inside, outside = pair()
                outside.update(status_code=None, error=receipt["transport_error"]["category"])
                self.assertNotEqual(paired(inside, outside).status, Status.PASS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
