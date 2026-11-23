**Bring your own vector store: LlamaCloud Index V2 → Azure AI Search**

LlamaCloud parses; you choose where the result lives. Land LlamaCloud-parsed documents in **your
own** Azure AI Search index using the official
[`index-v2-data-sinks`](https://github.com/run-llama/index-v2-data-sinks) exporter — one call and no
indexing code — then query it with LlamaIndex Retrieval Harness primitives your agents can use.

This cookbook builds on the official LlamaIndex ↔ Azure AI Search integration and extends it to
LlamaCloud's Index V2 export path.

| | |
|---|---|
| **Difficulty** | Intermediate |
| **Time to complete** | ~15 min |
| **Est. cost** | ~$0 incremental if you already run an Azure AI Search service (a few dozen small embedding calls; the demo index is deleted at the end). A dedicated Basic service is ~$75/mo if you create one just for this. |

## What you'll build, and why it matters

LlamaCloud's **Index V2** splits two things that vector databases usually weld together:
**parsing** (turning messy PDFs/HTML into clean, page-aware markdown) and **storage** (where the
embedded chunks live). Index V2 does the parsing and sync; the official `index-v2-data-sinks`
package lets you send the result to a store **you** own.

By the end you'll have run the Azure AI Search sink end-to-end against your own service — using
Entra ID rather than Azure service keys — verified the scope fields the exporter writes, and
layered LlamaIndex **Retrieval Harness** primitives (**List Files**, **File Grep**, **File Read**,
**Hybrid Retrieve**) on top. Every claim below is checked with an assertion as the notebook runs.

**Why Azure AI Search as the sink (the customer value):**

- **Your data stays in your tenant.** Chunks and vectors land in *your* Azure AI Search — your
  subscription, your network, your Entra ID identities and RBAC — not a third-party managed index.
  Access is governed by Azure RBAC on the service; the exporter additionally stamps `tenant_id` and
  `export_config_id` on every chunk so queries can be *scoped* server-side (see Step 4 for what
  that does and does not guarantee).
- **Zero indexing code to write or maintain.** The sink auto-provisions a hybrid-ready index (HNSW
  vectors + a searchable `content` field), writes deterministic document keys, does idempotent
  upserts, per-file replace, and exposes incremental-sync snapshots. You call one function.
- **One step from agentic retrieval.** An index landed here can be wrapped as a knowledge source
  and queried by an Azure AI Search knowledge base — query decomposition, parallel subqueries,
  semantic reranking, and grounded answers. This gives Azure AI Search a documented path from
  exported chunks to Foundry IQ agentic retrieval.
- **Reuse what you already run.** Land LlamaCloud-parsed content next to everything else in Azure
  AI Search and query it with the same security, hybrid ranking, and tooling — no new datastore to
  buy, secure, or operate.
- **Agent-ready by construction.** Because the exported index keeps `parsed_directory_file_id` and
  `content`, it doubles as a filesystem-style surface agents can List / Grep / Read — not just a
  fuzzy semantic search box.

![LlamaCloud Index V2 to Azure AI Search architecture, three columns left to right. Column 1, Parse + chunk: your documents flow into LlamaCloud Index V2 (parse + sync), which emits a ParseSyncOutput into index-v2-data-sinks (chunk + embed + export) — the official exporter, one call, no indexing code. Column 2, Your Azure AI Search: the exporter writes a hybrid-ready index (HNSW vectors + BM25 content) that stamps tenant_id and export_config_id on every chunk so queries can be scoped server-side, runs on Entra ID + RBAC in your subscription and network, and supports idempotent upserts, per-file replace, and sync snapshots. Column 3, Retrieval Harness to agents: the index exposes List Files, File Grep, File Read, and Hybrid Retrieve to your agents; the next step wraps the index as a knowledge source into a Foundry IQ knowledge base for agentic retrieval and an MCP tool.](media/llamacloud-index-v2-azure-ai-search/01-architecture.png)

## Prerequisites

- **Python 3.11–3.13** — the pinned `index-v2-data-sinks` commit declares
  `requires-python = ">=3.11,<3.14"`, so 3.14 is not supported.
- An **Azure AI Search** service. Any tier works for this demo; hybrid + semantic ranking on your
  own data wants Basic or higher.
- An **Azure OpenAI** (Microsoft Foundry) embedding deployment. This recipe supports
  `text-embedding-3-large` (3072-dim, default), `text-embedding-3-small` (1536-dim), or
  `text-embedding-ada-002` (1536-dim).
- **Keyless auth (the default path):** run `az login`, then assign these roles **to your own
  identity** (not to the service):
  - On the search service: `Search Service Contributor` (create/delete indexes) and
    `Search Index Data Contributor` (write and query documents)
  - On the Azure OpenAI resource: `Cognitive Services OpenAI User`

  This notebook calls the direct `/openai/v1` endpoint, so `Cognitive Services OpenAI User` is
  sufficient for embeddings. `Foundry User` is required only when you call a **Foundry project**
  endpoint for Foundry SDK, agents, or project tools.

  Role assignments take a few minutes to propagate — a `403` immediately after assigning is
  usually not a misconfiguration. Wait and retry.
- **~15 minutes.** The demo index is deleted at the end, so incremental cost is negligible.

Set these in your shell or a local `.env` next to this notebook (the repo `.gitignore` excludes `.env`):

```bash
SEARCH_ENDPOINT=https://<your-search-service>.search.windows.net
AOAI_ENDPOINT=https://<your-foundry-resource>.openai.azure.com
AOAI_EMBEDDING_DEPLOYMENT=<your-deployment-for-large-small-or-ada-002>
SEARCH_API_KEY=      # optional fallback ONLY if you can't get RBAC — leave unset for keyless
AOAI_API_KEY=        # optional fallback ONLY if you can't get RBAC — leave unset for keyless
```

> **Keyless for the Azure services used here.** No Azure API key value is embedded in this
> notebook: leave the key variables unset and the sink uses `DefaultAzureCredential`, so the
> Azure write path runs on your Entra ID identity. The production `export_pipeline` path is a
> separate matter — it still needs a `LLAMA_CLOUD_API_KEY` and credentials for whichever
> embedding provider you configure.

## Setup

Pinned to an exact commit — `index-v2-data-sinks` ships from GitHub (not PyPI) and has no releases,
so an unpinned install would drift the moment the repo moves. The Azure SDKs are pinned explicitly
rather than left to the sink's `>=` floors. The install runs unconditionally so a previously
installed revision can't silently change the behavior you see below.

```python
%%capture
# Installed unconditionally rather than behind a `try: import ... except ImportError`
# guard: a different revision already present in the environment would otherwise
# shadow the pinned commit, and you'd be reading results this recipe never verified.
# `--upgrade` makes pip re-resolve the direct git reference instead of keeping
# whatever is already installed. The pinned commit declares requires-python ">=3.11,<3.14".
%pip install --quiet --upgrade "index-v2-data-sinks@git+https://github.com/run-llama/index-v2-data-sinks@798cac7e25f7485aa78b5f666957af41cae62c2f" "azure-search-documents==12.0.0" "azure-identity==1.25.3" "openai==1.109.1" "beautifulsoup4==4.13.3" "python-dotenv==1.2.2"
```

## Configuration — the only cell you edit

Every knob lives here, named, so the rest of the notebook has no magic numbers. This is the cell the
copy-paste reader changes and nothing else.

```python
# --- Configuration ---------------------------------------------------------
# Index naming. The sink provisions ONE index per embedding model; the default
# model keeps the base name, others get a sanitized suffix.
#
# The prefix carries a short random suffix so this demo always creates its OWN
# index. A fixed, predictable name would let this notebook delete an index that
# an earlier run — or a colleague on the same service — is still using.
import uuid

RUN_ID = uuid.uuid4().hex[:8]
INDEX_PREFIX = f"forgebook-index-v2-sink-{RUN_ID}"

# Which model the sink sizes the index for. The Azure OpenAI deployment configured
# below must be the same base model, or query-time vectors and the index dimension will diverge.
EMBEDDING_MODELS = {
    "openai:text-embedding-3-large": 3072,
    "openai:text-embedding-3-small": 1536,
    "openai:text-embedding-ada-002": 1536,
}
EMBEDDING_MODEL = "openai:text-embedding-3-large"  # Change this with your deployment.
EMBEDDING_DIM = EMBEDDING_MODELS[EMBEDDING_MODEL]
AOAI_API_VERSION = "2024-10-21"   # Azure OpenAI data-plane api-version
EMBED_BATCH = 16                  # chunks embedded per Azure OpenAI call


def sink_index_name(prefix, embedding_model):
    """Match the official sink's one-index-per-model naming convention."""
    if embedding_model == "openai:text-embedding-3-small":
        return prefix
    suffix = embedding_model.replace(":", "-").replace("/", "-").replace(".", "-").replace("_", "-").lower()
    return f"{prefix}-{suffix}"


INDEX_NAME = sink_index_name(INDEX_PREFIX, EMBEDDING_MODEL)

# How the sink chunks each document: "fast" | "sentence" | "token".
CHUNK_STRATEGY = "sentence"

# Tenant + export-config labels written onto every chunk. In production these are
# your LlamaCloud project id and export-config id; here they're the scope fields
# queries can filter on, and the scope the sink uses for per-file replace and snapshots.
PROJECT_ID = "forgebook-demo"     # -> tenant_id on every document
CONFIG_ID = "forgebook-config"    # -> export_config_id; the snapshot/delete scope

# Retrieval Harness knobs.
TOP_K = 5        # final hits returned by Hybrid Retrieve
K_NEAREST = 50   # vector candidates fused before ranking; raise for recall
GREP_TOP = 50    # max chunks File Grep scans in one file
READ_TOP = 1000  # whole-file ceiling for File Read
LIST_TOP = 1000  # max docs List Files scans to build the map

# The demo corpus: three Paul Graham essays, each becomes one "file".
ESSAYS = {
    "great-work": "https://paulgraham.com/greatwork.html",
    "superlinear": "https://paulgraham.com/superlinear.html",
    "how-to-do-what-you-love": "https://paulgraham.com/love.html",
}
# ---------------------------------------------------------------------------
print(f"Config set. Index '{INDEX_NAME}' (unique to this run), {len(ESSAYS)} source files, top_k={TOP_K}.")
```

## Connect to your services — keyless by default

We resolve one `DefaultAzureCredential` for everything: your own Azure AI Search clients, the
Azure OpenAI embedding client, and the sink (its `AzureSearchService` reads
`DEFAULT_INDEX_AZURE_SEARCH_*` env vars and falls back to Entra ID when no key is set). If you set
the fallback keys in `.env`, they win — but the default path never touches one.

```python
import os

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv(override=True)


def env(name, *, required=True, default=None):
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required env var: {name}. See Prerequisites.")
    return value or None


SEARCH_ENDPOINT = env("SEARCH_ENDPOINT")
AOAI_ENDPOINT = env("AOAI_ENDPOINT").split("/openai/", 1)[0].rstrip("/")
EMBED_DEPLOYMENT = env(
    "AOAI_EMBEDDING_DEPLOYMENT",
    required=False,
    default="text-embedding-3-large",
)  # Use the same base model as EMBEDDING_MODEL.

# Optional key fallback — leave both unset for the keyless default path.
SEARCH_API_KEY = env("SEARCH_API_KEY", required=False)
AOAI_API_KEY = env("AOAI_API_KEY", required=False)

# The sink's AzureSearchService reads its target from these env vars. With no
# API key set, it resolves DefaultAzureCredential — the same identity as ours.
os.environ["DEFAULT_INDEX_AZURE_SEARCH_ENDPOINT"] = SEARCH_ENDPOINT
os.environ["DEFAULT_INDEX_AZURE_SEARCH_INDEX_PREFIX"] = INDEX_PREFIX
if SEARCH_API_KEY:
    os.environ["DEFAULT_INDEX_AZURE_SEARCH_API_KEY"] = SEARCH_API_KEY

# Credential for the clients this notebook creates directly.
search_credential = AzureKeyCredential(SEARCH_API_KEY) if SEARCH_API_KEY else DefaultAzureCredential()

if AOAI_API_KEY:
    aoai = AzureOpenAI(
        azure_endpoint=AOAI_ENDPOINT,
        api_key=AOAI_API_KEY,
        api_version=AOAI_API_VERSION,
    )
else:
    aoai = AzureOpenAI(
        azure_endpoint=AOAI_ENDPOINT,
        azure_ad_token_provider=get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        ),
        api_version=AOAI_API_VERSION,
    )


def _escape_odata(value):
    """OData string literals escape embedded single quotes by doubling them.
    Anything interpolated into a filter goes through this."""
    return value.replace("'", "''")


def embed(texts):
    """Embed with your Azure OpenAI deployment, batched."""
    vectors = []
    for i in range(0, len(texts), EMBED_BATCH):
        response = aoai.embeddings.create(
            model=EMBED_DEPLOYMENT,
            input=texts[i : i + EMBED_BATCH],
        )
        vectors.extend(item.embedding for item in response.data)
    return vectors


auth_mode = "API key (fallback)" if SEARCH_API_KEY else "Entra ID (keyless)"
print(f"Auth: {auth_mode} | embeddings: {EMBED_DEPLOYMENT} | sink will provision: {INDEX_NAME}")
```

## Verify setup

Fail loud *now* — on the pinned versions, the credential, and the embedding deployment — instead of
20 cells later inside an export call. A `403` here on the keyless path almost always means a role
hasn't finished propagating; see Prerequisites.

```python
import importlib.metadata as md
import json
import sys

# --- The environment is what we pinned -------------------------------------
PINNED_SHA = "798cac7e25f7485aa78b5f666957af41cae62c2f"
INSTALL_CMD = (
    '%pip install --quiet --upgrade '
    '"index-v2-data-sinks@git+https://github.com/run-llama/index-v2-data-sinks@' + PINNED_SHA + '" '
    '"azure-search-documents==12.0.0" "azure-identity==1.25.3"'
)

assert (3, 11) <= sys.version_info[:2] < (3, 14), (
    f"index-v2-data-sinks requires Python >=3.11,<3.14; this kernel is "
    f"{sys.version_info.major}.{sys.version_info.minor}. Switch kernels and re-run."
)

sink_dist = md.distribution("index-v2-data-sinks")
sink_sha = (json.loads(sink_dist.read_text("direct_url.json") or "{}")
            .get("vcs_info", {}).get("commit_id"))
assert sink_sha == PINNED_SHA, (
    f"index-v2-data-sinks is at {sink_sha}, expected {PINNED_SHA}. "
    f"Re-run the setup cell, or:\n    {INSTALL_CMD}"
)

for pkg, want in [("azure-search-documents", "12.0.0"), ("azure-identity", "1.25.3")]:
    got = md.version(pkg)
    assert got == want, f"{pkg} is {got}, expected {want}. Fix with:\n    {INSTALL_CMD}"

# --- The credential and the embedding deployment work ----------------------
from azure.search.documents.indexes import SearchIndexClient

probe = embed(["setup probe"])[0]
assert len(probe) == EMBEDDING_DIM, (
    f"Embedding returned {len(probe)} dims, expected {EMBEDDING_DIM} for {EMBEDDING_MODEL} — "
    f"is AOAI_EMBEDDING_DEPLOYMENT a deployment of that model?"
)

index_client = SearchIndexClient(SEARCH_ENDPOINT, search_credential)
existing = list(index_client.list_index_names())
assert INDEX_NAME not in existing, (
    f"'{INDEX_NAME}' already exists. The run id is random, so this is a collision — "
    f"re-run the Configuration cell to draw a new one."
)

print(f"Setup OK — sink @ {sink_sha[:7]}, Python {sys.version_info.major}.{sys.version_info.minor}, "
      f"embeddings return {len(probe)} dims.")
print(f"Azure AI Search reachable ({len(existing)} indexes); '{INDEX_NAME}' is free to create.")
```

## How you'd run this in production — one call

Point the sink at a LlamaCloud Index V2 directory and it pulls the parse outputs, chunks, embeds, and
writes to Azure AI Search for you:

```python
from index_v2_data_sinks.pipeline import export_pipeline

await export_pipeline(
    export_to="azure_search",
    directory_name="my-index-directory",
    project_id="<llamacloud-project-id>",
    config_id="<export-config-id>",
    embedding_model="openai:text-embedding-3-small",
    chunking_strategy="sentence",
)
```

That production path is **not** keyless: it needs a `LLAMA_CLOUD_API_KEY`, a parsed Index V2
directory, and credentials for your embedding provider. The keyless story in this notebook is
specifically about the **Azure** services — AI Search and Azure OpenAI — which is the part a
security review cares about. To keep
this notebook runnable on *just* Azure — no LlamaCloud account — we call the sink's own components
directly. Internally `export_pipeline` is exactly:

> build a `ParseSyncOutput` → chunk it (`ChunkerService`) → build `ExportedOutputV1` records → `AzureSearchExporter.export(...)`

We do the same, sourcing the `ParseSyncOutput` locally and the embeddings from Azure OpenAI.
**Everything that touches Azure AI Search is the unmodified official package.**

## Step 1 — Build parse outputs and chunk them (with the package)

We download three Paul Graham essays and wrap each as a `ParseSyncOutput` — the shape LlamaCloud hands
the sink. Then we chunk with the package's `ChunkerService` and build `ExportedOutputV1` records, the
exact calls `export_pipeline` makes internally.

```python
import re
import urllib.request

from bs4 import BeautifulSoup
from index_v2_data_sinks.chunking import ChunkerService
from index_v2_data_sinks.schema import ExportedOutputV1, ParsedPage, ParseSyncOutputV1


def fetch_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="ignore")
    return re.sub(r"\n{3,}", "\n\n", BeautifulSoup(html, "html.parser").get_text("\n")).strip()


chunker = ChunkerService()
files = {}  # parsed_directory_file_id -> list[ExportedOutputV1]
for file_id, url in ESSAYS.items():
    page_text = fetch_text(url)
    parse_output = ParseSyncOutputV1(pages=[ParsedPage(page_number=1, text=page_text)])
    # Single-page docs, so the chunker input is the page text itself.
    # ExportedOutputV1.build maps each chunk back to its page range internally.
    chunks = chunker.chunk(page_text, CHUNK_STRATEGY)
    files[file_id] = [
        ExportedOutputV1.build(parse_output, PROJECT_ID, CONFIG_ID, chunk, file_id, metadata={"file_name": file_id})
        for chunk in chunks
    ]
    print(f"{file_id:>26}: {len(files[file_id]):3d} chunks")
```

Each essay is now a list of `ExportedOutputV1` records carrying the chunk text, page range, and the
tenant/config scope — everything the sink needs, and nothing about Azure yet.

## Step 2 — Export to Azure AI Search via the official sink

`AzureSearchExporter.export(...)` provisions the index on first call (HNSW vectors, a searchable
`content` field, filterable scoping fields), then upserts the chunks with their embeddings. We embed
each file with Azure OpenAI and hand the vectors to the exporter. `export()` is async, so we `await`
it.

Nothing is deleted here. `INDEX_NAME` carries this run's random suffix and the previous cell asserted
it doesn't exist yet, so the exporter creates a fresh index and this notebook can never clobber an
index that something else owns.

```python
from index_v2_data_sinks.export.azure_search import AzureSearchExporter

exporter = AzureSearchExporter()

# Record what this run creates so the teardown cell deletes only this, and only
# if the export actually got that far.
CREATED_INDEXES = set()

total = 0
for file_id, outputs in files.items():
    embeddings = embed([o.content for o in outputs])
    assert len(embeddings) == len(outputs), (
        f"{file_id}: {len(embeddings)} embeddings for {len(outputs)} chunks — these must be 1:1."
    )
    await exporter.export(
        outputs,
        project_id=PROJECT_ID,
        embeddings=embeddings,
        embedding_model=EMBEDDING_MODEL,
    )
    CREATED_INDEXES.add(INDEX_NAME)
    total += len(outputs)
    print(f"exported {file_id}: {len(outputs)} chunks")

expected_total = sum(len(o) for o in files.values())
assert total == expected_total, f"Exported {total} chunks, expected {expected_total}."
assert INDEX_NAME in index_client.list_index_names(), (
    f"The exporter did not create '{INDEX_NAME}'."
)

print(f"\nExported {total} chunks via the official AzureSearchExporter into '{INDEX_NAME}'.")
print(f"Created by this run (teardown will delete only this): {sorted(CREATED_INDEXES)}")
```

That's the whole write path — no index schema, no field definitions, no upload loop, and no key
written by you. The sink owned all of it, on your Entra ID identity.

## Step 3 — Inspect the auto-provisioned index

Let's see what the sink actually built. The schema and the deterministic
`{parsed_directory_file_id}__{chunk_index}` document key both come straight from the package. Note
the scoping fields — `tenant_id` and `export_config_id` — on every document; we'll use them next.

```python
import time

from azure.search.documents import SearchClient

search_client = SearchClient(SEARCH_ENDPOINT, INDEX_NAME, search_credential)


def wait_for_docs(client, target, timeout=30):
    """Azure AI Search indexing is near-real-time, not instant — poll until
    the document count reaches the target (or the timeout passes)."""
    for _ in range(timeout):
        if client.get_document_count() >= target:
            break
        time.sleep(1)
    return client.get_document_count()


count = wait_for_docs(search_client, total)
assert count == total, (
    f"Index holds {count} documents, expected {total}. Azure AI Search indexing is "
    f"near-real-time — if this is short, raise the wait_for_docs timeout and re-run."
)

schema = index_client.get_index(INDEX_NAME)
field_names = {f.name for f in schema.fields}
for required in ("id", "content", "embedding", "tenant_id", "export_config_id", "parsed_directory_file_id", "chunk_index"):
    assert required in field_names, f"The sink did not provision the '{required}' field."

vector_field = next(f for f in schema.fields if f.name == "embedding")
assert vector_field.vector_search_dimensions == EMBEDDING_DIM, (
    f"Index vector field is {vector_field.vector_search_dimensions}-dim, but {EMBEDDING_MODEL} "
    f"produces {EMBEDDING_DIM}-dim vectors."
)
print("Index fields:", [f.name for f in schema.fields])
print("Documents:", count)

doc = next(iter(search_client.search(
    search_text="*",
    select=["id", "parsed_directory_file_id", "tenant_id", "chunk_index", "content"],
)))
print("\nRaw document:")
print("  id:", doc["id"])
print("  tenant_id:", doc["tenant_id"], "| file:", doc["parsed_directory_file_id"], "| chunk_index:", doc["chunk_index"])
print("  content:", " ".join(doc["content"].split())[:160], "...")
```

The assertion above is the real check: the sink provisioned a `content` field (searchable, for BM25)
and an `embedding` field sized to the model — side by side, which is what makes the index
hybrid-ready out of the box — plus `tenant_id` and `export_config_id` stamped on every chunk.

## Step 4 — Scoped retrieval on the fields the sink stamps

The exporter writes `tenant_id` (your LlamaCloud project) and `export_config_id` onto every chunk.
Filter on them and the narrowing happens **in the service**: Azure AI Search never scores, ranks, or
returns the excluded documents, so out-of-scope content can't reach your model's context window and
you're not paying to post-filter results in the client.

> **Read this before you rely on it.** An OData filter is a *query scope*, not an authorization
> boundary. Nothing here verifies that the caller is entitled to the `tenant_id` they pass — any
> client holding a credential that can query this index can supply a different value, or omit the
> filter entirely, and read everything. What actually restricts access is Azure RBAC on the search
> service, which is why the keyless setup above matters.
>
> To make per-user entitlement enforceable at query time, use
> [security trimming](https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search) — store permission identifiers on each document and filter against the
> caller's verified group membership, applied server-side from a token the client can't forge. That
> changes the index schema and the query path, so it's out of scope here.

With that stated plainly, here's what the scoping actually does:

```python
same_query = "What does it take to do great work?"


def scoped(tenant):
    return list(search_client.search(
        search_text=same_query,
        filter=f"tenant_id eq '{_escape_odata(tenant)}'",
        select=["parsed_directory_file_id", "chunk_index", "tenant_id"],
        top=TOP_K,
    ))


mine = scoped(PROJECT_ID)
other = scoped("another-tenant")
unscoped = list(search_client.search(search_text=same_query, select=["tenant_id"], top=TOP_K))

assert mine, f"Expected hits for tenant '{PROJECT_ID}'."
assert all(r["tenant_id"] == PROJECT_ID for r in mine), "A scoped query returned an out-of-scope document."
assert not other, f"Expected 0 hits for an unused scope, got {len(other)}."
assert unscoped, "Expected the unfiltered query to return documents."

print(f"scope '{PROJECT_ID}': {len(mine)} hits  |  scope 'another-tenant': {len(other)} hits")
print(f"no filter at all:     {len(unscoped)} hits  <- the same caller, unscoped, sees everything")
```

Two results worth separating. The scoped queries behave exactly as advertised — the service returns
only in-scope chunks, verified by assertion, and the excluded ones are never ranked or billed for.
The third line is the honest counterweight: the *same* credential with no filter reads the whole
index. Scoping is a correctness and cost control you apply on the query path. Entitlement is Azure
RBAC's job, and per-user entitlement is security trimming's.

## Step 5 — LlamaIndex Retrieval Harness primitives on the sink index

LlamaIndex's **Retrieval Harness** defines the primitives an agent needs over a corpus: **List
Files**, **File Grep**, **File Read**, and a high-recall **Hybrid Retrieve**. Because the sink
lands `parsed_directory_file_id`, `chunk_index`, and a searchable `content` field next to the
vector, all four run natively against Azure AI Search — no extra schema, no second store. We wrap
the raw SDK so every result stays inspectable (scores included).

> The sink doesn't provision a semantic-reranker config, so **Hybrid Retrieve** here is vector + BM25
> fusion. Add a semantic configuration to the index if you want Azure's reranker on top.

```python
from azure.search.documents.models import VectorizedQuery


class SinkRetrievalHarness:
    """Retrieval Harness primitives over an index-v2-data-sinks Azure AI Search index."""

    def __init__(self, client, embed_fn):
        self.client = client
        self.embed_fn = embed_fn
        self.select = ["parsed_directory_file_id", "chunk_index", "content"]

    def hybrid_retrieve(self, query, top_k=TOP_K, k_nearest=K_NEAREST):
        """High-recall first pass: vector + BM25 fusion over the sink index."""
        vector = self.embed_fn([query])[0]
        results = self.client.search(
            search_text=query,
            vector_queries=[VectorizedQuery(vector=vector, k_nearest_neighbors=k_nearest, fields="embedding")],
            select=self.select,
            top=top_k,
        )
        return [self._row(r) for r in results]

    def list_files(self, top=LIST_TOP):
        """Map the corpus: every parsed_directory_file_id and its chunk count."""
        results = self.client.search(search_text="*", select=["parsed_directory_file_id"], top=top)
        counts = {}
        for r in results:
            counts[r["parsed_directory_file_id"]] = counts.get(r["parsed_directory_file_id"], 0) + 1
        return [{"file": name, "chunks": n} for name, n in sorted(counts.items())]

    def file_grep(self, file_id, term, top=GREP_TOP):
        """Server-side term scan of one file. Matching goes through the query
        analyzer — tokenized and case-insensitive, not byte-exact."""
        odata = (
            f"parsed_directory_file_id eq '{_escape_odata(file_id)}' and "
            f"search.ismatch('{_escape_odata(term)}', 'content', 'full', 'any')"
        )
        results = self.client.search(search_text="*", filter=odata, select=self.select, top=top)
        return sorted((self._row(r) for r in results), key=lambda d: d["chunk_index"])

    def file_read(self, file_id, top=READ_TOP):
        """Pull a whole file back in chunk order."""
        results = self.client.search(
            search_text="*",
            filter=f"parsed_directory_file_id eq '{_escape_odata(file_id)}'",
            select=self.select,
            top=top,
        )
        return sorted((self._row(r) for r in results), key=lambda d: d["chunk_index"])

    def _row(self, r):
        return {
            "file": r.get("parsed_directory_file_id"),
            "chunk_index": r.get("chunk_index"),
            "score": r.get("@search.score"),
            "text": r.get("content"),
        }


harness = SinkRetrievalHarness(search_client, embed)


def show(rows, n=200):
    for r in rows:
        head = f"[{r['file']} #{r['chunk_index']:>3}]"
        if r.get("score") is not None:
            head += f"  score={r['score']:.4f}"
        print(head)
        print("  ", " ".join((r.get("text") or "").split())[:n], "...\n")


print("Harness ready:", ["hybrid_retrieve", "list_files", "file_grep", "file_read"])
```

### Hybrid Retrieve — find where an answer lives

One call embeds the query, runs a vector search, and fuses it with BM25. This is the agent's fast,
high-recall first pass over the whole corpus.

```python
answers = harness.hybrid_retrieve("What does it take to do great work?")

assert len(answers) == TOP_K, f"Hybrid Retrieve returned {len(answers)} hits, expected top_k={TOP_K}."
assert all({"file", "chunk_index", "score", "text"} <= r.keys() for r in answers), "Unexpected row shape."
assert all(r["score"] is not None and r["text"] for r in answers), "Every hit should carry a score and text."
assert answers == sorted(answers, key=lambda r: -r["score"]), "Hits should arrive ranked."

show(answers)
```

Top hits are the essay's thesis chunks, returned in rank order with fused relevance scores you can
inspect directly — asserted above, not just eyeballed.

### List Files — map the corpus

Before an agent reads or greps, it needs the directory. `list_files` returns every file and its chunk
count, straight from the `parsed_directory_file_id` field the sink wrote.

```python
listing = harness.list_files()

assert {f["file"] for f in listing} == set(ESSAYS), (
    f"List Files saw {sorted(f['file'] for f in listing)}, expected {sorted(ESSAYS)}."
)
assert sum(f["chunks"] for f in listing) == total, (
    f"Chunk counts sum to {sum(f['chunks'] for f in listing)}, expected {total}."
)

for f in listing:
    print(f"{f['file']:>26}  ({f['chunks']} chunks)")
```

Every source file, each with its chunk count, and the counts sum to exactly what was exported — the
corpus as a filesystem listing.

### File Grep — term scan inside one file

When the agent needs occurrences of a specific term, it scans a single file server-side
(`search.ismatch` scoped by an OData filter), spending no tokens on irrelevant chunks. One honesty
note: `search.ismatch` runs through the **query analyzer**, so matching is tokenized and
case-insensitive — closer to `grep -iw` than byte-exact `grep`. For byte-exact matching you'd add
a field with the `keyword` analyzer.

```python
TERM, TARGET_FILE = "exponential", "superlinear"
hits = harness.file_grep(TARGET_FILE, TERM)

assert hits, f"Expected at least one '{TERM}' hit in {TARGET_FILE}."
assert all(h["file"] == TARGET_FILE for h in hits), "File Grep leaked chunks from another file."
assert all(TERM in (h["text"] or "").lower() for h in hits), (
    f"Every hit should contain '{TERM}' — the analyzer is case-insensitive, so compare lowercased."
)
assert not harness.file_grep(TARGET_FILE, "zzzznotarealterm"), "A nonsense term should return nothing."

print(f"'{TERM}' -> {len(hits)} chunk(s) in {TARGET_FILE}; a nonsense term -> 0\n")
show(hits[:3])
```

Term hits only, confined to the file you named, with a negative control proving the filter isn't
just matching everything — the precision an agent needs to cite a specific chunk rather than a fuzzy
neighborhood.

### File Read — recover whole-file context

Top-k retrieval fragments documents. When a chunk cuts off mid-thought, the agent reads the file back
**in order** to recover surrounding context.

```python
TARGET = "how-to-do-what-you-love"
chapter = harness.file_read(TARGET)

expected_chunks = next(f["chunks"] for f in listing if f["file"] == TARGET)
assert len(chapter) == expected_chunks, (
    f"File Read returned {len(chapter)} chunks, but List Files counted {expected_chunks}."
)
assert all(r["file"] == TARGET for r in chapter), "File Read leaked chunks from another file."
indexes = [r["chunk_index"] for r in chapter]
assert indexes == sorted(indexes), "File Read must return chunks in order."

print(f"Reassembled {len(chapter)} chunks in order (indexes {indexes[0]}..{indexes[-1]}):\n")
for r in chapter[:3]:
    print(f"#{r['chunk_index']:>3}  {' '.join((r['text'] or '').split())[:200]}...")
```

The whole file comes back as a contiguous ordered sequence — asserted against the count List Files
reported — because the sink stored a `chunk_index` on every document.

## Step 6 — Idempotent re-export and incremental sync

Re-running the export for a file is safe: the deterministic key + `merge_or_upload` keeps the chunk
count stable instead of duplicating. The sink also exposes `list_snapshots()` — one record per file —
so an orchestrator can diff against the directory and re-export only what changed.

```python
before = search_client.get_document_count()

again = files["superlinear"]
await exporter.export(
    again, project_id=PROJECT_ID, embeddings=embed([o.content for o in again]), embedding_model=EMBEDDING_MODEL
)

# merge_or_upload with deterministic keys means the count must NOT grow. Poll for
# a few seconds so a would-be duplicate has time to surface before we compare —
# a count that is still equal only proves idempotency once indexing has settled.
deadline = time.time() + 8
while time.time() < deadline and search_client.get_document_count() <= before:
    time.sleep(1)

after = search_client.get_document_count()
assert after == before, (
    f"Re-export changed the document count {before} -> {after}. Deterministic keys plus "
    f"merge_or_upload should make a re-export a no-op; a growing count means duplicate keys."
)
print(f"doc count before re-export: {before}  |  after: {after}  ->  no duplicates")

snapshots = await exporter.list_snapshots(export_config_id=CONFIG_ID, embedding_model=EMBEDDING_MODEL)
snapshot_files = sorted(s.parsed_directory_file_id for s in snapshots)
assert snapshot_files == sorted(ESSAYS), (
    f"Expected one snapshot per file {sorted(ESSAYS)}, got {snapshot_files}."
)
print("snapshots (one per file):", snapshot_files)
```

Same document count after re-exporting a file, and a snapshot per file — the primitives an incremental
sync loop is built from. (Note `list_snapshots` needs `embedding_model` to resolve the per-model index
name; omit it and it queries the wrong index.)

## Make it yours

Everything above ran against three sample essays and demo labels. Here's what changes for your data:

| Config | Sample value | What you set | Watch out for |
|---|---|---|---|
| `ESSAYS` | 3 Paul Graham essays | Your own docs — or, in production, drop this entirely and use `export_pipeline` against a LlamaCloud directory | Each key becomes a `parsed_directory_file_id`; keep them stable across runs so re-export replaces instead of duplicating |
| `EMBEDDING_MODEL` | `openai:text-embedding-3-large` | The model id the sink sizes the index for | **Must match your actual embedding model** — a mismatch silently returns garbage. The Azure deployment and this id must be the same model |
| `AOAI_EMBEDDING_DEPLOYMENT` | `text-embedding-3-large` | Your Azure OpenAI deployment name | Use the same base model as `EMBEDDING_MODEL`: large = 3072 dims; small or ada-002 = 1536 |
| `INDEX_PREFIX` | `forgebook-index-v2-sink-<run id>` | Your index base name | The demo appends a random run id so it only ever deletes its own index. Drop that for a stable name — and then drop the teardown cell too. Final index = `{prefix}-{sanitized-model}`; one index per embedding model |
| `PROJECT_ID` / `CONFIG_ID` | demo labels | Your LlamaCloud project + export-config ids | `PROJECT_ID` becomes the `tenant_id` query scope (a scope, not an authorization boundary — see Step 4); `CONFIG_ID` scopes per-file delete and `list_snapshots` — keep both stable |
| `TOP_K` / `K_NEAREST` | `5` / `50` | Tune on your queries | Raise `K_NEAREST` for recall on hard queries; each point costs a little latency |
| Auth | Keyless for Azure (`az login` + RBAC) | Fallback: set `SEARCH_API_KEY` / `AOAI_API_KEY` in `.env` | Role assignments take a few minutes to propagate. The production `export_pipeline` path additionally needs a `LLAMA_CLOUD_API_KEY` |

**What changes at scale:** this ran over 3 files and 60 chunks. At thousands of files, drive exports
from `export_pipeline` against a real LlamaCloud directory and use `list_snapshots()` to sync only
changed files. Add a semantic configuration to the index if you want Azure AI Search's Semantic
Ranker on top of the vector + BM25 fusion shown here — it's also the prerequisite for wrapping this
index as a knowledge source (see Next steps).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: index_v2_data_sinks` | Unsupported Python, or the install cell was skipped | The pinned commit declares `requires-python = ">=3.11,<3.14"`. Re-run the setup cell on a 3.11–3.13 kernel |
| `AssertionError: index-v2-data-sinks is at <sha>, expected 798cac7...` | An older revision is installed and shadowing the pin | Re-run the setup cell; the assertion message includes the exact install command |
| `AssertionError: Index holds N documents, expected M` | Indexing hadn't settled before the count was read | Raise the `wait_for_docs` timeout and re-run the inspect cell |
| `403 Forbidden` on the keyless path | RBAC role not assigned to *you*, or still propagating | Assign `Search Service Contributor` + `Search Index Data Contributor` to your own identity; wait ~5 min and retry |
| Embedding probe asserts wrong dim | Deployment and `EMBEDDING_MODEL` differ | Use a matching pair: large = 3072 dims; small or ada-002 = 1536, then rebuild the index |
| `list_snapshots()` returns `[]` | Called without `embedding_model` → resolves the base index name, not the per-model one | Always pass `embedding_model=EMBEDDING_MODEL` |
| Queries return 0 results right after export | Azure AI Search indexing is near-real-time, not instant | The inspect cell polls with `wait_for_docs`; wait a moment and re-run the query |
| File Grep matches more (or less) than expected | `search.ismatch` runs through the query analyzer — tokenized, case-insensitive | Expected behavior; for byte-exact matching add a `keyword`-analyzer field |
| Retrieval feels random | Query-time and index-time embedding models differ | Make `EMBED_DEPLOYMENT` and `EMBEDDING_MODEL` the same model |

## Teardown

The index lives in *your* service. This deletes **only** the index this run created — tracked in
`CREATED_INDEXES` — so a stale variable or a re-run can't take out something you still need. Set
`DELETE_INDEX = False` to keep it and browse the raw documents in the Azure portal.

```python
DELETE_INDEX = True

if not DELETE_INDEX:
    print(f"Kept {sorted(CREATED_INDEXES)} — inspect in Azure portal > Search service > Indexes.")
else:
    for name in sorted(CREATED_INDEXES):
        index_client.delete_index(name)
        print(f"Deleted index '{name}'.")
    remaining = set(index_client.list_index_names())
    assert not (CREATED_INDEXES & remaining), "Teardown left an index behind."
    print("Teardown complete — only indexes created by this run were deleted.")
```

The Azure AI Search *service* is not deleted — it bills whether or not it's queried. If you spun one
up just for this, remove it from the portal or with `az search service delete`.

## Next steps

- **Run the real pipeline** — swap the local parse output for `export_pipeline(export_to="azure_search", ...)`
  pointed at a LlamaCloud Index V2 directory. The Azure AI Search half is identical to what you just ran.
- **Enforce per-user entitlement** — layer
  [security trimming](https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search)
  on top of the scoping in Step 4 so retrieval reflects the caller's actual permissions.
- **Add Azure AI Search's Semantic Ranker** — attach a semantic configuration to the index and
  switch Hybrid Retrieve to `query_type="semantic"` for 0–4 reranker scores and extractive captions.
- **Graduate to agentic retrieval** — wrap the exported index as a
  [search index knowledge source](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-search-index)
  (it needs the semantic configuration from the previous step) and add it to a
  [knowledge base](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-create-knowledge-base):
  complex questions get decomposed into parallel subqueries, semantically reranked, and answered
  with citations — over the same index the sink just built. Every knowledge base is also a
  standalone MCP server, so agents in Foundry Agent Service, GitHub Copilot, or Claude can call it
  as a tool directly.