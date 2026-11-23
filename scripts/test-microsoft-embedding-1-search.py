"""Offline execution and safety checks for the embedding/Search notebook.

Run ``python scripts/test-microsoft-embedding-1-search.py`` from the repo root
with nbformat and the notebook's SDK dependencies installed. Services are faked.
"""

from __future__ import annotations

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

# Saved outputs may contain only these exact line shapes; anything else is treated as unsafe.
ALLOWED_OUTPUT_LINES = [
    re.compile(pattern)
    for pattern in (
        r"SDK imports ready; using 1,536-dimensional dense vectors\.",
        r"Corpus: 6 fictional policy passages; query: 'Can I get reimbursed for a delayed flight\?'",
        r"Embedding helper ready\.",
        r"Search index definition ready\.",
        r"Index visibility check ready\.",
        r"Embedded \d+ passages and one query; vector dimensions: \d+\.",
        r"Reported input tokens: \d+",
        r"Temporary index: forgebook-embedding-[0-9a-f]{12}",
        r"Keyword hits: \d+",
        r"Vector result IDs: \[(?:'[a-z]+'(?:, '[a-z]+')*)?\]",
        r"Expected passage '[a-z]+' found at rank \d+ of \d+\.",
        r"  [a-z]+: Search score \d+\.\d{4}",
        r"Temporary index deleted\.",
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
    def get_token(self, *_scopes, **_kwargs):
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
        self.header_etag = None
        self.fail_deletion = False
        self.fail_inference = False
        self.fail_upload = False
        self.never_visible = False
        self.count_calls = 0
        self.delete_conditions = []
        self.deletion_etags = []

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
            def create_index(self, index, **kwargs):
                if cloud.fail_creation:
                    raise RuntimeError("Index already exists")
                if not cloud.missing_etag:
                    index["@odata.etag"] = cloud.body_etag
                cloud.created.append(index)
                headers = {"ETag": cloud.header_etag} if cloud.header_etag else {}
                kwargs["raw_response_hook"](
                    SimpleNamespace(http_response=SimpleNamespace(status_code=201, headers=headers))
                )
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
                if kwargs["search_text"] is not None:
                    terms = kwargs["search_text"].lower().split()
                    return [
                        document
                        for document in cloud.documents
                        if all(term in document["content"].lower() for term in terms)
                    ][: kwargs["top"]]

                query = kwargs["vector_queries"][0].vector
                ranked = sorted(
                    cloud.documents,
                    key=lambda doc: sum(a * b for a, b in zip(query, doc["content_vector"])),
                    reverse=True,
                )
                return [
                    {**doc, "@search.score": 1.0 if index == 0 else 0.5}
                    for index, doc in enumerate(ranked[: kwargs["top"]])
                ]

        return FakeSearchClient()


def notebook_cells():
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    nbformat.validate(notebook)
    return [cell for cell in notebook.cells if cell.cell_type == "code"]


def execute_offline(cloud):
    namespace = {"__name__": "__notebook__"}
    output = io.StringIO()
    environment = {
        "EMBEDDING_ENDPOINT": "https://embedding.example.test",
        "AZURE_SEARCH_ENDPOINT": "https://search.example.test",
    }
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, environment))
        stack.enter_context(patch("azure.data.ai.InferenceClient", side_effect=cloud.inference_client))
        stack.enter_context(patch("azure.identity.AzureCliCredential", return_value=FakeContext()))
        stack.enter_context(
            patch("azure.search.documents.indexes.SearchIndexClient", side_effect=cloud.index_client)
        )
        stack.enter_context(patch("azure.search.documents.SearchClient", side_effect=cloud.search_client))
        stack.enter_context(patch("time.sleep"))
        stack.enter_context(contextlib.redirect_stdout(output))
        for index, cell in enumerate(notebook_cells(), start=1):
            exec(compile(cell.source, f"{NOTEBOOK.name}:cell-{index}", "exec"), namespace)
    return namespace, output.getvalue()


class EmbeddingSearchNotebookTests(unittest.TestCase):
    def test_offline_run_exercises_requests_schema_results_and_cleanup(self):
        cloud = FakeCloud()
        namespace, output = execute_offline(cloud)

        self.assertIn("Keyword hits: 0", output)
        self.assertIn("Expected passage 'travel' found at rank 1 of 3.", output)
        self.assertIn("Temporary index deleted.", output)
        self.assertEqual(unsafe_output_lines(output), [])
        self.assertEqual(len(cloud.embedding_calls), 7)
        self.assertEqual(
            [call["inputs"][0]["kind"] for call in cloud.embedding_calls],
            ["text"] * 6 + ["query"],
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
        self.assertRegex(index.name, r"^forgebook-embedding-[0-9a-f]{12}$")
        self.assertEqual(cloud.deleted, [index.name])
        self.assertEqual(cloud.delete_conditions, [MatchConditions.IfNotModified])
        self.assertEqual(cloud.deletion_etags, ['"created"'])
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

        self.assertEqual(cloud.search_calls[0]["search_text"], namespace["query_text"])
        self.assertEqual(cloud.search_calls[0]["search_mode"], "all")
        vector_query = cloud.search_calls[1]["vector_queries"][0].as_dict()
        self.assertEqual(vector_query["fields"], "content_vector")
        self.assertEqual(vector_query["k"], 3)
        self.assertTrue(vector_query["exhaustive"])
        self.assertEqual(len(vector_query["vector"]), 1536)

    def test_public_notebook_has_no_saved_outputs(self):
        cells = notebook_cells()
        self.assertTrue(cells)
        for cell in cells:
            self.assertEqual(cell.outputs, [])
            self.assertIsNone(cell.execution_count)
            self.assertNotIn("execution", cell.metadata)

    def test_output_allowlist_rejects_secret_canaries(self):
        canaries = [
            "Authorization: Bearer synthetic-test-token",
            "api-key: TEST-ONLY-KEY-DO-NOT-USE",
            "Vector result IDs: ['travel'] sig=synthetic%2Fsignature&se=2030-01-01",
            "Temporary index: forgebook-embedding-000000000000 https://search.example.test",
            "Reported input tokens: 148 /subscriptions/synthetic-placeholder",
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
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            execute_offline(cloud)
        self.assertFalse(cloud.created)
        self.assertFalse(cloud.deleted)

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
        with self.assertRaisesRegex(RuntimeError, "No usable creation ETag.*verify ownership and delete manually") as caught:
            execute_offline(cloud)
        self.assertEqual(len(cloud.created), 1)
        self.assertIn(cloud.created[0].name, str(caught.exception))
        self.assertFalse(cloud.documents)
        self.assertFalse(cloud.delete_conditions)
        self.assertFalse(cloud.deleted)

    def test_wildcard_etag_never_allows_unconditional_cleanup(self):
        for source in ("body", "header"):
            with self.subTest(source=source):
                cloud = FakeCloud()
                if source == "body":
                    cloud.body_etag = "*"
                else:
                    cloud.missing_etag = True
                    cloud.header_etag = "*"
                with self.assertRaisesRegex(RuntimeError, "No usable creation ETag.*delete manually"):
                    execute_offline(cloud)
                self.assertFalse(cloud.documents)
                self.assertFalse(cloud.delete_conditions)
                self.assertFalse(cloud.deleted)

    def test_header_only_etag_is_used_for_conditional_cleanup(self):
        transport = OfflineTransport()
        transport.omit_body_etag = True
        transport.header_etag = '"created-header"'
        cloud = FakeCloud()
        cloud.index_client = lambda **kwargs: SearchIndexClient(
            endpoint=kwargs["endpoint"],
            credential=OfflineCredential(),
            transport=transport,
        )

        _, output = execute_offline(cloud)

        self.assertIn("Temporary index deleted.", output)
        index_request, deletion_request = transport.requests
        self.assertEqual(index_request.method, "POST")
        self.assertEqual(deletion_request.method, "DELETE")
        self.assertEqual(deletion_request.headers["If-Match"], '"created-header"')

    def test_conflicting_creation_etags_require_manual_cleanup(self):
        cloud = FakeCloud()
        cloud.header_etag = '"different"'
        with self.assertRaisesRegex(RuntimeError, "Conflicting creation ETags.*verify ownership and delete manually") as caught:
            execute_offline(cloud)
        self.assertIn(cloud.created[0].name, str(caught.exception))
        self.assertFalse(cloud.documents)
        self.assertFalse(cloud.delete_conditions)
        self.assertFalse(cloud.deleted)

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
        namespace = {"__name__": "__notebook__"}
        for cell in notebook_cells():
            exec(compile(cell.source, NOTEBOOK.name, "exec"), namespace)
            if "embed_text" in namespace:
                break

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
        namespace = {"__name__": "__notebook__"}
        with contextlib.redirect_stdout(io.StringIO()):
            for cell in notebook_cells():
                exec(compile(cell.source, NOTEBOOK.name, "exec"), namespace)
                if "make_index" in namespace:
                    break

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

        index_request, deletion_request = transport.requests
        self.assertIn(json.loads(index_request.body)["name"], str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__, ResourceModifiedError)
        self.assertEqual(deletion_request.headers["If-Match"], '"created"')


if __name__ == "__main__":
    unittest.main()
