---
name: azure-ai-projects-py
description: Build AI applications using the Azure AI Projects Python SDK v2 (azure-ai-projects 2.0.0b3+). Use for creating versioned agents with PromptAgentDefinition, conversations via OpenAI client, streaming responses, tools (CodeInterpreter, FileSearch, Function, BingGrounding, AzureAISearch, MCP, WebSearch, ImageGen, and more), multi-agent workflows with WorkflowAgentDefinition, evaluations, memory stores, fine-tuning, MCP integration, red teaming, datasets/indexes, and telemetry.
---

# Azure AI Projects Python SDK v2 (Foundry SDK)

Build AI agents on Azure AI Foundry using `azure-ai-projects>=2.0.0b3`.

## Installation

```bash
pip install "azure-ai-projects>=2.0.0b3" azure-identity python-dotenv
```

## Environment Variables

```bash
AZURE_AI_PROJECT_ENDPOINT="https://<resource>.services.ai.azure.com/api/projects/<project>"
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4o"
BING_PROJECT_CONNECTION_ID="<connection-id>"  # For web search
```

## Core Pattern: Two Clients

The v2 SDK uses **two clients** together:
1. **AIProjectClient** - Agent creation/versioning
2. **OpenAI Client** (from project) - Conversations and responses

```python
import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition

load_dotenv()
endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    project_client.get_openai_client() as openai_client,
):
    # 1. Create versioned agent
    agent = project_client.agents.create_version(
        agent_name="my-agent",
        definition=PromptAgentDefinition(
            model=model,
            instructions="You are a helpful assistant.",
        ),
    )
    
    # 2. Create conversation with initial message
    conversation = openai_client.conversations.create(
        items=[{"type": "message", "role": "user", "content": "Hello!"}],
    )
    
    # 3. Run agent and get response
    response = openai_client.responses.create(
        conversation=conversation.id,
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
        input="",
    )
    print(response.output_text)
    
    # 4. Cleanup
    openai_client.conversations.delete(conversation_id=conversation.id)
    project_client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
```

## Agent Creation with PromptAgentDefinition

```python
from azure.ai.projects.models import PromptAgentDefinition

agent = project_client.agents.create_version(
    agent_name="customer-support-agent",
    definition=PromptAgentDefinition(
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        instructions="You are a customer support specialist.",
        tools=[],  # Add tools as needed
    ),
)
print(f"Agent: name={agent.name}, version={agent.version}")
```

## Conversations (replaces Threads)

```python
# Create conversation with initial message
conversation = openai_client.conversations.create(
    items=[{"type": "message", "role": "user", "content": "Hello!"}],
)

# Add follow-up message
openai_client.conversations.items.create(
    conversation_id=conversation.id,
    items=[{"type": "message", "role": "user", "content": "Follow-up question"}],
)

# Run agent on conversation
response = openai_client.responses.create(
    conversation=conversation.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    input="",
)
print(response.output_text)
```

## Streaming Responses

```python
# Enable streaming with stream=True
with openai_client.responses.create(
    conversation=conversation.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    input="",
    stream=True,
) as stream:
    for event in stream:
        if event.type == "response.output_text.delta":
            print(event.delta, end="", flush=True)
        elif event.type == "response.completed":
            print("\n--- Done ---")
```

## Tools

### CodeInterpreterTool

```python
from azure.ai.projects.models import (
    PromptAgentDefinition,
    CodeInterpreterTool,
    CodeInterpreterToolAuto,
)

# Upload file for code interpreter
file = openai_client.files.create(purpose="assistants", file=open("data.csv", "rb"))

agent = project_client.agents.create_version(
    agent_name="data-analyst",
    definition=PromptAgentDefinition(
        model=model,
        instructions="Analyze data and create visualizations.",
        tools=[CodeInterpreterTool(container=CodeInterpreterToolAuto(file_ids=[file.id]))],
    ),
)
```

### FileSearchTool (RAG)

```python
from azure.ai.projects.models import PromptAgentDefinition, FileSearchTool

# Create vector store and upload files
vector_store = openai_client.vector_stores.create(name="KnowledgeBase")
openai_client.vector_stores.files.upload_and_poll(
    vector_store_id=vector_store.id,
    file=open("docs.md", "rb"),
)

agent = project_client.agents.create_version(
    agent_name="rag-agent",
    definition=PromptAgentDefinition(
        model=model,
        instructions="Search knowledge base to answer questions.",
        tools=[FileSearchTool(vector_store_ids=[vector_store.id])],
    ),
)
```

### FunctionTool

```python
from azure.ai.projects.models import PromptAgentDefinition, FunctionTool
from openai.types.responses.response_input_param import FunctionCallOutput
import json

# Define function
def get_weather(location: str) -> str:
    return f"Weather in {location}: 72F, sunny"

# Create tool with schema
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

agent = project_client.agents.create_version(
    agent_name="weather-agent",
    definition=PromptAgentDefinition(model=model, instructions="Help with weather.", tools=[tool]),
)

# Process function calls in response
response = openai_client.responses.create(
    input="What's the weather in Paris?",
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
)

# Handle function calls
input_list = []
for item in response.output:
    if item.type == "function_call" and item.name == "get_weather":
        result = get_weather(**json.loads(item.arguments))
        input_list.append(FunctionCallOutput(
            type="function_call_output",
            call_id=item.call_id,
            output=json.dumps({"weather": result}),
        ))

# Continue with function results
response = openai_client.responses.create(
    input=input_list,
    previous_response_id=response.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
)
```

### BingGroundingTool

```python
from azure.ai.projects.models import (
    PromptAgentDefinition,
    BingGroundingTool,
    BingGroundingSearchToolParameters,
    BingGroundingSearchConfiguration,
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

agent = project_client.agents.create_version(
    agent_name="web-search-agent",
    definition=PromptAgentDefinition(model=model, instructions="Search the web.", tools=[tool]),
)
```

## Multi-Agent Workflows

Use `WorkflowAgentDefinition` with YAML to orchestrate multiple agents:

```python
from azure.ai.projects.models import PromptAgentDefinition, WorkflowAgentDefinition

# Create specialist agents
teacher = project_client.agents.create_version(
    agent_name="teacher",
    definition=PromptAgentDefinition(model=model, instructions="Create math questions."),
)
student = project_client.agents.create_version(
    agent_name="student",
    definition=PromptAgentDefinition(model=model, instructions="Answer questions."),
)

# Define workflow in YAML
workflow_yaml = f"""
kind: workflow
trigger:
  kind: OnConversationStart
  id: math_workflow
  actions:
    - kind: SetVariable
      id: set_input
      variable: Local.Message
      value: "=UserMessage(System.LastMessageText)"
    - kind: InvokeAzureAgent
      id: student_turn
      agent:
        name: {student.name}
      input:
        messages: "=Local.Message"
      output:
        messages: Local.Message
    - kind: InvokeAzureAgent
      id: teacher_turn
      agent:
        name: {teacher.name}
      input:
        messages: "=Local.Message"
      output:
        messages: Local.Message
    - kind: ConditionGroup
      id: check_done
      conditions:
        - condition: '=!IsBlank(Find("[DONE]", Upper(Last(Local.Message).Text)))'
          actions:
            - kind: EndConversation
              id: end
      elseActions:
        - kind: GotoAction
          id: loop
          actionId: student_turn
"""

workflow = project_client.agents.create_version(
    agent_name="math-workflow",
    definition=WorkflowAgentDefinition(workflow=workflow_yaml),
)
```

## Async Pattern

```python
import asyncio
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition

async def main():
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
        project_client.get_openai_client() as openai_client,
    ):
        agent = await project_client.agents.create_version(
            agent_name="async-agent",
            definition=PromptAgentDefinition(model=model, instructions="Help users."),
        )
        
        conversation = await openai_client.conversations.create(
            items=[{"type": "message", "role": "user", "content": "Hello!"}],
        )
        
        response = await openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
            input="",
        )
        print(response.output_text)
        
        # Cleanup
        await openai_client.conversations.delete(conversation_id=conversation.id)
        await project_client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)

asyncio.run(main())
```

## Structured Output

```python
from azure.ai.projects.models import (
    PromptAgentDefinition,
    PromptAgentDefinitionText,
    ResponseTextFormatConfigurationJsonSchema,
)
from pydantic import BaseModel

class Event(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    date: str
    participants: list[str]

agent = project_client.agents.create_version(
    agent_name="structured-agent",
    definition=PromptAgentDefinition(
        model=model,
        text=PromptAgentDefinitionText(
            format=ResponseTextFormatConfigurationJsonSchema(
                name="Event",
                schema=Event.model_json_schema(),
            )
        ),
        instructions="Extract event information as JSON.",
    ),
)
```

## Key API Patterns

| Old Pattern (v1) | New Pattern (v2) |
|------------------|------------------|
| `client.agents.create_agent()` | `project_client.agents.create_version()` with `PromptAgentDefinition` |
| `client.agents.threads.create()` | `openai_client.conversations.create()` |
| `client.agents.messages.create()` | `openai_client.conversations.items.create()` |
| `client.agents.runs.create_and_process()` | `openai_client.responses.create()` |
| Agent ID reference | `extra_body={"agent": {"name": agent.name, "type": "agent_reference"}}` |
| `delete_agent()` | `delete_version(agent_name, agent_version)` |

## Additional Operations

### Memory Stores

Create and query persistent memory stores for agents. See [references/memories.md](references/memories.md).

### Fine-Tuning

Fine-tune models with SFT, DPO, or RFT methods. See [references/finetuning.md](references/finetuning.md).

### MCP Integration

Connect agents to MCP servers using `MCPTool`. See [references/mcp-client.md](references/mcp-client.md).

### Red Teaming

Automated red team testing against agents. See [references/red-teaming.md](references/red-teaming.md).

### Telemetry

Instrument agents and functions for tracing with OpenTelemetry. See [references/telemetry.md](references/telemetry.md).

### Datasets & Indexes

Upload and manage datasets. Create and manage search indexes. See [references/datasets.md](references/datasets.md) and [references/indexes.md](references/indexes.md).

### Responses API

Direct responses without conversations, multi-turn with `previous_response_id`. See [references/responses.md](references/responses.md).

## Reference Files

- [references/agents.md](references/agents.md): Agent CRUD, PromptAgentDefinition, WorkflowAgentDefinition, conversations, streaming, structured output
- [references/tools.md](references/tools.md): All 17+ agent tools (CodeInterpreter, FileSearch, Function, Bing, WebSearch, AzureAISearch, OpenAPI, ImageGen, MCP, A2A, SharePoint, Browser, Fabric, ComputerUse, Memory, AzureFunction, StructuredOutput)
- [references/evaluation.md](references/evaluation.md): Evaluations — built-in evaluators, custom evaluators, eval runs, rules, schedules, insights
- [references/connections.md](references/connections.md): Connection operations, ConnectionType enum, credential models
- [references/deployments.md](references/deployments.md): Deployment listing, ModelDeployment, DeploymentType
- [references/datasets.md](references/datasets.md): Dataset upload/download, CRUD, file/folder datasets
- [references/indexes.md](references/indexes.md): Index CRUD, AzureAISearchIndex, CosmosDBIndex, ManagedAzureAISearchIndex
- [references/files.md](references/files.md): File operations via OpenAI client, vector stores, container downloads
- [references/finetuning.md](references/finetuning.md): Fine-tuning jobs — SFT, DPO, RFT methods
- [references/memories.md](references/memories.md): Memory store CRUD, MemorySearchTool agent integration
- [references/mcp-client.md](references/mcp-client.md): MCPTool, MCP server integration, approval flow
- [references/red-teaming.md](references/red-teaming.md): Red team operations, attack strategies, risk categories
- [references/responses.md](references/responses.md): Responses API — direct input, multi-turn, streaming events, structured output
- [references/telemetry.md](references/telemetry.md): OpenTelemetry instrumentation, AIProjectInstrumentor, trace_function
