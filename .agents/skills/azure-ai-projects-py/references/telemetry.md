# Telemetry Reference — azure-ai-projects v2.0.0b3

## Installation

```bash
pip install "azure-ai-projects>=2.0.0b3" azure-identity opentelemetry-sdk azure-core-tracing-opentelemetry

# For Azure Monitor export
pip install azure-monitor-opentelemetry

# For OTLP export (Aspire Dashboard, Jaeger, etc.)
pip install opentelemetry-exporter-otlp
```

## Public API

```python
from azure.ai.projects.telemetry import AIProjectInstrumentor, trace_function
```

### AIProjectInstrumentor

Enables/disables OpenTelemetry trace instrumentation for Agents API and OpenAI Responses/Conversations APIs.

```python
class AIProjectInstrumentor:
    def instrument(self, enable_content_recording: Optional[bool] = None) -> None: ...
    def uninstrument(self) -> None: ...
    def is_instrumented(self) -> bool: ...
    def is_content_recording_enabled(self) -> bool: ...
```

- `enable_content_recording=True` — Capture message content, function names, parameter values in traces.
- `enable_content_recording=None` (default) — Read from env var `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`. Defaults to `False`.

### trace_function

Decorator for tracing custom function calls. Works with sync and async.

```python
from azure.ai.projects.telemetry import trace_function

@trace_function()
def get_weather(location: str) -> str:
    return f"72°F in {location}"

@trace_function(span_name="custom_name")
async def fetch_data(query: str) -> dict:
    return {"result": query}
```

Traced data: function parameters → `code.function.parameter.<name>`, return value → `code.function.return.value`, exceptions → `error.type`.

### TelemetryOperations

Accessed via `project_client.telemetry`.

```python
# Sync
connection_string = project_client.telemetry.get_application_insights_connection_string()

# Async
connection_string = await project_client.telemetry.get_application_insights_connection_string()
```

Retrieves Application Insights connection string from the project's connected resources. Raises `ResourceNotFoundError` if not found.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` | `false` | Enable content recording in traces |
| `AZURE_TRACING_GEN_AI_INSTRUMENT_RESPONSES_API` | `true` | Enable/disable Responses API instrumentation |
| `AZURE_TRACING_GEN_AI_INCLUDE_BINARY_DATA` | `false` | Include binary data in traces |

## Console Tracing Setup

```python
import os
from azure.core.settings import settings
settings.tracing_implementation = "opentelemetry"  # Set BEFORE other imports

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
from azure.ai.projects.telemetry import AIProjectInstrumentor
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)

AIProjectInstrumentor().instrument()

with tracer.start_as_current_span("my_scenario"):
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
        project_client.get_openai_client() as openai_client,
    ):
        agent = project_client.agents.create_version(
            agent_name="MyAgent",
            definition=PromptAgentDefinition(
                model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                instructions="You are a helpful assistant.",
            ),
        )
        conversation = openai_client.conversations.create()
        response = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
            input="Hello!",
        )
        print(response.output_text)
        project_client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
```

## Azure Monitor Setup

```python
from opentelemetry import trace
from azure.monitor.opentelemetry import configure_azure_monitor
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"], credential=credential) as project_client,
):
    connection_string = project_client.telemetry.get_application_insights_connection_string()
    configure_azure_monitor(connection_string=connection_string)

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("my_scenario"):
        # All operations here are traced and exported to Application Insights
        pass
```

## Traced Spans

### `create_agent` Span

From `agents.create_version`:

| Attribute | Key |
|---|---|
| Operation name | `gen_ai.operation.name` = `"create_agent"` |
| Agent name | `gen_ai.agent.name` |
| Agent ID | `gen_ai.agent.id` |
| Agent version | `gen_ai.agent.version` |
| Agent type | `gen_ai.agent.type` (`"prompt"`, `"workflow"`, `"hosted"`) |
| Model | `gen_ai.request.model` |
| Provider | `gen_ai.provider.name` = `"azure.ai.agents"` |

### `responses` Span

From `responses.create` / `.stream`:

| Attribute | Key |
|---|---|
| Operation name | `gen_ai.operation.name` = `"responses"` |
| Request model | `gen_ai.request.model` |
| Response model | `gen_ai.response.model` |
| Response ID | `gen_ai.response.id` |
| Conversation ID | `gen_ai.conversation.id` |
| Agent name | `gen_ai.agent.name` |
| Input tokens | `gen_ai.usage.input_tokens` |
| Output tokens | `gen_ai.usage.output_tokens` |
| Provider | `gen_ai.provider.name` = `"azure.openai"` |

### `create_conversation` Span

From `conversations.create`:

| Attribute | Key |
|---|---|
| Operation name | `gen_ai.operation.name` = `"create_conversation"` |
| Conversation ID | `gen_ai.conversation.id` |

## Metrics

Two histograms are automatically created:

| Metric | Unit | Description |
|---|---|---|
| `gen_ai.client.operation.duration` | seconds | Duration of GenAI operations |
| `gen_ai.client.token.usage` | tokens | Token usage with `gen_ai.token.type` = `"input"` or `"completion"` |

## Key Patterns

1. **Set `settings.tracing_implementation = "opentelemetry"` BEFORE imports** when using console tracing. Not needed with `azure-monitor-opentelemetry`.
2. **Call `AIProjectInstrumentor().instrument()` once** before any API calls.
3. **Wrap scenarios in parent spans** to group related operations.
4. **Content recording is opt-in** to protect sensitive data.
5. **Streaming responses are fully traced** — spans finalize when stream completes.
6. **Semantic conventions version**: `1.34.0`.
