# Files Reference — azure-ai-projects v2.0.0b3

## Architecture

All file operations use the **OpenAI client** (`project_client.get_openai_client()`), not `AIProjectClient` directly. There is no `project_client.files` — all file/vector-store/container operations go through the OpenAI API surface.

## File Operations (CRUD)

```python
# Upload a file
file = openai_client.files.create(
    file=open("data.csv", "rb"),
    purpose="assistants",  # or "fine-tune"
)

# Wait for processing (30 min default timeout)
openai_client.files.wait_for_processing(file.id)

# Retrieve file metadata
file = openai_client.files.retrieve(file.id)

# Get file content bytes
content = openai_client.files.content(file.id)

# List all files
for f in openai_client.files.list():
    print(f.id, f.filename)

# Delete a file
openai_client.files.delete(file.id)
```

### File Purposes

| Purpose | Use Case |
|---|---|
| `"assistants"` | Files used with CodeInterpreterTool, FileSearchTool, or agent tools |
| `"fine-tune"` | JSONL training data for fine-tuning jobs |

## Vector Stores (for FileSearchTool)

```python
# Create a vector store
vector_store = openai_client.vector_stores.create(name="KnowledgeBase")

# Upload file to vector store
openai_client.vector_stores.files.upload_and_poll(
    vector_store_id=vector_store.id,
    file=open("docs.md", "rb"),
)

# Use with FileSearchTool
from azure.ai.projects.models import FileSearchTool

agent = project_client.agents.create_version(
    agent_name="rag-agent",
    definition=PromptAgentDefinition(
        model=model,
        instructions="Search knowledge base to answer questions.",
        tools=[FileSearchTool(vector_store_ids=[vector_store.id])],
    ),
)

# Delete vector store
openai_client.vector_stores.delete(vector_store.id)
```

## CodeInterpreterTool with Files

```python
from azure.ai.projects.models import CodeInterpreterTool, CodeInterpreterToolAuto

# Upload file for code interpreter
file = openai_client.files.create(purpose="assistants", file=open("data.csv", "rb"))

# Create tool with file reference
tool = CodeInterpreterTool(container=CodeInterpreterToolAuto(file_ids=[file.id]))

agent = project_client.agents.create_version(
    agent_name="data-analyst",
    definition=PromptAgentDefinition(
        model=model,
        instructions="Analyze data and create visualizations.",
        tools=[tool],
    ),
)
```

## Container File Downloads

Code Interpreter generates files in containers. Download them via annotations:

```python
response = openai_client.responses.create(
    conversation=conversation.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    input="",
)

# Extract file annotations from response output
for item in response.output:
    if hasattr(item, "content"):
        for block in item.content:
            if hasattr(block, "annotations"):
                for annotation in block.annotations:
                    if annotation.type == "container_file_citation":
                        # Download the file
                        file_content = openai_client.containers.files.content.retrieve(
                            file_id=annotation.file_id,
                            container_id=annotation.container_id,
                        )
                        with open(annotation.filename, "wb") as f:
                            f.write(file_content.read())
                        print(f"Downloaded: {annotation.filename}")
```

## FileSearchTool with Streaming

```python
with openai_client.responses.create(
    conversation=conversation.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    input="",
    stream=True,
) as stream:
    for event in stream:
        if event.type == "response.file_search_call.searching":
            print("Searching files...")
        elif event.type == "response.file_search_call.completed":
            print("File search completed")
        elif event.type == "response.output_text.delta":
            print(event.delta, end="", flush=True)
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
        project_client.get_openai_client() as openai_client,
    ):
        file = await openai_client.files.create(
            file=open("data.csv", "rb"),
            purpose="assistants",
        )
        await openai_client.files.wait_for_processing(file.id)

        async for f in openai_client.files.list():
            print(f.id, f.filename)

        await openai_client.files.delete(file.id)

asyncio.run(main())
```

## Cleanup Order

Always clean up resources in this order:

1. Delete agent version: `project_client.agents.delete_version(agent_name=..., agent_version=...)`
2. Delete conversation: `openai_client.conversations.delete(conversation_id=...)`
3. Delete uploaded files: `openai_client.files.delete(file_id)`
4. Delete vector stores: `openai_client.vector_stores.delete(vector_store_id)`

## File-Related Models

From `azure.ai.projects.models`:

| Model | Description |
|---|---|
| `CodeInterpreterTool` | Code interpreter tool definition |
| `CodeInterpreterToolAuto` | Auto-container with `file_ids` |
| `FileSearchTool` | File search (RAG) tool with `vector_store_ids` |
