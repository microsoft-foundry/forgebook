When users mix paraphrased questions with exact policy codes, start with hybrid search. This recipe generates Microsoft Embedding 1 (preview) vectors through an **Azure Cosmos DB inference endpoint** and hands them to **Foundry IQ (Azure AI Search)**. Compare keyword, vector, and hybrid search over the same six fictional policies to see what each mode retrieves.

![Diagram: keyword search matches words and policy codes, vector search matches meaning, and hybrid search combines their rankings.](media/microsoft-embedding-1-azure-ai-search/01-hybrid-search.svg)

**When to use:** Your application needs both exact terms and matches by meaning.  
**What it does:** Your application supplies embeddings to direct Search index and query APIs. It does not configure a Search vectorizer or use a Foundry IQ knowledge base.  
**How to adapt:** Evaluate the three modes on labeled questions before choosing a dimension or deciding whether to add semantic ranking.

**Difficulty:** Intermediate. **Time:** Allow about 20–40 minutes for first-time setup and role propagation and about 5 minutes to run the notebook once resources are ready. **Cost:** Eight embedding requests and six Search queries, plus two Search queries if you enable the optional semantic ranker. See [model pricing](https://learn.microsoft.com/azure/cosmos-db/gen-ai/microsoft-embedding-1#pricing) and [Search pricing](https://azure.microsoft.com/pricing/details/search/). A paid Search service can accrue charges even when idle.

**Live verification:** The outputs below are from a fresh kernel on November 24, 2026, with the optional semantic step enabled. The temporary index suffix is redacted. This two-query smoke test verifies the integration, not retrieval quality on other data.

## Prerequisites

1. Use Python 3.10 or later. [Sign in with the Azure CLI](https://learn.microsoft.com/cli/azure/authenticate-azure-cli) and select the subscription for your test.
2. Register the inference provider in that subscription: `az provider register --namespace Microsoft.InferenceService --wait`. Ask a subscription administrator if you lack permission.
3. In the Azure Cosmos DB portal, open **AI Capabilities > Embedding generation (Preview)** and enable it in a [supported region](https://learn.microsoft.com/azure/cosmos-db/gen-ai/microsoft-embedding-1#model-specifications). See [Azure CLI and Bicep setup](https://learn.microsoft.com/azure/cosmos-db/gen-ai/generate-embedding#enable-embedding-generation) for alternatives. Copy the inference endpoint, not the database endpoint.
4. Choose a Foundry IQ (Azure AI Search) service with vector support and [role-based access enabled](https://learn.microsoft.com/azure/search/search-security-enable-roles). Basic is a starting point if you also want to try semantic ranking; verify feature availability and costs for your service.
5. Grant **Embedding User** on the companion inference account, and **Search Service Contributor** plus **Search Index Data Contributor** on the Search service, to the CLI identity. Allow time for assignment changes to propagate. The notebook does not create services or change roles.
6. Set `EMBEDDING_ENDPOINT` and `AZURE_SEARCH_ENDPOINT` before starting the kernel. If you use multiple Azure CLI subscriptions, optionally set `AZURE_SUBSCRIPTION_ID` to select the authorized subscription for both tokens. Install the tested dependencies in the notebook's Python environment:

   ```text
   python -m pip install "azure-data-ai==1.1.0b1" "azure-search-documents==12.0.0" "azure-identity==1.26.0"
   ```

## Configuration

Microsoft Embedding 1 [supports](https://learn.microsoft.com/azure/cosmos-db/gen-ai/microsoft-embedding-1#model-specifications) 1,024, 1,536, 2,048, and 2,560 dimensions (the model default). Start with 1,536: at the same precision it uses 40% less raw vector storage than 2,560. Measure the relevance tradeoff on your data. The [Azure Cosmos DB Blog announcement](https://devblogs.microsoft.com/cosmosdb/microsoft-embedding-one/) reports external benchmarks; this recipe does not reproduce them.

Run the numbered cells in order. If a cloud step fails, the notebook closes the clients and attempts to remove its index. Rerun from Configuration to start a new test.

```python
import math
import os
import time
import uuid
from contextlib import ExitStack, contextmanager

from azure.core import MatchConditions
from azure.core.exceptions import AzureError
from azure.data.ai import InferenceClient
from azure.identity import AzureCliCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration, HnswParameters, SearchField, SearchFieldDataType,
    SearchIndex, SearchableField, SemanticConfiguration, SemanticField,
    SemanticPrioritizedFields, SemanticSearch, SimpleField, VectorSearch, VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

MODEL = "microsoft-embedding-1-large"
DIMENSIONS = 1536
TEXT_ANALYZER = "en.microsoft"
TOP_K = 3
SEMANTIC_K = 50
SEMANTIC_CONFIG = "policy-text"
EMBEDDING_SCOPE = "https://dbinference.azure.com/.default"
SEARCH_SCOPE = "https://search.azure.com/.default"
EMBEDDING_ENDPOINT = os.environ.get("EMBEDDING_ENDPOINT")
SEARCH_ENDPOINT = os.environ.get("AZURE_SEARCH_ENDPOINT")
SUBSCRIPTION = os.environ.get("AZURE_SUBSCRIPTION_ID")
RUN_SEMANTIC = os.environ.get("RUN_SEMANTIC_RANKER", "0") == "1"

if "resources" in globals():
    resources.close()
resources = ExitStack()

@contextmanager
def cloud_step():
    try:
        yield
    except BaseException as exc:
        resources.__exit__(type(exc), exc, exc.__traceback__)
        raise

print(f"Configuration: {DIMENSIONS} dimensions; top {TOP_K} results.")
```

```text
Configuration: 1536 dimensions; top 3 results.
```

The same dimension is used for passages, questions, and the index field. The baselines show up to three hits each.

## Step 0: Verify access

Check both token scopes and make a Search call without printing endpoints, tokens, or the names of existing indexes. A token proves sign-in, not permission to call the embedding endpoint; Step 1 tests that role.

```python
with cloud_step():
    endpoints = {"EMBEDDING_ENDPOINT": EMBEDDING_ENDPOINT, "AZURE_SEARCH_ENDPOINT": SEARCH_ENDPOINT}
    missing = [name for name, value in endpoints.items() if not value]
    if missing:
        raise ValueError(f"Set {', '.join(missing)} before starting the kernel.")

    cli_options = {"subscription": SUBSCRIPTION} if SUBSCRIPTION else {}
    credential = resources.enter_context(AzureCliCredential(**cli_options))
    inference = resources.enter_context(InferenceClient(endpoint=EMBEDDING_ENDPOINT, credential=credential))
    index_client = resources.enter_context(SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=credential))
    credential.get_token(EMBEDDING_SCOPE)
    print("Embedding token OK.")
    credential.get_token(SEARCH_SCOPE)
    print("Search token OK.")
    next(iter(index_client.list_index_names()), None)
    print("Search index access OK.")
```

```text
Embedding token OK.
Search token OK.
Search index access OK.
```

The identity can list Search indexes. Write access is checked when the notebook creates the index and uploads documents.

## Step 1: Embed one policy passage

The [model API](https://learn.microsoft.com/azure/cosmos-db/gen-ai/microsoft-embedding-1#api-reference) accepts one input per request. Use `kind="text"` for passages and `kind="query"` for questions; both use the same model and dimensions. Run the first passage on its own, then reuse its vector in Step 3 rather than paying to embed it twice.

```python
documents = [
    {"id": "travel", "title": "Travel disruption expenses",
     "content": "Policy TRV-12. When an air trip disruption leaves an employee stranded overnight, the company covers reasonable hotel and meal expenses. Submit receipts to the travel team within 30 days."},
    {"id": "baggage", "title": "Lost baggage",
     "content": "Policy TRV-18. Employees whose checked baggage is lost during business travel may claim essential replacement items with receipts."},
    {"id": "booking", "title": "Changing a booking",
     "content": "Policy TRV-24. Use the booking portal to change an itinerary when a business meeting moves. A manager must approve higher fares."},
    {"id": "equipment", "title": "Remote work equipment",
     "content": "Policy IT-04. Remote employees may request a laptop and monitor from the IT catalog; equipment must be returned when employment ends."},
    {"id": "leave", "title": "Annual leave",
     "content": "Policy HR-09. Employees request annual leave through the HR portal. Managers approve requests based on team coverage."},
    {"id": "security", "title": "Lost devices",
     "content": "Policy SEC-07. Report a lost company device to the security team within one day, even if it is recovered later."},
]

def embed_text(client, text: str, kind: str) -> tuple[list[float], int | None]:
    if kind not in {"text", "query"}:
        raise ValueError("Use text for passages or query for questions.")
    response = client.get_embeddings(
        model=MODEL, inputs=[{"kind": kind, "content": text}],
        vector_kind="dense", dimensions=DIMENSIONS, output_data_kind="float32",
        encoding_format="float", delivery="inline",
    )
    if response.output is not None or response.warnings or len(response.data or []) != 1:
        raise ValueError("Expected one inline embedding without warnings; check input length and model status.")
    item = response.data[0]
    vector = getattr(item, "embedding", None)
    if (
        getattr(item, "truncated", False) or not isinstance(vector, list) or len(vector) != DIMENSIONS
        or not all(type(value) in (int, float) and math.isfinite(value) for value in vector)
        or not any(vector)
    ):
        raise ValueError(f"Expected an untruncated, nonzero, finite vector with {DIMENSIONS} dimensions.")
    return vector, response.usage.prompt_tokens if response.usage else None

with cloud_step():
    first_vector, first_tokens = embed_text(inference, documents[0]["content"], "text")
    print(f"First passage: {len(first_vector)} dimensions; input tokens: {first_tokens}.")
```

```text
First passage: 1536 dimensions; input tokens: 39.
```

The endpoint returned the requested vector length and reported token usage for the passage.

## Step 2: Create a temporary index

Use the [Microsoft English analyzer](https://learn.microsoft.com/azure/search/index-add-language-analyzers) for the prose in `title` and `content`. The [vector field](https://learn.microsoft.com/azure/search/vector-search-how-to-create-index) uses the matching dimension, cosine similarity, and `stored=True` so Search can preserve vectors during partial updates. The index also defines which text fields the optional ranker can read.

```python
def make_index(name: str) -> SearchIndex:
    return SearchIndex(
        name=name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="title", type=SearchFieldDataType.String, analyzer_name=TEXT_ANALYZER),
            SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name=TEXT_ANALYZER),
            SimpleField(name="embedding_model", type=SearchFieldDataType.String),
            SearchField(
                name="content_vector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True, hidden=True, stored=True,
                vector_search_dimensions=DIMENSIONS, vector_search_profile_name="dense-profile",
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-cosine", parameters=HnswParameters(metric="cosine"))],
            profiles=[VectorSearchProfile(name="dense-profile", algorithm_configuration_name="hnsw-cosine")],
        ),
        semantic_search=SemanticSearch(configurations=[SemanticConfiguration(
            name=SEMANTIC_CONFIG,
            prioritized_fields=SemanticPrioritizedFields(
                title_field=SemanticField(field_name="title"),
                content_fields=[SemanticField(field_name="content")],
            ),
        )]),
    )

def delete_owned_index(index_client, index):
    try:
        index_client.delete_index(index, match_condition=MatchConditions.IfNotModified)
    except AzureError as exc:
        raise RuntimeError(f"Could not delete {index.name}; verify ownership before manual cleanup.") from exc
    print("Temporary index deleted.")

with cloud_step():
    index_name = f"embedding1-cookbook-{uuid.uuid4().hex[:12]}"
    print(f"Temporary index: {index_name}")
    try:
        created_index = index_client.create_index(make_index(index_name))
    except AzureError as exc:
        raise RuntimeError(f"Creation of {index_name} failed or is uncertain; verify ownership before manual cleanup.") from exc
    etag = created_index.e_tag
    if not isinstance(etag, str) or not etag.strip() or etag.strip() == "*":
        raise RuntimeError(f"No usable creation ETag for {index_name}; verify ownership before manual cleanup.")
    resources.callback(delete_owned_index, index_client, created_index)
    search = resources.enter_context(SearchClient(endpoint=SEARCH_ENDPOINT, index_name=index_name, credential=credential))
    print("Index created with English text fields and a cosine vector field.")
```

```text
Temporary index: embedding1-cookbook-<random suffix>
Index created with English text fields and a cosine vector field.
```

The index name changes with each run. Keep it handy if cleanup fails.

## Step 3: Upload the policies

Reuse the first vector and embed the other five policies. Check every upload result and wait for all six documents to be available before querying.

```python
with cloud_step():
    passage_embeddings = [(first_vector, first_tokens)]
    passage_embeddings += [embed_text(inference, doc["content"], "text") for doc in documents[1:]]
    payload = [
        {**doc, "embedding_model": MODEL, "content_vector": vector}
        for doc, (vector, _) in zip(documents, passage_embeddings)
    ]
    uploaded = search.upload_documents(documents=payload)
    if len(uploaded) != len(payload) or any(not item.succeeded for item in uploaded):
        raise RuntimeError("At least one document upload failed; no query was run.")
    for attempt in range(30):
        count = search.get_document_count()
        if count == len(payload):
            break
        if attempt < 29:
            time.sleep(2)
    else:
        raise TimeoutError("Documents did not become searchable after 30 checks.")
    print(f"{len(uploaded)} uploaded; {count} searchable.")
```

```text
6 uploaded; 6 searchable.
```

All six policies are available in the index before the queries run.

## Step 4: Embed two questions

Try a paraphrase and a question containing the policy identifier `SEC-07`. Use `kind="query"` so the model treats each as a search query rather than a passage to store.

```python
queries = [
    ("Paraphrase", "Can I get reimbursed for a delayed flight?"),
    ("Policy code", "What does SEC-07 require?"),
]

with cloud_step():
    query_embeddings = {label: embed_text(inference, text, "query") for label, text in queries}
    token_counts = [tokens for _, tokens in passage_embeddings] + [tokens for _, tokens in query_embeddings.values()]
    print(f"Embedded {len(query_embeddings)} questions at {DIMENSIONS} dimensions.")
    if all(tokens is not None for tokens in token_counts):
        print(f"Reported input tokens across all embedding requests: {sum(token_counts)}.")
    else:
        print("Input token usage was not reported for every request; check Azure billing.")
```

```text
Embedded 2 questions at 1536 dimensions.
Reported input tokens across all embedding requests: 205.
```

The 205 input tokens include both questions and all six policies.

## Step 5a: Run keyword search

Use the default keyword mode (`any`) over the English text fields. Count the returned hits and note their IDs. In this example `top` limits the displayed results to three, so the count is not a total-match count.

```python
with cloud_step():
    keyword = {
        label: list(search.search(search_text=text, search_fields=["title", "content"], select=["id"], top=TOP_K))
        for label, text in queries
    }
    for label, hits in keyword.items():
        print(f"{label}: {len(hits)} keyword results; {[hit['id'] for hit in hits]}")
```

```text
Paraphrase: 0 keyword results; []
Policy code: 1 keyword results; ['security']
```

Keyword search found the policy-code match but missed the paraphrased travel question.

## Step 5b: Run vector search

Use exhaustive cosine search for this tiny corpus. For this single cosine query, convert [Search's vector score](https://learn.microsoft.com/azure/search/vector-search-ranking#scores-in-a-vector-search-results) back to cosine similarity as `2 - 1 / score`. Do not apply that formula to keyword, hybrid, or reranker scores.

```python
def vector_query(vector: list[float], k: int = TOP_K) -> VectorizedQuery:
    return VectorizedQuery(vector=vector, fields="content_vector", k_nearest_neighbors=k, exhaustive=True)

def retrieve(search, question: str, vector: list[float], *, semantic: bool = False) -> list[dict]:
    options = {"search_fields": ["title", "content"]}
    if semantic:
        options.update(query_type="semantic", semantic_configuration_name=SEMANTIC_CONFIG)
    return list(search.search(
        search_text=question, vector_queries=[vector_query(vector, SEMANTIC_K if semantic else TOP_K)],
        select=["id", "title", "content"], top=TOP_K, **options,
    ))

with cloud_step():
    vector_hits = {}
    for label, _ in queries:
        vector, _ = query_embeddings[label]
        hits = list(search.search(vector_queries=[vector_query(vector)], select=["id"], top=TOP_K))
        vector_hits[label] = hits
        print(f"{label}:")
        for hit in hits:
            score = hit["@search.score"]
            print(f"  {hit['id']}: score {score:.4f}, cosine {2 - 1 / score:.4f}")
```

```text
Paraphrase:
  travel: score 0.6965, cosine 0.5643
  baggage: score 0.6625, cosine 0.4906
  booking: score 0.6128, cosine 0.3681
Policy code:
  security: score 0.6669, cosine 0.5006
  leave: score 0.5782, cosine 0.2706
  equipment: score 0.5728, cosine 0.2541
```

Vector search ranked the relevant policy first for both questions in this run. The scores are not probabilities or relevance labels.

## Step 5c: Run hybrid search

Send text and vector in one request. Search combines the two rankings with [Reciprocal Rank Fusion (RRF)](https://learn.microsoft.com/azure/search/hybrid-search-ranking). Start here when your users need both wording and meaning, but compare the top IDs against the baselines: an RRF score isn't comparable to a cosine or keyword score.

```python
def top_id(hits):
    return hits[0]["id"] if hits else "(no match)"

with cloud_step():
    hybrid = {}
    for label, text in queries:
        vector, _ = query_embeddings[label]
        hits = retrieve(search, text, vector)
        hybrid[label] = hits
        print(f"{label}: " + ", ".join(f"{h['id']} (RRF {h['@search.score']:.4f})" for h in hits))

    print("| Mode | Paraphrase | Policy code |")
    print("| --- | --- | --- |")
    for mode, results in (("Keyword", keyword), ("Vector", vector_hits), ("Hybrid", hybrid)):
        print(f"| {mode} | " + " | ".join(top_id(results[label]) for label, _ in queries) + " |")
    if hybrid["Paraphrase"]:
        hit = hybrid["Paraphrase"][0]
        print(f"Top paraphrase match: {hit['title']}")
        print(hit["content"])
```

```text
Paraphrase: travel (RRF 0.0167), baggage (RRF 0.0164), booking (RRF 0.0161)
Policy code: security (RRF 0.0333), leave (RRF 0.0164), equipment (RRF 0.0161)
```

| Mode | Paraphrase | Policy code |
| --- | --- | --- |
| Keyword | (no match) | security |
| Vector | travel | security |
| Hybrid | travel | security |

```text
Top paraphrase match: Travel disruption expenses
Policy TRV-12. When an air trip disruption leaves an employee stranded overnight, the company covers reasonable hotel and meal expenses. Submit receipts to the travel team within 30 days.
```

Hybrid recovered the paraphrase like vector search did, and `security` ranked first in both inputs to RRF for the policy-code query. Hybrid did not improve the top hit over vector alone on these two questions. Test labeled queries to see when fusing the two rankings helps your application.

## Step 5d: Optionally add semantic ranking

Set `RUN_SEMANTIC_RANKER=1` before starting the kernel only if semantic ranking is already enabled on your service and you're comfortable with its [separate billing](https://learn.microsoft.com/azure/search/semantic-how-to-enable-disable). The ranker reorders the hybrid candidates based on their text. The optional query asks for up to 50 vector candidates following [semantic hybrid query guidance](https://learn.microsoft.com/azure/search/hybrid-search-how-to-query); this six-document index can supply at most six.

```python
with cloud_step():
    if RUN_SEMANTIC:
        for label, text in queries:
            vector, _ = query_embeddings[label]
            reranked = retrieve(search, text, vector, semantic=True)
            print(f"{label} after semantic ranking: {[hit['id'] for hit in reranked]}")
    else:
        print("Semantic ranking skipped (opt-in).")
```

```text
Paraphrase after semantic ranking: ['travel', 'booking', 'baggage']
Policy code after semantic ranking: ['security', 'travel', 'booking']
```

The optional semantic query kept both top matches but changed the lower-ranked hits. It also used a larger candidate pool than the baseline, so the change isn't attributable to reranking alone. Without the opt-in, this cell prints `Semantic ranking skipped (opt-in).`

## Step 6: Clean up

Delete the temporary index and close the Azure clients. This is the only resource the notebook creates. If creation or deletion wasn't confirmed, verify ownership before manual cleanup. This cell also works after a handled failure.

```python
resources.close()
print("Azure clients closed.")
```

```text
Temporary index deleted.
Azure clients closed.
```

If cleanup already ran after a handled failure, you won't see the deletion message again.

## Make it yours

Copy the Configuration cell, `embed_text`, `vector_query`, and `retrieve`. Keep the model, vector type, dimensions, and index metric consistent when you index and query.

| Sample choice | Change for your application |
| --- | --- |
| Six fictional policies | Chunk your documents. Inputs over 8,192 tokens can be truncated. Re-embed when text changes. |
| English analyzer and embedded policy codes | Pick the language analyzer for your corpus. If a query must match an exact code, add a dedicated filterable code field and use an equality filter; hybrid alone isn't a guarantee. |
| 1,536-dimensional float32 vectors | Test another supported dimension in a separate index and re-embed the corpus. [`Collection(Edm.Half)`](https://learn.microsoft.com/azure/search/vector-search-how-to-assign-narrow-data-types) is a way to reduce raw storage after testing its quality impact. |
| Exhaustive search, three displayed results | Measure approximate HNSW recall against exhaustive search on a labeled sample. Tune candidate count and query latency separately from the number of hits you display. |
| CLI identity for a local notebook | Use an explicitly configured managed identity in Azure and assign the same scoped roles. |

For larger corpora, bound concurrent embedding requests, respect `Retry-After`, and use [bounded Search upload batches](https://learn.microsoft.com/azure/search/search-how-to-large-index). Measure recall at your chosen `k`, latency, and total cost on labeled questions before deploying. For images or multi-vector output, see the [model documentation](https://learn.microsoft.com/azure/cosmos-db/gen-ai/microsoft-embedding-1); this recipe is text-only.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Inference setup fails | Register `Microsoft.InferenceService` and choose a supported region. |
| Embedding call returns 403 | Assign **Embedding User** on the companion inference account, not the Cosmos DB database account. Verify the signed-in identity. |
| Search returns 401 or 403 | Check the service endpoint, role-based access, and both Search roles. |
| Upload rejects vectors | Match the embedding dimensions and field type to the index definition. |
| Keyword results include unrelated policies | Inspect the terms produced by your language analyzer and evaluate a dedicated filter for literal codes. |
| Hybrid scores look small | RRF scores use a different scale from keyword and vector scores. |
| Semantic query fails with a plan or quota error | Skip the optional step or check the semantic ranker plan and remaining usage with the service owner. |
| Index creation or cleanup is uncertain | Verify ownership of the printed index before any manual deletion. |