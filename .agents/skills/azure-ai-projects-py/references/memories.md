# Memory Stores Reference — azure-ai-projects v2.0.0b3

## Overview

Memory stores provide persistent memory for agents. Access via `project_client.memory_stores` (`MemoryStoresOperations`).

## Prerequisites

```bash
pip install "azure-ai-projects>=2.0.0b3" azure-identity python-dotenv
```

Required: deployed chat model (e.g., `gpt-4.1`) and embedding model (e.g., `text-embedding-3-small`).

## MemoryStoresOperations

Accessed via `project_client.memory_stores`.

### Methods

| Method | Parameters | Returns |
|---|---|---|
| `create` | `*, name, definition, description?, metadata?` | `MemoryStoreDetails` |
| `get` | `name` | `MemoryStoreDetails` |
| `update` | `name, *, description?, metadata?` | `MemoryStoreDetails` |
| `list` | `*, limit?, order?, before?` | `ItemPaged[MemoryStoreDetails]` |
| `delete` | `name` | `DeleteMemoryStoreResult` |
| `search_memories` | `name, *, scope, items?, previous_search_id?, options?` | `MemoryStoreSearchResult` |
| `delete_scope` | `name, *, scope` | `MemoryStoreDeleteScopeResult` |
| `begin_update_memories` | `name, body/scope, *, items?, previous_update_id?, update_delay?` | `UpdateMemoriesLROPoller` |

## Basic Usage

```python
import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    MemoryStoreDefaultDefinition,
    MemoryStoreDefaultOptions,
    MemorySearchOptions,
    ResponsesUserMessageItemParam,
    ResponsesAssistantMessageItemParam,
)

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
):
    # Create memory store
    store = project_client.memory_stores.create(
        name="my-memory-store",
        definition=MemoryStoreDefaultDefinition(
            options=MemoryStoreDefaultOptions(
                user_profile_enabled=True,
                chat_summary_enabled=True,
            )
        ),
    )

    # Update memories with conversation items
    poller = project_client.memory_stores.begin_update_memories(
        name=store.name,
        scope="user123",
        items=[
            ResponsesUserMessageItemParam(role="user", content="I love hiking in Colorado."),
            ResponsesAssistantMessageItemParam(role="assistant", content="That sounds wonderful!"),
        ],
        update_delay=0,  # Process immediately (default: 300s batching window)
    )
    result = poller.result()  # Block until complete
    print(f"Update ID: {result.update_id}")

    # Search memories
    search_result = project_client.memory_stores.search_memories(
        name=store.name,
        scope="user123",
        items=[
            ResponsesUserMessageItemParam(role="user", content="What do I like to do?"),
        ],
    )
    for memory in search_result.memories:
        print(f"[{memory.type}] {memory.content}")

    # Delete scope
    project_client.memory_stores.delete_scope(name=store.name, scope="user123")

    # Delete store
    project_client.memory_stores.delete(name=store.name)
```

## CRUD Operations

```python
# Create
store = project_client.memory_stores.create(
    name="my-store",
    definition=MemoryStoreDefaultDefinition(
        options=MemoryStoreDefaultOptions(
            user_profile_enabled=True,
            chat_summary_enabled=True,
        )
    ),
    description="My memory store",
    metadata={"team": "support"},
)

# Get
store = project_client.memory_stores.get(name="my-store")

# Update
store = project_client.memory_stores.update(
    name="my-store",
    description="Updated description",
    metadata={"team": "engineering"},
)

# List
for store in project_client.memory_stores.list():
    print(store.name)

# Delete
project_client.memory_stores.delete(name="my-store")
```

## Advanced Patterns

### Incremental Updates with `previous_update_id`

```python
# First update
poller1 = project_client.memory_stores.begin_update_memories(
    name=store.name,
    scope="user123",
    items=[ResponsesUserMessageItemParam(role="user", content="I work at Contoso.")],
    update_delay=0,
)
result1 = poller1.result()

# Follow-up update referencing previous
poller2 = project_client.memory_stores.begin_update_memories(
    name=store.name,
    scope="user123",
    items=[ResponsesUserMessageItemParam(role="user", content="My title is PM.")],
    previous_update_id=result1.update_id,
    update_delay=0,
)
result2 = poller2.result()
```

### Follow-Up Searches with `previous_search_id`

```python
result1 = project_client.memory_stores.search_memories(
    name=store.name,
    scope="user123",
    items=[ResponsesUserMessageItemParam(role="user", content="What do I like?")],
)

result2 = project_client.memory_stores.search_memories(
    name=store.name,
    scope="user123",
    items=[ResponsesUserMessageItemParam(role="user", content="Tell me more about that.")],
    previous_search_id=result1.id,
)
```

### Superseding with `update_delay`

```python
# Queue with 300s delay (default)
poller1 = project_client.memory_stores.begin_update_memories(
    name=store.name,
    scope="user123",
    items=[ResponsesUserMessageItemParam(role="user", content="First message")],
    update_delay=300,
)

# This supersedes the queued update
poller2 = project_client.memory_stores.begin_update_memories(
    name=store.name,
    scope="user123",
    items=[ResponsesUserMessageItemParam(role="user", content="Updated message")],
    update_delay=300,
)
```

## Agent Integration with MemorySearchTool

```python
from azure.ai.projects.models import PromptAgentDefinition, MemorySearchTool

agent = project_client.agents.create_version(
    agent_name="memory-agent",
    definition=PromptAgentDefinition(
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        instructions="Use memory to personalize responses.",
        tools=[
            MemorySearchTool(
                memory_store_name=store.name,
                scope="user123",
            )
        ],
    ),
)
```

## Models

| Model | Description |
|---|---|
| `MemoryStoreDefaultDefinition` | Definition with `options: MemoryStoreDefaultOptions` |
| `MemoryStoreDefaultOptions` | `user_profile_enabled: bool`, `chat_summary_enabled: bool` |
| `MemoryStoreDetails` | Store details: `name`, `id`, `definition`, `description`, `metadata` |
| `MemorySearchOptions` | Search options for `search_memories` |
| `MemoryItem` | Base memory item with `type`, `content` |
| `ChatSummaryMemoryItem` | Chat summary memory |
| `UserProfileMemoryItem` | User profile memory |
| `MemoryStoreSearchResult` | Search result with `memories: list[MemorySearchItem]` |
| `MemorySearchTool` | Agent tool: `memory_store_name`, `scope`, `search_options?`, `update_delay?` |
| `ResponsesUserMessageItemParam` | User message input: `role="user"`, `content` |
| `ResponsesAssistantMessageItemParam` | Assistant message input: `role="assistant"`, `content` |
| `DeleteMemoryStoreResult` | Delete result |
| `MemoryStoreDeleteScopeResult` | Scope delete result |
| `UpdateMemoriesLROPoller` | LRO poller with `update_id`, `superseded_by` |

## Enums

| Enum | Values |
|---|---|
| `MemoryStoreKind` | `DEFAULT` |
| `MemoryOperationKind` | `CREATE`, `UPDATE`, `DELETE` |
| `MemoryStoreUpdateStatus` | `QUEUED`, `IN_PROGRESS`, `COMPLETED`, `FAILED`, `SUPERSEDED` |

## Key Patterns

- **Scope isolation**: Use user IDs or session IDs as scopes to isolate memories per user/session.
- **`update_delay`**: Default 300s batching window. Set `0` for immediate processing.
- **`previous_update_id`**: Chain incremental updates for context continuity.
- **`previous_search_id`**: Provide context for follow-up searches.
- **Superseding**: Newer updates supersede queued ones within the same scope.
- **`MemoryStoreDefaultOptions` workaround**: Explicitly set `user_profile_enabled=True, chat_summary_enabled=True` (service defaults may not apply correctly).
- **LRO polling**: `result()` blocks until complete. Access `update_id` and `superseded_by` during polling.
