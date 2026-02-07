# Fine-Tuning Reference — azure-ai-projects v2.0.0b3

## Architecture

Fine-tuning uses the **OpenAI client** from `project_client.get_openai_client()`. There is no custom fine-tuning operations client — all operations go through `openai_client.fine_tuning.jobs` and `openai_client.files`.

## Installation

```bash
pip install "azure-ai-projects>=2.0.0b3" azure-identity python-dotenv
# For deployment of fine-tuned models:
pip install azure-mgmt-cognitiveservices
```

## File Upload

```python
# Upload training data
with open("training_data.jsonl", "rb") as f:
    training_file = openai_client.files.create(file=f, purpose="fine-tune")

# Wait for processing
openai_client.files.wait_for_processing(training_file.id)
```

## Training Data Formats

### Supervised Fine-Tuning (SFT)

```jsonl
{"messages": [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "What is AI?"}, {"role": "assistant", "content": "AI is artificial intelligence."}]}
```

### Direct Preference Optimization (DPO)

```jsonl
{"input": {"messages": [{"role": "user", "content": "Explain AI"}]}, "preferred_output": [{"role": "assistant", "content": "AI is..."}], "non_preferred_output": [{"role": "assistant", "content": "I don't know"}]}
```

### Reinforcement Fine-Tuning (RFT)

```jsonl
{"messages": [{"role": "system", "content": "Solve the problem."}, {"role": "user", "content": "What is 2+2?"}], "target": "4", "nums": [2, 2]}
```

## Creating Fine-Tuning Jobs

### SFT (Supervised)

Models: GPT-4o, GPT-4o-mini, GPT-4.1, GPT-4.1-mini

```python
job = openai_client.fine_tuning.jobs.create(
    model=os.environ["MODEL_NAME"],
    training_file=training_file.id,
    method={
        "type": "supervised",
        "supervised": {
            "hyperparameters": {
                "n_epochs": 3,
                "batch_size": 1,
                "learning_rate_multiplier": 1.0,
            }
        },
    },
)
```

### DPO (Direct Preference Optimization)

Models: GPT-4o, GPT-4.1, GPT-4.1-mini, GPT-4.1-nano, GPT-4o-mini

```python
job = openai_client.fine_tuning.jobs.create(
    model=os.environ["MODEL_NAME"],
    training_file=training_file.id,
    method={
        "type": "dpo",
        "dpo": {
            "hyperparameters": {
                "n_epochs": 3,
                "batch_size": 1,
                "learning_rate_multiplier": 1.0,
            }
        },
    },
)
```

### RFT (Reinforcement)

Models: o4-mini

```python
job = openai_client.fine_tuning.jobs.create(
    model=os.environ["MODEL_NAME"],
    training_file=training_file.id,
    method={
        "type": "reinforcement",
        "reinforcement": {
            "grader": {
                "type": "score_model",
                "name": "grader",
                "model": "o3-mini",
                "input": [
                    {"role": "user", "content": "Grade the answer: {{item.target}} vs {{sample.output_text}}"},
                ],
            },
            "hyperparameters": {
                "n_epochs": 3,
                "eval_interval": 5,
                "eval_samples": 10,
                "reasoning_effort": "medium",
            },
        },
    },
)
```

### Training Types

Pass via `extra_body`:

```python
job = openai_client.fine_tuning.jobs.create(
    model=model,
    training_file=training_file.id,
    method={"type": "supervised", "supervised": {"hyperparameters": {"n_epochs": 3}}},
    extra_body={"trainingType": "Standard"},  # "Standard", "GlobalStandard", or "DeveloperTier"
)
```

| Type | Description |
|---|---|
| `"Standard"` | Default training type |
| `"GlobalStandard"` | Cross-region, cost savings for OSS models |
| `"DeveloperTier"` | Developer tier pricing |

## Job Management

```python
# Retrieve job status
job = openai_client.fine_tuning.jobs.retrieve(job.id)
print(job.status)  # "validating_files", "queued", "running", "succeeded", "failed", "cancelled"

# List all jobs
for job in openai_client.fine_tuning.jobs.list():
    print(job.id, job.status)

# Cancel a job
openai_client.fine_tuning.jobs.cancel(job.id)

# Pause/Resume
openai_client.fine_tuning.jobs.pause(job.id)
openai_client.fine_tuning.jobs.resume(job.id)

# List events
for event in openai_client.fine_tuning.jobs.list_events(job.id):
    print(event.created_at, event.level, event.message)

# List checkpoints
for checkpoint in openai_client.fine_tuning.jobs.checkpoints.list(job.id):
    print(checkpoint.id, checkpoint.step_number)
```

### Job Properties

| Property | Description |
|---|---|
| `id` | Job ID |
| `status` | Job status |
| `training_file` | Training file ID |
| `validation_file` | Validation file ID (optional) |
| `method.type` | `"supervised"`, `"dpo"`, or `"reinforcement"` |
| `fine_tuned_model` | Output model name (set when succeeded) |
| `model` | Base model name |
| `created_at` | Creation timestamp |

## Deployment of Fine-Tuned Models

Uses `azure-mgmt-cognitiveservices` (separate package):

```python
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.mgmt.cognitiveservices.models import Deployment, DeploymentProperties, DeploymentModel, Sku

mgmt_client = CognitiveServicesManagementClient(credential, subscription_id)

deployment = Deployment(
    properties=DeploymentProperties(
        model=DeploymentModel(
            name=job.fine_tuned_model,
            format="OpenAI",
            version="1",
        ),
    ),
    sku=Sku(name="Standard", capacity=1),
)

mgmt_client.deployments.begin_create_or_update(
    resource_group_name=resource_group,
    account_name=account_name,
    deployment_name="my-finetuned-deployment",
    deployment=deployment,
).result()
```

## Inference with Fine-Tuned Model

```python
response = openai_client.chat.completions.create(
    model="my-finetuned-deployment",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
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
        with open("training_data.jsonl", "rb") as f:
            training_file = await openai_client.files.create(file=f, purpose="fine-tune")
        await openai_client.files.wait_for_processing(training_file.id)

        job = await openai_client.fine_tuning.jobs.create(
            model=model,
            training_file=training_file.id,
            method={"type": "supervised", "supervised": {"hyperparameters": {"n_epochs": 3}}},
        )

        job = await openai_client.fine_tuning.jobs.retrieve(job.id)
        print(job.status)

        await openai_client.files.delete(training_file.id)

asyncio.run(main())
```
