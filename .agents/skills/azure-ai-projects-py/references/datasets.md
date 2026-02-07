# Datasets Reference — azure-ai-projects v2.0.0b3

## DatasetsOperations

Accessed via `project_client.datasets`.

### Methods

| Method | Signature | Returns |
|---|---|---|
| `upload_file` | `upload_file(*, name, version, file_path, connection_name=None)` | `FileDatasetVersion` |
| `upload_folder` | `upload_folder(*, name, version, folder, connection_name=None, file_pattern=None)` | `FolderDatasetVersion` |
| `get` | `get(name, version)` | `DatasetVersion` |
| `list` | `list()` | `ItemPaged[DatasetVersion]` (latest version of each) |
| `list_versions` | `list_versions(name)` | `ItemPaged[DatasetVersion]` |
| `delete` | `delete(name, version)` | `None` |
| `get_credentials` | `get_credentials(name, version)` | `DatasetCredential` |
| `create_or_update` | `create_or_update(name, version, dataset_version)` | `DatasetVersion` (lower-level) |
| `pending_upload` | `pending_upload(name, version, pending_upload_request)` | `PendingUploadResponse` (internal) |

## Models

### DatasetVersion (base)

| Field | Type |
|---|---|
| `data_uri` | `str` |
| `type` | `str \| DatasetType` |
| `is_reference` | `bool` |
| `connection_name` | `str` |
| `id` | `str` |
| `name` | `str` |
| `version` | `str` |
| `description` | `str` |
| `tags` | `dict[str, str]` |

Subtypes: `FileDatasetVersion` (`uri_file`), `FolderDatasetVersion` (`uri_folder`)

### DatasetCredential

```
DatasetCredential.blob_reference.credential.sas_uri  # SAS URI for download
```

## Upload Examples

```python
import re

# Upload a single file
dataset = project_client.datasets.upload_file(
    name="my-dataset",
    version="1",
    file_path="./data/training_data.csv",
)

# Upload a folder with file filter
dataset = project_client.datasets.upload_folder(
    name="documents",
    version="1",
    folder="./data/docs/",
    file_pattern=re.compile(r"\.(txt|csv|md|json)$", re.IGNORECASE),
)

# With specific storage connection
dataset = project_client.datasets.upload_file(
    name="my-dataset",
    version="2",
    file_path="./data.csv",
    connection_name="my-storage-connection",
)
```

## CRUD Operations

```python
# Get
dataset = project_client.datasets.get(name="my-dataset", version="1")

# List all (latest versions)
for ds in project_client.datasets.list():
    print(f"{ds.name}: v{ds.version}")

# List versions
for ds in project_client.datasets.list_versions(name="my-dataset"):
    print(f"v{ds.version}")

# Delete
project_client.datasets.delete(name="my-dataset", version="1")
```

## Download via Credentials

Requires `azure-storage-blob`:

```python
from azure.storage.blob import ContainerClient

# Get SAS credentials
creds = project_client.datasets.get_credentials(name="my-dataset", version="1")
sas_uri = creds.blob_reference.credential.sas_uri

# Download files
container_client = ContainerClient.from_container_url(sas_uri)
for blob in container_client.list_blobs():
    blob_client = container_client.get_blob_client(blob.name)
    with open(blob.name, "wb") as f:
        f.write(blob_client.download_blob().readall())
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
        dataset = await project_client.datasets.upload_file(
            name="my-dataset", version="1", file_path="./data.csv",
        )
        async for ds in project_client.datasets.list():
            print(ds.name)
        await project_client.datasets.delete(name="my-dataset", version="1")

asyncio.run(main())
```

## Key Patterns

- **`connection_name`** is optional — defaults to the project's default storage connection.
- **`upload_file`** raises `ValueError` if path is a directory.
- **`upload_folder`** raises `ValueError` if path is a file or folder is empty.
- **`file_pattern`** accepts `re.Pattern` to filter files during folder upload.
- **Upload internals**: `pending_upload` → get SAS URI → `ContainerClient` upload → `create_or_update`.
- **Dependency**: `azure-storage-blob` required for download; upload methods handle it internally.
