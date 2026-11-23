**Use Microsoft Embedding 1 with Foundry IQ (Azure AI Search)**

For developers building text retrieval, generate document and query embeddings with Microsoft Embedding 1 (preview) through an Azure Cosmos DB inference endpoint, then send the vectors to a [Foundry IQ (Azure AI Search)](https://learn.microsoft.com/azure/search/search-what-is-azure-search) index you control. Compare a keyword query with a dense-vector query over three synthetic passages. This recipe uses direct index APIs (classic search), not a Foundry IQ knowledge base or agentic retrieval.

**When to use:** Keyword matching misses a differently worded question.

**What it does:** Your application embeds each passage as `text`, embeds the question as `query`, and searches a cosine vector index.

**How to adapt:** Replace the passages and test questions with your own labeled examples; measure retrieval quality before choosing dimensions or deploying the pattern.

## Prerequisites and cost

- Python 3.10 or later and the Azure CLI; allow about 10 minutes after the Azure resources and permissions are ready.
- An Azure Cosmos DB account with an [inference endpoint enabled](https://learn.microsoft.com/azure/cosmos-db/gen-ai/generate-embedding). Use the inference endpoint, not the Cosmos DB data endpoint. Microsoft Embedding 1 is **preview**, available through this endpoint in the [listed regions](https://learn.microsoft.com/azure/cosmos-db/gen-ai/microsoft-embedding-1#model-specifications); the model documentation lists Foundry availability as coming soon.
- A Foundry IQ (Azure AI Search) service that supports vector indexes. Enable role-based access on the service. The calling identity needs **Embedding User** on the inference account and **Search Service Contributor** plus **Search Index Data Contributor** on the Search service. Ask an administrator to configure access; this notebook does not change roles.
- Sign in with `az login` and select the authorized CLI account. This notebook uses `AzureCliCredential`, so another credential in the environment does not take precedence. For an Azure-hosted application, replace it with an explicitly configured `ManagedIdentityCredential` and grant that identity the same roles. See [credential selection](https://learn.microsoft.com/azure/developer/python/sdk/authentication/credential-chains).
- Set `EMBEDDING_ENDPOINT` to the inference endpoint and `AZURE_SEARCH_ENDPOINT` to the Search service endpoint in the environment **before starting the kernel**. No keys are embedded in the notebook. Production applications can obtain any required secrets from a managed store such as Azure Key Vault.
- Install the dependencies in the notebook's Python environment:

  ```text
  python -m pip install "azure-data-ai==1.1.0b1" "azure-search-documents==12.0.0" "azure-identity>=1.25,<2"
  ```

Running this notebook makes **four embedding requests** and a small number of Search operations. The [published preview price](https://learn.microsoft.com/azure/cosmos-db/gen-ai/microsoft-embedding-1#pricing) is **$0.12 per million text/query input tokens**; 1,000 such tokens would cost about $0.00012. Actual usage is reported by the service when available. Search charges are separate and can continue while a paid service exists. For example, on November 20, 2026, [US East 2 retail pricing](https://prices.azure.com/api/retail/prices?%24filter=serviceName%20eq%20%27Azure%20Cognitive%20Search%27%20and%20armRegionName%20eq%20%27eastus2%27%20and%20meterName%20eq%20%27Basic%20Unit%27) for one Basic search unit was $0.101/hour; [free tier availability and pricing](https://azure.microsoft.com/pricing/details/search/) depend on the subscription and region. This notebook deletes only its temporary **index**, not either service.

The corpus below is synthetic and written for this recipe. No external files or image permissions are required.

```python
import math
import os
import time
import uuid

from azure.core import MatchConditions
from azure.core.exceptions import AzureError
from azure.data.ai import InferenceClient
from azure.data.ai.models import MultimodalDenseEmbedding
from azure.identity import AzureCliCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

MODEL = "microsoft-embedding-1-large"
DIMENSIONS = 1536
print("SDK imports ready; using 1,536-dimensional dense vectors.")
```

## Choose a small retrieval check

The two words in the question do not appear in any passage. A keyword search requiring both words should return zero hits; the vector search should find `lake` in its first two results. This is a smoke test, not a relevance benchmark.

```python
documents = [
    {
        "id": "lake",
        "title": "Lakeside walk",
        "content": "A footpath follows the shoreline of a lake. Walk beside the water past benches and a small pier.",
    },
    {
        "id": "desert",
        "title": "Desert route",
        "content": "A dry hiking route crosses open sand dunes and rocky canyons.",
    },
    {
        "id": "rail",
        "title": "Train timetable",
        "content": "A commuter train schedule lists morning departures from the central station.",
    },
]
query_text = "stroll waterfront"
expected_id = "lake"
top_k = 2
print(f"Corpus: {len(documents)} synthetic passages; query: {query_text!r}")
```

## Generate one dense vector per request

The [model API](https://learn.microsoft.com/azure/cosmos-db/gen-ai/microsoft-embedding-1#api-reference) allows one text or query input per request. Use `kind="text"` for stored passages and `kind="query"` for the question, with the same model and dimensions for both. Start with 1,536 dimensions: its raw float32 vector is 40% smaller than the 2,560-dimensional option. The model also supports 1,024 and 2,048 dimensions; evaluate recall on your data before choosing.

Request inline numeric float32 output for Search. Stop rather than index a truncated, warned, linked, malformed, or unexpected response. Inputs longer than 8,192 tokens can be truncated; chunk and evaluate real documents separately.

```python
def embed_text(client, text: str, kind: str) -> tuple[list[float], int | None]:
    if kind not in {"text", "query"}:
        raise ValueError("Use text for passages or query for questions.")

    response = client.get_embeddings(
        model=MODEL,
        inputs=[{"kind": kind, "content": text}],
        vector_kind="dense",
        dimensions=DIMENSIONS,
        output_data_kind="float32",
        encoding_format="float",
        delivery="inline",
    )
    if response.output is not None:
        raise ValueError("Expected an inline result; do not log a result-file URL or SAS token.")
    if response.warnings:
        raise ValueError("Embedding response contained warnings; inspect them securely before indexing.")
    if response.model != MODEL or response.output_data_kind != "float32" or len(response.data) != 1:
        raise ValueError("Expected one float32 result from the requested model.")

    item = response.data[0]
    if (
        not isinstance(item, MultimodalDenseEmbedding)
        or item.index != 0
        or item.content_kind != kind
        or item.vector_kind != "dense"
        or item.truncated
    ):
        raise ValueError("Expected an ordered, untruncated dense embedding of the requested kind.")
    vector = item.embedding
    if (
        not isinstance(vector, list)
        or len(vector) != DIMENSIONS
        or not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in vector)
        or not any(vector)
    ):
        raise ValueError("Expected a nonzero, finite, numeric, 1,536-dimensional dense vector.")
    tokens = response.usage.prompt_tokens if response.usage is not None else None
    return vector, tokens

print("Embedding helper ready.")
```

## Define the Search index

Use a `Collection(Edm.Single)` field with the **same 1,536 dimensions**, an HNSW profile, and cosine similarity. At float32, the raw vector is 6,144 bytes per passage before Search index and metadata overhead; the model's float16 storage figures are not the size of this field. The model name is stored alongside each vector so a later migration can identify incompatible embeddings.

Keep `stored=True` so Search can preserve the vector during partial document updates, and keep it hidden from query results. With `stored=False`, an update that omits the vector can silently lose it; see [vector storage options](https://learn.microsoft.com/azure/search/vector-search-how-to-storage-options).

No Search vectorizer is configured: the application supplies both document and query vectors. See [create a vector index](https://learn.microsoft.com/azure/search/vector-search-how-to-create-index) and [vector ranking](https://learn.microsoft.com/azure/search/vector-search-ranking).

```python
def make_index(name: str) -> SearchIndex:
    return SearchIndex(
        name=name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(name="embedding_model", type=SearchFieldDataType.String),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                hidden=True,
                stored=True,
                vector_search_dimensions=DIMENSIONS,
                vector_search_profile_name="dense-profile",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-cosine", parameters=HnswParameters(metric="cosine"))],
            profiles=[VectorSearchProfile(name="dense-profile", algorithm_configuration_name="hnsw-cosine")],
        ),
    )

print("Search index definition ready.")
```

## Upload and compare

Search indexing is asynchronous. Check visibility up to 30 times, sleeping two seconds between checks; network calls and retries add to that time. For this tiny corpus, request an **exhaustive** search on the HNSW field so approximate-neighbor variation does not affect the smoke test. Use HNSW without exhaustive search for a larger workload only after measuring recall and latency.

```python
def wait_for_documents(client, expected_count: int) -> None:
    for attempt in range(30):
        if client.get_document_count() >= expected_count:
            return
        if attempt < 29:
            time.sleep(2)
    raise TimeoutError("Documents did not become searchable after 30 checks.")

print("Index visibility check ready.")
```

Run the cell below against your own services. It creates a uniquely named index using `create_index` rather than overwriting an existing index, checks every upload result, and compares keyword and vector results. Cleanup uses the returned index ETag to avoid deleting a replaced or modified index definition. It prints no endpoints, authentication tokens, or vector values.

```python
embedding_endpoint = os.environ.get("EMBEDDING_ENDPOINT")
search_endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
if not embedding_endpoint or not search_endpoint:
    raise ValueError("Set EMBEDDING_ENDPOINT and AZURE_SEARCH_ENDPOINT before starting the kernel.")

with AzureCliCredential() as credential:
    with InferenceClient(endpoint=embedding_endpoint, credential=credential) as inference:
        payload = []
        token_counts = []
        for document in documents:
            vector, tokens = embed_text(inference, document["content"], "text")
            payload.append({**document, "embedding_model": MODEL, "content_vector": vector})
            token_counts.append(tokens)
        query_vector, tokens = embed_text(inference, query_text, "query")
        token_counts.append(tokens)

    print(f"Embedded {len(payload)} passages and one query; vector dimensions: {len(query_vector)}.")
    if all(count is not None for count in token_counts):
        print(f"Reported input tokens: {sum(token_counts)}")
    else:
        print("Input token usage was not reported for every request; check Azure billing.")

    index_name = f"forgebook-embedding-{uuid.uuid4().hex[:12]}"
    print(f"Temporary index: {index_name}")
    with SearchIndexClient(endpoint=search_endpoint, credential=credential) as index_client:
        created_index = index_client.create_index(make_index(index_name))
        if not created_index.e_tag:
            raise RuntimeError(f"No ETag returned for temporary index {index_name}; confirm ownership before cleanup.")
        try:
            with SearchClient(endpoint=search_endpoint, index_name=index_name, credential=credential) as search:
                upload_results = search.upload_documents(documents=payload)
                if len(upload_results) != len(payload) or any(not result.succeeded for result in upload_results):
                    raise RuntimeError("At least one document upload failed; no query was run.")
                wait_for_documents(search, len(payload))

                keyword_hits = list(search.search(
                    search_text=query_text, search_fields=["content"], search_mode="all", select=["id"], top=top_k
                ))
                vector_query = VectorizedQuery(
                    vector=query_vector, k_nearest_neighbors=top_k, fields="content_vector", exhaustive=True
                )
                vector_hits = list(search.search(
                    search_text=None, vector_queries=[vector_query], select=["id", "title", "content"], top=top_k
                ))
                ids = [hit["id"] for hit in vector_hits]
                print(f"Keyword hits: {len(keyword_hits)}")
                print(f"Vector result IDs: {ids}")
                if keyword_hits or len(vector_hits) != top_k or expected_id not in ids:
                    raise AssertionError("The retrieval smoke test did not meet its expected results.")
                rank = ids.index(expected_id) + 1
                print(f"Expected passage {expected_id!r} found at rank {rank} of {top_k}.")
                for hit in vector_hits:
                    print(f"  {hit['id']}: Search score {hit['@search.score']:.4f}")
        finally:
            try:
                index_client.delete_index(created_index, match_condition=MatchConditions.IfNotModified)
            except AzureError as exc:
                raise RuntimeError(f"Could not delete temporary index {index_name}; confirm ownership before cleanup.") from exc
            print("Temporary index deleted.")
```

## Interpret and adapt

The expected smoke-test output is zero keyword hits and `lake` among the two vector results. One live run returned the following; the temporary index name printed during that run is omitted:

```text
Embedded 3 passages and one query; vector dimensions: 1536.
Reported input tokens: 62
Keyword hits: 0
Vector result IDs: ['lake', 'desert']
Expected passage 'lake' found at rank 1 of 2.
  lake: Search score 0.6730
  desert: Search score 0.5793
Temporary index deleted.
```

Your order and scores can differ. A Search score is a transformed ranking score, **not** a probability or a raw cosine similarity. A nearest-neighbor query can return a result even when none is useful. Evaluate labeled queries and establish thresholds on your own data rather than generalizing from three passages.

Copy `embed_text` and `make_index` along with their imports and `MODEL` and `DIMENSIONS` constants as the starting artifact: keep the model, vector kind, dimensions, and metric consistent when indexing and querying. When source text changes, generate its vector again; when changing an incompatible embedding configuration, rebuild a separate index and evaluate it before switching traffic. This recipe does not implement image inputs or multi-vector/MaxSim retrieval.

## Troubleshooting and cleanup

| Symptom | Check |
| --- | --- |
| 401 or 403 from inference | Confirm the inference endpoint, active Azure CLI identity, and **Embedding User** role; role changes can take time to propagate. |
| 403 from Search | Confirm role-based access is enabled and the identity has the Search roles listed above. |
| 429 from inference | Respect the service's `Retry-After` guidance and retry with a bounded policy. |
| Dimension or result validation error | Use the same model and dimensions for passages, index, and query; inspect warnings securely. |
| Indexing timeout or failed upload | Check service diagnostics and quotas, then rerun; cleanup is attempted for the created index. |
| Index ETag missing or cleanup fails | Confirm ownership of the printed index before deleting it manually; a changed ETag prevents automatic deletion. |
| Index creation response is lost | Its outcome is uncertain, so automatic cleanup does not delete anything. Inspect the printed unique index name and remove it only if you confirm this run created it. |

The cell attempts conditional index deletion even when upload or query validation fails. A failed cleanup reports the index name and retains the original error in the traceback. If the kernel is interrupted, the ETag is missing or changed, or deletion fails, delete only the printed temporary index after confirming ownership. The ETag protects the index definition, not concurrent changes to its documents. Delete any **services or resource groups you created solely for your own test** separately; do not delete shared resources.

For a no-cloud check of this notebook's code and cleanup behavior, install `nbformat` alongside the SDK dependencies and run `python scripts/test-microsoft-embedding-1-search.py` from the repository root. Those tests use fake services and do **not** verify the live model or Azure Search.