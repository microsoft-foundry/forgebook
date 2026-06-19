You have an Azure AI Search index whose URL, title, and content fields are **not** named
`url` / `title` / `content` — they're `blob_url`, `uid`, `snippet`, or whatever your blob or
SharePoint integrated-vectorization pipeline produced. You wire it into a Foundry Agent with the
**Azure AI Search tool**, the answers are great, but the `url_citation` annotations come back as
useless placeholders:

```text
title='doc_0'   url='https://<service>.search.windows.net/'
```

**The pattern this recipe teaches:** register the index as a *project asset* with a `FieldMapping`,
then point the `AzureAISearchTool` at it via `index_asset_id`. The agent's citations then resolve to
your real fields. No re-indexing, no schema change, no touching the index.

### What you'll do

1. Register your existing index as a project asset with a `FieldMapping`
2. Create an agent that references the asset by `index_asset_id`
3. Ask a question and read citations that resolve to your real `url` / `title` fields
4. Learn the failure modes that produce `doc_0` placeholders and how to avoid each one

By the end you have a copyable two-step (`create_or_update` + `index_asset_id`) you can drop into any
agent that grounds on a custom-schema Azure AI Search index.

## 1 · Prerequisites

| | |
|---|---|
| Microsoft Foundry project | A project endpoint and one chat deployment (e.g. `gpt-4.1`) |
| Azure AI Search | An existing index, connected to the project as a `CognitiveSearch` connection |
| Index field attributes | The fields you map to `url` and `title` must be **retrievable** and **searchable** in the index definition, or they won't appear in citation annotations |
| Identity | `az login` — the notebook uses `DefaultAzureCredential` |

You do **not** need to re-index or rename any fields. This recipe works against the schema you
already have.

### Install dependencies

```python
%pip install --quiet "azure-ai-projects>=2.0.0" "azure-identity>=1.19.0"
```

## 2 · Configure endpoints and your index's real field names

Set these in your shell (or a local `.env`) and the cell below reads them. The three field names at
the bottom are the whole point — they are the part of your index that differs from the docs.

```bash
PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
SEARCH_CONNECTION_NAME=my-search-connection   # the CognitiveSearch connection NAME, not its id
INDEX_NAME=my-custom-index                    # your existing index
```

```python
import os

PROJECT_ENDPOINT = os.getenv("PROJECT_ENDPOINT", "https://<resource>.services.ai.azure.com/api/projects/<project>")
SEARCH_CONNECTION_NAME = os.getenv("SEARCH_CONNECTION_NAME", "my-search-connection")  # connection NAME, not id
INDEX_NAME = os.getenv("INDEX_NAME", "my-custom-index")
MODEL = os.getenv("MODEL", "gpt-4.1")

# Your index's real field names -- the part that differs from the docs.
URL_FIELD     = os.getenv("URL_FIELD", "blob_url")    # your URL field      -> annotation.url
TITLE_FIELD   = os.getenv("TITLE_FIELD", "uid")       # your title field    -> annotation.title
CONTENT_FIELD = os.getenv("CONTENT_FIELD", "snippet")  # your content field

print(f"project    : {PROJECT_ENDPOINT}")
print(f"connection : {SEARCH_CONNECTION_NAME}")
print(f"index      : {INDEX_NAME}")
print(f"fields     : url={URL_FIELD!r}  title={TITLE_FIELD!r}  content={CONTENT_FIELD!r}")
```

## 3 · Create the client

```python
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

project = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=DefaultAzureCredential())
openai = project.get_openai_client()
print("client created")
```

## 4 · Register the index as an asset **with a field mapping**

This is the step that makes citations work. `FieldMapping` maps your custom fields onto the citation
slots the tool understands. The mapping lives on the **registered asset** — not on the tool (see the
Gotchas table for why that distinction matters).

```python
from azure.ai.projects.models import AzureAISearchIndex, FieldMapping

ASSET_NAME, ASSET_VERSION = "my-custom-index-mapped", "1"

asset = project.indexes.create_or_update(
    name=ASSET_NAME, version=ASSET_VERSION,
    index=AzureAISearchIndex(
        name=ASSET_NAME, version=ASSET_VERSION,
        connection_name=SEARCH_CONNECTION_NAME,   # connection NAME
        index_name=INDEX_NAME,
        field_mapping=FieldMapping(
            content_fields=[CONTENT_FIELD],       # required
            url_field=URL_FIELD,                  # -> annotation.url
            title_field=TITLE_FIELD,              # -> annotation.title
            # filepath_field="...",             # optional
        ),
    ),
)
print(f"registered asset {ASSET_NAME}/versions/{ASSET_VERSION}")
```

## 5 · Create the agent, referencing the asset by `index_asset_id`

> ⚠️ `index_asset_id` **must** be `"<name>/versions/<version>"`, and it is **mutually exclusive**
> with `project_connection_id` + `index_name`. Set **only** `index_asset_id`, or the service rejects
> the request with `Multiple values specified for oneof knowledge_index`.

```python
from azure.ai.projects.models import (
    AzureAISearchTool, AzureAISearchToolResource, AISearchIndexResource,
    AzureAISearchQueryType, PromptAgentDefinition,
)

agent = project.agents.create_version(
    agent_name="search-custom-schema",
    definition=PromptAgentDefinition(
        model=MODEL,
        instructions=(
            "Answer only from the Azure AI Search tool. Always cite sources, "
            "rendered as [message_idx:search_idx†source]."
        ),
        tools=[AzureAISearchTool(azure_ai_search=AzureAISearchToolResource(indexes=[
            AISearchIndexResource(
                index_asset_id=f"{ASSET_NAME}/versions/{ASSET_VERSION}",
                query_type=AzureAISearchQueryType.SEMANTIC,   # or VECTOR_SEMANTIC_HYBRID
                top_k=5,
            )
        ]))],
    ),
)
print(f"agent {agent.name} v{agent.version}")
```

## 6 · Ask a question and read the citations

Stream a response and pull the `url_citation` annotations off the final message. With the mapping in
place, `title` and `url` now carry your real field values.

```python
stream = openai.responses.create(
    stream=True, tool_choice="required",
    input="What does the P4324 do?",
    extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
)

for event in stream:
    if event.type == "response.output_text.delta":
        print(event.delta, end="")
    elif event.type == "response.output_item.done":
        item = event.item
        if item.type == "message" and item.content:
            last = item.content[-1]
            if getattr(last, "type", None) == "output_text":
                for a in (last.annotations or []):
                    if a.type == "url_citation":
                        print(f"\nCITATION  title={a.title!r}  url={a.url!r}")
```

**Expected output** — your real fields now surface instead of `doc_0` placeholders:

```text
CITATION  title='P4324 Programmable Flow Controller — Overview'
          url='https://contoso-docs.example.com/p4324/overview'
```

## 7 · Clean up (optional)

Delete the agent version. Keep the asset if you want to reuse the mapping for other agents.

```python
project.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
# project.indexes.delete(name=ASSET_NAME, version=ASSET_VERSION)  # keep it to reuse the mapping
print("cleaned up agent")
```

## Gotchas

Every row here is a failure mode that produces broken or placeholder citations.

| Symptom | Cause | Fix |
|---|---|---|
| `title="doc_0"`, `url=https://<svc>.search.windows.net/` | Direct `project_connection_id` + `index_name` path — citations only read literal `url` / `title` fields | Use the `index_asset_id` + `FieldMapping` path above |
| `Invalid IndexId format` | `index_asset_id` was a bare name or `name:1` | Must be `"<name>/versions/<version>"` (e.g. `.../versions/1` or `.../versions/latest`) |
| `Multiple values specified for oneof knowledge_index` | Set both `index_asset_id` and `project_connection_id` / `index_name` | Set **only** `index_asset_id` |
| Field mapping ignored | Passed `parameters.field_mapping` as a dict on the tool | That key is silently dropped; the mapping must live on the **registered asset**, not the tool |
| Answer is right but citations wrong | The tool concatenates content regardless of field names, so answers work even when citations don't | The mapping fixes citations specifically |

**Alternative (no asset registration):** rename or alias your URL and title fields to literally `url`
and `title` in the index (indexer output field mappings, or write both on push). The direct path then
works too. Prefer the asset + `FieldMapping` route when you can't touch the index.

## Verified run (real output)

Ran these steps **verbatim** on 2026-06-05 against a real index `azstool-e2e-custom`
(fields `id`, `uid`, `blob_url`, `snippet`) on a live Foundry project, starting from a fresh asset
registration. Actual console output:

```text
[step 1] client created
[step 2] registered asset cookbook-verify-mapped/versions/1:
         {'type': 'AzureSearch', 'connectionName': 'fsunavala-srch-demos-prod',
          'indexName': 'azstool-e2e-custom',
          'fieldMapping': {'contentFields': ['snippet'], 'titleField': 'uid', 'urlField': 'blob_url'},
          'name': 'cookbook-verify-mapped', 'version': '1'}
[step 3] agent search-custom-schema v1
[step 4] streamed answer + citations:

The P4324 is a programmable industrial flow controller designed to regulate the flow rate of
liquids and gases in process pipelines. It does this by modulating a built-in proportional valve.
The device takes 4-20mA and Modbus RTU setpoints and can maintain flow to within +/- 0.5 percent
of the target value【4:0†source】.

CITATION  title='P4324 Programmable Flow Controller — Overview'  url='https://contoso-docs.example.com/p4324/overview'

[step 5] cleaned up agent + asset
```

**Confirmed:** `title` resolved from the index's `uid` field and `url` from its `blob_url` field —
no `doc_0` placeholder, no `https://<svc>.search.windows.net/` fallback. The same index referenced
*directly* (without the asset + `FieldMapping`) returns `title='doc_0'`,
`url='https://<svc>.search.windows.net/'` — the broken baseline this recipe fixes.