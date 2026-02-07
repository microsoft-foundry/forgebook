# Agent Operations Reference — azure-ai-projects v2.0.0b3

## AgentsOperations

Accessed via `project_client.agents`.

### Methods

| Method | Parameters | Returns |
|---|---|---|
| `create` | `name, definition, metadata?, description?` | `AgentDetails` |
| `create_version` | `agent_name, definition, metadata?, description?` | `AgentVersionDetails` |
| `get` | `agent_name` | `AgentDetails` |
| `get_version` | `agent_name, agent_version` | `AgentVersionDetails` |
| `update` | `agent_name, definition, metadata?, description?` | `AgentDetails` |
| `list` | `kind?, limit?, order?, before?` | `ItemPaged[AgentDetails]` |
| `list_versions` | `agent_name, limit?, order?, before?` | `ItemPaged[AgentVersionDetails]` |
| `delete` | `agent_name` | `DeleteAgentResponse` |
| `delete_version` | `agent_name, agent_version` | `DeleteAgentVersionResponse` |

### Agent Name Constraints

- Alphanumeric start/end
- Hyphens allowed in middle
- Max 63 characters

### Metadata Constraints

- Max 16 key-value pairs
- Keys max 64 characters
- Values max 512 characters

## Agent Definition Models

### PromptAgentDefinition

Standard prompt-based agents:

```python
from azure.ai.projects.models import PromptAgentDefinition

agent = project_client.agents.create_version(
    agent_name="my-agent",
    definition=PromptAgentDefinition(
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        instructions="You are a helpful assistant.",
        tools=[],  # CodeInterpreterTool, FileSearchTool, FunctionTool, etc.
    ),
)
```

### WorkflowAgentDefinition

Multi-agent workflow orchestration via YAML:

```python
from azure.ai.projects.models import WorkflowAgentDefinition

workflow = project_client.agents.create_version(
    agent_name="my-workflow",
    definition=WorkflowAgentDefinition(workflow=workflow_yaml),
)
```

### Other Definition Types

| Type | Use Case |
|---|---|
| `HostedAgentDefinition` | Hosted agent configurations |
| `ImageBasedHostedAgentDefinition` | Image-based hosted agents |
| `ContainerAppAgentDefinition` | Container App backed agents |

## AgentKind Enum

```python
from azure.ai.projects.models import AgentKind

# Filter by kind
agents = project_client.agents.list(kind=AgentKind.PROMPT)
```

| Value | Description |
|---|---|
| `PROMPT` | Standard prompt-based agents |
| `HOSTED` | Hosted agents |
| `CONTAINER_APP` | Container App agents |
| `WORKFLOW` | Workflow agents |

## Conversations (replaces Threads in v2)

```python
# Create conversation with initial message
conversation = openai_client.conversations.create(
    items=[{"type": "message", "role": "user", "content": "Hello!"}],
)

# Add follow-up messages
openai_client.conversations.items.create(
    conversation_id=conversation.id,
    items=[{"type": "message", "role": "user", "content": "Follow-up"}],
)

# Run agent on conversation
response = openai_client.responses.create(
    conversation=conversation.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    input="",
)

# Retrieve conversation
conversation = openai_client.conversations.retrieve(conversation_id=conversation.id)

# Delete conversation
openai_client.conversations.delete(conversation_id=conversation.id)
```

## Responses (replaces Runs in v2)

Two modes:

### With Conversation

```python
response = openai_client.responses.create(
    conversation=conversation.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    input="",  # Input comes from conversation items
)
print(response.output_text)
```

### Without Conversation (Direct)

```python
response = openai_client.responses.create(
    input="What is AI?",
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
)
print(response.output_text)
```

### Multi-Turn Without Conversation

```python
r1 = openai_client.responses.create(
    input="What is France's size?",
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
)
r2 = openai_client.responses.create(
    input="And its capital?",
    previous_response_id=r1.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
)
```

## Streaming

```python
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
            print(f"\nDone: {event.response.output_text}")
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
        instructions="Extract event info as JSON.",
    ),
)
```

## Complete Lifecycle Example

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
    # Create agent
    agent = project_client.agents.create_version(
        agent_name="my-agent",
        definition=PromptAgentDefinition(
            model=model,
            instructions="You are a helpful assistant.",
        ),
    )

    # Create conversation
    conversation = openai_client.conversations.create(
        items=[{"type": "message", "role": "user", "content": "Hello!"}],
    )

    # Get response
    response = openai_client.responses.create(
        conversation=conversation.id,
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
        input="",
    )
    print(response.output_text)

    # Cleanup
    openai_client.conversations.delete(conversation_id=conversation.id)
    project_client.agents.delete_version(
        agent_name=agent.name, agent_version=agent.version
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

        await openai_client.conversations.delete(conversation_id=conversation.id)
        await project_client.agents.delete_version(
            agent_name=agent.name, agent_version=agent.version
        )

asyncio.run(main())
```

## Multi-Agent Workflows

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

# Define workflow YAML
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

### YAML Action Kinds

| Kind | Description |
|---|---|
| `SetVariable` | Set a local variable |
| `CreateConversation` | Create a new conversation |
| `InvokeAzureAgent` | Invoke an agent |
| `ConditionGroup` | Conditional branching |
| `GotoAction` | Jump to another action |
| `EndConversation` | End the workflow |
| `SendActivity` | Send an activity |
