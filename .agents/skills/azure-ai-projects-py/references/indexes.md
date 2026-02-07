# Indexes Reference — azure-ai-projects v2.0.0b3

## IndexesOperations

Accessed via `project_client.indexes`.

```python
# Create or update an index
index = project_client.indexes.create_or_update(
    name="my-index",
    version="1",
    index=AzureAISearchIndex(
        connection_name="my-search-connection",
        index_name="my-search-index",
    ),
)

# Get an index
index = project_client.indexes.get(name="my-index", version="1")

# List all indexes (latest version of each)
for index in project_client.indexes.list():
    print(index.name, index.version, index.type)

# List all versions of an index
for index in project_client.indexes.list_versions(name="my-index"):
    print(index.version)

# Delete an index (idempotent)
project_client.indexes.delete(name="my-index", version="1")
```

### Method Signatures

| Method | Parameters | Returns |
|---|---|---|
| `create_or_update` | `name: str, version: str, index: Index` | `Index` |
| `get` | `name: str, version: str` | `Index` |
| `list` | (none) | `ItemPaged[Index]` |
| `list_versions` | `name: str` | `ItemPaged[Index]` |
| `delete` | `name: str, version: str` | `None` |

## Index Model Hierarchy

### Index (base)

Discriminated by `type` field.

| Field | Type | Visibility |
|---|---|---|
| `type` | `str \| IndexType` | Read-only |
| `id` | `str` | Read-only |
| `name` | `str` | Read-only |
| `version` | `str` | Read-only |
| `description` | `str` | Read/Write |
| `tags` | `dict[str, str]` | Read/Write |

### AzureAISearchIndex

Standard Azure AI Search index backed by an existing search connection.

```python
from azure.ai.projects.models import AzureAISearchIndex, FieldMapping

index = AzureAISearchIndex(
    connection_name="my-search-connection",
    index_name="my-search-index",
    field_mapping=FieldMapping(
        content_fields=["content"],
        title_field="title",
        url_field="url",
        filepath_field="filepath",
        vector_fields=["contentVector"],
    ),
)
```

| Field | Type | Required |
|---|---|---|
| `connection_name` | `str` | Yes (create-only) |
| `index_name` | `str` | Yes (create-only) |
| `field_mapping` | `FieldMapping` | No |

### CosmosDBIndex

Index backed by Azure Cosmos DB with embedding configuration.

```python
from azure.ai.projects.models import CosmosDBIndex, FieldMapping, EmbeddingConfiguration

index = CosmosDBIndex(
    connection_name="my-cosmos-connection",
    database_name="my-database",
    container_name="my-container",
    embedding_configuration=EmbeddingConfiguration(
        model_deployment_name="text-embedding-3-small",
        embedding_field="embedding",
    ),
    field_mapping=FieldMapping(
        content_fields=["content"],
        title_field="title",
    ),
)
```

| Field | Type | Required |
|---|---|---|
| `connection_name` | `str` | Yes (create-only) |
| `database_name` | `str` | Yes (create-only) |
| `container_name` | `str` | Yes (create-only) |
| `embedding_configuration` | `EmbeddingConfiguration` | Yes |
| `field_mapping` | `FieldMapping` | Yes |

### ManagedAzureAISearchIndex

Managed search index backed by an OpenAI vector store.

```python
from azure.ai.projects.models import ManagedAzureAISearchIndex

index = ManagedAzureAISearchIndex(
    vector_store_id="vs_abc123",
)
```

| Field | Type | Required |
|---|---|---|
| `vector_store_id` | `str` | Yes |

## Supporting Models

### FieldMapping

| Field | Type | Required |
|---|---|---|
| `content_fields` | `list[str]` | Yes |
| `filepath_field` | `str` | No |
| `title_field` | `str` | No |
| `url_field` | `str` | No |
| `vector_fields` | `list[str]` | No |
| `metadata_fields` | `list[str]` | No |

### EmbeddingConfiguration

| Field | Type | Required |
|---|---|---|
| `model_deployment_name` | `str` | Yes |
| `embedding_field` | `str` | Yes |

## IndexType Enum

| Value | String |
|---|---|
| `AZURE_SEARCH` | `"AzureSearch"` |
| `COSMOS_DB` | `"CosmosDB"` |
| `MANAGED_AZURE_SEARCH` | `"ManagedAzureSearch"` |

## Async Pattern

```python
import asyncio
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import AzureAISearchIndex

async def main():
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        index = await project_client.indexes.create_or_update(
            name="my-index",
            version="1",
            index=AzureAISearchIndex(
                connection_name="my-search-connection",
                index_name="my-search-index",
            ),
        )
        print(index.name, index.version)

        async for idx in project_client.indexes.list():
            print(idx.name, idx.type)

        await project_client.indexes.delete(name="my-index", version="1")

asyncio.run(main())
```

## Key Patterns

- **Create-only fields** (`connection_name`, `index_name`, etc.) are set at creation and may not be returned on read.
- **Read-only fields** (`id`, `name`, `version`) are server-assigned.
- **Delete is idempotent** — no error if the index doesn't exist.
- **`create_or_update`** uses PATCH semantics (`application/merge-patch+json`).
