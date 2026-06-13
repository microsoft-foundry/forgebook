![The Microsoft IQ platform — unified intelligence for enterprise AI. Four knowledge layers shown side by side: Work IQ (“how your employees work”) grounds on context about people, collaboration, and workflows; Fabric IQ (“how your business operates”) grounds on business entities, systems of record, and actions; Foundry IQ (“how your agents unlock knowledge”) grounds on policies, authoritative documents, and knowledge bases; and Web IQ (“how you connect to web intelligence”) grounds on context from the web, news, images, and video.](media/microsoft-iq-in-foundry/01-architecture.png)

# Build your own knowledge layer with Microsoft IQ

[**Microsoft IQ**](https://learn.microsoft.com/en-us/microsoft-iq/) is a family of knowledge layers that ground AI agents in your reality — your files, your people's work, your business, and the live web. [**Foundry IQ**](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview) is the layer that federates them: one **Knowledge Base** that fans a single question across every source, then plans, retrieves, reranks, and returns one cited answer. It runs on Azure AI Search agentic retrieval.

**You'll build it one layer at a time — each layer makes your agent smarter:**

| Layer | Grounds on | Setup |
|---|---|---|
| 📁 **Your files** *(start here)* | Documents you upload straight into Foundry IQ | **None** — runs out of the box |
| 🌐 **Web IQ** | The live web — web + news | Waitlist |
| 👥 **Work IQ** | Microsoft 365 mail, chats, files, meetings | Gated + licensed |
| 📊 **Fabric IQ** | Your business as an ontology in Microsoft Fabric | An ontology item |

Start with the file hero — it works with **zero setup**. Then add the optional layers you have access to; each one re-queries the Knowledge Base so you can *see* the new intelligence. Every optional layer **skips cleanly** if you're not set up for it, so the notebook always runs top to bottom.

> **Preview.** These Knowledge Base / Knowledge Source types are **preview** on the `2026-05-01-preview` Search API. Your Search service must be in a [preview region](https://learn.microsoft.com/azure/search/search-region-support) (e.g. **West Central US**). Cells ship with outputs cleared and call live services — run them against your own resources.


## 1 · Setup

You need an **Azure AI Search** service (in a preview region) and a **Microsoft Foundry** project with one **chat** deployment and one **embedding** deployment (the embedding powers the file hero). Set these, or drop them in a local `.env` next to this notebook — **secrets are read from the environment, never written into the notebook**:

```bash
SEARCH_ENDPOINT=https://<your-search-service>.search.windows.net
SEARCH_API_KEY=<your-search-admin-key>
AOAI_ENDPOINT=https://<your-foundry-resource>.openai.azure.com
AOAI_API_KEY=<your-azure-openai-key>
AOAI_GPT_DEPLOYMENT=gpt-4.1                       # chat / synthesis
AOAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large  # powers the file hero

# Optional — each unlocks one extra layer (leave blank to skip):
WEB_IQ_MCP_API_KEY=<your-web-iq-mcp-key>          # Web IQ
FABRIC_WORKSPACE_ID=<your-fabric-workspace-id>    # Fabric IQ
FABRIC_ONTOLOGY_ID=<your-fabric-ontology-id>      # Fabric IQ
```


```python
%%capture
# Foundry IQ rides on the public-preview azure-search-documents SDK (ships on PyPI).
import importlib.metadata as _md

try:
    _ok = _md.version("azure-search-documents").startswith("12.1.0b")
except _md.PackageNotFoundError:
    _ok = False

if not _ok:
    %pip install --quiet --pre "azure-search-documents==12.1.0b1" \
        "azure-identity>=1.17.1" "openai>=1.40.0" "python-dotenv>=1.0.1"

```

The next cell is the whole engine: it reads your config, then defines two helpers you'll use for the rest of the notebook — **`build_kb(sources)`** (create/update the Foundry IQ Knowledge Base over a set of sources) and **`ask(question)`** (send one natural-language question and print the cited answer plus which sources grounded it). Each layer below just creates a Knowledge Source, appends it, and calls these two.


```python
import os, time
from pathlib import Path
from typing import Optional

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.search.documents import __version__ as sdk_version
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizerParameters,
    KnowledgeBase,
    KnowledgeBaseAzureOpenAIModel,
    KnowledgeSourceReference,
)
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import (
    FabricOntologyKnowledgeSourceParams,
    FileKnowledgeSourceParams,
    KnowledgeBaseMessage,
    KnowledgeBaseMessageTextContent,
    KnowledgeBaseRetrievalRequest,
    KnowledgeRetrievalLowReasoningEffort,
    KnowledgeRetrievalOutputMode,
    KnowledgeSourceAzureOpenAIVectorizer,
    KnowledgeSourceIngestionParameters,
    McpServerKnowledgeSourceParams,
    WorkIQKnowledgeSourceParams,
)
from dotenv import load_dotenv

load_dotenv(override=True)


def env(name: str, *, required: bool = True, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value or None


def skip(layer: str, reason: str) -> None:
    print(f"[skipped] {layer}: {reason}")


# ---- Config --------------------------------------------------------------
SEARCH_ENDPOINT = env("SEARCH_ENDPOINT")
SEARCH_API_KEY = env("SEARCH_API_KEY")
AOAI_ENDPOINT = env("AOAI_ENDPOINT").split("/openai/", 1)[0].rstrip("/")
AOAI_API_KEY = env("AOAI_API_KEY")
GPT_DEPLOYMENT = env("AOAI_GPT_DEPLOYMENT", required=False, default="gpt-4.1")
EMBEDDING_DEPLOYMENT = env("AOAI_EMBEDDING_DEPLOYMENT", required=False, default="text-embedding-3-large")

KS_FILES = "miq-ks-files"
KS_WEB_IQ = "miq-ks-web-iq"
KS_WORK_IQ = "miq-ks-work-iq"
KS_FABRIC_IQ = "miq-ks-fabric-iq"
KB_NAME = "miq-foundry-iq-kb"

credential = AzureKeyCredential(SEARCH_API_KEY)
index_client = SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=credential)
kb_client = KnowledgeBaseRetrievalClient(
    endpoint=SEARCH_ENDPOINT, credential=credential, knowledge_base_name=KB_NAME,
)

kb_sources: list[str] = []  # grows as you add layers; drives the KB and cleanup


def _aoai(deployment: str) -> AzureOpenAIVectorizerParameters:
    return AzureOpenAIVectorizerParameters(
        resource_url=AOAI_ENDPOINT, deployment_name=deployment,
        api_key=AOAI_API_KEY, model_name=deployment,
    )


def file_ingestion_parameters() -> KnowledgeSourceIngestionParameters:
    """Minimal extraction + Foundry embedding for the uploaded-files layer."""
    return KnowledgeSourceIngestionParameters(
        content_extraction_mode="minimal",
        embedding_model=KnowledgeSourceAzureOpenAIVectorizer(azure_open_ai_parameters=_aoai(EMBEDDING_DEPLOYMENT)),
    )


# Work IQ + Fabric IQ enforce per-user permissions: pass the signed-in user's
# token on retrieve. Best-effort -- Web IQ + files work without it.
try:
    USER_TOKEN = DefaultAzureCredential().get_token("https://search.azure.com/.default").token
except Exception as exc:  # noqa: BLE001
    USER_TOKEN = None
    print(f"(no user token: {exc}; Work IQ + Fabric IQ will return no references)")


def build_kb(sources: list[str]) -> None:
    """Create/update the one Foundry IQ Knowledge Base over `sources`."""
    kb = KnowledgeBase(
        name=KB_NAME,
        description="Foundry IQ Knowledge Base layering your files, Web IQ, Work IQ, and Fabric IQ.",
        models=[KnowledgeBaseAzureOpenAIModel(azure_open_ai_parameters=_aoai(GPT_DEPLOYMENT))],
        knowledge_sources=[KnowledgeSourceReference(name=n) for n in sources],
        retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort(),
        output_mode=KnowledgeRetrievalOutputMode.ANSWER_SYNTHESIS,
        retrieval_instructions=(
            "Route each subquery to the source most likely to answer it: use the files "
            "source for uploaded company documents; Web IQ for current events and public "
            "information; Work IQ for internal people and collaboration context; Fabric IQ "
            "for live business facts from the ontology. Use several when a question spans more than one."
        ),
        answer_instructions="Answer only from the retrieved content and keep the [ref_id:N] citations.",
    )
    index_client.create_or_update_knowledge_base(kb)
    print(f"Knowledge Base '{KB_NAME}' now covers {len(sources)} source(s): {', '.join(sources)}")


def _ks_params(name: str):
    common = dict(knowledge_source_name=name, include_references=True, include_reference_source_data=True)
    if name == KS_FILES:
        return FileKnowledgeSourceParams(**common)
    if name == KS_WEB_IQ:
        return McpServerKnowledgeSourceParams(knowledge_source_name=name, include_references=True)
    if name == KS_WORK_IQ:
        return WorkIQKnowledgeSourceParams(**common)
    if name == KS_FABRIC_IQ:
        return FabricOntologyKnowledgeSourceParams(reranker_threshold=0.0, **common)
    return None


def ask(question: str, *, max_runtime_seconds: int = 180) -> None:
    """Send one question to the KB; print the cited answer and grounding sources.

    A KB update takes a few seconds to reach the retrieve path, so a query fired
    immediately after build_kb() can transiently 400 with "must match a Knowledge
    Base Knowledge Source name" -- retry briefly to let the update propagate.
    """
    request = KnowledgeBaseRetrievalRequest(
        messages=[KnowledgeBaseMessage(role="user", content=[KnowledgeBaseMessageTextContent(text=question)])],
        knowledge_source_params=[p for p in (_ks_params(n) for n in kb_sources) if p],
        include_activity=True,
        max_runtime_in_seconds=max_runtime_seconds,
    )
    for attempt in range(1, 6):
        try:
            result = kb_client.retrieve(request, query_source_authorization=USER_TOKEN)
            break
        except Exception as exc:  # noqa: BLE001
            if "must match" in str(exc) and attempt < 5:
                time.sleep(4)
                continue
            raise
    answer = "\n\n".join(
        c.text for m in (result.response or []) for c in (m.content or []) if getattr(c, "text", None)
    ).strip()
    grounded: dict = {}
    for r in (result.references or []):
        t = getattr(r, "type", None)
        grounded[t] = grounded.get(t, 0) + 1
    print(f"Q: {question}\n\n{answer or '(no answer)'}\n\ngrounded by: {grounded}")


def enable(ks_name: str, question: str, *, max_runtime_seconds: int = 180) -> None:
    """Add a just-created Knowledge Source to the KB, re-query, and (if the query
    fails) roll the source back out so later layers stay clean."""
    kb_sources.append(ks_name)
    try:
        build_kb(kb_sources)
        ask(question, max_runtime_seconds=max_runtime_seconds)
    except Exception as exc:  # noqa: BLE001
        kb_sources.remove(ks_name)
        if kb_sources:
            build_kb(kb_sources)
        skip(ks_name, f"created the source but the query failed: {str(exc)[:140]}")


print(f"azure-search-documents {sdk_version}  |  search: {SEARCH_ENDPOINT}")
print(f"chat: {GPT_DEPLOYMENT}  |  embedding: {EMBEDDING_DEPLOYMENT}")

```

## 2 · Start with your files 📁

The fastest knowledge layer: **upload files straight into Foundry IQ** — no storage account, no indexer, no data source. Foundry IQ extracts and embeds each file for you (`kind="file"`). To run with **zero setup**, the cell below writes a tiny built-in company brief and uploads that; point `ZAVA_FILE` at your own PDF / DOCX / HTML / TXT to use real documents.

Create the Knowledge Source, upload, **`build_kb()`**, and **`ask()`** — your agent can already answer from your files.


```python
from azure.search.documents.indexes.models import FileKnowledgeSource, FileKnowledgeSourceParameters

# Built-in sample so the hero runs with zero setup. Replace with your own files
# by setting ZAVA_FILE to a local path.
sample = Path("data/microsoft-iq-in-foundry/zava-brief.md")
sample.parent.mkdir(parents=True, exist_ok=True)
sample.write_text(
    "# Zava Air \u2014 Company Brief\n\n"
    "Zava Air is a mid-size carrier specializing in transatlantic routes between "
    "North America and Europe. Our strategy is to standardize on fuel-efficient "
    "widebody aircraft and grow premium-cabin capacity on long-haul corridors.\n\n"
    "## Fleet strategy\n"
    "- Consolidate around two widebody families to simplify maintenance and crew training.\n"
    "- Prioritize range and fuel efficiency for transatlantic missions.\n"
    "- Retire older narrowbodies as widebody deliveries arrive.\n\n"
    "## Network\n"
    "Primary hubs anchor the transatlantic network; we add seasonal frequency on the "
    "highest-demand premium corridors.\n",
    encoding="utf-8",
)
file_path = Path(env("ZAVA_FILE", required=False, default=str(sample))).expanduser()

# 1) Create the File Knowledge Source.
index_client.create_or_update_knowledge_source(
    FileKnowledgeSource(
        name=KS_FILES,
        description="Your own files, uploaded straight into Foundry IQ -- no storage account.",
        file_parameters=FileKnowledgeSourceParameters(ingestion_parameters=file_ingestion_parameters()),
    )
)

# 2) Upload the file (pass filename so Foundry can label the blob). The upload
#    triggers a synchronous embed pass, which can transiently 429 on shared
#    embedding deployments -- retry with backoff.
for attempt in range(1, 6):
    try:
        with file_path.open("rb") as fh:
            uploaded = index_client.upload_knowledge_source_file(KS_FILES, fh.read(), filename=file_path.name)
        break
    except Exception as exc:  # noqa: BLE001
        if "429" in str(exc) and attempt < 5:
            time.sleep(2 ** attempt)
            continue
        raise
print(f"Uploaded {file_path.name} ({uploaded.file_size_bytes:,} bytes)")

# 3) Build the KB over just your files, and ask.
kb_sources.append(KS_FILES)
build_kb(kb_sources)
ask("What does Zava Air do, and what is its fleet strategy?")

```

## 3 · Add Web IQ 🌐

[**Web IQ**](https://aka.ms/WebIQLearn) grounds your agent in the **live web** — web and news — through the remote Microsoft Grounding MCP server, with **nothing to index**. It authenticates with a stored `x-apikey` header.

> **Get access:** Web IQ is **waitlisted** — [**join the waitlist**](https://aka.ms/webiq-waitlist). Once approved, set `WEB_IQ_MCP_API_KEY` and re-run. No key yet? This layer skips and the notebook keeps going.


```python
from azure.search.documents.indexes.models import (
    McpServerKnowledgeSource,
    McpServerKnowledgeSourceParameters,
    McpServerStoredHeadersAuthentication,
    McpServerStoredHeadersParameters,
)

web_key = env("WEB_IQ_MCP_API_KEY", required=False)  # secret -- env only
if not web_key:
    skip("Web IQ", "set WEB_IQ_MCP_API_KEY to add live web grounding -- waitlist: https://aka.ms/webiq-waitlist")
else:
    tools = [
        {"name": t, "outputParsing": {"kind": "auto"}, "inclusionMode": "reranked", "maxOutputTokens": 4096}
        for t in ("web", "news")
    ]
    index_client.create_or_update_knowledge_source(
        McpServerKnowledgeSource(
            name=KS_WEB_IQ,
            description="Web IQ -- Microsoft Grounding MCP server (web, news).",
            mcp_server_parameters=McpServerKnowledgeSourceParameters(
                server_url="https://api.microsoft.ai/v3/mcp",
                # storedHeaders auth: send the Web IQ x-apikey directly.
                authentication=McpServerStoredHeadersAuthentication(
                    stored_headers_parameters=McpServerStoredHeadersParameters(headers={"x-apikey": web_key}),
                ),
                tools=tools,
            ),
        )
    )
    enable(KS_WEB_IQ, "What's the latest public news on transatlantic routes and long-haul aircraft?")

```

## 4 · Add Work IQ 👥

[**Work IQ**](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-work-iq?pivots=python) grounds your agent in *how your people work* — Microsoft 365 mail, chats, files, and meetings — enforcing each user's permissions at query time. The typed model is tiny: just a name and description.

> **Get access:** Work IQ is **gated + licensed**. Register the `EnableFoundryIQWithWorkIQ` flag, re-register `Microsoft.Search`, have a tenant admin complete the [access request form](https://aka.ms/foundry-iq-work-iq-admin-consent-form), and give each user a **Microsoft 365 Copilot license**. Not entitled yet? This layer skips. *(Work IQ can take 40–60s to answer.)*


```python
from azure.search.documents.indexes.models import WorkIQKnowledgeSource

try:
    index_client.create_or_update_knowledge_source(
        WorkIQKnowledgeSource(name=KS_WORK_IQ, description="Work IQ -- M365 mail, chats, files, meetings.")
    )
except Exception as exc:  # noqa: BLE001
    skip("Work IQ", f"tenant not entitled yet ({exc}) -- request access: https://aka.ms/foundry-iq-work-iq-admin-consent-form")
else:
    enable(KS_WORK_IQ, "Summarize what we've discussed internally about transatlantic route planning.")

```

## 5 · Add Fabric IQ 📊

[**Fabric IQ**](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-fabric-ontology?pivots=python) grounds your agent in the live state of *your business* — a semantic **ontology** in Microsoft Fabric (entities, relationships, rules). This recipe uses an **airline ontology** as the example; point it at your own.

> **Get access:** you need a Fabric **ontology item** in the same Entra tenant as your Search service. Both IDs are in the ontology item URL — `.../groups/<workspace-id>/ontologies/<ontology-id>` — set them as `FABRIC_WORKSPACE_ID` / `FABRIC_ONTOLOGY_ID`. Not set? This layer skips.


```python
from azure.search.documents.indexes.models import (
    FabricOntologyKnowledgeSource,
    FabricOntologyKnowledgeSourceParameters,
)

workspace_id = env("FABRIC_WORKSPACE_ID", required=False)
ontology_id = env("FABRIC_ONTOLOGY_ID", required=False)
if not (workspace_id and ontology_id):
    skip("Fabric IQ", "set FABRIC_WORKSPACE_ID and FABRIC_ONTOLOGY_ID (from your ontology item URL) to add live business data")
else:
    index_client.create_or_update_knowledge_source(
        FabricOntologyKnowledgeSource(
            name=KS_FABRIC_IQ,
            description="Fabric IQ -- your business ontology in Microsoft Fabric.",
            fabric_ontology_parameters=FabricOntologyKnowledgeSourceParameters(
                workspace_id=workspace_id, ontology_id=ontology_id,
            ),
        )
    )
    enable(KS_FABRIC_IQ, "From our ontology, how many aircraft are in the fleet, grouped by manufacturer?")

```

## 6 · Ask across every layer

Now the payoff. Send **one** question that no single layer can answer alone — Foundry IQ plans the subqueries, routes each to the right Microsoft IQ (steered by the `retrieval_instructions` from §1), reranks, and synthesizes one cited answer across whatever layers you enabled.


```python
ask(
    "I'm prepping a transatlantic route-planning review. What is our fleet strategy "
    "and composition (from our files and our ontology), the latest public news on "
    "long-haul aircraft, and anything we've discussed internally?"
)

```

## 7 · Take it further — point any agent at the layer

Your Knowledge Base also exposes a **Model Context Protocol (MCP) endpoint**, so the same layer grounds *any* MCP-compatible agent — no re-plumbing:

```
{SEARCH_ENDPOINT}/knowledgebases/{KB_NAME}/mcp?api-version=2026-05-01-preview
```

It exposes one `knowledge_base_retrieve` tool. Point any consumer at it:

- **Foundry Agent Service** — add it as a `RemoteTool` MCP connection (`authType=ProjectManagedIdentity`). See [Build an agentic retrieval solution](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-create-pipeline).
- **Microsoft Agent Framework** — register the endpoint as a tool on your agent.
- **GitHub Copilot** (VS Code) — add the URL to `.vscode/mcp.json` with an `api-key` header, then use **Agent** mode.


## 8 · Clean up

The Knowledge Base and Knowledge Sources are stateful. Delete them so a re-run starts clean — comment this out to keep the KB for the §7 consumers.


```python
try:
    index_client.delete_knowledge_base(KB_NAME)
    print(f"Deleted KB {KB_NAME}")
except ResourceNotFoundError:
    pass
except Exception as exc:  # noqa: BLE001
    print(f"KB delete: {exc}")

for ks_name in (KS_FILES, KS_WEB_IQ, KS_WORK_IQ, KS_FABRIC_IQ):
    try:
        index_client.delete_knowledge_source(ks_name)
        print(f"Deleted KS {ks_name}")
    except ResourceNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"KS {ks_name} delete: {exc}")

```

## 9 · Next steps

You built a **Microsoft IQ knowledge layer** — starting from your own files, then layering in Web IQ, Work IQ, and Fabric IQ, all federated by **Foundry IQ** into one Knowledge Base you query with a single `ask()`. From here:

- **Tour every Knowledge Source type.** The companion recipe [Mastering Foundry IQ](mastering-foundry-iq) walks indexed, uploaded, and federated sources end to end.
- **Ground an agent.** Wire the KB's MCP endpoint into Foundry Agent Service, the Microsoft Agent Framework, or GitHub Copilot (§7).

### Reference docs

- [Microsoft IQ](https://learn.microsoft.com/en-us/microsoft-iq/)
- [Work IQ knowledge source](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-work-iq?pivots=python)
- [Fabric ontology knowledge source](https://learn.microsoft.com/en-us/azure/search/agentic-knowledge-source-how-to-fabric-ontology?pivots=python)
- [Web IQ](https://aka.ms/WebIQLearn) · [waitlist](https://aka.ms/webiq-waitlist)
- [Retrieve from a knowledge base](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-how-to-retrieve?pivots=python)
- [Create a Knowledge Base](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-create-knowledge-base)
