# Evaluation Reference — azure-ai-projects v2.0.0b3

## Architecture

Evaluations use **two clients** together:
1. **AIProjectClient** — `project_client.evaluators`, `.evaluation_rules`, `.evaluation_taxonomies`, `.insights`, `.schedules`
2. **OpenAI Client** — `openai_client.evals.create()`, `.runs.create()`, `.runs.retrieve()`, `.runs.output_items.list()`, `.delete()`

## Testing Criteria (Evaluators)

```python
testing_criteria = [
    {
        "type": "azure_ai_evaluator",
        "name": "display_name",
        "evaluator_name": "builtin.<name>",
        "evaluator_version": "optional_version",
        "initialization_parameters": {"deployment_name": "gpt-4o"},  # optional
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_text}}",
        },
    },
]
```

### Built-in Evaluators

#### Safety

| Name | Description |
|---|---|
| `builtin.violence` | Detects violent content |
| `builtin.sexual` | Detects sexual content |
| `builtin.self_harm` | Detects self-harm content |
| `builtin.hate_unfairness` | Detects hate/unfairness |
| `builtin.prohibited_actions` | Detects prohibited actions |
| `builtin.sensitive_data_leakage` | Detects sensitive data leaks |

#### Quality

| Name | Description |
|---|---|
| `builtin.coherence` | Logical coherence |
| `builtin.fluency` | Response fluency |
| `builtin.groundedness` | Factual grounding |
| `builtin.relevance` | Response relevance |
| `builtin.f1_score` | F1 score comparison |
| `builtin.task_adherence` | Instruction following |
| `builtin.task_completion` | Task completion |
| `builtin.task_navigation_efficiency` | Navigation efficiency |

#### Agentic

| Name | Description |
|---|---|
| `builtin.tool_call_accuracy` | Tool call correctness |
| `builtin.tool_input_accuracy` | Tool input correctness |
| `builtin.tool_output_utilization` | Tool output usage |
| `builtin.tool_selection` | Correct tool selection |

## Create and Run Evaluation

### Agent Evaluation

```python
from azure.ai.projects.models import PromptAgentDefinition

# Create agent
agent = project_client.agents.create_version(
    agent_name="eval-agent",
    definition=PromptAgentDefinition(
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        instructions="Answer questions concisely.",
    ),
)

# Define data source config
data_source_config = {
    "type": "custom",
    "item_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    "include_sample_schema": True,
}

# Define testing criteria
testing_criteria = [
    {
        "type": "azure_ai_evaluator",
        "name": "fluency",
        "evaluator_name": "builtin.fluency",
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_text}}",
        },
    },
    {
        "type": "azure_ai_evaluator",
        "name": "relevance",
        "evaluator_name": "builtin.relevance",
        "data_mapping": {
            "query": "{{item.query}}",
            "response": "{{sample.output_text}}",
        },
    },
]

# Create evaluation
eval_obj = openai_client.evals.create(
    name="Agent Quality",
    data_source_config=data_source_config,
    testing_criteria=testing_criteria,
)

# Run evaluation against agent
data_source = {
    "type": "azure_ai_target_completions",
    "source": {
        "type": "file_content",
        "content": [
            {"item": {"query": "What is 2+2?"}},
            {"item": {"query": "Who wrote Romeo and Juliet?"}},
        ],
    },
    "input_messages": {
        "type": "template",
        "template": [
            {
                "type": "message",
                "role": "user",
                "content": {"type": "input_text", "text": "{{item.query}}"},
            }
        ],
    },
    "target": {
        "type": "azure_ai_agent",
        "name": agent.name,
        "version": agent.version,
    },
}

eval_run = openai_client.evals.runs.create(
    eval_id=eval_obj.id,
    name="Test Run",
    data_source=data_source,
)
print(f"Run: {eval_run.id}, Status: {eval_run.status}")
```

### Model Evaluation (without Agent)

```python
data_source = {
    "type": "azure_ai_target_completions",
    "source": {
        "type": "file_content",
        "content": [{"item": {"query": "What is AI?"}}],
    },
    "input_messages": {
        "type": "template",
        "template": [
            {
                "type": "message",
                "role": "user",
                "content": {"type": "input_text", "text": "{{item.query}}"},
            }
        ],
    },
    "target": {
        "type": "azure_ai_model",
        "model": os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        "sampling_params": {"temperature": 0.7, "max_tokens": 500},
    },
}
```

### Inline Data Evaluation

```python
from openai.types.evals.create_eval_jsonl_run_data_source_param import (
    CreateEvalJSONLRunDataSourceParam,
    SourceFileContent,
    SourceFileContentContent,
)

data_source = CreateEvalJSONLRunDataSourceParam(
    type="jsonl",
    source=SourceFileContent(
        type="file_content",
        content=[
            SourceFileContentContent(
                item={"query": "What is AI?", "response": "Artificial intelligence is..."}
            ),
        ],
    ),
)
```

## EvaluatorsOperations

Accessed via `project_client.evaluators`.

| Method | Signature | Returns |
|---|---|---|
| `list_latest_versions` | `list_latest_versions(*, type=None, limit=None)` | `ItemPaged[EvaluatorVersion]` |
| `list_versions` | `list_versions(name, *, type=None, limit=None)` | `ItemPaged[EvaluatorVersion]` |
| `get_version` | `get_version(name, version)` | `EvaluatorVersion` |
| `create_version` | `create_version(name, evaluator_version)` | `EvaluatorVersion` |
| `update_version` | `update_version(name, version, evaluator_version)` | `EvaluatorVersion` |
| `delete_version` | `delete_version(name, version)` | `None` |

### Custom Evaluator (Prompt-Based)

```python
from azure.ai.projects.models import (
    EvaluatorVersion,
    PromptBasedEvaluatorDefinition,
    EvaluatorMetric,
    EvaluatorMetricType,
    EvaluatorMetricDirection,
)

evaluator = project_client.evaluators.create_version(
    name="custom-quality",
    evaluator_version=EvaluatorVersion(
        display_name="Custom Quality Evaluator",
        definition=PromptBasedEvaluatorDefinition(
            prompt_text="Rate the quality of this response on a scale of 1-5...",
            init_parameters={"deployment_name": "gpt-4o"},
        ),
        metrics=[
            EvaluatorMetric(
                type=EvaluatorMetricType.ORDINAL,
                desirable_direction=EvaluatorMetricDirection.INCREASE,
                min_value=1,
                max_value=5,
                is_primary=True,
            )
        ],
    ),
)
```

### Custom Evaluator (Code-Based)

```python
from azure.ai.projects.models import (
    EvaluatorVersion,
    CodeBasedEvaluatorDefinition,
)

evaluator = project_client.evaluators.create_version(
    name="length-check",
    evaluator_version=EvaluatorVersion(
        display_name="Response Length Check",
        definition=CodeBasedEvaluatorDefinition(
            code_text="""
def evaluate(response: str) -> dict:
    length = len(response)
    return {"score": min(length / 100, 1.0)}
""",
        ),
    ),
)
```

## EvaluationRulesOperations

Accessed via `project_client.evaluation_rules`. For continuous evaluation.

| Method | Returns |
|---|---|
| `create_or_update(id, evaluation_rule)` | `EvaluationRule` |
| `get(id)` | `EvaluationRule` |
| `list(*, action_type?, agent_name?, enabled?)` | `ItemPaged[EvaluationRule]` |
| `delete(id)` | `None` |

## SchedulesOperations

Accessed via `project_client.schedules`. For scheduled evaluations.

| Method | Returns |
|---|---|
| `create_or_update(id, schedule)` | `Schedule` |
| `get(id)` | `Schedule` |
| `list()` | `ItemPaged[Schedule]` |
| `delete(id)` | `None` |
| `list_runs(id)` | `ItemPaged[ScheduleRun]` |

## InsightsOperations

Accessed via `project_client.insights`. For evaluation comparison and analysis.

| Method | Returns |
|---|---|
| `generate(insight)` | `Insight` |
| `get(id, *, include_coordinates?)` | `Insight` |
| `list(*, type?, eval_id?, run_id?, agent_name?, include_coordinates?)` | `ItemPaged[Insight]` |

## Red Team Evaluation

```python
data_source = {
    "type": "azure_ai_red_team",
    "item_generation_params": {
        "attack_strategies": ["jailbreak", "crescendo"],
        "num_turns": 3,
    },
    "source": {
        "type": "azure_ai_source",
        "scenario": "red_team",
    },
}
```

## Key Patterns

- **Two clients required**: `AIProjectClient` for evaluator management, `openai_client` for eval runs.
- **Data mapping**: Use `{{item.field}}` for input data, `{{sample.output_text}}` for model/agent output.
- **Target types**: `azure_ai_agent` (with `name`, `version`) or `azure_ai_model` (with `model`, `sampling_params`).
- **Evaluator types**: `"builtin"`, `"custom"`, `"all"` (for filtering `list_latest_versions`).
