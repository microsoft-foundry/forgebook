"""Offline execution and safety checks for the embedding/Search notebook.

Run ``python scripts/test-microsoft-embedding-1-search.py`` from the repo root
with nbformat and the notebook's SDK dependencies installed. Services are faked.
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import math
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import nbformat
from azure.core import MatchConditions
from azure.core.credentials import AccessToken
from azure.core.exceptions import ResourceModifiedError, ServiceRequestError
from azure.core.pipeline.transport import HttpResponse, HttpTransport
from azure.data.ai import InferenceClient
from azure.data.ai.models import MultimodalDenseEmbedding
from azure.search.documents.indexes import SearchIndexClient


NOTEBOOK = (
    Path(__file__).resolve().parents[1]
    / "notebooks"
    / "microsoft-embedding-1-azure-ai-search.ipynb"
)

# Reject unexpected data in the bounded synthetic-output capture.
ALLOWED_OUTPUT_LINES = [
    re.compile(pattern)
    for pattern in (
        r"Configuration: \d+ dimensions; top \d+ results\.",
        r"(?:Embedding token|Search token|Search index access) OK\.",
        r"First passage: \d+ dimensions; input tokens: (?:\d+|None)\.",
        r"Temporary index: embedding1-cookbook-[a-f0-9]{12}",
        r"Index created with text, policy-code, and vector fields\.",
        r"\d+ uploaded; \d+ searchable\.",
        r"Embedded \d+ questions at \d+ dimensions\.",
        r"Reported input tokens across all embedding requests: \d+\.",
        r"(?:Paraphrase|Policy code) (?:keyword matches \(up to 3\)|vector matches): \[(?:'[A-Z]+-\d{2}'(?:, '[A-Z]+-\d{2}')*)?\]",
        r"Can I get reimbursed for a delayed flight\?",
        r"Does trv-18 cover hotel expenses after a delayed flight\?",
        r"  (?:Keyword|Vector|Hybrid): \[(?:'[A-Z]+-\d{2}'(?:, '[A-Z]+-\d{2}')*)?\]",
        r"  TRV-12: Travel disruption expenses\. When an air trip disruption leaves an employee stranded overnight, the company covers reasonable hotel and meal expenses\. Submit receipts to the travel team within 30 days\.",
        r"  TRV-18: Lost baggage\. Employees whose checked baggage is lost during business travel may claim essential replacement items with receipts\.",
        r"  TRV-24: Changing a booking\. Use the booking portal to change an itinerary when a business meeting moves\. A manager must approve higher fares\.",
        r"Semantic ranking skipped \(opt-in\)\.",
        r"(?:Paraphrase|Policy code) after semantic ranking: \[(?:'[A-Z]+-\d{2}'(?:, '[A-Z]+-\d{2}')*)?\]",
        r"Temporary index deleted\.",
        r"Azure clients closed\.",
    )
]


def unsafe_output_lines(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line and not any(pattern.fullmatch(line) for pattern in ALLOWED_OUTPUT_LINES)
    ]


class FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class OfflineResponse(HttpResponse):
    def __init__(self, request, status, content):
        super().__init__(request, None)
        self.status_code = status
        self.headers = {"content-type": "application/json"}
        self._data = json.dumps(content).encode()

    def body(self):
        return self._data

    def text(self, encoding=None):
        return self._data.decode(encoding or "utf-8")

    def json(self):
        return json.loads(self._data)


class OfflineCredential:
    def __init__(self):
        self.scopes = []

    def get_token(self, *_scopes, **_kwargs):
        self.scopes.extend(_scopes)
        return AccessToken("offline-token", 4_000_000_000)


class OfflineTransport(HttpTransport):
    def __init__(self):
        self.requests = []
        self.reject_delete = False
        self.omit_body_etag = False
        self.header_etag = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def open(self):
        pass

    def close(self):
        pass

    def send(self, request, **_kwargs):
        self.requests.append(request)
        if request.url.startswith("https://embedding.example.test/") and request.method == "POST":
            body = json.loads(request.body)
            return OfflineResponse(
                request,
                200,
                {
                    "model": body["model"],
                    "outputDataKind": "float32",
                    "data": [
                        {
                            "kind": "multimodal_dense",
                            "contentKind": body["inputs"][0]["kind"],
                            "vectorKind": "dense",
                            "index": 0,
                            "embedding": [1.0] + [0.0] * (body["dimensions"] - 1),
                        }
                    ],
                    "usage": {"promptTokens": 5},
                },
            )
        if request.url.startswith("https://search.example.test/"):
            if request.method == "GET":
                return OfflineResponse(request, 200, {"value": []})
            if request.method == "POST":
                index = json.loads(request.body)
                if not self.omit_body_etag:
                    index["@odata.etag"] = '"created"'
                response = OfflineResponse(request, 201, index)
                if self.header_etag:
                    response.headers["ETag"] = self.header_etag
                return response
            if request.method == "DELETE":
                if self.reject_delete:
                    return OfflineResponse(
                        request,
                        412,
                        {"error": {"code": "PreconditionFailed", "message": "ETag mismatch"}},
                    )
                return OfflineResponse(request, 204, {})
        raise AssertionError(f"Unexpected offline request: {request.method} {request.url}")


class FakeCloud:
    def __init__(self):
        self.embedding_calls = []
        self.created = []
        self.deleted = []
        self.documents = []
        self.search_calls = []
        self.fail_creation = False
        self.missing_etag = False
        self.body_etag = '"created"'
        self.fail_deletion = False
        self.fail_inference = False
        self.fail_upload = False
        self.never_visible = False
        self.count_calls = 0
        self.delete_conditions = []
        self.deletion_etags = []
        self.keyword_override = None
        self.vector_override = None
        self.hybrid_override = None
        self.fail_query = False
        self.closed = []

    def inference_client(self, **_kwargs):
        cloud = self

        class FakeInference(FakeContext):
            def get_embeddings(self, **kwargs):
                cloud.embedding_calls.append(kwargs)
                if cloud.fail_inference:
                    raise ServiceRequestError("Simulated inference failure")
                item = kwargs["inputs"][0]
                if item["kind"] == "query" or "air trip disruption" in item["content"]:
                    position = 0
                elif "baggage" in item["content"]:
                    position = 1
                else:
                    position = 2
                vector = [0.0] * kwargs["dimensions"]
                vector[position] = 1.0
                return SimpleNamespace(
                    model=kwargs["model"],
                    output_data_kind="float32",
                    output=None,
                    warnings=[],
                    data=[
                        MultimodalDenseEmbedding(
                            {
                                "index": 0,
                                "contentKind": item["kind"],
                                "vectorKind": "dense",
                                "embedding": vector,
                            }
                        )
                    ],
                    usage=SimpleNamespace(prompt_tokens=5),
                )

        return FakeInference()

    def index_client(self, **_kwargs):
        cloud = self

        class FakeIndexClient(FakeContext):
            def list_index_names(self):
                return iter(["unrelated-index"])

            def __exit__(self, *_args):
                cloud.closed.append("index")
                return False

            def create_index(self, index, **kwargs):
                if cloud.fail_creation:
                    raise ServiceRequestError("Simulated uncertain creation")
                if not cloud.missing_etag:
                    index["@odata.etag"] = cloud.body_etag
                cloud.created.append(index)
                return index

            def delete_index(self, index, *, match_condition):
                cloud.delete_conditions.append(match_condition)
                cloud.deletion_etags.append(index.e_tag)
                if cloud.fail_deletion:
                    raise ServiceRequestError("Simulated deletion failure")
                cloud.deleted.append(index.name)

        return FakeIndexClient()

    def search_client(self, **_kwargs):
        cloud = self

        class FakeSearchClient(FakeContext):
            def __exit__(self, *_args):
                cloud.closed.append("search")
                return False

            def upload_documents(self, documents):
                cloud.documents = documents
                return [
                    SimpleNamespace(succeeded=not (cloud.fail_upload and index == 0))
                    for index, _ in enumerate(documents)
                ]

            def get_document_count(self):
                cloud.count_calls += 1
                return 0 if cloud.never_visible else len(cloud.documents)

            def search(self, **kwargs):
                cloud.search_calls.append(kwargs)
                if cloud.fail_query:
                    raise ServiceRequestError("Simulated search failure")
                text = kwargs.get("search_text")
                vector_queries = kwargs.get("vector_queries")
                code_matches = [
                    doc for doc in cloud.documents
                    if kwargs.get("search_fields") == ["policy_code"] and text == f'"{doc["policy_code"]}"'
                ]
                if text is not None and not vector_queries:
                    if cloud.keyword_override is not None:
                        return cloud.keyword_override
                    return code_matches[: kwargs["top"]]

                if text is not None and cloud.hybrid_override is not None:
                    return cloud.hybrid_override
                if text is None and cloud.vector_override is not None:
                    return cloud.vector_override
                query = vector_queries[0].vector
                ranked = sorted(
                    cloud.documents,
                    key=lambda doc: sum(a * b for a, b in zip(query, doc["content_vector"])),
                    reverse=True,
                )
                if text is not None:
                    # Stub the lexical promotion; Azure ranking is verified separately.
                    ranked = code_matches + [doc for doc in ranked if doc not in code_matches]
                return ranked[: kwargs["top"]]

        return FakeSearchClient()


def notebook_cells():
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    nbformat.validate(notebook)
    return [cell for cell in notebook.cells if cell.cell_type == "code"]


def execute_offline(cloud, *, semantic=False, overrides=None, retry_query=None):
    namespace = {"__name__": "__notebook__"}
    output = io.StringIO()
    environment = {
        "EMBEDDING_ENDPOINT": "https://embedding.example.test",
        "AZURE_SEARCH_ENDPOINT": "https://search.example.test",
        "AZURE_SUBSCRIPTION_ID": "",
        "RUN_SEMANTIC_RANKER": "1" if semantic else "0",
        **(overrides or {}),
    }
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, environment))
        stack.enter_context(patch("azure.data.ai.InferenceClient", side_effect=cloud.inference_client))
        credential = type("FakeCredential", (OfflineCredential, FakeContext), {})()
        stack.enter_context(patch("azure.identity.AzureCliCredential", return_value=credential))
        stack.enter_context(
            patch("azure.search.documents.indexes.SearchIndexClient", side_effect=cloud.index_client)
        )
        stack.enter_context(patch("azure.search.documents.SearchClient", side_effect=cloud.search_client))
        stack.enter_context(patch("time.sleep"))
        stack.enter_context(contextlib.redirect_stdout(output))
        for index, cell in enumerate(notebook_cells(), start=1):
            code = compile(cell.source, f"{NOTEBOOK.name}:cell-{index}", "exec")
            try:
                exec(code, namespace)
            except ServiceRequestError as exc:
                if retry_query is None:
                    raise
                retry_query(exc)
                exec(code, namespace)
    return namespace, output.getvalue()


def load_definitions(*names):
    namespace = {"__name__": "__notebook__"}
    config, *steps = notebook_cells()
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(config.source, NOTEBOOK.name, "exec"), namespace)
    for cell in steps:
        tree = ast.parse(cell.source)
        definitions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        exec(compile(ast.Module(body=definitions, type_ignores=[]), NOTEBOOK.name, "exec"), namespace)
    return namespace


class EmbeddingSearchNotebookTests(unittest.TestCase):
    def test_offline_run_exercises_requests_schema_results_and_cleanup(self):
        cloud = FakeCloud()
        namespace, output = execute_offline(cloud)

        self.assertIn("Paraphrase keyword matches (up to 3): []", output)
        self.assertIn(
            "  Keyword: ['TRV-18']\n  Vector: ['TRV-12', 'TRV-18', 'TRV-24']\n"
            "  Hybrid: ['TRV-18', 'TRV-12', 'TRV-24']",
            output,
        )
        self.assertIn("  Keyword: []\n  Vector: ['TRV-12',", output)
        self.assertIn("TRV-12: Travel disruption expenses.", output)
        self.assertIn("TRV-18: Lost baggage.", output)
        self.assertIn(cloud.documents[0]["content"], output)
        self.assertIn("Semantic ranking skipped (opt-in).", output)
        self.assertIn("Temporary index deleted.", output)
        self.assertEqual(unsafe_output_lines(output), [])
        self.assertEqual(namespace["credential"].scopes, [
            "https://dbinference.azure.com/.default", "https://search.azure.com/.default"
        ])
        self.assertEqual(
            [call["inputs"][0]["kind"] for call in cloud.embedding_calls],
            ["text"] * 6 + ["query"] * 2,
        )
        for call in cloud.embedding_calls:
            self.assertEqual(len(call["inputs"]), 1)
            self.assertEqual(call["model"], "microsoft-embedding-1-large")
            self.assertEqual(call["dimensions"], 1536)
            self.assertEqual(call["vector_kind"], "dense")
            self.assertEqual(call["encoding_format"], "float")
            self.assertEqual(call["output_data_kind"], "float32")
            self.assertEqual(call["delivery"], "inline")

        index = cloud.created[0]
        self.assertRegex(index.name, r"^embedding1-cookbook-[0-9a-f]{12}$")
        self.assertEqual(cloud.deleted, [index.name])
        self.assertEqual(cloud.delete_conditions, [MatchConditions.IfNotModified])
        self.assertEqual(cloud.deletion_etags, ['"created"'])
        self.assertEqual(cloud.closed, ["search", "index"])
        definition = index.as_dict()
        field = next(field for field in definition["fields"] if field["name"] == "content_vector")
        self.assertEqual(field["type"], "Collection(Edm.Single)")
        self.assertEqual(field["dimensions"], 1536)
        self.assertTrue(field["searchable"])
        self.assertFalse(field["retrievable"])
        self.assertTrue(field["stored"])
        self.assertEqual(field["vectorSearchProfile"], "dense-profile")
        self.assertEqual(definition["vectorSearch"]["algorithms"][0]["hnswParameters"]["metric"], "cosine")
        self.assertEqual(definition["vectorSearch"]["profiles"][0]["algorithm"], "hnsw-cosine")
        self.assertTrue(all(doc["embedding_model"] == namespace["MODEL"] for doc in cloud.documents))

        fields = {item["name"]: item for item in definition["fields"]}
        self.assertEqual(fields["title"]["analyzer"], "en.microsoft")
        self.assertEqual(fields["content"]["analyzer"], "en.microsoft")
        self.assertEqual(fields["policy_code"]["analyzer"], "keyword")
        self.assertTrue(fields["policy_code"]["filterable"])
        self.assertEqual(len(cloud.search_calls), 6)
        self.assertEqual(cloud.search_calls[0]["search_text"], namespace["queries"][0][1])
        self.assertNotIn("search_mode", cloud.search_calls[0])
        self.assertNotIn("vector_queries", cloud.search_calls[0])
        self.assertEqual(cloud.search_calls[1]["search_text"], '"TRV-18"')
        self.assertEqual(cloud.search_calls[1]["search_fields"], ["policy_code"])
        self.assertNotIn("TRV-18", cloud.embedding_calls[1]["inputs"][0]["content"])
        self.assertIn("trv-18", cloud.embedding_calls[-1]["inputs"][0]["content"])
        self.assertNotIn("search_text", cloud.search_calls[2])
        vector_query = cloud.search_calls[2]["vector_queries"][0].as_dict()
        self.assertEqual(vector_query["fields"], "content_vector")
        self.assertEqual(vector_query["k"], 50)
        self.assertTrue(vector_query["exhaustive"])
        self.assertEqual(len(vector_query["vector"]), 1536)
        for lexical_call, vector_call, hybrid_call in zip(
            cloud.search_calls[:2], cloud.search_calls[2:4], cloud.search_calls[4:]
        ):
            for key in ("search_text", "search_fields", "top"):
                self.assertEqual(hybrid_call[key], lexical_call[key])
            self.assertEqual(hybrid_call["top"], vector_call["top"])
            self.assertEqual(hybrid_call["vector_queries"][0].as_dict(), vector_call["vector_queries"][0].as_dict())
            self.assertNotIn("filter", hybrid_call)
            self.assertNotIn("semantic_query", hybrid_call)

    def test_semantic_opt_in_adds_reranking_without_changing_plain_hybrid(self):
        cloud = FakeCloud()
        namespace, output = execute_offline(cloud, semantic=True)
        self.assertEqual(len(cloud.search_calls), 8)
        self.assertIn("Paraphrase after semantic ranking:", output)
        for (_, question), normal, semantic in zip(
            namespace["queries"], cloud.search_calls[4:6], cloud.search_calls[6:]
        ):
            self.assertEqual(semantic["semantic_query"], question)
            self.assertEqual(semantic["semantic_configuration_name"], "policy-text")
            self.assertEqual(
                {key: value for key, value in semantic.items() if not key.startswith("semantic_")},
                normal,
            )

    def test_keyword_input_extracts_complete_codes_and_normalizes_case(self):
        lexical = load_definitions("keyword_args")["keyword_args"]
        for question in ("Does trv-18 apply?", "Does TrV-18 apply?", "Does TRV-18 apply?"):
            with self.subTest(question=question):
                self.assertEqual(lexical(question), {"search_text": '"TRV-18"', "search_fields": ["policy_code"]})
        question = "Which policy applies to TRV-180?"
        self.assertEqual(lexical(question), {"search_text": question, "search_fields": ["title", "content"]})

    def test_missing_endpoint_fails_before_service_calls(self):
        cloud = FakeCloud()
        with self.assertRaisesRegex(ValueError, "Set EMBEDDING_ENDPOINT"):
            execute_offline(cloud, overrides={"EMBEDDING_ENDPOINT": ""})
        self.assertFalse(cloud.embedding_calls)
        self.assertFalse(cloud.created)

    def test_search_failure_can_be_retried_without_rebuilding_the_index(self):
        cloud = FakeCloud()
        cloud.fail_query = True

        def retry_query(exc):
            self.assertIn("search failure", str(exc))
            self.assertFalse(cloud.deleted)
            self.assertFalse(cloud.closed)
            self.assertEqual(len(cloud.embedding_calls), 8)
            cloud.fail_query = False

        execute_offline(cloud, retry_query=retry_query)
        self.assertFalse(cloud.fail_query)
        self.assertEqual(len(cloud.created), 1)
        self.assertEqual(len(cloud.embedding_calls), 8)
        self.assertEqual(cloud.deleted, [cloud.created[0].name])
        self.assertEqual(cloud.closed, ["search", "index"])

    def test_public_notebook_has_no_saved_outputs(self):
        notebook = nbformat.read(NOTEBOOK, as_version=4)
        for cell in (cell for cell in notebook.cells if cell.cell_type == "code"):
            self.assertEqual(cell.outputs, [])
            self.assertIsNone(cell.execution_count)
            self.assertNotIn("execution", cell.metadata)
        markdown = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "markdown")
        text_blocks = re.findall(r"```text\n(.*?)```", markdown, re.S)
        self.assertEqual(len(text_blocks), 1)
        self.assertTrue(text_blocks[0].lstrip().startswith("python -m pip install"))
        self.assertNotIn("| Mode |", markdown)

    def test_output_allowlist_rejects_secret_canaries(self):
        canaries = [
            "Authorization: Bearer synthetic-test-token",
            "api-key: TEST-ONLY-KEY-DO-NOT-USE",
            "Paraphrase keyword matches (up to 3): ['TRV-12'] sig=synthetic%2Fsignature&se=2030-01-01",
            "Temporary index: embedding1-cookbook-000000000000 https://search.example.test",
            "Reported input tokens across all embedding requests: 148. /subscriptions/synthetic-placeholder",
        ]
        for canary in canaries:
            with self.subTest(canary=canary):
                self.assertEqual(unsafe_output_lines(canary), [canary])

    def test_failed_upload_still_deletes_the_created_index(self):
        cloud = FakeCloud()
        cloud.fail_upload = True
        with self.assertRaisesRegex(RuntimeError, "upload failed"):
            execute_offline(cloud)
        self.assertEqual(cloud.deleted, [cloud.created[0].name])
        self.assertFalse(cloud.search_calls)

    def test_failed_creation_does_not_delete_an_existing_index(self):
        cloud = FakeCloud()
        cloud.fail_creation = True
        with self.assertRaisesRegex(RuntimeError, "uncertain; verify ownership before manual cleanup") as caught:
            execute_offline(cloud)
        self.assertIsInstance(caught.exception.__cause__, ServiceRequestError)
        self.assertFalse(cloud.created)
        self.assertFalse(cloud.deleted)

    def test_relevance_outcomes_are_informational(self):
        cloud = FakeCloud()
        cloud.keyword_override = [{"policy_code": "ZZ-02"}]
        cloud.vector_override = [{"id": "other", "policy_code": "ZZ-01", "title": "Another policy", "content": "Other text."}]
        cloud.hybrid_override = cloud.vector_override
        _, output = execute_offline(cloud)
        self.assertIn("  Keyword: ['ZZ-02']\n  Vector: ['ZZ-01']\n  Hybrid: ['ZZ-01']", output)
        self.assertIn("  ZZ-01: Another policy. Other text.", output)
        self.assertEqual(cloud.deleted, [cloud.created[0].name])

    def test_empty_vector_results_are_informational(self):
        cloud = FakeCloud()
        cloud.vector_override = []
        _, output = execute_offline(cloud)
        self.assertEqual(output.count("  Vector: []"), 2)
        self.assertEqual(cloud.deleted, [cloud.created[0].name])

    def test_inference_failure_stops_before_creating_an_index(self):
        cloud = FakeCloud()
        cloud.fail_inference = True
        with self.assertRaisesRegex(ServiceRequestError, "inference failure"):
            execute_offline(cloud)
        self.assertFalse(cloud.created)
        self.assertFalse(cloud.deleted)

    def test_missing_etag_never_deletes_the_created_index(self):
        cloud = FakeCloud()
        cloud.missing_etag = True
        with self.assertRaisesRegex(RuntimeError, "No usable creation ETag.*verify ownership before manual cleanup") as caught:
            execute_offline(cloud)
        self.assertEqual(len(cloud.created), 1)
        self.assertIn(cloud.created[0].name, str(caught.exception))
        self.assertFalse(cloud.documents)
        self.assertFalse(cloud.delete_conditions)
        self.assertFalse(cloud.deleted)

    def test_wildcard_etag_never_allows_unconditional_cleanup(self):
        cloud = FakeCloud()
        cloud.body_etag = "*"
        with self.assertRaisesRegex(RuntimeError, "No usable creation ETag.*manual cleanup"):
            execute_offline(cloud)
        self.assertFalse(cloud.documents)
        self.assertFalse(cloud.delete_conditions)
        self.assertFalse(cloud.deleted)

    def test_header_only_etag_requires_manual_cleanup(self):
        transport = OfflineTransport()
        transport.omit_body_etag = True
        transport.header_etag = '"created-header"'
        cloud = FakeCloud()
        cloud.index_client = lambda **kwargs: SearchIndexClient(
            endpoint=kwargs["endpoint"],
            credential=OfflineCredential(),
            transport=transport,
        )

        with self.assertRaisesRegex(RuntimeError, "No usable creation ETag.*manual cleanup"):
            execute_offline(cloud)
        self.assertEqual([request.method for request in transport.requests], ["GET", "POST"])

    def test_failed_cleanup_reports_index_and_chains_original_failure(self):
        cloud = FakeCloud()
        cloud.fail_upload = True
        cloud.fail_deletion = True
        with self.assertRaises(RuntimeError) as caught:
            execute_offline(cloud)
        self.assertIn(cloud.created[0].name, str(caught.exception))
        cleanup_error = caught.exception.__cause__
        self.assertIsInstance(cleanup_error, ServiceRequestError)
        self.assertIsInstance(cleanup_error.__context__, RuntimeError)
        self.assertIn("upload failed", str(cleanup_error.__context__))
        self.assertEqual(cloud.delete_conditions, [MatchConditions.IfNotModified])
        self.assertFalse(cloud.deleted)

    def test_indexing_timeout_still_deletes_the_created_index(self):
        cloud = FakeCloud()
        cloud.never_visible = True
        with self.assertRaisesRegex(TimeoutError, "30 checks"):
            execute_offline(cloud)
        self.assertEqual(cloud.count_calls, 30)
        self.assertEqual(cloud.deleted, [cloud.created[0].name])
        self.assertFalse(cloud.search_calls)

    def test_embedding_validation_rejects_unusable_results(self):
        namespace = load_definitions("embed_text")

        def result(**changes):
            item = MultimodalDenseEmbedding(
                {
                    "index": 0,
                    "contentKind": "text",
                    "vectorKind": "dense",
                    "embedding": [1.0] + [0.0] * 1535,
                }
            )
            values = {
                "model": namespace["MODEL"],
                "output_data_kind": "float32",
                "output": None,
                "warnings": [],
                "data": [item],
                "usage": SimpleNamespace(prompt_tokens=5),
            }
            values.update(changes)
            return SimpleNamespace(**values)

        def item(**changes):
            values = {
                "index": 0,
                "contentKind": "text",
                "vectorKind": "dense",
                "embedding": [1.0] + [0.0] * 1535,
            }
            values.update(changes)
            return MultimodalDenseEmbedding(values)

        bad_results = [
            result(output=object()),
            result(warnings=["truncated"]),
            result(data=None),
            result(data=[]),
            result(data=[SimpleNamespace(index=0)]),
            result(data=[item(truncated=True)]),
            result(data=[item(embedding=[])]),
            result(data=[item(embedding=[1.0])]),
            result(data=[item(embedding=[math.nan] * 1536)]),
            result(data=[item(embedding=[math.inf] * 1536)]),
            result(data=[item(embedding=[0.0] * 1536)]),
        ]
        for response in bad_results:
            with self.subTest(response=response):
                client = SimpleNamespace(get_embeddings=lambda **_kwargs: response)
                with self.assertRaises(ValueError):
                    namespace["embed_text"](client, "sample", "text")

    def test_sdk_wire_contracts_with_in_memory_transport(self):
        namespace = load_definitions("embed_text", "make_index")

        transport = OfflineTransport()
        credential = OfflineCredential()
        with InferenceClient(
            endpoint="https://embedding.example.test",
            credential=credential,
            transport=transport,
        ) as inference:
            response = inference.get_embeddings(
                model=namespace["MODEL"],
                inputs=[{"kind": "query", "content": "sample query"}],
                vector_kind="dense",
                dimensions=1536,
                output_data_kind="float32",
                encoding_format="float",
                delivery="inline",
            )
            self.assertEqual(response.model, namespace["MODEL"])
            self.assertEqual(response.output_data_kind, "float32")
            self.assertEqual(len(response.data), 1)
            self.assertIsInstance(response.data[0], MultimodalDenseEmbedding)
            self.assertEqual(response.data[0].index, 0)
            self.assertEqual(response.data[0].content_kind, "query")
            self.assertEqual(response.data[0].vector_kind, "dense")
            self.assertFalse(response.data[0].truncated)
            vector, tokens = namespace["embed_text"](inference, "sample query", "query")
        self.assertEqual(len(vector), 1536)
        self.assertEqual(tokens, 5)

        with SearchIndexClient(
            endpoint="https://search.example.test",
            credential=credential,
            transport=transport,
        ) as search:
            index = search.create_index(namespace["make_index"]("contract-test"))
            self.assertEqual(index.e_tag, '"created"')
            search.delete_index(index, match_condition=MatchConditions.IfNotModified)

        _, embedding_request, index_request, deletion_request = transport.requests
        self.assertEqual(
            json.loads(embedding_request.body),
            {
                "model": "microsoft-embedding-1-large",
                "inputs": [{"kind": "query", "content": "sample query"}],
                "vectorKind": "dense",
                "dimensions": 1536,
                "outputDataKind": "float32",
                "encodingFormat": "float",
                "delivery": "inline",
            },
        )
        index_body = json.loads(index_request.body)
        field = next(field for field in index_body["fields"] if field["name"] == "content_vector")
        self.assertTrue(field["stored"])
        self.assertFalse(field["retrievable"])
        self.assertEqual(deletion_request.headers["If-Match"], '"created"')

    def test_etag_conflict_surfaces_cleanup_error(self):
        transport = OfflineTransport()
        transport.reject_delete = True
        cloud = FakeCloud()
        cloud.index_client = lambda **kwargs: SearchIndexClient(
            endpoint=kwargs["endpoint"],
            credential=OfflineCredential(),
            transport=transport,
        )

        with self.assertRaises(RuntimeError) as caught:
            execute_offline(cloud)

        _, index_request, deletion_request = transport.requests
        self.assertIn(json.loads(index_request.body)["name"], str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__, ResourceModifiedError)
        self.assertEqual(deletion_request.headers["If-Match"], '"created"')


if __name__ == "__main__":
    unittest.main()
