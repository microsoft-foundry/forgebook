# Deployments Reference — azure-ai-projects v2.0.0b3

## DeploymentsOperations

Accessed via `project_client.deployments`. Read-only — list and get model deployments.

### Methods

| Method | Signature | Returns |
|---|---|---|
| `get` | `get(name)` | `Deployment` |
| `list` | `list(*, model_publisher=None, model_name=None, deployment_type=None)` | `ItemPaged[Deployment]` |

## Models

### ModelDeployment

Subclass of `Deployment`. All fields are read-only.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Deployment name |
| `type` | `str \| DeploymentType` | Always `"ModelDeployment"` |
| `model_name` | `str` | Model name (e.g., `"gpt-4o"`) |
| `model_version` | `str` | Model version |
| `model_publisher` | `str` | Publisher (e.g., `"OpenAI"`) |
| `capabilities` | `dict[str, str]` | Model capabilities |
| `sku` | `ModelDeploymentSku` | SKU details |
| `connection_name` | `str \| None` | Associated connection |

### ModelDeploymentSku

| Field | Type |
|---|---|
| `capacity` | `int` |
| `family` | `str` |
| `name` | `str` |
| `tier` | `str` |

### DeploymentType Enum

```python
from azure.ai.projects.models import DeploymentType

# Currently one value:
DeploymentType.MODEL_DEPLOYMENT  # "ModelDeployment"
```

## Usage Examples

### List All Deployments

```python
for deployment in project_client.deployments.list():
    print(f"{deployment.name}: {deployment.model_name} ({deployment.model_publisher})")
```

### Filter Deployments

```python
from azure.ai.projects.models import DeploymentType

# By publisher
for d in project_client.deployments.list(model_publisher="OpenAI"):
    print(f"{d.name}: {d.model_name}")

# By model name
for d in project_client.deployments.list(model_name="gpt-4o"):
    print(f"{d.name}: v{d.model_version}")

# By type
for d in project_client.deployments.list(deployment_type=DeploymentType.MODEL_DEPLOYMENT):
    print(d.name)
```

### Get Deployment Details

```python
from azure.ai.projects.models import ModelDeployment

deployment = project_client.deployments.get("gpt-4o-mini")

if isinstance(deployment, ModelDeployment):
    print(f"Model: {deployment.model_name} v{deployment.model_version}")
    print(f"Publisher: {deployment.model_publisher}")
    print(f"SKU: {deployment.sku.name} (capacity: {deployment.sku.capacity})")
    print(f"Capabilities: {deployment.capabilities}")
    if deployment.connection_name:
        print(f"Connection: {deployment.connection_name}")
```

### Dynamic Model Selection

```python
from azure.ai.projects.models import PromptAgentDefinition

gpt4_deployments = [
    d for d in project_client.deployments.list()
    if "gpt-4" in d.model_name.lower()
]

if gpt4_deployments:
    agent = project_client.agents.create_version(
        agent_name="dynamic-agent",
        definition=PromptAgentDefinition(
            model=gpt4_deployments[0].name,
            instructions="You are helpful.",
        ),
    )
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
        async for d in project_client.deployments.list():
            print(f"{d.name}: {d.model_name}")

        deployment = await project_client.deployments.get("gpt-4o")
        print(deployment.model_version)

asyncio.run(main())
```
