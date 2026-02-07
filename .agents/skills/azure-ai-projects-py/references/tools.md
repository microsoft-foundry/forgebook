# Agent Tools Reference — azure-ai-projects v2.0.0b3

## Imports

All v2 tools import from `azure.ai.projects.models`:

```python
from azure.ai.projects.models import (
    # Core agent definition
    PromptAgentDefinition,
    # Code Interpreter
    CodeInterpreterTool, CodeInterpreterToolAuto,
    # File Search
    FileSearchTool,
    # Function
    FunctionTool,
    # Bing/Web Search
    BingGroundingTool, BingGroundingSearchToolParameters, BingGroundingSearchConfiguration,
    WebSearchPreviewTool, ApproximateLocation,
    # Azure AI Search
    AzureAISearchTool, AzureAISearchToolResource, AISearchIndexResource, AzureAISearchQueryType,
    # OpenAPI
    OpenApiTool, OpenApiFunctionDefinition, OpenApiAnonymousAuthDetails,
    # Image Generation
    ImageGenTool,
    # Agent-to-Agent
    A2APreviewTool,
    # MCP
    MCPTool,
    # SharePoint
    SharepointPreviewTool, SharepointGroundingToolParameters,
    # Browser Automation
    BrowserAutomationPreviewTool, BrowserAutomationToolParameters,
    # Microsoft Fabric
    MicrosoftFabricPreviewTool, FabricDataAgentToolParameters,
    # Computer Use
    ComputerUsePreviewTool,
    # Memory Search
    MemorySearchTool,
    # Azure Functions
    AzureFunctionTool, AzureFunctionDefinition, AzureFunctionStorageQueue,
    # Structured Output
    CaptureStructuredOutputsTool,
)
```

## CodeInterpreterTool

Execute Python code in a sandboxed container.

```python
from azure.ai.projects.models import CodeInterpreterTool, CodeInterpreterToolAuto

# Basic (no files)
tool = CodeInterpreterTool(container=CodeInterpreterToolAuto())

# With files
file = openai_client.files.create(purpose="assistants", file=open("data.csv", "rb"))
tool = CodeInterpreterTool(container=CodeInterpreterToolAuto(file_ids=[file.id]))

agent = project_client.agents.create_version(
    agent_name="analyst",
    definition=PromptAgentDefinition(
        model=model, instructions="Analyze data.", tools=[tool],
    ),
)
```

## FileSearchTool

RAG over uploaded documents via vector stores.

```python
from azure.ai.projects.models import FileSearchTool

vector_store = openai_client.vector_stores.create(name="KnowledgeBase")
openai_client.vector_stores.files.upload_and_poll(
    vector_store_id=vector_store.id, file=open("docs.md", "rb"),
)

tool = FileSearchTool(vector_store_ids=[vector_store.id])
```

## FunctionTool

Custom function calling with JSON schema.

```python
from azure.ai.projects.models import FunctionTool
from openai.types.responses.response_input_param import FunctionCallOutput
import json

def get_weather(location: str) -> str:
    return f"72F in {location}"

tool = FunctionTool(
    name="get_weather",
    description="Get weather for a location",
    parameters={
        "type": "object",
        "properties": {"location": {"type": "string", "description": "City name"}},
        "required": ["location"],
    },
    strict=True,
)

# Handle function calls in response
for item in response.output:
    if item.type == "function_call" and item.name == "get_weather":
        result = get_weather(**json.loads(item.arguments))
        input_list.append(FunctionCallOutput(
            type="function_call_output",
            call_id=item.call_id,
            output=json.dumps({"weather": result}),
        ))
```

## BingGroundingTool

Web search via Bing connection.

```python
from azure.ai.projects.models import (
    BingGroundingTool, BingGroundingSearchToolParameters, BingGroundingSearchConfiguration,
)

tool = BingGroundingTool(
    bing_grounding=BingGroundingSearchToolParameters(
        search_configurations=[
            BingGroundingSearchConfiguration(
                project_connection_id=os.environ["BING_PROJECT_CONNECTION_ID"]
            )
        ]
    )
)
```

## WebSearchPreviewTool

Built-in web search (preview).

```python
from azure.ai.projects.models import WebSearchPreviewTool, ApproximateLocation

tool = WebSearchPreviewTool(
    user_location=ApproximateLocation(city="Seattle", region="WA", country="US"),
)
```

## AzureAISearchTool

Enterprise search over Azure AI Search indexes.

```python
from azure.ai.projects.models import (
    AzureAISearchTool, AzureAISearchToolResource, AISearchIndexResource, AzureAISearchQueryType,
)

search_connection = project_client.connections.get("my-search-connection")

tool = AzureAISearchTool(
    azure_ai_search=AzureAISearchToolResource(
        indexes=[
            AISearchIndexResource(
                project_connection_id=search_connection.id,
                index_name="my-index",
                query_type=AzureAISearchQueryType.SEMANTIC,
            )
        ]
    )
)
```

### Query Types

| Value | Description |
|---|---|
| `SIMPLE` | Simple keyword search |
| `SEMANTIC` | Semantic ranking |
| `VECTOR` | Vector search |
| `VECTOR_SIMPLE_HYBRID` | Vector + keyword hybrid |
| `VECTOR_SEMANTIC_HYBRID` | Vector + semantic hybrid |

## OpenApiTool

Call external REST APIs.

```python
from azure.ai.projects.models import OpenApiTool, OpenApiFunctionDefinition, OpenApiAnonymousAuthDetails

tool = OpenApiTool(
    openapi=OpenApiFunctionDefinition(
        name="weather_api",
        spec=openapi_spec_string,
        description="Get weather information",
        auth=OpenApiAnonymousAuthDetails(),
    ),
)
```

## ImageGenTool

Image generation (DALL-E).

```python
from azure.ai.projects.models import ImageGenTool

tool = ImageGenTool(
    model=os.environ.get("IMAGE_GEN_DEPLOYMENT_NAME", "dall-e-3"),
    quality="standard",  # or "hd"
    size="1024x1024",
)
```

## MCPTool

Model Context Protocol server integration. See [mcp-client.md](mcp-client.md).

```python
from azure.ai.projects.models import MCPTool

tool = MCPTool(
    server_label="my-server",
    server_url="https://gitmcp.io/my/repo",
    require_approval="always",
)
```

## A2APreviewTool

Agent-to-Agent communication (preview).

```python
from azure.ai.projects.models import A2APreviewTool

tool = A2APreviewTool(
    project_connection_id=os.environ["A2A_CONNECTION_ID"],
)
```

## SharepointPreviewTool

SharePoint content search (preview).

```python
from azure.ai.projects.models import SharepointPreviewTool, SharepointGroundingToolParameters

tool = SharepointPreviewTool(
    sharepoint=SharepointGroundingToolParameters(
        # Configure SharePoint search parameters
    ),
)
```

## BrowserAutomationPreviewTool

Browser automation (preview).

```python
from azure.ai.projects.models import BrowserAutomationPreviewTool, BrowserAutomationToolParameters

tool = BrowserAutomationPreviewTool(
    browser_automation=BrowserAutomationToolParameters(),
)
```

## MicrosoftFabricPreviewTool

Microsoft Fabric Data Agent (preview).

```python
from azure.ai.projects.models import MicrosoftFabricPreviewTool, FabricDataAgentToolParameters

tool = MicrosoftFabricPreviewTool(
    microsoft_fabric=FabricDataAgentToolParameters(
        # Configure Fabric parameters
    ),
)
```

## ComputerUsePreviewTool

Computer use tool (preview).

```python
from azure.ai.projects.models import ComputerUsePreviewTool

tool = ComputerUsePreviewTool()
```

## MemorySearchTool

Memory store integration. See [memories.md](memories.md).

```python
from azure.ai.projects.models import MemorySearchTool

tool = MemorySearchTool(
    memory_store_name="my-store",
    scope="user123",
)
```

## AzureFunctionTool

Azure Functions integration.

```python
from azure.ai.projects.models import (
    AzureFunctionTool, AzureFunctionDefinition, AzureFunctionStorageQueue,
)

tool = AzureFunctionTool(
    azure_function=AzureFunctionDefinition(
        name="my-function",
        description="Process data",
        parameters={
            "type": "object",
            "properties": {"input": {"type": "string"}},
            "required": ["input"],
        },
        input_queue=AzureFunctionStorageQueue(
            queue_name="input-queue",
            storage_service_endpoint=os.environ["STORAGE_ENDPOINT"],
        ),
        output_queue=AzureFunctionStorageQueue(
            queue_name="output-queue",
            storage_service_endpoint=os.environ["STORAGE_ENDPOINT"],
        ),
    ),
)
```

## CaptureStructuredOutputsTool

Capture structured outputs from agent responses.

```python
from azure.ai.projects.models import CaptureStructuredOutputsTool

tool = CaptureStructuredOutputsTool()
```

## Tools Quick Reference

| Tool | Class | Connection | Use Case |
|---|---|---|---|
| Code Interpreter | `CodeInterpreterTool` | No | Execute Python, generate files |
| File Search | `FileSearchTool` | No | RAG over documents |
| Function | `FunctionTool` | No | Custom function calling |
| Bing Grounding | `BingGroundingTool` | Yes | Web search via Bing |
| Web Search | `WebSearchPreviewTool` | No | Built-in web search |
| Azure AI Search | `AzureAISearchTool` | Yes | Enterprise search |
| OpenAPI | `OpenApiTool` | No | REST API calls |
| Image Gen | `ImageGenTool` | No | Image generation |
| MCP | `MCPTool` | Optional | MCP server integration |
| A2A | `A2APreviewTool` | Yes | Agent-to-agent |
| SharePoint | `SharepointPreviewTool` | Yes | SharePoint search |
| Browser | `BrowserAutomationPreviewTool` | No | Browser automation |
| Fabric | `MicrosoftFabricPreviewTool` | Yes | Microsoft Fabric |
| Computer Use | `ComputerUsePreviewTool` | No | Computer use |
| Memory | `MemorySearchTool` | No | Memory store search |
| Azure Function | `AzureFunctionTool` | Yes | Azure Functions |
| Structured Output | `CaptureStructuredOutputsTool` | No | Capture structured outputs |
