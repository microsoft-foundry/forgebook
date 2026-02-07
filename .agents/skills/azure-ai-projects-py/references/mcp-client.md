# MCP (Model Context Protocol) Reference — azure-ai-projects v2.0.0b3

## Overview

Two approaches to MCP integration:

1. **Agent-based MCP** — Attach MCP servers as tools to Prompt Agents via `MCPTool`. The agent orchestrates tool calls with an approval flow via the Responses API.
2. **Direct MCP Client** — Use the `mcp` Python library to connect directly to the Foundry Project MCP endpoint (`{endpoint}/mcp_tools`) and invoke tools programmatically.

## Installation

```bash
# Agent-based MCP tools
pip install "azure-ai-projects>=2.0.0b3" python-dotenv

# Direct MCP client (additional dependency)
pip install "azure-ai-projects>=2.0.0b3" python-dotenv mcp
```

## MCPTool Class

```python
from azure.ai.projects.models import MCPTool

MCPTool(
    server_label: str,                    # Required. Label to identify this MCP server.
    server_url: str,                      # Required. URL of the MCP server.
    headers: Optional[dict[str, str]],    # Optional HTTP headers for auth.
    allowed_tools: Optional[Union[list[str], MCPToolAllowedTools1]],  # Filter exposed tools.
    require_approval: Optional[Union[MCPToolRequireApproval1, "always", "never"]],  # Approval behavior.
    project_connection_id: Optional[str], # Connection ID for auth credentials.
)
```

## Supporting Models

```python
from azure.ai.projects.models import (
    MCPToolAllowedTools1,       # tool_names: list[str]
    MCPToolRequireApproval1,    # always: MCPToolRequireApprovalAlways, never: MCPToolRequireApprovalNever
    MCPToolRequireApprovalAlways,  # tool_names: list[str]
    MCPToolRequireApprovalNever,   # tool_names: list[str]
    ToolChoiceObjectMCP,        # server_label: str, name: str (force specific MCP tool)
)
```

## Agent-Based MCP with Approval Flow

```python
import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, MCPTool
from openai.types.responses.response_input_param import McpApprovalResponse, ResponseInputParam

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    project_client.get_openai_client() as openai_client,
):
    # Create MCP tool
    mcp_tool = MCPTool(
        server_label="api-specs",
        server_url="https://gitmcp.io/Azure/azure-rest-api-specs",
        require_approval="always",
    )

    # Create agent with MCP tool
    agent = project_client.agents.create_version(
        agent_name="MyAgent",
        definition=PromptAgentDefinition(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            instructions="You are a helpful agent that can use MCP tools.",
            tools=[mcp_tool],
        ),
    )

    conversation = openai_client.conversations.create()

    # Send initial request
    response = openai_client.responses.create(
        conversation=conversation.id,
        input="Summarize the Azure REST API specs",
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )

    # Handle approval requests
    input_list: ResponseInputParam = []
    for item in response.output:
        if item.type == "mcp_approval_request":
            if item.server_label == "api-specs" and item.id:
                input_list.append(
                    McpApprovalResponse(
                        type="mcp_approval_response",
                        approve=True,
                        approval_request_id=item.id,
                    )
                )

    # Send approval response to continue
    response = openai_client.responses.create(
        input=input_list,
        previous_response_id=response.id,
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )
    print(response.output_text)

    # Cleanup
    project_client.agents.delete_version(
        agent_name=agent.name, agent_version=agent.version
    )
```

## MCP with Project Connection (Authenticated Server)

```python
tool = MCPTool(
    server_label="api-specs",
    server_url="https://api.githubcopilot.com/mcp",
    require_approval="always",
    project_connection_id=os.environ["MCP_PROJECT_CONNECTION_ID"],
)
```

Set up the connection in the Foundry portal under Custom Keys, with key `"Authorization"` and value `"Bearer <token>"`.

## Direct MCP Client (Low-Level)

Connect directly to the Foundry Project MCP endpoint without an agent:

```python
import asyncio
import base64
import os
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from mcp import ClientSession
from mcp.types import ImageContent
from mcp.client.streamable_http import streamablehttp_client

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]

async def main():
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
        project_client.get_openai_client() as openai_client,
        streamablehttp_client(
            url=f"{endpoint}/mcp_tools?api-version=2025-05-15-preview",
            headers={
                "Authorization": f"Bearer {(await credential.get_token('https://ai.azure.com')).token}"
            },
        ) as (read_stream, write_stream, _),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()

        # Discover available tools
        tools = await session.list_tools()
        for tool in tools.tools:
            print(f"Tool: {tool.name}")

        # Code interpreter
        result = await session.call_tool(
            name="code_interpreter",
            arguments={"code": "print('Hello from MCP!')"},
        )
        print(result.content)

        # Image generation
        result = await session.call_tool(
            name="image_generation",
            arguments={"prompt": "A cute puppy"},
            meta={"imagegen_model_deployment_name": os.getenv("IMAGE_GEN_DEPLOYMENT_NAME", "")},
        )
        if result.content and isinstance(result.content[0], ImageContent):
            with open("output.png", "wb") as f:
                f.write(base64.b64decode(result.content[0].data))

        # File search (requires a vector store)
        vector_store = await openai_client.vector_stores.create(name="store")
        await openai_client.vector_stores.files.upload_and_poll(
            vector_store_id=vector_store.id,
            file=open("./docs.md", "rb"),
        )
        result = await session.call_tool(
            name="file_search",
            arguments={"queries": ["What features are available?"]},
            meta={"vector_store_ids": [vector_store.id]},
        )
        print(result.content)

asyncio.run(main())
```

## MCP Streaming Events

| Event Type | Description |
|---|---|
| `response.mcp_call.in_progress` | MCP tool call started |
| `response.mcp_call.arguments_delta` | Partial arguments update |
| `response.mcp_call.arguments_done` | Arguments finalized |
| `response.mcp_call.completed` | Tool call succeeded |
| `response.mcp_call.failed` | Tool call failed |
| `response.mcp_list_tools.in_progress` | Tool listing started |
| `response.mcp_list_tools.completed` | Tool listing succeeded |
| `response.mcp_list_tools.failed` | Tool listing failed |

## MCP Response Output Types

| `item.type` | Description |
|---|---|
| `"mcp_approval_request"` | Needs human approval. Has `id`, `server_label`, `name`, `arguments`. |
| `"mcp_call"` | Completed tool call. Has `server_label`, `name`, `arguments`, `output`, `error`. |
| `"mcp_list_tools"` | Tool discovery. Has `server_label`, `tools`, `error`. |

## Key Patterns

- **Always check `item.type == "mcp_approval_request"`** when `require_approval="always"`. Missing this causes the agent to stall.
- **Chain responses with `previous_response_id`** after sending approvals.
- **`McpApprovalResponse`** is imported from `openai.types.responses.response_input_param`, not from `azure.ai.projects.models`.
- **Direct MCP endpoint**: `{AZURE_AI_PROJECT_ENDPOINT}/mcp_tools?api-version=2025-05-15-preview`. Authenticate with Bearer token scoped to `https://ai.azure.com`.
- **`MCPTool` vs `McpTool`**: The `azure-ai-projects` v2 SDK uses `MCPTool` (PascalCase). The older `azure-ai-agents` SDK uses `McpTool` (camelCase).
