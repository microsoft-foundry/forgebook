# Responses API Reference — azure-ai-projects v2.0.0b3

## Overview

The Responses API is accessed via the OpenAI client from `project_client.get_openai_client()`. It replaces the v1 "runs" pattern. Supports standalone model calls and agent-based conversations.

## `responses.create()`

```python
openai_client.responses.create(
    input: str | list[dict],                  # Required. User input or message list.
    model: str = None,                        # Model deployment (not needed with agent ref).
    instructions: str = None,                 # System instructions.
    conversation: str = None,                 # Conversation ID (for agent flows).
    previous_response_id: str = None,         # Chain responses for multi-turn.
    stream: bool = False,                     # Enable streaming.
    temperature: float = None,
    top_p: float = None,
    max_output_tokens: int = None,
    store: bool = None,                       # Store response server-side.
    metadata: dict[str, str] = None,
    tools: list[dict] = None,
    tool_choice: str | dict = None,           # "auto", "none", "required", or specific.
    text: dict = None,                        # Structured output config.
    extra_body: dict = None,                  # Agent reference, etc.
) -> Response
```

## Other Methods

```python
# Alternative streaming (streaming is implicit)
openai_client.responses.stream(...) -> ResponseStreamManager

# Retrieve a response
openai_client.responses.retrieve(response_id) -> Response

# Delete a response
openai_client.responses.delete(response_id) -> None

# List input items
openai_client.responses.input_items.list(response_id) -> SyncCursorPage
```

## Response Object

| Property | Type | Description |
|---|---|---|
| `id` | `str` | Unique response ID |
| `status` | `str` | `"completed"`, `"incomplete"`, `"failed"`, `"in_progress"` |
| `output` | `list` | Output items (messages, function calls, etc.) |
| `output_text` | `str` | Concatenated text from all output messages |
| `usage` | `ResponseUsage` | `.input_tokens`, `.output_tokens`, `.total_tokens` |
| `previous_response_id` | `str \| None` | Previous response in chain |
| `model` | `str` | Model used |

## Input Formats

### Simple String

```python
response = openai_client.responses.create(model=model, input="What is AI?")
```

### Message List

```python
response = openai_client.responses.create(
    model=model,
    input=[{"role": "user", "content": "Tell me about Paris"}],
)
```

### Multi-Modal (Image)

```python
response = openai_client.responses.create(
    model=model,
    input=[{
        "type": "message",
        "role": "user",
        "content": [
            {"type": "input_text", "text": "What's in this image?"},
            {"type": "input_image", "detail": "auto", "image_url": f"data:image/png;base64,{b64}"},
        ],
    }],
)
```

### Function Call Output

```python
from openai.types.responses.response_input_param import FunctionCallOutput, ResponseInputParam

input_list: ResponseInputParam = [
    FunctionCallOutput(
        type="function_call_output",
        call_id=item.call_id,
        output=json.dumps({"result": "value"}),
    )
]
response = openai_client.responses.create(
    input=input_list,
    previous_response_id=response.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
)
```

## Output Item Types

| `item.type` | Description | Key Properties |
|---|---|---|
| `"message"` | Text message | `.content[].text`, `.role` |
| `"function_call"` | Function call request | `.name`, `.arguments`, `.call_id` |
| `"file_search_call"` | File search | `.results` |
| `"web_search_call"` | Web search | `.status` |
| `"code_interpreter_call"` | Code interpreter | `.code`, `.results` |
| `"mcp_call"` | MCP tool call | `.name`, `.arguments` |
| `"mcp_approval_request"` | MCP approval needed | `.id`, `.name`, `.server_label` |
| `"image_generation_call"` | Image generation | `.result` |
| `"reasoning"` | Reasoning trace | `.summary` |

## Multi-Turn Patterns

### With `previous_response_id` (No Conversation)

```python
r1 = openai_client.responses.create(model=model, input="What is France's size?")
r2 = openai_client.responses.create(
    model=model, input="And its capital?", previous_response_id=r1.id
)
```

### With Conversations (Agent-Based)

```python
conversation = openai_client.conversations.create(
    items=[{"type": "message", "role": "user", "content": "Hello!"}],
)

response = openai_client.responses.create(
    conversation=conversation.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    input="",  # Input comes from conversation items
)

# Add follow-up
openai_client.conversations.items.create(
    conversation_id=conversation.id,
    items=[{"type": "message", "role": "user", "content": "Follow-up"}],
)
response = openai_client.responses.create(
    conversation=conversation.id,
    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    input="",
)
```

## Streaming

### Method 1: `create(stream=True)`

```python
with openai_client.responses.create(
    model=model,
    input="Tell me about France",
    stream=True,
) as stream:
    for event in stream:
        if event.type == "response.output_text.delta":
            print(event.delta, end="", flush=True)
        elif event.type == "response.completed":
            print(f"\nDone: {event.response.output_text}")
```

### Method 2: `responses.stream()`

```python
with openai_client.responses.stream(
    model=model,
    input="Tell me about France",
) as stream:
    for event in stream:
        if event.type == "response.output_text.delta":
            print(event.delta, end="", flush=True)
```

### Streaming with Agent

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
```

## Streaming Event Types

### Core Events

| Event | Description |
|---|---|
| `response.created` | Response created |
| `response.in_progress` | Processing started |
| `response.completed` | Fully completed — `event.response` |
| `response.failed` | Failed |
| `response.incomplete` | Ended incomplete |

### Text Output

| Event | Description |
|---|---|
| `response.output_text.delta` | Text chunk — `event.delta` |
| `response.output_text.done` | Text complete |
| `response.output_item.added` | Output item added |
| `response.output_item.done` | Output item complete |

### Function Calls

| Event | Description |
|---|---|
| `response.function_call_arguments.delta` | Arguments streaming |
| `response.function_call_arguments.done` | Arguments complete |

### Tool Calls

| Event | Description |
|---|---|
| `response.file_search_call.in_progress/searching/completed` | File search |
| `response.web_search_call.in_progress/searching/completed` | Web search |
| `response.code_interpreter_call.in_progress/interpreting/completed` | Code interpreter |
| `response.image_generation_call.in_progress/generating/completed` | Image gen |
| `response.mcp_call.in_progress/completed/failed` | MCP tools |

### Reasoning

| Event | Description |
|---|---|
| `response.reasoning.delta` | Reasoning content |
| `response.reasoning_summary_text.delta` | Summary text chunk |

## Structured Output

### Without Agent

```python
from pydantic import BaseModel

class Event(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    date: str
    participants: list[str]

response = openai_client.responses.create(
    model=model,
    instructions="Extract event info as JSON.",
    text={
        "format": {
            "type": "json_schema",
            "name": "Event",
            "schema": Event.model_json_schema(),
        }
    },
    input="Alice and Bob are going to a fair on Friday.",
)
```

### With Agent

```python
from azure.ai.projects.models import (
    PromptAgentDefinition,
    PromptAgentDefinitionText,
    ResponseTextFormatConfigurationJsonSchema,
)

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

## Key Patterns

- **Agent reference via `extra_body`**: `extra_body={"agent": {"name": agent.name, "type": "agent_reference"}}`
- **Empty `input` with conversations**: When using conversations with agents, pass `input=""`.
- **Function call loop**: Get function_call items → execute locally → send `FunctionCallOutput` with `previous_response_id`.
- **`FunctionCallOutput`** imported from `openai.types.responses.response_input_param`.
