> **Azure OpenAI On Your Data retires October 14, 2026.** It does not support GPT-5 and
> is no longer being developed. If you call On Your Data today against an Azure AI Search
> index, you need a replacement before that date.

This recipe is the shortest path off On Your Data (OYD) for the most common setup: **one
REST call, one Azure AI Search index, one Azure OpenAI model.** You keep both of those
resources exactly as they are. You swap a single API call.

The replacement is a **Foundry IQ Knowledge Base** in **answer synthesis** mode. Like
OYD, it takes a question and returns a grounded, cited answer in one REST call — but it
runs on the actively developed agentic-retrieval stack (query planning, parallel
retrieval, semantic reranking, synthesis) and works with current models including GPT-5.

| | On Your Data (today) | Foundry IQ Knowledge Base (after) |
|---|---|---|
| Your Search index | unchanged | unchanged — wrapped, not copied |
| Your Azure OpenAI model | unchanged | unchanged — same deployment for synthesis |
| The call | `POST .../chat/completions` with a `data_sources` block | `POST .../knowledgebases/{kb}/retrieve` |
| Status | retires **Oct 14, 2026** | preview (`2026-05-01-preview`), actively developed |
| Output | answer + citations | answer + citations + activity trace |

**What this recipe does not do:** re-index your data, add new source types (Blob,
SharePoint, OneLake, Web), or wire up an agent. Those are all possible later — see
[Mastering Foundry IQ](mastering-foundry-iq.ipynb). Here we stay strictly on the migration.

## What you need

You almost certainly already have all of this — it is the same setup On Your Data uses.

| | |
|---|---|
| **Azure AI Search service** | The one your OYD `data_sources` block points at, with your existing index. The service must be in a [preview region](https://learn.microsoft.com/azure/search/search-region-support) for Knowledge Bases. |
| **An existing index** | With a semantic configuration (OYD's `query_type: semantic` already requires one). |
| **Azure OpenAI / Foundry resource** | The same chat deployment your OYD call uses (e.g. `gpt-4.1-mini`, `gpt-4o`, or now `gpt-5-mini`). |

This recipe uses **API-key auth** so it runs with copy-paste. For production, switch to
Microsoft Entra ID — see [Best practices](#best-practices) at the end.

**Runtime and cost:** about 2–3 minutes end-to-end against a small index. You only pay for
what you already use — Search queries plus Azure OpenAI tokens for query planning and
synthesis (cents at this scale). Creating the Knowledge Source and Knowledge Base costs
nothing, and the cleanup cell deletes both.

Set these in your shell or a local `.env` file next to the notebook:

```bash
SEARCH_ENDPOINT=https://<your-search-service>.search.windows.net
SEARCH_API_KEY=<your-search-admin-key>
SEARCH_INDEX_NAME=<your-existing-index>
SEARCH_SEMANTIC_CONFIG=<your-semantic-config-name>   # optional; omit if your index has none

AOAI_ENDPOINT=https://<your-foundry-resource>.openai.azure.com
AOAI_API_KEY=<your-azure-openai-key>
AOAI_GPT_DEPLOYMENT=gpt-4.1-mini                      # the SAME deployment OYD uses
```

```python
%%capture
%pip install --quiet "requests>=2.31" "python-dotenv>=1.0.1"
```

## Configure

One config cell. Everything above the line is what you already have for On Your Data;
everything below is the two names this recipe will create on your Search service.

```python
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv(override=True)


def env(name, *, required=True, default=None):
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


# ---- What you already have (straight from your OYD setup) ----------------
SEARCH_ENDPOINT = env("SEARCH_ENDPOINT").rstrip("/")
SEARCH_API_KEY = env("SEARCH_API_KEY")
SEARCH_INDEX = env("SEARCH_INDEX_NAME")
SEMANTIC_CONFIG = env("SEARCH_SEMANTIC_CONFIG", required=False)

AOAI_ENDPOINT = env("AOAI_ENDPOINT").rstrip("/")
AOAI_API_KEY = env("AOAI_API_KEY")
AOAI_DEPLOYMENT = env("AOAI_GPT_DEPLOYMENT")
AOAI_MODEL = env("AOAI_GPT_MODEL", required=False, default=AOAI_DEPLOYMENT)

# ---- API versions --------------------------------------------------------
OYD_API_VERSION = "2024-10-21"          # GA Azure OpenAI chat completions (On Your Data)
KB_API_VERSION = "2026-05-01-preview"   # Foundry IQ Knowledge Base (preview)

# ---- The two resources this recipe creates -------------------------------
KS_NAME = "oyd-migrated-ks"   # Knowledge Source that wraps your existing index
KB_NAME = "oyd-migrated-kb"   # Knowledge Base that answers in synthesis mode

# Your OYD system message — the `system` role message your app sends today (older OYD
# code passed this as `role_information`). Reused verbatim as the KB's answerInstructions.
SYSTEM_MESSAGE = (
    "You are a helpful assistant for our company. Answer the question using only the "
    "information in the retrieved sources."
)

# A real question your index can answer. Replace this.
QUESTION = "What is our return policy?"

print(f"Search : {SEARCH_ENDPOINT}  (index: {SEARCH_INDEX})")
print(f"Model  : {AOAI_DEPLOYMENT}  @ {AOAI_ENDPOINT}")
print(f"KB API : {KB_API_VERSION}")
```

## 1 · The call you make today (On Your Data)

This is the On Your Data pattern: a normal chat-completions request with a `data_sources`
block that points at your Search index. Azure OpenAI does the retrieval for you and folds
citations into `context.citations`. **This is the call that stops working on Oct 14, 2026.**

The cell below sends it and prints the answer plus its citations. Note the parameters
inside `data_sources[0].parameters` — `query_type`, `semantic_configuration`,
`strictness`, `top_n_documents`, `in_scope` — and the `system` message that carries your
instructions. Those are exactly what we map over in the next section.

> **Heads-up on the system message.** The current GA API (`2024-10-21`) takes your
> instructions as a normal `system` message in `messages`. Older On Your Data code passed
> a `role_information` field *inside* `data_sources[0].parameters` — that field is rejected
> today (`"Extra inputs are not permitted"`). If your code still sends `role_information`,
> move it to a `system` message as shown here.

```python
def oyd_answer(question, *, strictness=3, top_n=5, query_type="semantic"):
    """The Azure OpenAI On Your Data call. Retires Oct 14, 2026."""
    url = (
        f"{AOAI_ENDPOINT}/openai/deployments/{AOAI_DEPLOYMENT}"
        f"/chat/completions?api-version={OYD_API_VERSION}"
    )
    parameters = {
        "endpoint": SEARCH_ENDPOINT,
        "index_name": SEARCH_INDEX,
        "authentication": {"type": "api_key", "key": SEARCH_API_KEY},
        "query_type": query_type,
        "strictness": strictness,
        "top_n_documents": top_n,
        "in_scope": True,
    }
    if SEMANTIC_CONFIG:
        parameters["semantic_configuration"] = SEMANTIC_CONFIG

    body = {
        "messages": [
            {"role": "system", "content": SYSTEM_MESSAGE},
            {"role": "user", "content": question},
        ],
        "data_sources": [{"type": "azure_search", "parameters": parameters}],
    }
    resp = requests.post(
        url,
        headers={"api-key": AOAI_API_KEY, "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


oyd = oyd_answer(QUESTION)
oyd_message = oyd["choices"][0]["message"]

print(oyd_message["content"])
citations = oyd_message.get("context", {}).get("citations", [])
print(f"\nCitations: {len(citations)}")
for i, c in enumerate(citations, start=1):
    label = c.get("title") or c.get("filepath") or c.get("url") or f"source {i}"
    print(f"  [doc{i}] {label}")
```

## 2 · How the parameters map

Foundry IQ splits the one OYD `data_sources` block into three places: a **Knowledge
Source** (your index), a **Knowledge Base** (your model + answer behavior), and the
per-call **retrieve** request. Here is every OYD parameter and where it goes.

| OYD `parameters` field | Foundry IQ equivalent | Lives on |
|---|---|---|
| `endpoint` | Search endpoint (unchanged) | retrieve URL |
| `index_name` | `searchIndexParameters.searchIndexName` | Knowledge Source |
| `semantic_configuration` | `searchIndexParameters.semanticConfigurationName` | Knowledge Source |
| `authentication` | `api-key` header (or Entra token) | request headers |
| `role_information` *(old field)* → `system` message | `answerInstructions` | Knowledge Base |
| `in_scope: true` | grounding sentence appended to `answerInstructions` | Knowledge Base |
| model / deployment | `models[].azureOpenAIParameters.deploymentId` | Knowledge Base |
| `strictness` (1–5) | `rerankerThreshold` (0.0–4.0), as `(strictness − 1) × 1.0` | retrieve call |
| `top_n_documents` (3–20) | *no direct knob* — the planner sizes context; widen the pool with `maxOutputDocuments` (50–200) if needed | retrieve call |
| `query_type` | *(no knob)* — the KB always runs agentic hybrid + semantic reranking | KB pipeline |
| `fields_mapping` | *(optional)* `searchIndexParameters.sourceDataFields` controls which fields come back in references | Knowledge Source |

> **`query_type` has no equivalent on purpose.** On Your Data made you choose `simple`,
> `semantic`, `vector`, or a hybrid. A Knowledge Base always plans subqueries, retrieves
> with hybrid search, and reranks — so the best strategy is the default. If your index has
> a vector field and an embedding vectorizer, the KB uses them automatically.

## 3 · Create the Knowledge Source over your existing index

A Knowledge Source of `kind: searchIndex` is a thin wrapper that points at an index you
already have. **Nothing is re-indexed, copied, or moved** — it references your index in
place. This maps the OYD `index_name` and `semantic_configuration`.

```python
def search_rest(method, path, body=None):
    """Call the Azure AI Search data plane and surface errors verbatim."""
    sep = "&" if "?" in path else "?"
    url = f"{SEARCH_ENDPOINT}{path}{sep}api-version={KB_API_VERSION}"
    resp = requests.request(
        method,
        url,
        headers={"api-key": SEARCH_API_KEY, "Content-Type": "application/json"},
        json=body,
        timeout=180,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {resp.status_code}\n{resp.text}")
    return resp.json() if resp.text else {}


search_index_parameters = {"searchIndexName": SEARCH_INDEX}
if SEMANTIC_CONFIG:
    search_index_parameters["semanticConfigurationName"] = SEMANTIC_CONFIG

ks_body = {
    "name": KS_NAME,
    "kind": "searchIndex",
    "description": "Wraps the existing On Your Data search index.",
    "searchIndexParameters": search_index_parameters,
}
search_rest("PUT", f"/knowledgesources/{KS_NAME}", ks_body)
print(f"Knowledge Source '{KS_NAME}' now points at index '{SEARCH_INDEX}'.")
```

## 4 · Create the Knowledge Base with your existing model

The Knowledge Base ties your **Azure OpenAI model** to the Knowledge Source and sets the
answer behavior. Three fields carry your OYD configuration:

- **`models`** → the same Azure OpenAI deployment OYD used, for query planning + synthesis.
- **`outputMode: answerSynthesis`** → return a written, cited answer (not raw chunks). This
  is what makes the KB a drop-in for OYD.
- **`answerInstructions`** → your OYD system message, plus the grounding sentence that
  `in_scope: true` used to enforce.

Default `retrievalReasoningEffort` to `low`: it adds query planning (the big jump over
single-shot OYD retrieval) without much latency. Raise it to `medium` only for genuinely
multi-part questions.

```python
# in_scope: true  ->  an explicit grounding instruction
answer_instructions = (
    SYSTEM_MESSAGE
    + " Only use the retrieved sources. If the answer is not in them, say you do not know."
)

kb_body = {
    "name": KB_NAME,
    "description": "Migrated from Azure OpenAI On Your Data.",
    "models": [
        {
            "kind": "azureOpenAI",
            "azureOpenAIParameters": {
                "resourceUri": AOAI_ENDPOINT,
                "deploymentId": AOAI_DEPLOYMENT,
                "modelName": AOAI_MODEL,
                "apiKey": AOAI_API_KEY,
            },
        }
    ],
    "knowledgeSources": [{"name": KS_NAME}],
    "outputMode": "answerSynthesis",
    "retrievalReasoningEffort": {"kind": "low"},
    "answerInstructions": answer_instructions,
}
search_rest("PUT", f"/knowledgebases/{KB_NAME}", kb_body)
print(f"Knowledge Base '{KB_NAME}' ready (answerSynthesis, model '{AOAI_DEPLOYMENT}').")
```

## 5 · The call you make instead (Foundry IQ)

This is the replacement for §1. One `POST` to `/knowledgebases/{kb}/retrieve`, one
question, one grounded answer with citations. The remaining OYD knobs map onto the
per-call `knowledgeSourceParams`:

- `strictness: 3` → `rerankerThreshold: 2.0`  (the `(strictness − 1) × 1.0` from the table)

OYD's `top_n_documents` has no direct equivalent — the planner decides how much grounding
to pass to synthesis. If you need to widen the candidate pool, set `maxOutputDocuments`
(allowed range **50–200**) on the source params.

The synthesized answer comes back in `response[]`; the citations in `references[]`; and a
step-by-step `activity[]` trace shows what the planner did.

```python
def kb_answer(question, *, strictness=3):
    reranker_threshold = (strictness - 1) * 1.0  # OYD strictness 1-5 -> KB threshold 0-4
    body = {
        "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}],
        "knowledgeSourceParams": [
            {
                "kind": "searchIndex",
                "knowledgeSourceName": KS_NAME,
                "includeReferences": True,
                "includeReferenceSourceData": True,
                "rerankerThreshold": reranker_threshold,
            }
        ],
        "includeActivity": True,
    }
    return search_rest("POST", f"/knowledgebases/{KB_NAME}/retrieve", body)


def answer_text(result):
    parts = []
    for message in result.get("response", []):
        for content in message.get("content", []):
            if content.get("text"):
                parts.append(content["text"])
    return "\n\n".join(parts)


kb = kb_answer(QUESTION)

print(answer_text(kb))
print("\nReferences:")
for ref in kb.get("references", [])[:5]:
    source = ref.get("sourceData") or {}
    label = source.get("title") or source.get("filepath") or ref.get("docKey") or ""
    print(f"  [ref_id:{ref.get('id')}] {label}")
print(f"\nActivity steps: {len(kb.get('activity', []))}   References: {len(kb.get('references', []))}")
```

### See the planner's work

On Your Data was a black box. The Knowledge Base returns an `activity` trace: the
subqueries it planned, which source it hit, and token counts for planning vs. synthesis.

```python
print(json.dumps(kb.get("activity", []), indent=2)[:2000])
```

### What a real run looks like

Here is a representative run against the public **`hotels-sample-index`** (create it in
seconds from the Azure portal's *Import data → hotels-sample*), asking *"Which hotels are
luxury resorts with free wifi, and what amenities make them stand out?"*

**On Your Data (before)** — one model call, retrieval hidden, `[doc1]`-style citations:

```text
1. Double Sanctuary Resort: 5-star luxury hotel ... fitness center, and Nespresso
   machines in the rooms [doc1].
2. Marquis Plaza & Suites: free Wi-Fi, a full kitchen, and a free breakfast buffet [doc2].
Citations: 5
```

**Foundry IQ (after)** — the planner fans out, then synthesizes with `[ref_id:N]` citations:

```text
1. Double Sanctuary Resort — 5-star, ranked #1 by Conde Nast Traveler; free WiFi,
   fitness center, Nespresso in room [ref_id:2].
2. Marquis Plaza & Suites — free WiFi, full kitchen, free breakfast buffet [ref_id:3].
...
References: 41   Activity steps: 5
```

The `activity` trace shows *why* the second answer is broader — it ran two planned
subqueries instead of one lookup:

```text
modelQueryPlanning     gpt-4.1-mini  (~1.3s)
searchIndex            "luxury resorts with free wifi"     -> 19 hits
searchIndex            "amenities of luxury resorts"       -> 38 hits
modelAnswerSynthesis   gpt-4.1-mini
```

Same index, same model, one call each — but only the Foundry IQ path keeps working after
Oct 14, 2026, and it grounds the answer in a wider candidate set.

## 6 · Side by side

Same question, both engines. The answers should be comparable — same index, same model —
but only the Foundry IQ call still runs after Oct 14, 2026.

```python
print("On Your Data  (retires Oct 14, 2026)")
print("-" * 44)
print(oyd_message["content"])
print()
print("Foundry IQ Knowledge Base  (answer synthesis)")
print("-" * 44)
print(answer_text(kb))
```

## 7 · Multi-turn

On Your Data was stateless — every call started over. The retrieve API takes a `messages`
array, so you can pass prior turns and the planner uses them as context. Append the answer
and ask a follow-up.

```python
def kb_answer_messages(messages, *, strictness=3):
    reranker_threshold = (strictness - 1) * 1.0
    body = {
        "messages": [
            {"role": m["role"], "content": [{"type": "text", "text": m["content"]}]}
            for m in messages
        ],
        "knowledgeSourceParams": [
            {
                "kind": "searchIndex",
                "knowledgeSourceName": KS_NAME,
                "includeReferences": True,
                "includeReferenceSourceData": True,
                "rerankerThreshold": reranker_threshold,
            }
        ],
        "includeActivity": False,
    }
    return search_rest("POST", f"/knowledgebases/{KB_NAME}/retrieve", body)


conversation = [
    {"role": "user", "content": QUESTION},
    {"role": "assistant", "content": answer_text(kb)},
    {"role": "user", "content": "Can you give me more detail on that?"},
]
follow_up = kb_answer_messages(conversation)
print(answer_text(follow_up))
```

## Common errors

The failures you are most likely to hit — including two the migration itself surfaces:

| Error | Cause | Fix |
|---|---|---|
| OYD `400` — `role_information: Extra inputs are not permitted` | The GA API (`2024-10-21`) removed the `role_information` data-source parameter | Move your instructions to a `system` message in `messages[]` (see §1) |
| Retrieve `400` — `MaxOutputDocuments must be between 50 and 200` | `maxOutputDocuments` is a candidate-pool cap, not OYD's `top_n` | Omit it (the planner sizes context), or pass a value in 50–200 |
| Retrieve `401`/`403` with Entra auth | The caller lacks a data-plane role | Grant **Search Index Data Reader** on the Search service; wait 5–10 min for propagation |
| `403` during synthesis with managed identity | The Search service MI can't reach Azure OpenAI | Give the Search MI **Cognitive Services OpenAI User** on the Azure OpenAI resource |
| Retrieve `404` on the KB | The Knowledge Base does not exist or the name is wrong | Create the KB (§4) first; match `KB_NAME` |
| Empty answer, `references: 0` | `rerankerThreshold` too high, or the index has no semantic config | Lower `rerankerThreshold`; confirm `semanticConfigurationName` matches your index |

## Best practices

You have a working migration. Before you ship it:

- **Evaluate the change, don't eyeball it.** Run your real questions through both engines
  and score groundedness and relevance. Microsoft Foundry ships built-in RAG evaluators
  (groundedness, relevance, retrieval) for exactly this — see
  [Evaluation of generative AI applications](https://learn.microsoft.com/azure/ai-foundry/concepts/evaluation-approach-gen-ai).
- **Use Microsoft Entra ID in production.** Drop the `api-key` headers and the `apiKey` in
  the model block. Send `Authorization: Bearer <token>` (Search audience
  `https://search.azure.com/.default`). Grant **Search Service Contributor** to create the
  Knowledge Source and Knowledge Base, and **Search Index Data Reader** to run retrieve.
  For synthesis, enable a managed identity on the Search service, give it **Cognitive
  Services OpenAI User** on your Azure OpenAI resource, and replace the model's `apiKey`
  with `authIdentity`. See
  [Azure AI Search role-based access](https://learn.microsoft.com/azure/search/search-security-rbac).
- **Tune two dials, not five.** `rerankerThreshold` is your old `strictness` (raise it to
  cut weak matches); `retrievalReasoningEffort` (`minimal` / `low` / `medium`) trades
  latency for harder query planning. Start at `low`.
- **Mind the preview.** The Knowledge Base API is `2026-05-01-preview`. Pin the version and
  watch the [agentic retrieval migration guide](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-migrate)
  before moving to production.

When you outgrow a single index — multiple sources, SharePoint/OneLake/Web, or an agent
that calls the KB as a tool — keep the same Knowledge Base and follow
[Mastering Foundry IQ](mastering-foundry-iq.ipynb).

## Hand it to a coding agent

To migrate a real application, point a coding agent (GitHub Copilot, Claude Code, etc.) at
your repository with the prompt below. It captures the whole recipe: find the OYD call, map
the parameters, create the two resources, swap the call.

```text
Migrate this codebase off Azure OpenAI On Your Data (retires Oct 14, 2026) to a Foundry IQ
Knowledge Base in answer-synthesis mode. Keep the existing Azure AI Search index and Azure
OpenAI deployment. Steps:

1. Find the On Your Data call: search for `data_sources`, `azure_search`,
   `AzureSearchChatExtensionConfiguration`, or `extra_body={"data_sources"...}`.
2. Read these fields from data_sources[0].parameters: endpoint, index_name,
   semantic_configuration, strictness, top_n_documents, in_scope, query_type. The OYD
   instructions are the `system` message in messages[] (older code may put them in a
   `role_information` parameter, which the current API rejects).
3. Create a Knowledge Source (kind: searchIndex) over that index, carrying index_name ->
   searchIndexName and semantic_configuration -> semanticConfigurationName.
   PUT {search_endpoint}/knowledgesources/{ks}?api-version=2026-05-01-preview
4. Create a Knowledge Base with outputMode=answerSynthesis. Map the existing chat
   deployment into models[].azureOpenAIParameters, the OYD system message (+ an in_scope
   grounding sentence) into answerInstructions, and reference the Knowledge Source.
   PUT {search_endpoint}/knowledgebases/{kb}?api-version=2026-05-01-preview
5. Replace the chat-completions call with:
   POST {search_endpoint}/knowledgebases/{kb}/retrieve?api-version=2026-05-01-preview
   Map strictness -> rerankerThreshold via (strictness-1)*1.0 on knowledgeSourceParams.
   OYD's top_n_documents has no direct equal; only set maxOutputDocuments if you need to
   widen the candidate pool (allowed range 50-200). Read the answer from
   response[].content[].text and citations from references[].
6. Keep the existing system message identical via answerInstructions. Do not re-index data.
   Use Microsoft Entra ID auth in production instead of api-key headers.
```

For a CLI that discovers your OYD config and scaffolds the migration, see the companion
[azure-openai-on-your-data-migrator](https://github.com/farzad528/azure-openai-on-your-data-migrator).

## Clean up

This recipe created exactly two resources on your Search service — the Knowledge Source and
the Knowledge Base. Your index and model are untouched. Remove the two to leave no residue.

```python
for path in (f"/knowledgebases/{KB_NAME}", f"/knowledgesources/{KS_NAME}"):
    try:
        search_rest("DELETE", path)
        print(f"Deleted {path}")
    except Exception as exc:
        print(f"Skipped {path}: {exc}")
```

## References

- [Azure OpenAI On Your Data](https://learn.microsoft.com/azure/ai-foundry/openai/concepts/use-your-data)
- [Azure OpenAI model & feature retirements](https://learn.microsoft.com/azure/ai-foundry/openai/concepts/model-retirements)
- [What is Foundry IQ?](https://learn.microsoft.com/azure/ai-foundry/agents/concepts/what-is-foundry-iq)
- [Agentic retrieval concept](https://learn.microsoft.com/azure/search/search-agentic-retrieval-concept)
- [Create a Knowledge Source over a search index](https://learn.microsoft.com/azure/search/agentic-knowledge-source-how-to-search-index)
- [Create a Knowledge Base](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-create-knowledge-base)
- [Retrieve from a Knowledge Base](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-retrieve)
- [Agentic retrieval migration guide](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-migrate)
- [azure-openai-on-your-data-migrator (companion CLI)](https://github.com/farzad528/azure-openai-on-your-data-migrator)