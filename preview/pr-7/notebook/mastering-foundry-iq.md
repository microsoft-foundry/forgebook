Build 2026 ships **Foundry IQ**, Microsoft's intelligence layer for agentic
retrieval. A Foundry IQ *Knowledge Base* (KB) wraps one or more
*Knowledge Sources* (KS) with an LLM that **plans subqueries**, executes
them in parallel, **reranks** the results, and **synthesizes** a cited
answer.

This notebook is the canonical recipe for the full surface. It walks you
through every Knowledge Source supported on the
**`2026-05-01-preview`** API surface (the one backing the upcoming Build
2026 release), assembles **one** KB that fans out to all of them, and
plugs that KB into both a **Foundry Agent** (hero scenario) and a
**Microsoft Agent Framework** agent.

## Learning goals

By the end you will:

1. Provision a Search index with vector + semantic configuration and load it
2. Create one Knowledge Source per supported type — Search Index, Azure
   Blob, **File**, Indexed OneLake, Indexed SharePoint, Remote SharePoint,
   **Indexed SQL**, Web, **Fabric Data Agent**, **Fabric Ontology**,
   **WorkIQ**, and **MCP Server**
3. Assemble **one** Knowledge Base that references every KS you configured
4. Run a complex multi-part query and inspect the planner's activity trace
5. Continue the conversation multi-turn
6. Talk to the KB directly over MCP (`tools/list` + `tools/call`)
7. Wire the KB into a **Foundry Agent** (hero) — `RemoteTool` project
   connection + agent + conversation + Responses API
8. Wire the same KB into a **Microsoft Agent Framework** agent via
   `MCPStreamableHTTPTool`
9. Tear every resource down

## Architecture

```text
            ┌───────────────────────────────────────────────────────────┐
            │                    Foundry IQ Pipeline                    │
            └───────────────────────────────────────────────────────────┘
   query ─► Knowledge Base ─► LLM planner ─► parallel subqueries ─┐
              │                                                    │
              │                                                    ▼
              │                          ┌──────── Knowledge Sources ────────┐
              │                          │ Search Index │ Blob │ File │ SQL │
              │                          │ OneLake │ SharePoint (Indexed +  │
              │                          │ Remote) │ Web │ Fabric DA/Ont │  │
              │                          │ WorkIQ │ MCP Server             │
              │                          └────────────────────────────────────┘
              ▼                                                    │
        Answer synthesis ◄── reranked, deduped results ◄──────────┘
              │
              ▼
          Cited answer + activity trace
```

Every section that creates a Knowledge Source is **independently skippable**.
Set its env vars to enable, leave them blank to skip cleanly — the KB at the
bottom is assembled from whichever KS were created in this run.


## 1 - Prerequisites

| | |
|---|---|
| Azure AI Search service | In a [Build 2026 preview region](https://learn.microsoft.com/azure/search/search-region-support) |
| Microsoft Foundry project | One chat deployment (e.g. `gpt-4.1-mini`, `gpt-5-mini`, `gpt-4o`) + one embedding deployment (e.g. `text-embedding-3-large`, `text-embedding-ada-002`) |

Each Knowledge Source section below lists its own resource prerequisites. **None of them are required** to run this notebook end-to-end - any section whose env vars are blank is skipped cleanly.

### Configure your environment

Set the variables below in your shell, or drop them into a local `.env` file next to this notebook (the repo's `.gitignore` already excludes `.env`).

**Required:**

```bash
SEARCH_ENDPOINT=https://<your-search-service>.search.windows.net
SEARCH_API_KEY=<your-search-admin-key>
AOAI_ENDPOINT=https://<your-foundry-resource>.openai.azure.com
AOAI_API_KEY=<your-azure-openai-key>
AOAI_GPT_DEPLOYMENT=gpt-4.1-mini          # or gpt-5-mini, gpt-4o, ...
AOAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
```

**Optional** (each unlocks one Knowledge Source - leave blank to skip): `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_PROJECT_RESOURCE_ID`, `BB26_STORAGE_RID`, `BB26_BLOB_CONTAINER`, `BB26_FILE_UPLOAD_PATH`, `BB26_ONELAKE_*`, `BB26_FABRIC_*`, `BB26_SQL_*`, `BB26_SP_*`, `BB26_MCP_SERVER_*`, `BB26_WORKIQ_USER_TOKEN`. See the per-section prereq tables below for exact names.

### Install dependencies

Foundry IQ ships on the `2026-05-01-preview` Search API which is only exposed by the **alpha** `azure-search-documents` SDK from the [Azure SDK public feed](https://pkgs.dev.azure.com/azure-sdk/public/_packaging/azure-sdk-for-python/pypi/simple/). The next cell installs the pinned dependencies in-place; you do not need a separate `requirements.txt`.


```python
%%capture
# Foundry IQ requires the alpha azure-search-documents SDK that exposes the
# 2026-05-01-preview KnowledgeBase / KnowledgeSource surface. If a 12.1.0a*
# build is already installed (e.g. from a previous run) this cell is a fast
# no-op. The --extra-index-url points at the Azure SDK public preview feed.
import importlib.metadata as _md
try:
    _v = _md.version("azure-search-documents")
    _ok = _v.startswith("12.1.0a")
except _md.PackageNotFoundError:
    _ok = False
if not _ok:
    %pip install --quiet \
        "azure-search-documents==12.1.0a20260526002" \
        "azure-identity>=1.19.0" \
        "azure-core>=1.32.0" \
        "python-dotenv>=1.0.1" \
        "requests>=2.32.3" \
        "httpx>=0.28.1" \
        "agent-framework>=0.1.0" \
        "agent-framework-openai>=0.1.0" \
        --extra-index-url https://pkgs.dev.azure.com/azure-sdk/public/_packaging/azure-sdk-for-python/pypi/simple/

```

## 2 · Configure clients + helpers

One `SearchIndexClient` + one `DefaultAzureCredential` for Foundry/ARM is
reused throughout. We also define:

- `env(name, required=False)` — env-var lookup with a friendly error
- `azure_openai_resource_uri()` — trims `/openai/...` paths
- `ks_status(name)` — `GET /knowledgesources(name)/status`, used after
  every create to confirm the KS isn't stuck on `creating`
- `created_ks` — a list that every KS section appends to on success; the
  single Knowledge Base in §15 reads from it
- `created_resources` — a dict the cleanup section walks in dependency
  order


```python
import os
from pathlib import Path
from typing import Optional

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from dotenv import load_dotenv

load_dotenv(override=True)


def env(name: str, *, required: bool = True, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value or None


def azure_openai_resource_uri(endpoint: str) -> str:
    return endpoint.split("/openai/", 1)[0].rstrip("/")


# ---- Required ------------------------------------------------------------
SEARCH_ENDPOINT = env("SEARCH_ENDPOINT")
SEARCH_API_KEY = env("SEARCH_API_KEY")
AOAI_ENDPOINT = azure_openai_resource_uri(env("AOAI_ENDPOINT"))
AOAI_API_KEY = env("AOAI_API_KEY")

GPT_DEPLOYMENT = env("AOAI_GPT_DEPLOYMENT", required=False, default="gpt-4.1-mini")
GPT_MODEL = env("AOAI_GPT_MODEL", required=False, default=GPT_DEPLOYMENT)
EMBEDDING_DEPLOYMENT = env("AOAI_EMBEDDING_DEPLOYMENT", required=False, default="text-embedding-3-large")
EMBEDDING_MODEL = env("AOAI_EMBEDDING_MODEL", required=False, default=EMBEDDING_DEPLOYMENT)
EMBEDDING_DIMENSIONS = int(env("AOAI_EMBEDDING_DIMENSIONS", required=False, default="3072"))

# ---- API + resource names -----------------------------------------------
API_VERSION = "2026-05-01-preview"
INDEX_NAME = "mfiq-earth-at-night"
KB_NAME = "mfiq-master-kb"

credential = AzureKeyCredential(SEARCH_API_KEY)
index_client = SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=credential)

# ---- Trackers consumed by §15 (KB) and §22 (cleanup) --------------------
created_ks: list[str] = []
created_resources: dict[str, str] = {}

print(f"Search service       : {SEARCH_ENDPOINT}")
print(f"Foundry / AOAI       : {AOAI_ENDPOINT}")
print(f"Chat deployment      : {GPT_DEPLOYMENT} ({GPT_MODEL})")
print(f"Embedding deployment : {EMBEDDING_DEPLOYMENT} ({EMBEDDING_MODEL}, {EMBEDDING_DIMENSIONS} dims)")
print(f"API version          : {API_VERSION}")

```

A handful of REST helpers — most Build 2026 Knowledge Source kinds are
not yet wrapped by the alpha SDK, so we hit `/knowledgesources(...)` over
`requests` directly. The bodies mirror the validated `.http` templates in
`../build2026/templates/`.


```python
import json
import requests

SEARCH_HEADERS = {
    "api-key": SEARCH_API_KEY,
    "Content-Type": "application/json",
}


def ks_url(name: str) -> str:
    return f"{SEARCH_ENDPOINT}/knowledgesources('{name}')?api-version={API_VERSION}"


def kb_url(name: str) -> str:
    return f"{SEARCH_ENDPOINT}/knowledgebases('{name}')?api-version={API_VERSION}"


def put_ks(name: str, body: dict) -> dict:
    """PUT a Knowledge Source and return the representation."""
    headers = {**SEARCH_HEADERS, "Prefer": "return=representation"}
    r = requests.put(ks_url(name), headers=headers, json=body, timeout=120)
    if r.status_code >= 300:
        raise RuntimeError(f"PUT KS {name} failed: HTTP {r.status_code} -- {r.text[:600]}")
    return r.json()


def get_ks_status(name: str) -> dict:
    url = f"{SEARCH_ENDPOINT}/knowledgesources('{name}')/status?api-version={API_VERSION}"
    r = requests.get(url, headers=SEARCH_HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def summarize_ks(name: str) -> None:
    try:
        status = get_ks_status(name)
    except Exception as exc:
        print(f"  status: <unavailable: {exc.__class__.__name__}>")
        return
    sync = status.get("synchronizationStatus", "?")
    last = (status.get("lastSynchronizationState") or {}).get("status", "n/a")
    stats = status.get("statistics") or {}
    print(f"  synchronizationStatus={sync}  lastSync={last}  stats={stats}")


def skip(section: str, reason: str) -> None:
    print(f"[skipped] {section}: {reason}")

```

## 3 · Provision the backing Search index

The **Search Index KS** in §4 needs an existing index to point at. We
declare a tiny but production-shaped index with three configurations:

- A **vector field** sized for whatever embedding model you configured (1536
  for `text-embedding-ada-002`, 3072 for `text-embedding-3-large`).
- An **HNSW** vector profile plus an `AzureOpenAIVectorizer` so the service
  embeds query strings on the fly — you never have to embed at query time.
- A **semantic configuration** — required for agentic retrieval; the KB's
  planner uses the semantic ranker to rerank candidates before synthesis.


```python
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

fields = [
    SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=True, facetable=True),
    SearchField(name="page_chunk", type=SearchFieldDataType.String),
    SearchField(
        name="page_embedding",
        type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
        vector_search_dimensions=EMBEDDING_DIMENSIONS,
        vector_search_profile_name="hnsw_profile",
    ),
    SimpleField(name="page_number", type=SearchFieldDataType.Int32, filterable=True, sortable=True, facetable=True),
]

embedding_params = AzureOpenAIVectorizerParameters(
    resource_url=AOAI_ENDPOINT,
    deployment_name=EMBEDDING_DEPLOYMENT,
    api_key=AOAI_API_KEY,
    model_name=EMBEDDING_MODEL,
)

vector_search = VectorSearch(
    profiles=[VectorSearchProfile(name="hnsw_profile", algorithm_configuration_name="alg", vectorizer_name="aoai_vec")],
    algorithms=[HnswAlgorithmConfiguration(name="alg")],
    vectorizers=[AzureOpenAIVectorizer(vectorizer_name="aoai_vec", parameters=embedding_params)],
)

semantic_search = SemanticSearch(
    default_configuration_name="semantic_config",
    configurations=[
        SemanticConfiguration(
            name="semantic_config",
            prioritized_fields=SemanticPrioritizedFields(content_fields=[SemanticField(field_name="page_chunk")]),
        )
    ],
)

index_client.create_or_update_index(
    SearchIndex(
        name=INDEX_NAME,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )
)
created_resources["index"] = INDEX_NAME
print(f"Index '{INDEX_NAME}' is ready ({EMBEDDING_DIMENSIONS}-dim vector field).")

```

Load the NASA *Earth at Night* dataset. Each row is a pre-chunked page
with an embedding already attached. If your embedding deployment is
`text-embedding-3-large` (3072 dims) the file works as-is; for any other
model we **re-embed** each chunk using the deployment configured in §2,
so the dimensions match what the index expects.


```python
from azure.search.documents import SearchIndexingBufferedSender
from openai import AzureOpenAI

DATA_URL = (
    "https://raw.githubusercontent.com/Azure-Samples/azure-search-sample-data"
    "/refs/heads/main/nasa-e-book/earth-at-night-json/documents.json"
)
raw_docs = requests.get(DATA_URL, timeout=60).json()

# Re-embed if the file's pre-computed 3072-dim vectors don't match this index.
needs_reembed = EMBEDDING_DIMENSIONS != 3072
if needs_reembed:
    print(f"Re-embedding {len(raw_docs)} chunks with {EMBEDDING_DEPLOYMENT} ({EMBEDDING_DIMENSIONS} dims)...")
    oai = AzureOpenAI(api_key=AOAI_API_KEY, azure_endpoint=AOAI_ENDPOINT, api_version="2024-10-21")
    # Batch in groups of 16 to avoid token-rate spikes.
    batch_size = 16
    for start in range(0, len(raw_docs), batch_size):
        batch = raw_docs[start : start + batch_size]
        resp = oai.embeddings.create(model=EMBEDDING_DEPLOYMENT, input=[d["page_chunk"] for d in batch])
        for doc, item in zip(batch, resp.data):
            doc["page_embedding"] = item.embedding
            doc.pop("page_embedding_text_3_large", None)
else:
    for d in raw_docs:
        d["page_embedding"] = d.pop("page_embedding_text_3_large")

with SearchIndexingBufferedSender(
    endpoint=SEARCH_ENDPOINT, index_name=INDEX_NAME, credential=credential
) as sender:
    sender.upload_documents(documents=raw_docs)

print(f"Uploaded {len(raw_docs)} documents to '{INDEX_NAME}'.")

```

## 4 · Search Index Knowledge Source

| | |
|---|---|
| **`kind`** | `searchIndex` |
| **Auth model** | Same-service — Search admin api-key only. |
| **Pipeline** | None — points at an existing index. Most flexible; you keep full control of the schema, vectorizer, and skillset. |
| **Status** | Build 2026 preview (`2026-05-01-preview`) |
| **Env vars** | _(none)_ |

**Prereqs:** the index from §3 (already created above).

**Known issues / gotchas:** `baseFilter` on the KS narrows the queryable subset for the KB; semantics differ from per-call `filterAddOn`. Use `alwaysQuerySource=true` at retrieve time to bypass the planner's relevance heuristic.

[Docs](https://learn.microsoft.com/azure/search/agentic-knowledge-source-how-to-search-index)


```python
KS_SEARCH_INDEX = "mfiq-ks-search-index"

body = {
    "name": KS_SEARCH_INDEX,
    "kind": "searchIndex",
    "description": "Search Index KS over the NASA Earth at Night sample.",
    "searchIndexParameters": {
        "searchIndexName": INDEX_NAME,
        "semanticConfigurationName": "semantic_config",
        "sourceDataFields": [
            {"name": "id"},
            {"name": "page_chunk"},
            {"name": "page_number"},
        ],
    },
}
put_ks(KS_SEARCH_INDEX, body)
created_ks.append(KS_SEARCH_INDEX)
print(f"Created {KS_SEARCH_INDEX}")
summarize_ks(KS_SEARCH_INDEX)

```

## 5 · Azure Blob Knowledge Source

| | |
|---|---|
| **`kind`** | `azureBlob` |
| **Auth model** | System-assigned Managed Identity on the Search service. Grant it `Storage Blob Data Reader` on the storage account. |
| **Pipeline** | Generates an indexer + skillset behind the scenes; ingestion may take 30-180 s for large containers. |
| **Status** | Build 2026 preview (`2026-05-01-preview`) |
| **Env vars** | `BB26_STORAGE_RID`, `BB26_BLOB_CONTAINER` |

**Prereqs:** Azure Storage account, a container with at least one document, MI role grant.

**Known issues / gotchas:** `connectionString` uses the `ResourceId=...;` form (NOT account keys). `contentExtractionMode: 'minimal'` is the recommended default — `enhanced` invokes Document Intelligence and changes per-chunk pricing.

[Docs](https://learn.microsoft.com/azure/search/agentic-knowledge-source-how-to-blob)


```python
KS_BLOB = "mfiq-ks-blob"

storage_rid = env("BB26_STORAGE_RID", required=False)
container = env("BB26_BLOB_CONTAINER", required=False)

if not storage_rid or not container:
    skip(KS_BLOB, "set BB26_STORAGE_RID and BB26_BLOB_CONTAINER to enable")
else:
    body = {
        "name": KS_BLOB,
        "kind": "azureBlob",
        "description": "Indexed Azure Blob knowledge source.",
        "azureBlobParameters": {
            "connectionString": f"ResourceId={storage_rid};",
            "containerName": container,
            "ingestionParameters": {
                "contentExtractionMode": "minimal",
                "embeddingModel": {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": AOAI_ENDPOINT,
                        "apiKey": AOAI_API_KEY,
                        "deploymentId": EMBEDDING_DEPLOYMENT,
                        "modelName": EMBEDDING_MODEL,
                    },
                },
            },
        },
    }
    put_ks(KS_BLOB, body)
    created_ks.append(KS_BLOB)
    print(f"Created {KS_BLOB}")
    summarize_ks(KS_BLOB)

```

## 6 · File Knowledge Source (Build 2026)

| | |
|---|---|
| **`kind`** | `file` |
| **Auth model** | Search admin api-key. Files upload directly into the KS — no separate data source or storage account. |
| **Pipeline** | Per-file ingestion. Files are POSTed individually after KS create. |
| **Status** | Build 2026 preview (`2026-05-01-preview`) |
| **Env vars** | `BB26_FILE_UPLOAD_PATH` |

**Prereqs:** any local file (PDF, DOCX, HTML, TXT, etc.).

**Known issues / gotchas:** Upload uses the **non-OData** route `POST /knowledgesources/{name}/files` (no quotes/parens, no `('...')`) with `Content-Type: application/octet-stream`. The OData form is fronted by a JSON-only middleware that rejects binary bodies.


```python
KS_FILE = "mfiq-ks-file"

file_path_str = env("BB26_FILE_UPLOAD_PATH", required=False)
file_path = Path(file_path_str).expanduser().resolve() if file_path_str else None

if not file_path or not file_path.is_file():
    skip(KS_FILE, f"set BB26_FILE_UPLOAD_PATH to an existing file (got: {file_path_str!r})")
else:
    # 1) Create the KS
    body = {
        "name": KS_FILE,
        "kind": "file",
        "description": f"File KS holding uploaded copies of {file_path.name}.",
        "fileParameters": {
            "ingestionParameters": {
                "contentExtractionMode": "minimal",
                "embeddingModel": {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": AOAI_ENDPOINT,
                        "apiKey": AOAI_API_KEY,
                        "deploymentId": EMBEDDING_DEPLOYMENT,
                        "modelName": EMBEDDING_MODEL,
                    },
                },
            },
        },
    }
    put_ks(KS_FILE, body)
    print(f"Created {KS_FILE}")

    # 2) Upload the file via the non-OData /files route
    upload_url = f"{SEARCH_ENDPOINT}/knowledgesources/{KS_FILE}/files?api-version={API_VERSION}"
    upload_headers = {
        "api-key": SEARCH_API_KEY,
        "Content-Type": "application/octet-stream",
        "Content-Disposition": f'attachment; filename="{file_path.name}"',
    }
    # Retry with backoff — file upload triggers a synchronous embed pass,
    # which on shared embedding deployments can transiently 429.
    import time as _time
    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        with file_path.open("rb") as fh:
            r = requests.post(upload_url, headers=upload_headers, data=fh.read(), timeout=300)
        if r.status_code < 300:
            break
        if r.status_code == 429 and attempt < max_attempts:
            wait = 2 ** attempt
            print(f"  upload attempt {attempt} got 429 — backing off {wait}s")
            _time.sleep(wait)
            continue
        raise RuntimeError(f"File upload failed: HTTP {r.status_code} -- {r.text[:600]}")
    print(f"Uploaded {file_path.name} ({file_path.stat().st_size:,} bytes) in {attempt} attempt(s)")

    created_ks.append(KS_FILE)
    summarize_ks(KS_FILE)

```

## 7 · Indexed OneLake Knowledge Source (Fabric)

| | |
|---|---|
| **`kind`** | `indexedOneLake` |
| **Auth model** | System-assigned Managed Identity on the Search service. Grant the MI **Contributor** on the Fabric workspace. |
| **Pipeline** | Indexer + skillset over the OneLake `Files/` path you choose. |
| **Status** | Build 2026 preview (`2026-05-01-preview`) |
| **Env vars** | `BB26_ONELAKE_WORKSPACE_ID`, `BB26_ONELAKE_ID`, `BB26_ONELAKE_PATH` |

**Prereqs:** Fabric workspace + lakehouse with files at the target path.

**Known issues / gotchas:** Workspace MI role assignment can take 5-10 min to propagate. If the indexer log shows 401/403, wait and re-trigger.

[Docs](https://learn.microsoft.com/azure/search/agentic-knowledge-source-how-to-onelake)


```python
KS_ONELAKE = "mfiq-ks-onelake"

workspace_id = env("BB26_ONELAKE_WORKSPACE_ID", required=False)
lakehouse_id = env("BB26_ONELAKE_ID", required=False)
target_path = env("BB26_ONELAKE_PATH", required=False)

if not (workspace_id and lakehouse_id and target_path):
    skip(KS_ONELAKE, "set BB26_ONELAKE_WORKSPACE_ID, BB26_ONELAKE_ID, BB26_ONELAKE_PATH to enable")
else:
    body = {
        "name": KS_ONELAKE,
        "kind": "indexedOneLake",
        "description": "Indexed OneLake KS over a Fabric lakehouse folder.",
        "indexedOneLakeParameters": {
            "fabricWorkspaceId": workspace_id,
            "lakehouseId": lakehouse_id,
            "targetPath": target_path,
            "ingestionParameters": {
                "contentExtractionMode": "minimal",
                "disableImageVerbalization": False,
                "ingestionPermissionOptions": [],
                "embeddingModel": {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": AOAI_ENDPOINT,
                        "apiKey": AOAI_API_KEY,
                        "deploymentId": EMBEDDING_DEPLOYMENT,
                        "modelName": EMBEDDING_MODEL,
                    },
                },
            },
        },
    }
    put_ks(KS_ONELAKE, body)
    created_ks.append(KS_ONELAKE)
    print(f"Created {KS_ONELAKE}")
    summarize_ks(KS_ONELAKE)

```

        ## 8 · Indexed SharePoint Knowledge Source

        | | |
        |---|---|
        | **`kind`** | `indexedSharePoint` |
        | **Auth model** | App-only auth — Entra app with `Sites.Selected`. Connection string carries the app id + secret + tenant id. |
        | **Pipeline** | Indexer + skillset over an SP document library. |
        | **Status** | Build 2026 preview (`2026-05-01-preview`) |
        | **Env vars** | `BB26_SP_TENANT_ID`, `BB26_SP_SITE_URL`, `BB26_SP_LIBRARY_NAME`, `BB26_SP_CLIENT_ID`, `BB26_SP_CLIENT_SECRET` |

        **Prereqs:** SP site, an Entra app with **Sites.Selected** granted on the site (admin consent required), and a client secret.

```bash
az ad sp create-for-rbac --name mfiq-sp-indexer --skip-assignment
# Then in PowerShell:
# Grant-PnPAzureADAppSitePermission -AppId <id> -Site <site-url> -Permissions Read
```


        **Known issues / gotchas:** The connection string format is `SharePointOnlineEndpoint=...;ApplicationId=...;ApplicationSecret=...;TenantId=...`. Do NOT use account-key style strings.

        [Docs](https://learn.microsoft.com/azure/search/agentic-knowledge-source-how-to-sharepoint-indexed)


```python
KS_SP_INDEXED = "mfiq-ks-sp-indexed"

sp_tenant = env("BB26_SP_TENANT_ID", required=False)
sp_site = env("BB26_SP_SITE_URL", required=False)
sp_library = env("BB26_SP_LIBRARY_NAME", required=False)
sp_app_id = env("BB26_SP_CLIENT_ID", required=False)
sp_app_secret = env("BB26_SP_CLIENT_SECRET", required=False)

if not all([sp_tenant, sp_site, sp_library, sp_app_id, sp_app_secret]):
    skip(KS_SP_INDEXED, "set BB26_SP_* to enable")
else:
    connection_string = (
        f"SharePointOnlineEndpoint={sp_site};"
        f"ApplicationId={sp_app_id};"
        f"ApplicationSecret={sp_app_secret};"
        f"TenantId={sp_tenant}"
    )
    body = {
        "name": KS_SP_INDEXED,
        "kind": "indexedSharePoint",
        "description": "Indexed SharePoint KS over a site document library.",
        "indexedSharePointParameters": {
            "connectionString": connection_string,
            "containerName": sp_library,
            "query": None,
            "ingestionParameters": {
                "contentExtractionMode": "minimal",
                "disableImageVerbalization": False,
                "ingestionPermissionOptions": [],
                "embeddingModel": {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": AOAI_ENDPOINT,
                        "apiKey": AOAI_API_KEY,
                        "deploymentId": EMBEDDING_DEPLOYMENT,
                        "modelName": EMBEDDING_MODEL,
                    },
                },
            },
        },
    }
    put_ks(KS_SP_INDEXED, body)
    created_ks.append(KS_SP_INDEXED)
    print(f"Created {KS_SP_INDEXED}")
    summarize_ks(KS_SP_INDEXED)

```

## 9 · Remote SharePoint Knowledge Source (federated)

| | |
|---|---|
| **`kind`** | `remoteSharePoint` |
| **Auth model** | **Per-user OBO** — the *caller's* token is passed on every retrieve via `x-ms-query-source-authorization`. Nothing stored on the KS or the Foundry connection. |
| **Pipeline** | None — federated. Real-time query into SharePoint Graph API. |
| **Status** | Build 2026 preview (`2026-05-01-preview`) |
| **Env vars** | `BB26_SP_TENANT_ID (only to confirm tenant; no creds stored)` |

**Prereqs:** at query time, a user OBO token scoped to `https://search.azure.com/.default` from the **72f** Microsoft tenant.

**Known issues / gotchas:** The KS body itself has **no credentials** — auth happens at retrieve. In Foundry Agent definitions, headers apply to all invocations; for true per-user auth, route via the Azure OpenAI Responses API + `structured_inputs`.

[Docs](https://learn.microsoft.com/azure/search/agentic-knowledge-source-how-to-sharepoint-remote)


```python
KS_SP_REMOTE = "mfiq-ks-sp-remote"

body = {
    "name": KS_SP_REMOTE,
    "kind": "remoteSharePoint",
    "description": "Federated SharePoint KS — token passed at retrieve time.",
    "encryptionKey": None,
    "remoteSharePointParameters": {
        "filterExpression": "filetype:docx OR filetype:pdf OR filetype:pptx",
        "resourceMetadata": ["Author", "Title", "LastModifiedDateTime"],
        "containerTypeId": None,
    },
}
try:
    put_ks(KS_SP_REMOTE, body)
    created_ks.append(KS_SP_REMOTE)
    print(f"Created {KS_SP_REMOTE} — remember: requires per-user OBO at retrieve time.")
    summarize_ks(KS_SP_REMOTE)
except Exception as exc:
    # KS create itself is unauthenticated, so this usually only fails if SP federation
    # is disabled on the service. We don't block the rest of the notebook.
    skip(KS_SP_REMOTE, f"create failed: {exc}")

```

        ## 10 · Indexed SQL Knowledge Source (Build 2026)

        | | |
        |---|---|
        | **`kind`** | `indexedSql` |
        | **Auth model** | System-assigned MI on the Search service. The MI must exist as a SQL **EXTERNAL PROVIDER user** with `db_datareader`. |
        | **Pipeline** | Indexer + skillset over a table/view. Change-tracking via a high-water-mark column. |
        | **Status** | Build 2026 preview (`2026-05-01-preview`) |
        | **Env vars** | `BB26_SQL_SUBSCRIPTION`, `BB26_SQL_RESOURCE_GROUP`, `BB26_SQL_SERVER`, `BB26_SQL_DATABASE`, `BB26_SQL_TABLE`, `BB26_SQL_HWM_COLUMN` |

        **Prereqs:** Azure SQL DB, a table/view with a monotonically-increasing column for HWM. In the DB, as Entra admin:

```sql
CREATE USER [<search-mi-name>] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [<search-mi-name>];
```


        **Known issues / gotchas:** `connectionString` uses the `Database=...;ResourceId=...;` shape with the FULL ARM ID of the SQL DB. Vary `contentColumns` and `embeddingColumns` to fit your schema.


```python
KS_SQL = "mfiq-ks-sql"
from datetime import datetime, timezone

sub = env("BB26_SQL_SUBSCRIPTION", required=False)
rg = env("BB26_SQL_RESOURCE_GROUP", required=False)
server = env("BB26_SQL_SERVER", required=False)
db = env("BB26_SQL_DATABASE", required=False)
table = env("BB26_SQL_TABLE", required=False)
hwm = env("BB26_SQL_HWM_COLUMN", required=False, default="UpdatedAt")

if not all([sub, rg, server, db, table]):
    skip(KS_SQL, "set BB26_SQL_SUBSCRIPTION/RESOURCE_GROUP/SERVER/DATABASE/TABLE to enable")
else:
    sql_db_rid = f"/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.Sql/servers/{server}/databases/{db}"
    connection_string = f"Database={db};ResourceId={sql_db_rid};Connection Timeout=30;"
    body = {
        "name": KS_SQL,
        "kind": "indexedSql",
        "description": "Indexed SQL KS over a documented knowledge-articles table.",
        "indexedSqlParameters": {
            "connectionString": connection_string,
            "tableOrView": table,
            "highWaterMarkColumnName": hwm,
            "contentColumns": [
                {"name": "title", "sourceField": "Title", "searchFieldType": "Edm.String"},
                {"name": "description", "sourceField": "Description", "searchFieldType": "Edm.String"},
                {"name": "category", "sourceField": "Category", "searchFieldType": "Edm.String"},
                {"name": "searchText", "sourceField": "SearchText", "searchFieldType": "Edm.String"},
                {"name": "updatedAt", "sourceField": hwm, "searchFieldType": "Edm.DateTimeOffset"},
            ],
            "embeddingColumns": [{"name": "contentEmbedding", "sourceField": "SearchText"}],
            "ingestionParameters": {
                "contentExtractionMode": "minimal",
                "embeddingModel": {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": {
                        "resourceUri": AOAI_ENDPOINT,
                        "apiKey": AOAI_API_KEY,
                        "deploymentId": EMBEDDING_DEPLOYMENT,
                        "modelName": EMBEDDING_MODEL,
                    },
                },
                "ingestionSchedule": {
                    "interval": "P1D",
                    "startTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            },
        },
    }
    try:
        put_ks(KS_SQL, body)
        created_ks.append(KS_SQL)
        print(f"Created {KS_SQL}")
        summarize_ks(KS_SQL)
    except Exception as exc:
        skip(KS_SQL, f"create failed (commonly an MI-on-SQL prereq issue): {exc}")

```

## 11 · Web Knowledge Source

| | |
|---|---|
| **`kind`** | `web` |
| **Auth model** | None — Foundry IQ brokers the search. No Bing key required from you. |
| **Pipeline** | Federated — real-time web search at every retrieve. |
| **Status** | Build 2026 preview (`2026-05-01-preview`) |
| **Env vars** | _(none)_ |

**Prereqs:** none. Just decide which domains the planner is allowed to query and which are off-limits.

**Known issues / gotchas:** `allowedDomains` is an allow-list — if you list any, only those are queried. `includeSubpages: true` is almost always what you want.

[Docs](https://learn.microsoft.com/azure/search/agentic-knowledge-source-how-to-web)


```python
KS_WEB = "mfiq-ks-web"

body = {
    "name": KS_WEB,
    "kind": "web",
    "description": "Web KS scoped to Microsoft Learn and Tech Community.",
    "webParameters": {
        "domains": {
            "allowedDomains": [
                {"address": "learn.microsoft.com", "includeSubpages": True},
                {"address": "techcommunity.microsoft.com", "includeSubpages": True},
            ],
            "blockedDomains": [
                {"address": "bing.com", "includeSubpages": False},
            ],
        }
    },
}
put_ks(KS_WEB, body)
created_ks.append(KS_WEB)
print(f"Created {KS_WEB}")
summarize_ks(KS_WEB)

```

## 12 · Fabric Data Agent Knowledge Source (Build 2026)

| | |
|---|---|
| **`kind`** | `fabricDataAgent` |
| **Auth model** | System-assigned MI on the Search service. MI must be **Contributor** on the Fabric workspace hosting the Data Agent. |
| **Pipeline** | Federated — every retrieve invokes the published Fabric Data Agent. |
| **Status** | Build 2026 preview (`2026-05-01-preview`) |
| **Env vars** | `BB26_FABRIC_DATA_AGENT_WORKSPACE`, `BB26_FABRIC_DATA_AGENT_ID`, `BB26_FABRIC_DATA_AGENT_ENDPOINT` |

**Prereqs:** a **published** Data Agent in Fabric, and the workspace + agent GUIDs.

**Known issues / gotchas:** Fabric tokens are scoped to `https://api.fabric.microsoft.com/.default` — different from the AI Foundry scope. Workspace role propagation can take minutes.


```python
KS_FABRIC_DA = "mfiq-ks-fabric-data-agent"

fda_workspace = env("BB26_FABRIC_DATA_AGENT_WORKSPACE", required=False)
fda_agent = env("BB26_FABRIC_DATA_AGENT_ID", required=False)
fda_endpoint = env("BB26_FABRIC_DATA_AGENT_ENDPOINT", required=False, default="https://msitapi.fabric.microsoft.com")

if not (fda_workspace and fda_agent):
    skip(KS_FABRIC_DA, "set BB26_FABRIC_DATA_AGENT_WORKSPACE and _ID to enable")
else:
    body = {
        "name": KS_FABRIC_DA,
        "kind": "fabricDataAgent",
        "description": "Federated KS over a published Fabric Data Agent.",
        "fabricDataAgentParameters": {
            "fabricEndpoint": fda_endpoint,
            "workspaceId": fda_workspace,
            "dataAgentId": fda_agent,
        },
    }
    try:
        put_ks(KS_FABRIC_DA, body)
        created_ks.append(KS_FABRIC_DA)
        print(f"Created {KS_FABRIC_DA}")
        summarize_ks(KS_FABRIC_DA)
    except Exception as exc:
        skip(KS_FABRIC_DA, f"create failed: {exc}")

```

## 13 · Fabric Ontology Knowledge Source (Build 2026)

| | |
|---|---|
| **`kind`** | `fabricOntology` |
| **Auth model** | Same MI pattern as Fabric Data Agent — workspace Contributor. |
| **Pipeline** | Federated — KB queries are translated into ontology / semantic-model queries. |
| **Status** | Build 2026 preview (`2026-05-01-preview`) |
| **Env vars** | `BB26_FABRIC_ONTOLOGY_WORKSPACE`, `BB26_FABRIC_ONTOLOGY_ID`, `BB26_FABRIC_ONTOLOGY_ENDPOINT` |

**Prereqs:** a published Ontology in Fabric.


```python
KS_FABRIC_ONT = "mfiq-ks-fabric-ontology"

ont_workspace = env("BB26_FABRIC_ONTOLOGY_WORKSPACE", required=False)
ont_id = env("BB26_FABRIC_ONTOLOGY_ID", required=False)
ont_endpoint = env("BB26_FABRIC_ONTOLOGY_ENDPOINT", required=False, default="https://msitapi.fabric.microsoft.com")

if not (ont_workspace and ont_id):
    skip(KS_FABRIC_ONT, "set BB26_FABRIC_ONTOLOGY_WORKSPACE and _ID to enable")
else:
    body = {
        "name": KS_FABRIC_ONT,
        "kind": "fabricOntology",
        "description": "Federated KS over a Fabric ontology.",
        "fabricOntologyParameters": {
            "fabricEndpoint": ont_endpoint,
            "workspaceId": ont_workspace,
            "ontologyId": ont_id,
        },
    }
    try:
        put_ks(KS_FABRIC_ONT, body)
        created_ks.append(KS_FABRIC_ONT)
        print(f"Created {KS_FABRIC_ONT}")
        summarize_ks(KS_FABRIC_ONT)
    except Exception as exc:
        skip(KS_FABRIC_ONT, f"create failed: {exc}")

```

## 14 · WorkIQ Knowledge Source (Build 2026)

| | |
|---|---|
| **`kind`** | `workIQ` |
| **Auth model** | **Per-user OBO**, just like Remote SharePoint. The caller's token (Microsoft `72f` tenant, scoped to `https://search.azure.com/.default`) is passed on every retrieve. |
| **Pipeline** | Federated — Microsoft 365 Graph search via the WorkIQ surface. |
| **Status** | Build 2026 preview (`2026-05-01-preview`) |
| **Env vars** | `BB26_WORKIQ_USER_TOKEN (only at retrieve time; KS create itself is unauthenticated)` |

**Prereqs:** an account in the Microsoft `72f` tenant with WorkIQ entitlements.

**Known issues / gotchas:** Set `maxRuntimeInSeconds: 180+` on the retrieve request — WorkIQ can be slow on first call as caches warm.


```python
KS_WORKIQ = "mfiq-ks-workiq"

body = {
    "name": KS_WORKIQ,
    "kind": "workIQ",
    "description": "Federated WorkIQ (M365 Graph) KS.",
}
try:
    put_ks(KS_WORKIQ, body)
    created_ks.append(KS_WORKIQ)
    print(f"Created {KS_WORKIQ}")
    summarize_ks(KS_WORKIQ)
except Exception as exc:
    skip(KS_WORKIQ, f"create failed: {exc}")

```

## 15 · MCP Server Knowledge Source (Build 2026)

| | |
|---|---|
| **`kind`** | `mcpServer` |
| **Auth model** | Either **none** (public MCP servers like Microsoft Learn) or via a **Foundry CustomKeys connection** (for servers that need an API key, e.g. Speedbird). |
| **Pipeline** | Federated — every retrieve does `tools/call` on the upstream MCP server. |
| **Status** | Build 2026 preview (`2026-05-01-preview`) |
| **Env vars** | `BB26_MCP_SERVER_URL (optional override)`, `BB26_MCP_SERVER_API_KEY (optional — only if your server requires a key)` |

**Prereqs:** the upstream MCP server URL + tool names it publishes.

**Known issues / gotchas:** `tools[].name` MUST match a tool the upstream server actually publishes. For `outputParsing.kind = 'auto'` Foundry IQ infers; use `'text'` or `'structured'` if auto fails.


```python
KS_MCP = "mfiq-ks-mcp-learn"

# Default to the always-public Microsoft Learn MCP server.
server_url = env("BB26_MCP_SERVER_URL", required=False, default="https://learn.microsoft.com/api/mcp")
learn_default = "learn.microsoft.com" in server_url

body = {
    "name": KS_MCP,
    "kind": "mcpServer",
    "description": "MCP Server KS — Microsoft Learn (no auth required).",
    "mcpServerParameters": {
        "serverURL": server_url,
        "tools": [
            {
                "name": "microsoft_docs_search" if learn_default else "web",
                "outputParsing": {"kind": "auto"},
                "inclusionMode": "reranked",
                "maxOutputTokens": 4096,
            }
        ],
    },
}
# For servers that need an API key, the canonical pattern is a Foundry
# CustomKeys connection: see build2026/templates/foundryiq-mcp-server-ks.http
# for the PUT body. We skip that here to keep the notebook self-contained.

try:
    put_ks(KS_MCP, body)
    created_ks.append(KS_MCP)
    print(f"Created {KS_MCP} ({server_url})")
    summarize_ks(KS_MCP)
except Exception as exc:
    skip(KS_MCP, f"create failed: {exc}")

```

## 16 · Sidebar: Purview ACL trim for indexed KS

Indexed KS (Blob, OneLake, SharePoint Indexed, SQL) can optionally enforce
**document-level security** by snapshotting the source ACLs into Search and
requiring an `x-ms-query-source-authorization` header at retrieve time.

Opt in by setting the KS's `ingestionParameters.ingestionPermissionOptions`
to e.g. `["userIds", "groupIds"]`. Then at retrieve time, pass the user's
OBO token in the header — Search filters references down to what they're
allowed to see.

Reference body: [`build2026/templates/foundryiq-purview-acl-integration.http`](../build2026/templates/foundryiq-purview-acl-integration.http).


## 17 · The Knowledge Base — one KB, three heterogeneous Knowledge Sources

The KB is the singleton consumer of the KS layer. Sections 4–15 above
create up to twelve different KS so you can see the shape of each one;
this notebook then deliberately picks **three** of them to assemble a
**diverse but readable** demo KB:

| KS in the demo KB | Why we picked it |
|---|---|
| `mfiq-ks-search-index` | The canonical KS — an existing Azure AI Search index you fully control. |
| `mfiq-ks-file` | Build 2026's direct-upload KS — no storage account, no indexer, no skillset. |
| `mfiq-ks-mcp-learn` | A federated MCP KS — every retrieve calls a live external MCP server (Microsoft Learn). |

> Why only three? The preview cap is 10 KS per KB, but more importantly,
> three is enough to demonstrate **heterogeneity** (indexed vs. uploaded
> vs. federated). For your own KBs, mix any of the twelve types above —
> just keep the per-KB total under the current preview limit.

The KB carries:

| Setting | What it controls |
|---|---|
| `models` | Chat model used for query planning + answer synthesis |
| `knowledgeSources` | Which sources are in scope (we pass the curated three) |
| `retrievalReasoningEffort` | `minimal` / `low` / `medium` — how hard the planner thinks |
| `outputMode` | `extractiveData` (raw chunks) or `answerSynthesis` (cited NL answer) |
| `answerInstructions` | System prompt that shapes the synthesized answer |

We pick **`answerSynthesis`** + **`low`** as the production-friendly default.


```python
if not created_ks:
    raise RuntimeError("No Knowledge Sources were created — cannot build a KB. Configure at least one KS env block.")

# For the demo KB we deliberately pick a SMALL, DIVERSE subset (max 10 KS per
# KB in current preview, but more importantly readability). Three is enough
# to show heterogeneity: one canonical index-backed source, one direct file
# upload source, and one federated MCP source.
HERO_KS = [
    "mfiq-ks-search-index",   # existing-index canonical
    "mfiq-ks-file",           # direct-upload (Build 2026)
    "mfiq-ks-mcp-learn",      # federated MCP (Microsoft Learn)
]
kb_sources = [n for n in HERO_KS if n in created_ks]
if not kb_sources:
    kb_sources = created_ks[:1]

print(f"Building KB '{KB_NAME}' referencing {len(kb_sources)} knowledge source(s):")
for n in kb_sources:
    print(f"  - {n}")
skipped = [n for n in created_ks if n not in kb_sources]
if skipped:
    print(f"\n(The following KS were created but not added to this demo KB — they're available for your own KBs:)")
    for n in skipped:
        print(f"  · {n}")

kb_body = {
    "name": KB_NAME,
    "description": "Master KB fanning out to a curated, heterogeneous mix of KS configured in this notebook run.",
    "outputMode": "answerSynthesis",
    "answerInstructions": (
        "Provide a concise, faithful answer using only the retrieved content. "
        "Preserve [ref_id:N] citations the planner returns."
    ),
    "retrievalReasoningEffort": {"kind": "low"},
    "knowledgeSources": [{"name": n} for n in kb_sources],
    "models": [
        {
            "kind": "azureOpenAI",
            "azureOpenAIParameters": {
                "resourceUri": AOAI_ENDPOINT,
                "apiKey": AOAI_API_KEY,
                "deploymentId": GPT_DEPLOYMENT,
                "modelName": GPT_MODEL,
            },
        }
    ],
}
r = requests.put(kb_url(KB_NAME), headers={**SEARCH_HEADERS, "Prefer": "return=representation"}, json=kb_body, timeout=60)
if r.status_code >= 300:
    raise RuntimeError(f"PUT KB failed: HTTP {r.status_code} -- {r.text[:600]}")
created_resources["kb"] = KB_NAME
print(f"\nKnowledge Base '{KB_NAME}' is ready.")

```

## 18 · Hero query — multi-source, multi-part question

This is where agentic retrieval earns its keep. The query below bundles
**three different concerns** in one turn — exactly the case where naive
single-vector RAG falls apart, because no one source knows the answer.

The KB will:

1. **Plan** — the LLM decomposes the user turn into focused subqueries
2. **Retrieve** — each subquery is routed to the right KS in parallel
   (Earth-at-Night chunks for auroras, the uploaded Zava PDF for the
   corporate description, Microsoft Learn over MCP for agentic retrieval),
   and the semantic ranker reorders candidates
3. **Synthesize** — the LLM writes one grounded answer with `[ref_id:N]`
   citations that span all three sources

`alwaysQuerySource=True` forces the planner to actually query each source
instead of short-circuiting. `includeActivity=True` exposes every step.


```python
retrieve_url = f"{SEARCH_ENDPOINT}/knowledgebases('{KB_NAME}')/retrieve?api-version={API_VERSION}"

# Per-KS retrieve parameter blocks. Only certain `kind`s expose tunables
# at retrieve time; the others use sensible defaults from the KB.
def ks_params_for(name: str) -> dict | None:
    if name == "mfiq-ks-search-index":
        return {
            "kind": "searchIndex",
            "knowledgeSourceName": name,
            "includeReferences": True,
            "includeReferenceSourceData": True,
            "alwaysQuerySource": True,
            "maxOutputDocuments": 50,
            "failOnError": False,
            "rerankerThreshold": 0.0,
        }
    if name == "mfiq-ks-file":
        return {
            "kind": "file",
            "knowledgeSourceName": name,
            "includeReferences": True,
            "includeReferenceSourceData": True,
            "alwaysQuerySource": True,
        }
    if name == "mfiq-ks-mcp-learn":
        return {
            "kind": "mcpServer",
            "knowledgeSourceName": name,
            "includeReferences": True,
        }
    return None


def retrieve(messages: list[dict], max_runtime_seconds: int = 180) -> dict:
    body = {
        "messages": [
            {"role": m["role"], "content": [{"type": "text", "text": m["content"]}]}
            for m in messages
        ],
        "includeActivity": True,
        "maxRuntimeInSeconds": max_runtime_seconds,
        "knowledgeSourceParams": [p for p in (ks_params_for(n) for n in kb_sources) if p],
    }
    r = requests.post(retrieve_url, headers=SEARCH_HEADERS, json=body, timeout=300)
    if r.status_code >= 300:
        raise RuntimeError(f"Retrieve failed: HTTP {r.status_code} -- {r.text[:600]}")
    return r.json()


def answer_text(result: dict) -> str:
    return "\n\n".join(
        c.get("text", "")
        for message in (result.get("response") or [])
        for c in (message.get("content") or [])
        if c.get("type") == "text"
    )


messages = [
    {
        "role": "user",
        "content": (
            "Compare how the NASA Earth at Night dataset describes auroras versus "
            "how the Zava corporate presentation describes Zava's business. "
            "Then, separately, what does the Microsoft Learn documentation say "
            "about agentic retrieval in Azure AI Search?"
        ),
    }
]
result = retrieve(messages)
first_answer = answer_text(result)

print("ANSWER")
print("------")
print(first_answer)
print()
print(f"Activity steps : {len(result.get('activity') or [])}")
print(f"References     : {len(result.get('references') or [])}")

```

### 18b · Inspect the planner activity trace


```python
print(json.dumps(result.get("activity") or [], indent=2)[:3500])

```

### 18c · Inspect the first few references (the citations that ground the answer)


```python
for ref in (result.get("references") or [])[:3]:
    src = ref.get("sourceData") or {}
    page_no = src.get("page_number")
    snippet = (src.get("page_chunk") or "")[:240].replace("\n", " ")
    print(f"[ref_id:{ref.get('id')}] doc_key={ref.get('docKey')!r}  page={page_no}")
    if snippet:
        print(f"  {snippet}{'...' if len(snippet) == 240 else ''}")
    print()

```

## 19 · Continue the conversation (multi-turn)

Agentic retrieval is conversation-aware. We append the prior answer and
ask a narrower question — the planner uses the earlier context when
deciding what to retrieve next.


```python
messages.append({"role": "assistant", "content": first_answer})
messages.append({"role": "user", "content": "Looking at the auroras described in those references, what causes the different colors observed at different altitudes?"})

result2 = retrieve(messages)
print("FOLLOW-UP ANSWER")
print("----------------")
print(answer_text(result2))
print()
print(f"Activity steps : {len(result2.get('activity') or [])}")
print(f"References     : {len(result2.get('references') or [])}")

```

## 20 · Talk to the Knowledge Base directly over MCP

Every Foundry IQ KB exposes itself as a **Model Context Protocol** server
at:

```
{SEARCH_ENDPOINT}/knowledgebases/{KB_NAME}/mcp?api-version=2026-05-01-preview
```

Any MCP-capable client — Claude Desktop, VS Code Copilot, the Foundry Agent
Service, the Microsoft Agent Framework, a custom Python script — can call
the same retrieval pipeline using one tool: **`knowledge_base_retrieve`**.

The transport is plain JSON-RPC 2.0 over HTTP with either JSON or
SSE-streamable responses. Auth is the same Search admin api-key. For
federated KS that need user identity (Remote SharePoint, WorkIQ), you
also pass `x-ms-query-source-authorization: <user OBO token>`.


```python
MCP_URL = f"{SEARCH_ENDPOINT}/knowledgebases/{KB_NAME}/mcp?api-version={API_VERSION}"
MCP_HEADERS = {
    "api-key": SEARCH_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _parse_mcp(response: requests.Response) -> dict:
    ct = response.headers.get("Content-Type", "")
    if "text/event-stream" in ct:
        for line in response.text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[len("data: "):])
        raise RuntimeError(f"No data event in SSE response: {response.text[:200]}")
    return response.json()


# tools/list — discover the surface this KB publishes.
list_resp = requests.post(MCP_URL, headers=MCP_HEADERS,
    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, timeout=60)
list_resp.raise_for_status()
tools_payload = _parse_mcp(list_resp)
print("Tools published by this KB")
print("--------------------------")
for t in tools_payload["result"]["tools"]:
    first_line = (t.get("description", "") or "").splitlines()[0]
    print(f"- {t['name']}: {first_line[:140]}")
print()

# tools/call — same retrieval, JSON-RPC envelope.
call_resp = requests.post(MCP_URL, headers=MCP_HEADERS, json={
    "jsonrpc": "2.0", "id": 2,
    "method": "tools/call",
    "params": {
        "name": "knowledge_base_retrieve",
        "arguments": {"queries": ["What does the dataset show about wildfires visible at night?"]},
    },
}, timeout=180)
call_resp.raise_for_status()
call_payload = _parse_mcp(call_resp)

print("knowledge_base_retrieve (over MCP)")
print("----------------------------------")
for block in call_payload["result"].get("content", []):
    if block.get("type") == "text":
        print(block["text"])

```

## 21 · Hero — wire the KB into a Foundry Agent

The Foundry Agent Service hosts the agent loop, the conversation store,
and the MCP runtime for you. To attach a Foundry IQ KB:

1. **Create a `RemoteTool` project connection** pointing at the KB's MCP URL.
   `authType=ProjectManagedIdentity` lets the project assume its own
   identity when calling Search — no per-user tokens stored on the connection.
2. **Create an agent** that declares an `mcp` tool referencing the
   connection and allow-lists `knowledge_base_retrieve`.
3. **Create a conversation**, then **POST to `/openai/v1/responses`** with
   the agent reference and user input. The Responses API runs the chain
   and returns a grounded answer.

> **Auth:** `DefaultAzureCredential`. Run `az login` first. Roles needed:
> *Cognitive Services Contributor* (agent), *Azure AI User* (project
> endpoint), and write access on the project's resource group (connection PUT).

> **Skip:** if `FOUNDRY_PROJECT_ENDPOINT` is blank, this cell prints a
> skip message and the rest of the notebook still runs.


```python
import time
from azure.identity import DefaultAzureCredential

project_endpoint = env("FOUNDRY_PROJECT_ENDPOINT", required=False)
project_rid = env("FOUNDRY_PROJECT_RESOURCE_ID", required=False)
agent_name = "mfiq-cookbook-agent"
connection_name = "mfiq-cookbook-connection"

if not (project_endpoint and project_rid):
    skip("Foundry Agent", "set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_PROJECT_RESOURCE_ID to enable")
else:
    cred = DefaultAzureCredential()
    arm_token = cred.get_token("https://management.azure.com/.default").token
    foundry_token = cred.get_token("https://ai.azure.com/.default").token
    arm_headers = {"Authorization": f"Bearer {arm_token}", "Content-Type": "application/json"}
    foundry_headers = {"Authorization": f"Bearer {foundry_token}", "Content-Type": "application/json"}

    # 1) RemoteTool connection
    conn_url = (
        f"https://management.azure.com{project_rid}/connections/{connection_name}"
        f"?api-version=2025-10-01-preview"
    )
    conn_body = {
        "name": connection_name,
        "type": "Microsoft.MachineLearningServices/workspaces/connections",
        "properties": {
            "authType": "ProjectManagedIdentity",
            "category": "RemoteTool",
            "target": MCP_URL,
            "isSharedToAll": True,
            "audience": "https://search.azure.com/",
            "metadata": {"ApiType": "Azure"},
        },
    }
    r = requests.put(conn_url, headers=arm_headers, json=conn_body, timeout=60)
    r.raise_for_status()
    created_resources["foundry_connection_url"] = conn_url
    print(f"Project connection ready: {connection_name}")

    # 2) Agent
    agent_url = f"{project_endpoint}/agents?api-version=v1"
    agent_body = {
        "name": agent_name,
        "definition": {
            "model": GPT_DEPLOYMENT,
            "instructions": (
                "Always call knowledge_base_retrieve before answering. "
                "Preserve [ref_id:N] citations the tool returns. "
                "If a question spans multiple sources, integrate them faithfully."
            ),
            "tools": [
                {
                    "type": "mcp",
                    "server_label": "knowledge-base",
                    "server_url": MCP_URL,
                    "require_approval": "never",
                    "allowed_tools": ["knowledge_base_retrieve"],
                    "project_connection_id": connection_name,
                }
            ],
            "kind": "prompt",
        },
    }
    r = requests.post(agent_url, headers=foundry_headers, json=agent_body, timeout=60)
    if r.status_code == 409:
        requests.delete(f"{project_endpoint}/agents/{agent_name}?api-version=v1",
                        headers=foundry_headers, timeout=60)
        time.sleep(1)
        r = requests.post(agent_url, headers=foundry_headers, json=agent_body, timeout=60)
    r.raise_for_status()
    created_resources["foundry_agent"] = agent_name
    print(f"Agent ready: {agent_name}")

    # 3) Conversation + first turn
    r = requests.post(f"{project_endpoint}/openai/v1/conversations",
                      headers=foundry_headers, json={}, timeout=30)
    r.raise_for_status()
    conv_id = r.json()["id"]

    r = requests.post(f"{project_endpoint}/openai/v1/responses",
        headers=foundry_headers,
        json={
            "conversation": conv_id,
            "input": "How are city lights used to track urbanization patterns over time?",
            "agent_reference": {"type": "agent_reference", "name": agent_name},
        },
        timeout=240,
    )
    r.raise_for_status()
    payload = r.json()

    chunks = []
    for item in payload.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") in ("output_text", "text"):
                    chunks.append(c.get("text", ""))
    print("\nFoundry agent answer")
    print("--------------------")
    print("\n".join(chunks) or json.dumps(payload, indent=2)[:1500])

```

## 22 · Microsoft Agent Framework (secondary)

The [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/)
ships first-class MCP transports. To plug the same KB in:

| Piece | What it does |
|---|---|
| `MCPStreamableHTTPTool` | Connects to the KB MCP endpoint and surfaces `knowledge_base_retrieve` as a tool. |
| `OpenAIChatClient` (Azure mode) | Drives the Azure OpenAI Responses API. |
| `Agent` | The minimal runtime — receives the user message, lets the model decide when to call the tool, returns the final answer. |

**Two gotchas worth remembering:**

- The KB MCP server is **stateless** — pass `load_prompts=False` so the
  framework doesn't try to call the unsupported `prompts/list`.
- The api-key (or `x-ms-query-source-authorization` for federated KS)
  must be attached at the HTTP layer. Build an `httpx.AsyncClient(headers=...)`
  and pass it in via `http_client=`.


```python
import warnings, asyncio
warnings.filterwarnings("ignore", message=".*is experimental.*")

import httpx
from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework_openai import OpenAIChatClient


async def run_maf() -> str:
    mcp_http = httpx.AsyncClient(
        headers={"api-key": SEARCH_API_KEY, "Accept": "application/json, text/event-stream"},
        timeout=httpx.Timeout(120.0, connect=30.0),
    )
    try:
        async with MCPStreamableHTTPTool(
            name="foundry_iq_kb",
            url=MCP_URL,
            http_client=mcp_http,
            allowed_tools=["knowledge_base_retrieve"],
            approval_mode="never_require",
            load_prompts=False,
        ) as kb_tool:
            chat_client = OpenAIChatClient(
                azure_endpoint=AOAI_ENDPOINT,
                api_key=AOAI_API_KEY,
                api_version="preview",
                model=GPT_DEPLOYMENT,
            )
            agent = Agent(
                client=chat_client,
                name="MasteringFoundryIqAgent",
                instructions=(
                    "You are a grounded research assistant. For every user question, "
                    "call foundry_iq_kb-knowledge_base_retrieve first and answer only "
                    "with information returned by the tool. Always preserve the "
                    "[ref_id:N] citations the tool returns."
                ),
                tools=kb_tool,
            )
            response = await agent.run(
                "What patterns of light do auroras create when observed from orbit at night?"
            )
            return response.text
    finally:
        await mcp_http.aclose()


maf_answer = await run_maf()
print("Microsoft Agent Framework answer")
print("--------------------------------")
print(maf_answer)

```

## 23 · Clean up

The KB, every KS, the sample index, the Foundry agent, and the Foundry
project connection are all chargeable. We delete them in dependency order
so a re-run starts from a blank slate.

Comment this cell out if you want to keep the KB for further experimentation.


```python
# 1) Delete the Foundry agent + project connection (best-effort).
if created_resources.get("foundry_agent"):
    try:
        cred = DefaultAzureCredential()
        foundry_token = cred.get_token("https://ai.azure.com/.default").token
        arm_token = cred.get_token("https://management.azure.com/.default").token
        requests.delete(
            f"{project_endpoint}/agents/{created_resources['foundry_agent']}?api-version=v1",
            headers={"Authorization": f"Bearer {foundry_token}"}, timeout=60,
        )
        print(f"Deleted Foundry agent: {created_resources['foundry_agent']}")
        requests.delete(
            created_resources["foundry_connection_url"],
            headers={"Authorization": f"Bearer {arm_token}"}, timeout=60,
        )
        print("Deleted Foundry project connection.")
    except Exception as exc:
        print(f"Foundry cleanup partial: {exc}")

# 2) Delete the KB.
if created_resources.get("kb"):
    r = requests.delete(kb_url(created_resources["kb"]), headers=SEARCH_HEADERS, timeout=60)
    print(f"Deleted KB {created_resources['kb']} (HTTP {r.status_code})")

# 3) Delete every KS we created.
for ks in created_ks:
    r = requests.delete(ks_url(ks), headers=SEARCH_HEADERS, timeout=60)
    print(f"Deleted KS {ks} (HTTP {r.status_code})")

# 4) Delete the sample index.
if created_resources.get("index"):
    try:
        index_client.delete_index(created_resources["index"])
        print(f"Deleted index {created_resources['index']}")
    except Exception as exc:
        print(f"Index delete: {exc}")

```

## 24 · Next steps

You now have the full **Index → KS (× many) → KB → Agent** pipeline working
with agentic retrieval, multi-turn context, answer synthesis, and both
Foundry Agent + Microsoft Agent Framework consumers. From here:

- **Productionize Foundry Agent auth** — Step 21 used `ProjectManagedIdentity`.
  For federated KS (Remote SharePoint, WorkIQ) wire **per-user OBO** by
  passing `x-ms-query-source-authorization` via `structured_inputs`.
  See: [Connect a knowledge base to a Foundry agent](https://learn.microsoft.com/azure/foundry/agents/how-to/foundry-iq-connect).
- **Add Purview ACL trim** to your indexed KS (Blob, OneLake, SP, SQL) by
  setting `ingestionPermissionOptions=["userIds","groupIds"]` and passing the
  same OBO header at retrieve time.
- **Tune retrieval** — raise `retrievalReasoningEffort` to `medium` for
  hard queries; switch `outputMode` to `extractiveData` if you want raw
  chunks for a downstream model.
- **Move to Managed Identity end-to-end** — swap `AzureKeyCredential` for
  `DefaultAzureCredential` and assign *Search Service Contributor*,
  *Search Index Data Contributor*, *Cognitive Services User*.
- **Private networking** — see the validated private-KB pattern in
  `Foundry_IQ_Private_Knowledge_Base_with_Foundry_Standard_Agent_Setup`.

### Reference docs

- [Agentic retrieval overview](https://learn.microsoft.com/azure/search/agentic-retrieval-overview)
- [Knowledge Source overview](https://learn.microsoft.com/azure/search/agentic-knowledge-source-overview)
- [Create a Knowledge Base](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-create-knowledge-base)
- [Answer synthesis](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-answer-synthesis)
- [Connect a KB to a Foundry agent](https://learn.microsoft.com/azure/foundry/agents/how-to/foundry-iq-connect)
- [Migration: 2025-08 → 2025-11 (`knowledgeAgents` → `knowledgeBases`)](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-migrate)
