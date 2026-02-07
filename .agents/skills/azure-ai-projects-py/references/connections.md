# Connections Reference — azure-ai-projects v2.0.0b3

## ConnectionsOperations

Accessed via `project_client.connections`.

### Methods

| Method | Signature | Returns |
|---|---|---|
| `get` | `get(name, *, include_credentials=False)` | `Connection` |
| `get_default` | `get_default(connection_type, *, include_credentials=False)` | `Connection` |
| `list` | `list(*, connection_type=None, default_connection=None)` | `ItemPaged[Connection]` |

## Connection Model

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Friendly name |
| `id` | `str` | Unique ID |
| `type` | `str \| ConnectionType` | Connection type (**not** `connection_type`) |
| `target` | `str` | Connection URL (**not** `endpoint_url`) |
| `is_default` | `bool` | Whether this is the default for its type |
| `credentials` | `BaseCredentials` | Credential information |
| `metadata` | `dict[str, str]` | Metadata key-value pairs |

## ConnectionType Enum

```python
from azure.ai.projects.models import ConnectionType
```

| Value | String |
|---|---|
| `AZURE_OPEN_AI` | `"AzureOpenAI"` |
| `AZURE_BLOB_STORAGE` | `"AzureBlob"` |
| `AZURE_STORAGE_ACCOUNT` | `"AzureStorageAccount"` |
| `AZURE_AI_SEARCH` | `"CognitiveSearch"` |
| `COSMOS_DB` | `"CosmosDB"` |
| `API_KEY` | `"ApiKey"` |
| `APPLICATION_CONFIGURATION` | `"AppConfig"` |
| `APPLICATION_INSIGHTS` | `"AppInsights"` |
| `CUSTOM` | `"CustomKeys"` |
| `REMOTE_TOOL` | `"RemoteTool"` |

## Credential Models

```python
from azure.ai.projects.models import CredentialType
```

| Class | `CredentialType` | Extra Fields |
|---|---|---|
| `EntraIDCredentials` | `"AAD"` | None |
| `AgenticIdentityCredentials` | `"AgenticIdentityToken"` | None |
| `ApiKeyCredentials` | `"ApiKey"` | `api_key: str` |
| `CustomCredential` | `"CustomKeys"` | `credential_keys: dict` (when `include_credentials=True`) |
| `NoAuthenticationCredentials` | `"None"` | None |
| `SASCredentials` | `"SAS"` | `sas_token: str` |

## Usage Examples

### List Connections

```python
from azure.ai.projects.models import ConnectionType

# List all
for conn in project_client.connections.list():
    print(f"{conn.name}: {conn.type}")

# Filter by type
for conn in project_client.connections.list(connection_type=ConnectionType.AZURE_OPEN_AI):
    print(f"Azure OpenAI: {conn.name}")
```

### Get Connection

```python
# By name (positional argument, not keyword)
connection = project_client.connections.get("my-connection")
print(f"Name: {connection.name}, Type: {connection.type}, Target: {connection.target}")

# With credentials
connection = project_client.connections.get("my-connection", include_credentials=True)
print(f"Credentials type: {connection.credentials.type}")
```

### Get Default Connection

```python
from azure.ai.projects.models import ConnectionType

default_aoai = project_client.connections.get_default(
    connection_type=ConnectionType.AZURE_OPEN_AI,
    include_credentials=True,
)
print(f"Default AOAI: {default_aoai.name}")
```

### Custom Connection Credentials

```python
# Custom connections have credential_keys dict
conn = project_client.connections.get("my-custom-conn", include_credentials=True)
if conn.credentials.type == "CustomKeys":
    keys = conn.credentials.credential_keys  # dict of secret key-value pairs
    print(keys)
```

### OpenAI Client from Connection

```python
openai_client = project_client.get_openai_client(
    connection_name="my-aoai-connection",
)
```

## Async Pattern

```python
import asyncio
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient

async def main():
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        conn = await project_client.connections.get("my-connection", include_credentials=True)
        print(f"{conn.name}: {conn.type}")

        async for conn in project_client.connections.list():
            print(conn.name)

asyncio.run(main())
```
