![The Microsoft IQ platform — unified intelligence for enterprise AI. Four knowledge layers shown side by side: Work IQ (“how your employees work”) grounds on context about people, collaboration, and workflows; Fabric IQ (“how your business operates”) grounds on business entities, systems of record, and actions; Foundry IQ (“how your agents unlock knowledge”) grounds on policies, authoritative documents, and knowledge bases; and Web IQ (“how you connect to web intelligence”) grounds on context from the web, news, images, and video.](media/microsoft-iq-in-foundry/01-architecture.png)

# Build a Microsoft IQ knowledge layer in Foundry IQ

[**Microsoft IQ**](https://learn.microsoft.com/en-us/microsoft-iq/) is a family
of knowledge layers that give AI agents the context they need to act with
judgment. Each IQ grounds a different slice of reality:

| Microsoft IQ | What it grounds on |
|---|---|
| [**Work IQ**](https://learn.microsoft.com/en-us/microsoft-iq/) | The live understanding of *how your people work* — mail, chats, files, and meetings across Microsoft 365. |
| [**Fabric IQ**](https://learn.microsoft.com/en-us/microsoft-iq/) | The live state of *your business* as a semantic **ontology** in Microsoft Fabric — here, an **airline ontology** (flights, routes, aircraft, crews). |
| [**Web IQ**](https://aka.ms/WebIQLearn) | Fresh, real-world intelligence from the **open web** — web, news, videos, and browse. |
| [**Foundry IQ**](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview) | The **federation layer**. It curates the other IQs into one Knowledge Base and grounds any agent. |

**Foundry IQ is the layer you build here.** It is built on Azure AI Search's
information-retrieval ranking and **agentic-retrieval** pipelines: a *Knowledge
Base* (KB) fans a single natural-language question out across many *Knowledge
Sources* (KS), then plans, retrieves, reranks, and **synthesizes a cited
answer**. Wire Work IQ, Fabric IQ, and Web IQ in as three federated sources and
you get one knowledge layer that grounds *any* agent with work, business, and
web knowledge at once.

The arc of this recipe: **three Microsoft IQ sources → one Foundry IQ Knowledge
Base → a query that proves each IQ answers, plus a cross-source query that joins
them**. We stop at retrieval — the closing section shows how to point any agent
at the resulting MCP endpoint.

> **Preview status & region.** These federated KS types (Work IQ, Fabric
> ontology, Web IQ via MCP) are **preview** on the `2026-05-01-preview` Search
> API. Your Search service must live in a
> [preview region](https://learn.microsoft.com/azure/search/search-region-support)
> — this recipe was authored against **West Central US**. GA timing and region
> coverage change; check
> [What's new](https://learn.microsoft.com/azure/search/whats-new) first.

> **Note on running this notebook.** Every section degrades gracefully: any IQ
> whose credential/entitlement is missing prints a `[skipped]` line and the rest
> still runs top-to-bottom. Cells ship with **outputs cleared** — they call live
> Azure / Foundry / Microsoft Grounding endpoints, so run them against your own
> resources.


## 1 · Prerequisites

Each Microsoft IQ has its own access path. Foundry IQ (the KB) only needs an
Azure AI Search service + a chat model; the three IQs you federate in have the
gates below.

| Requirement | Notes |
|---|---|
| **Azure AI Search service** (Foundry IQ) | In a [region that provides agentic retrieval](https://learn.microsoft.com/azure/search/search-region-support) (e.g. **West Central US**). Use *Search Service Contributor* (keyless, recommended) or an admin key. |
| **Microsoft Foundry project** | One chat model deployment (e.g. `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`) — the KB planner/synthesizer. |
| **Work IQ access** *(gated + licensed)* | Work IQ retrieval is **off by default**. Register the `EnableFoundryIQWithWorkIQ` feature flag, re-register the `Microsoft.Search` provider, and have a tenant admin submit the [Work IQ access request form](https://aka.ms/foundry-iq-work-iq-admin-consent-form). Each querying user needs a **Microsoft 365 Copilot license**, and the search service + Work IQ + users must share **one Entra tenant**. How-to: [Work IQ knowledge source](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-work-iq?pivots=python). |
| **Fabric IQ ontology** | A Fabric workspace with the [ontology tenant settings](https://learn.microsoft.com/fabric/iq/ontology/overview-tenant-settings) enabled and an [ontology item](https://learn.microsoft.com/fabric/iq/ontology/tutorial-1-create-ontology) — in the **same Entra tenant** as the search service. How-to: [Fabric ontology knowledge source](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-fabric-ontology?pivots=python). |
| **Web IQ access** *(waitlist)* | Web IQ is available through a **waitlist** — [join here](https://aka.ms/webiq-waitlist) ([learn more](https://aka.ms/WebIQLearn)). Once approved you get an API key for the **remote Microsoft Grounding MCP server** at `https://api.microsoft.ai/v3/mcp`. |

> **One token, two per-user IQs.** Both Work IQ and Fabric IQ enforce
> permissions at query time via an **on-behalf-of (OBO)** token — you pass the
> *signed-in user's* token (audience `https://search.azure.com/.default`) on the
> retrieve call. §7 mints it for you. Web IQ uses its own stored `x-apikey`.

### Configure your environment

Set these in your shell, or drop them into a local `.env` next to this notebook
(the repo `.gitignore` already excludes `.env`). **Secrets are read from the
environment — never written into this notebook.**

```bash
SEARCH_ENDPOINT=https://<your-search-service>.search.windows.net
SEARCH_API_KEY=<your-search-admin-key>
AOAI_ENDPOINT=https://<your-foundry-resource>.openai.azure.com
AOAI_API_KEY=<your-azure-openai-key>
AOAI_GPT_DEPLOYMENT=gpt-4.1                  # or gpt-4.1-mini, gpt-4o, ...

# Secret — required for Web IQ (§5). Leave blank to skip that source.
WEB_IQ_MCP_API_KEY=<your-web-iq-mcp-key>

# Fabric IQ ontology IDs (defaults below point at a sample airline ontology).
FABRIC_WORKSPACE_ID=<your-fabric-workspace-id>
FABRIC_ONTOLOGY_ID=<your-fabric-ontology-id>
```

### Install dependencies

This recipe pins the public-preview `azure-search-documents` build that exposes
the `2026-05-01-preview` Knowledge Base / Knowledge Source surface.


```python
%%capture
# Foundry IQ rides on the public-preview azure-search-documents SDK, which
# exposes the 2026-05-01-preview Knowledge Base / Knowledge Source surface.
# It ships on PyPI -- no extra package feed required.
import importlib.metadata as _md

try:
    _ok = _md.version("azure-search-documents").startswith("12.1.0b")
except _md.PackageNotFoundError:
    _ok = False

if not _ok:
    %pip install --quiet \
        "azure-search-documents==12.1.0b1" \
        "azure-identity>=1.19.0" \
        "azure-core>=1.32.0" \
        "python-dotenv>=1.0.1"

```

## 2 · Configure clients + helpers

One `SearchIndexClient` + one `AzureKeyCredential` are reused throughout:

- `env(name, required=...)` — env-var lookup (with `.env` support) and a
  friendly error. **Secrets like `WEB_IQ_MCP_API_KEY` are read here — never
  hard-coded.**
- `skip(section, reason)` — prints a `[skipped]` line so a missing
  credential never breaks the run.
- `summarize_ks(name)` — prints the SDK status of a KS right after create.
- `created_ks` — every IQ section appends to it on success; §6 builds the
  single Foundry IQ KB from whatever it finds.
- `created_resources` — a dict the cleanup section (§9) walks in dependency
  order.


```python
import os
from typing import Optional

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import __version__ as search_sdk_version
from azure.search.documents.indexes import SearchIndexClient
from dotenv import load_dotenv

load_dotenv(override=True)


def env(name: str, *, required: bool = True, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value or None


def foundry_resource_uri(endpoint: str) -> str:
    # Strip any /openai/... path so we have the bare Foundry resource URI.
    return endpoint.split("/openai/", 1)[0].rstrip("/")


# ---- Required ------------------------------------------------------------
SEARCH_ENDPOINT = env("SEARCH_ENDPOINT")
SEARCH_API_KEY = env("SEARCH_API_KEY")
AOAI_ENDPOINT = foundry_resource_uri(env("AOAI_ENDPOINT"))
AOAI_API_KEY = env("AOAI_API_KEY")

GPT_DEPLOYMENT = env("AOAI_GPT_DEPLOYMENT", required=False, default="gpt-4.1")
GPT_MODEL = env("AOAI_GPT_MODEL", required=False, default=GPT_DEPLOYMENT)

# ---- Resource names ------------------------------------------------------
KS_WORK_IQ = "miq-ks-work-iq"
KS_FABRIC_IQ = "miq-ks-fabric-iq"
KS_WEB_IQ = "miq-ks-web-iq"
KB_NAME = "miq-foundry-iq-kb"

credential = AzureKeyCredential(SEARCH_API_KEY)
index_client = SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=credential)

# ---- Trackers consumed by the KB section and cleanup --------------------
created_ks: list[str] = []
created_resources: dict[str, str] = {}

print(f"azure-search-documents : {search_sdk_version}")
print(f"Search service         : {SEARCH_ENDPOINT}")
print(f"Foundry endpoint       : {AOAI_ENDPOINT}")
print(f"Chat deployment        : {GPT_DEPLOYMENT} ({GPT_MODEL})")

```

```python
from azure.core.exceptions import ResourceNotFoundError


def skip(section: str, reason: str) -> None:
    print(f"[skipped] {section}: {reason}")


def summarize_ks(name: str) -> None:
    """Print the SDK status of a Knowledge Source after create."""
    try:
        status = index_client.get_knowledge_source_status(name)
    except Exception as exc:  # pragma: no cover - best-effort summary
        print(f"  status: <unavailable: {exc.__class__.__name__}>")
        return
    sync = getattr(status, "synchronization_status", None) or "?"
    last_state = getattr(status, "last_synchronization_state", None)
    last = getattr(last_state, "status", None) if last_state else "n/a"
    stats = getattr(status, "statistics", None) or {}
    print(f"  synchronizationStatus={sync}  lastSync={last}  stats={stats}")

```

## 3 · Work IQ — how your people work

[**Work IQ**](https://learn.microsoft.com/en-us/microsoft-iq/) is the live
understanding of how your organization works: the mail, chats, files, and
meetings across Microsoft 365. As a Foundry IQ Knowledge Source it grounds
agents in *your* tenant's work content.

| | |
|---|---|
| **`kind`** | `workIQ` |
| **Grounds on** | Microsoft 365 work content (mail, chats, files, meetings) via Work IQ. |
| **Pipeline** | Federated — queries Work IQ live at retrieve time; nothing is indexed. |
| **Auth model** | **Per-user OBO.** Each retrieve passes the caller's token via `x-ms-query-source-authorization` (audience `https://search.azure.com/.default`); the engine exchanges it for a Work IQ token and enforces that user's M365 permissions. |

The typed model is intentionally tiny — `workIQ` takes **only** a `name` and
`description` (no parameters object). Creation requires the gated access from
§1, so we wrap it in `try/except` and `skip()` cleanly if your tenant isn't
enabled yet.

> **Gated + licensed.** Register the `EnableFoundryIQWithWorkIQ` feature flag,
> re-register `Microsoft.Search`, and have a tenant admin complete the
> [access request form](https://aka.ms/foundry-iq-work-iq-admin-consent-form).
> Each querying user needs a **Microsoft 365 Copilot license**.

> **Latency.** Work IQ can take **40–60 seconds or more** to respond. Keep
> `max_runtime_in_seconds` at **120+** on the retrieve call (we use 180 in §7).

[Create a Work IQ knowledge source (Python)](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-work-iq?pivots=python)


```python
from azure.search.documents.indexes.models import WorkIQKnowledgeSource

# Work IQ takes no parameters object -- just name + description (kind="workIQ").
ks = WorkIQKnowledgeSource(
    name=KS_WORK_IQ,
    description="Work IQ -- tenant mail, chats, files, and meetings via Microsoft 365.",
)
try:
    index_client.create_or_update_knowledge_source(ks)
    created_ks.append(KS_WORK_IQ)
    print(f"Created {KS_WORK_IQ}")
    summarize_ks(KS_WORK_IQ)
except Exception as exc:
    skip(KS_WORK_IQ, f"create failed (tenant may not be entitled for Work IQ): {exc}")

```

## 4 · Fabric IQ — the live state of your business

[**Fabric IQ**](https://learn.microsoft.com/en-us/microsoft-iq/) represents the
live state of your business as a semantic **ontology** in Microsoft Fabric —
entities, relationships, properties, and rules. Here it's an **airline
ontology** (flights, routes, aircraft, crews), so agents answer in business
terms instead of reasoning over raw tables.

| | |
|---|---|
| **`kind`** | `fabricOntology` |
| **Grounds on** | A semantic ontology in Microsoft Fabric — an airline ontology. |
| **Pipeline** | Federated — queries the ontology graph in Fabric live. |
| **Auth model** | **Two layers.** *Creation:* the search service's **managed identity** needs access to the Fabric workspace. *Retrieval:* a per-user `query_source_authorization` OBO token (audience `https://search.azure.com/.default`), which the engine exchanges for a Fabric-scoped token (see §7). |

A Fabric ontology is addressed by a **workspace id** + **ontology id** (both
visible in the Fabric portal URL of the ontology item). Set them via
`FABRIC_WORKSPACE_ID` / `FABRIC_ONTOLOGY_ID`.

> **Reasoning-effort constraint.** Fabric Ontology sources **don't support the
> `minimal`** retrieval reasoning effort — use **`low`** or **`medium`**. Our KB
> in §6 uses `low`.

> **Response shape.** Fabric references carry `sourceData.fabricAnswer` (a
> natural-language answer) and `sourceData.fabricRawData` (the grounding data as
> CSV). Set `include_reference_source_data=True` (we do, in §7) to receive them.

> **Managed-identity gotcha.** If creation or retrieval returns a `403`/access
> error, grant the search service identity **Viewer** (or higher) on the Fabric
> workspace, then re-run.

[Create a Fabric ontology knowledge source (Python)](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-fabric-ontology?pivots=python)


```python
from azure.search.documents.indexes.models import (
    FabricOntologyKnowledgeSource,
    FabricOntologyKnowledgeSourceParameters,
)

# Point this at YOUR ontology. Both IDs are in the Fabric ontology item URL:
#   https://app.fabric.microsoft.com/groups/<workspace-id>/ontologies/<ontology-id>
# This recipe uses an airline ontology as the running example; substitute your own.
FABRIC_WORKSPACE_ID = env("FABRIC_WORKSPACE_ID", required=False)
FABRIC_ONTOLOGY_ID = env("FABRIC_ONTOLOGY_ID", required=False)

if not (FABRIC_WORKSPACE_ID and FABRIC_ONTOLOGY_ID):
    skip(KS_FABRIC_IQ, "set FABRIC_WORKSPACE_ID and FABRIC_ONTOLOGY_ID to your own ontology to enable Fabric IQ")
else:
    ks = FabricOntologyKnowledgeSource(
        name=KS_FABRIC_IQ,
        description="Fabric IQ -- a business ontology (here, an airline ontology: flights, routes, aircraft, crews) in Microsoft Fabric.",
        fabric_ontology_parameters=FabricOntologyKnowledgeSourceParameters(
            workspace_id=FABRIC_WORKSPACE_ID,
            ontology_id=FABRIC_ONTOLOGY_ID,
        ),
    )
    try:
        index_client.create_or_update_knowledge_source(ks)
        created_ks.append(KS_FABRIC_IQ)
        print(f"Created {KS_FABRIC_IQ} (workspace={FABRIC_WORKSPACE_ID}, ontology={FABRIC_ONTOLOGY_ID})")
        summarize_ks(KS_FABRIC_IQ)
    except Exception as exc:
        skip(KS_FABRIC_IQ, f"create failed (check Search MI access to the Fabric workspace): {exc}")

```

## 5 · Web IQ — fresh real-world web intelligence

[**Web IQ**](https://aka.ms/WebIQLearn) gives agents fresh, real-world
intelligence from the open web — web pages, news, videos, and browse — through
the **remote Microsoft Grounding MCP server** at `https://api.microsoft.ai/v3/mcp`.
Foundry IQ federates it in as an MCP Server Knowledge Source.

> **Access is waitlisted.** You must [**join the Web IQ waitlist**](https://aka.ms/webiq-waitlist)
> to get an API key. Once approved, set it as `WEB_IQ_MCP_API_KEY` (secret).
> Until then, this section `skip()`s and the rest of the notebook still runs.

| | |
|---|---|
| **`kind`** | `mcpServer` |
| **Grounds on** | The live web via the remote Web IQ / Microsoft Grounding MCP server. |
| **Tools** | `web`, `news`, `videos`, `browse` — each reranked and capped at 4096 output tokens. |
| **Auth model** | A **stored header** (`x-apikey`) carrying your Web IQ MCP key. |
| **Env vars** | `WEB_IQ_MCP_API_KEY` (**secret** — read from the environment, never committed). |

> **Why stored headers and not a Foundry connection?** The MCP server supports
> both a `foundryConnection` auth variant and a `storedHeaders` variant. As of
> this preview, the `foundryConnection` form returns **HTTP 502 "Could not
> resolve the tool manifest"** on KB Retrieve (a known preview bug). The
> `storedHeaders` form (below) sends `x-apikey` directly and works reliably.

[MCP Server knowledge source (Python)](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-overview)


```python
from azure.search.documents.indexes.models import (
    McpServerKnowledgeSource,
    McpServerKnowledgeSourceParameters,
    McpServerStoredHeadersAuthentication,
    McpServerStoredHeadersParameters,
)

WEB_IQ_MCP_SERVER_URL = "https://api.microsoft.ai/v3/mcp"  # public URL -- fine to commit

# The API key is a SECRET: read it from the environment, never hard-code it.
web_iq_key = env("WEB_IQ_MCP_API_KEY", required=False)

if not web_iq_key:
    skip(KS_WEB_IQ, "set WEB_IQ_MCP_API_KEY (your Web IQ MCP key) to enable Web IQ -- join the waitlist at https://aka.ms/webiq-waitlist")
else:
    web_iq_tools = [
        {"name": "web",    "outputParsing": {"kind": "auto"}, "inclusionMode": "reranked", "maxOutputTokens": 4096},
        {"name": "news",   "outputParsing": {"kind": "auto"}, "inclusionMode": "reranked", "maxOutputTokens": 4096},
        {"name": "videos", "outputParsing": {"kind": "auto"}, "inclusionMode": "reranked", "maxOutputTokens": 4096},
        {"name": "browse", "outputParsing": {"kind": "auto"}, "inclusionMode": "reranked", "maxOutputTokens": 4096},
    ]
    ks = McpServerKnowledgeSource(
        name=KS_WEB_IQ,
        description="Web IQ -- Microsoft Grounding MCP server (web, news, videos, browse).",
        mcp_server_parameters=McpServerKnowledgeSourceParameters(
            server_url=WEB_IQ_MCP_SERVER_URL,
            # storedHeaders auth (x-apikey). NOT foundryConnection -- that variant
            # currently 502s ("Could not resolve the tool manifest") on KB Retrieve.
            authentication=McpServerStoredHeadersAuthentication(
                stored_headers_parameters=McpServerStoredHeadersParameters(
                    headers={"x-apikey": web_iq_key},
                ),
            ),
            tools=web_iq_tools,
        ),
    )
    try:
        index_client.create_or_update_knowledge_source(ks)
        created_ks.append(KS_WEB_IQ)
        print(f"Created {KS_WEB_IQ} ({WEB_IQ_MCP_SERVER_URL})")
        summarize_ks(KS_WEB_IQ)
    except Exception as exc:
        skip(KS_WEB_IQ, f"create failed: {exc}")

```

## 6 · Build the Foundry IQ Knowledge Base

One **Foundry IQ** Knowledge Base consumes whichever of the three Microsoft IQ
sources came up. The KB:

| Setting | What it controls |
|---|---|
| `models` | The Azure OpenAI chat model that **plans** subqueries and **synthesizes** the answer. |
| `knowledge_sources` | The federated IQs in scope — Work IQ, Fabric IQ, Web IQ. |
| `retrieval_reasoning_effort` | `low` / `medium` — how hard the planner thinks before fanning out. |
| `output_mode` | `extractiveData` (raw chunks) or **`answerSynthesis`** (cited NL answer). |

We pick **`answerSynthesis`** + **`low`** — the production-friendly default.
(`low` also satisfies Fabric IQ, which **rejects `minimal`**.) The cell raises
only if *none* of the three IQs were created.


```python
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizerParameters,
    KnowledgeBase,
    KnowledgeBaseAzureOpenAIModel,
    KnowledgeSourceReference,
)
from azure.search.documents.knowledgebases.models import (
    KnowledgeRetrievalLowReasoningEffort,
    KnowledgeRetrievalOutputMode,
)

if not created_ks:
    raise RuntimeError(
        "No Knowledge Sources were created -- cannot build a KB. Enable at least "
        "one of Work IQ / Fabric IQ / Web IQ above."
    )

# Build the Foundry IQ KB over whatever Microsoft IQ sources came up this run.
kb_sources = list(created_ks)
print(f"Building Foundry IQ KB '{KB_NAME}' over {len(kb_sources)} federated source(s):")
for n in kb_sources:
    print(f"  - {n}")

gpt_params = AzureOpenAIVectorizerParameters(
    resource_url=AOAI_ENDPOINT,
    deployment_name=GPT_DEPLOYMENT,
    api_key=AOAI_API_KEY,
    model_name=GPT_MODEL,
)

kb = KnowledgeBase(
    name=KB_NAME,
    description="Foundry IQ KB federating Work IQ, Fabric IQ (airline ontology), and Web IQ.",
    models=[KnowledgeBaseAzureOpenAIModel(azure_open_ai_parameters=gpt_params)],
    knowledge_sources=[KnowledgeSourceReference(name=n) for n in kb_sources],
    retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort(),
    output_mode=KnowledgeRetrievalOutputMode.ANSWER_SYNTHESIS,
    answer_instructions=(
        "Answer using only the retrieved content across all sources. "
        "When a question spans work content, the airline ontology, and the web, "
        "integrate them faithfully and preserve the [ref_id:N] citations."
    ),
)
index_client.create_or_update_knowledge_base(kb)
created_resources["kb"] = KB_NAME
print(f"\nFoundry IQ Knowledge Base '{KB_NAME}' is ready.")

```

## 7 · Query the knowledge layer

This is the payoff. We run **four** retrievals against the one Foundry IQ KB:

1. **7a Work IQ** — a work question, scoped to Work IQ.
2. **7b Fabric IQ** — an airline-ontology question, scoped to Fabric IQ.
3. **7c Web IQ** — a fresh-web question, scoped to Web IQ.
4. **7d Cross-source** — one question that **joins ≥2 IQs**, with all sources in
   scope.

Each cell prints the synthesized answer, the **reference count per source**, and
a sample extract — so you can *see* each Microsoft IQ grounding the answer.

> **Per-user IQs need a caller token.** Both **Work IQ** and **Fabric IQ** are
> identity-scoped: each retrieve must carry a user token via
> `query_source_authorization` (audience `https://search.azure.com`). **Web IQ**
> authenticates with its own stored `x-apikey`, so it grounds with or without
> the token. The setup cell below mints the signed-in user's token with
> `DefaultAzureCredential`. See
> [Retrieve from a knowledge base (Python)](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve?pivots=python).


```python
import json as _json

from azure.identity import DefaultAzureCredential
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import (
    FabricOntologyKnowledgeSourceParams,
    KnowledgeBaseMessage,
    KnowledgeBaseMessageTextContent,
    KnowledgeBaseRetrievalRequest,
    McpServerKnowledgeSourceParams,
    WorkIQKnowledgeSourceParams,
)

retrieval_client = KnowledgeBaseRetrievalClient(
    endpoint=SEARCH_ENDPOINT,
    credential=credential,
    knowledge_base_name=KB_NAME,
)


def user_query_authorization() -> Optional[str]:
    """Mint the signed-in user's token for the per-user IQs (Work IQ, Fabric IQ)."""
    try:
        token = DefaultAzureCredential().get_token("https://search.azure.com/.default").token
        print("query_source_authorization : acquired user token")
        return token
    except Exception as exc:  # noqa: BLE001 -- best-effort; Web IQ still works
        print(f"query_source_authorization : unavailable ({exc}); Work IQ + Fabric IQ will return no references")
        return None


query_auth = user_query_authorization()


def ks_params_for(name: str, reranker_threshold: Optional[float] = None):
    """Per-kind retrieve params for the federated IQ wired into the KB."""
    common = dict(
        knowledge_source_name=name,
        include_references=True,
        include_reference_source_data=True,
    )
    if reranker_threshold is not None:
        common["reranker_threshold"] = reranker_threshold
    if name == KS_WORK_IQ:
        return WorkIQKnowledgeSourceParams(**common)
    if name == KS_FABRIC_IQ:
        return FabricOntologyKnowledgeSourceParams(**common)
    if name == KS_WEB_IQ:
        return McpServerKnowledgeSourceParams(**common)
    return None


def retrieve(question: str, sources: list[str], *, reranker_threshold=None, max_runtime_seconds: int = 180):
    """Run one KB retrieval, scoped to `sources` (a subset of the KB's IQs)."""
    params = [ks_params_for(n, reranker_threshold) for n in sources]
    request = KnowledgeBaseRetrievalRequest(
        messages=[
            KnowledgeBaseMessage(
                role="user",
                content=[KnowledgeBaseMessageTextContent(text=question)],
            )
        ],
        knowledge_source_params=[p for p in params if p],
        include_activity=True,
        max_runtime_in_seconds=max_runtime_seconds,
    )
    # query_source_authorization auths the per-user IQs (Work IQ, Fabric IQ).
    return retrieval_client.retrieve(request, query_source_authorization=query_auth)


def answer_text(result) -> str:
    parts = []
    for message in (result.response or []):
        for content in (message.content or []):
            text = getattr(content, "text", None)
            if text:
                parts.append(text)
    return "\n\n".join(parts)


def describe_reference(ref) -> str:
    """Pull a human-readable snippet out of a reference, per IQ type."""
    rtype = getattr(ref, "type", None)
    src = ref.source_data or {}
    if not isinstance(src, dict):
        return str(src)[:240]
    if rtype == "fabricOntology":                              # Fabric IQ
        bits = []
        if src.get("fabricAnswer"):
            bits.append(str(src["fabricAnswer"]))
        if src.get("fabricRawData"):
            bits.append("data: " + str(src["fabricRawData"])[:160])
        return "  |  ".join(bits) or _json.dumps(src)[:240]
    if rtype == "workIQ":                                      # Work IQ
        texts = [e.get("text") for e in (src.get("extracts") or []) if e.get("text")]
        more = [a.get("seeMoreWebUrl") for a in (src.get("attributions") or []) if a.get("seeMoreWebUrl")]
        out = (" ".join(texts) or src.get("content") or src.get("text") or "")[:200]
        if more:
            out += f"  (see more: {more[0]})"
        return out or _json.dumps(src)[:240]
    return (src.get("title") or "") + " " + (src.get("content") or src.get("text") or _json.dumps(src))[:200]


def refs_by_type(result) -> dict:
    counts: dict = {}
    for r in (result.references or []):
        t = getattr(r, "type", None)
        counts[t] = counts.get(t, 0) + 1
    return counts


def report(label: str, result, *, max_answer: int = 600, max_refs: int = 3) -> None:
    if result is None:
        print(f"=== {label} ===\n[skipped] source not created this run\n")
        return
    refs = result.references or []
    print(f"=== {label} ===")
    print(f"references: {len(refs)}   by_type: {refs_by_type(result)}")
    ans = answer_text(result).strip()
    if ans:
        print(f"\nANSWER\n------\n{ans[:max_answer]}{'...' if len(ans) > max_answer else ''}")
    for ref in refs[:max_refs]:
        snippet = describe_reference(ref).strip().replace("\n", " ")
        print(f"  [ref_id:{ref.id}] type={getattr(ref, 'type', None)!r} :: {snippet[:200]}")
    print()

```

### 7a · Work IQ — a work question

Scope the retrieve to Work IQ alone and ask about internal work content. A
non-empty `references` list (type `workIQ`) proves Work IQ grounded the answer.


```python
work_question = (
    "Summarize what we've discussed internally about transatlantic route "
    "planning, long-haul fleet decisions, or premium-cabin strategy."
)

if KS_WORK_IQ in kb_sources:
    res_work = retrieve(work_question, [KS_WORK_IQ])
else:
    res_work = None
    skip("7a Work IQ", "Work IQ source not created -- enable it in §3")

report("7a · Work IQ", res_work)

```

### 7b · Fabric IQ — an airline-ontology question

Scope to Fabric IQ and ask a **narrow, aggregate** question the ontology can
answer in business terms. We pass `reranker_threshold=0.0` so on-topic ontology
rows aren't filtered out.

> **Keep Fabric questions narrow.** A broad ontology question ("list every
> aircraft *and* its routes") can trip a **"data is too large to process in a
> single request"** response — Fabric tries to pull a whole entity table.
> Aggregate or scoped questions ("how many aircraft *by manufacturer*?") return
> clean `fabricAnswer` + `fabricRawData`.


```python
fabric_question = (
    "Using our airline ontology, how many aircraft are in the fleet, grouped by "
    "manufacturer?"
)

if KS_FABRIC_IQ in kb_sources:
    # reranker_threshold=0.0 keeps on-ontology rows that a higher bar would drop.
    # A narrow, aggregate question avoids the "data too large" Fabric error you
    # get when a broad query tries to pull an entire entity table at once.
    res_fabric = retrieve(fabric_question, [KS_FABRIC_IQ], reranker_threshold=0.0)
else:
    res_fabric = None
    skip("7b Fabric IQ", "Fabric IQ source not created -- enable it in §4")

report("7b · Fabric IQ", res_fabric)

```

### 7c · Web IQ — a fresh-web question

Scope to Web IQ and ask something only the live web can answer. References of
type `web` / `mcpServer` prove Web IQ grounded the answer. (Web IQ needs no user
token — it uses its stored `x-apikey`.)


```python
web_question = (
    "What's the latest public news on long-haul, transatlantic aircraft and "
    "route announcements from major carriers?"
)

if KS_WEB_IQ in kb_sources:
    res_web = retrieve(web_question, [KS_WEB_IQ])
else:
    res_web = None
    skip("7c Web IQ", "Web IQ source not created -- set WEB_IQ_MCP_API_KEY in §5 (waitlist: https://aka.ms/webiq-waitlist)")

report("7c · Web IQ", res_web)

```

### 7d · Cross-source — join the IQs

Now the hero query. One question that **no single IQ can answer alone**: it pairs
our **fleet composition by manufacturer** (Fabric IQ) with the **latest public
news** on new long-haul aircraft and transatlantic routes (Web IQ), and folds in
any **internal context** (Work IQ). All sources are in scope; the planner fans
out, reranks, and synthesizes one cited answer. The activity trace shows how the
turn was decomposed.


```python
cross_question = (
    "I'm prepping a transatlantic route-planning review. Using our airline "
    "ontology, what is our fleet composition by manufacturer? Then combine that "
    "with the latest public news on new long-haul aircraft and transatlantic "
    "routes — which manufacturers in the news do we already operate? Add "
    "anything we've discussed internally."
)

# reranker_threshold=0.0 lets each IQ's top row survive the shared rerank so the
# answer is grounded across sources, not dominated by one.
res_cross = retrieve(cross_question, kb_sources, reranker_threshold=0.0)
report("7d · Cross-source", res_cross, max_answer=900, max_refs=6)

# The planner activity trace: how the one turn was decomposed across the IQs.
activity = [a.as_dict() if hasattr(a, "as_dict") else dict(a) for a in (res_cross.activity or [])]
print("PLANNER ACTIVITY (truncated)")
print("----------------------------")
print(_json.dumps(activity, indent=2)[:2500])

```

## 8 · Take it further — point any agent at the knowledge layer

You now have one **Foundry IQ Knowledge Base** federating Work IQ, Fabric IQ, and
Web IQ. Every KB also exposes a **Model Context Protocol (MCP) endpoint**, so the
same knowledge layer grounds *any* MCP-compatible agent — no re-plumbing:

```
{SEARCH_ENDPOINT}/knowledgebases/{KB_NAME}/mcp?api-version=2026-05-01-preview
```

The MCP server exposes a single `knowledge_base_retrieve` tool. Point any of
these consumers at it:

- **Foundry Agent Service** — create a `RemoteTool` project connection to the KB
  MCP URL (`authType=ProjectManagedIdentity`) and bind it as an `mcp` tool that
  allow-lists `knowledge_base_retrieve`. See
  [Build an end-to-end agentic retrieval solution](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-create-pipeline)
  and [Retrieve from a knowledge base](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve?pivots=python).
- **Microsoft Agent Framework** — register the same MCP endpoint as a tool on
  your agent and let the framework orchestrate retrieval-augmented turns.
- **GitHub Copilot** (VS Code + CLI) — drop the endpoint into `.vscode/mcp.json`:

```json
{
  "servers": {
    "foundry-iq-kb": {
      "type": "http",
      "url": "https://<your-search>.search.windows.net/knowledgebases/<kb-name>/mcp?api-version=2026-05-01-preview",
      "headers": { "api-key": "${input:search_api_key}" }
    }
  },
  "inputs": [
    { "id": "search_api_key", "type": "promptString", "description": "Azure AI Search query or admin key", "password": true }
  ]
}
```

Run **MCP: Reload Servers**, switch Copilot Chat to **Agent** mode, and it will
call `knowledge_base_retrieve` to ground answers (with `[ref_id:N]` citations) on
your federated Microsoft IQ layer. The `${input:...}` reference keeps the key out
of the committed file.

> **One Knowledge Base, many consumers.** The same URL + header works for the
> Copilot CLI, Claude Desktop, and any other MCP host.


## 9 · Clean up

The KB and the three Knowledge Sources are stateful. We delete them in
dependency order (best-effort, each guarded) so a re-run starts clean. Comment
this out to keep the KB around for the §8 consumers.


```python
# 1) Delete the KB.
if created_resources.get("kb"):
    try:
        index_client.delete_knowledge_base(created_resources["kb"])
        print(f"Deleted KB {created_resources['kb']}")
    except ResourceNotFoundError:
        pass
    except Exception as exc:
        print(f"KB delete: {exc}")

# 2) Delete every KS we created (Work IQ, Fabric IQ, Web IQ).
for ks_name in created_ks:
    try:
        index_client.delete_knowledge_source(ks_name)
        print(f"Deleted KS {ks_name}")
    except ResourceNotFoundError:
        pass
    except Exception as exc:
        print(f"KS {ks_name} delete: {exc}")

```

## 10 · Next steps

You built a **Microsoft IQ knowledge layer** — Work IQ, Fabric IQ, and Web IQ
federated by **Foundry IQ** into one Knowledge Base, proven to answer from each
IQ and across them. From here:

- **Tour every KS type.** The companion recipe
  [Mastering Foundry IQ](mastering-foundry-iq) walks indexed, uploaded, and
  federated sources end-to-end.
- **Mix in indexed sources.** Add a Search Index / Blob / OneLake KS alongside
  these federated IQs for a hybrid KB.
- **Ground an agent.** Wire the KB's MCP endpoint into Foundry Agent Service,
  the Microsoft Agent Framework, or GitHub Copilot (§8).

### Reference docs

- [Microsoft IQ](https://learn.microsoft.com/en-us/microsoft-iq/)
- [Work IQ knowledge source](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-work-iq?pivots=python)
- [Fabric ontology knowledge source](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-fabric-ontology?pivots=python)
- [Web IQ](https://aka.ms/WebIQLearn) · [waitlist](https://aka.ms/webiq-waitlist)
- [Retrieve from a knowledge base](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve?pivots=python)
- [Agentic retrieval overview](https://learn.microsoft.com/azure/search/agentic-retrieval-overview)
- [Create a Knowledge Base](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-create-knowledge-base)
