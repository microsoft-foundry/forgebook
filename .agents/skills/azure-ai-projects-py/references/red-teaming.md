# Red Teaming Reference — azure-ai-projects v2.0.0b3

## Overview

Red teaming is a **service-side** API that submits adversarial scans to Azure AI Foundry. Access via `project_client.red_teams` (`RedTeamsOperations`).

## RedTeamsOperations

| Method | Parameters | Returns |
|---|---|---|
| `create` | `red_team: RedTeam` | `RedTeam` |
| `get` | `name: str` | `RedTeam` |
| `list` | (none) | `ItemPaged[RedTeam]` |

## RedTeam Model

| Property | Type | Read-Only |
|---|---|---|
| `name` | `str` | Yes |
| `display_name` | `str` | No |
| `description` | `str` | No |
| `status` | `str` | Yes |
| `target` | `AzureOpenAIModelConfiguration` | No |
| `risk_categories` | `list[RiskCategory]` | No |
| `attack_strategies` | `list[AttackStrategy]` | No |
| `num_turns` | `int` | No |
| `simulation_count` | `int` | No |
| `properties` | `dict` | Yes |
| `system_data` | `dict` | Yes |

## AzureOpenAIModelConfiguration

```python
from azure.ai.projects.models import AzureOpenAIModelConfiguration

# Option 1: Connection-based (recommended)
target = AzureOpenAIModelConfiguration(
    model_deployment_name="connection_name/deployment_name",
)

# Option 2: Direct model with headers
target = AzureOpenAIModelConfiguration(
    model_deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
)
# Pass headers for direct auth:
# headers={"model-endpoint": ..., "model-api-key": ...}
```

## AttackStrategy Enum

### Meta-Strategies (select subsets)

| Value | Description |
|---|---|
| `EASY` | Easy complexity strategies |
| `MODERATE` | Moderate complexity strategies |
| `DIFFICULT` | Difficult complexity strategies |

### Encoding-Based

| Value | Description |
|---|---|
| `BASE64` | Base64 encoding |
| `FLIP` | Text flipping |
| `MORSE_CODE` | Morse code encoding |
| `BINARY` | Binary encoding |
| `ROT13` | ROT13 cipher |
| `UNICODE_TAGS` | Unicode tag encoding |
| `UNICODE_CONFUSABLE` | Unicode confusable characters |
| `CAESAR_CIPHER` | Caesar cipher |
| `LEETSPEAK` | Leetspeak substitution |
| `ATBASH` | Atbash cipher |
| `MATH_PROMPT` | Math prompt obfuscation |
| `DIACRITICS` | Diacritic substitution |

### LLM-Based

| Value | Description |
|---|---|
| `JAILBREAK` | Jailbreak prompts |
| `CRESCENDO` | Crescendo escalation |
| `COMPOSE_INFILLING` | Compose infilling |
| `SUFFIX_APPEND` | Suffix appending |

### Multi-Turn

| Value | Description |
|---|---|
| `MULTI_TURN` | Multi-turn conversation attacks |
| `TENSE` | Tense manipulation |

## RiskCategory Enum

| Value | String |
|---|---|
| `VIOLENCE` | `"Violence"` |
| `HATE_UNFAIRNESS` | `"HateUnfairness"` |
| `SEXUAL` | `"Sexual"` |
| `SELF_HARM` | `"SelfHarm"` |
| `PROTECTED_MATERIAL_IP` | `"ProtectedMaterialIP"` |
| `PROTECTED_MATERIAL_CODE` | `"ProtectedMaterialCode"` |
| `UNGROUNDED_CONTENT` | `"UngroundedContent"` |
| `DIRECT_ATTACK` | `"DirectAttack"` |
| `INDIRECT_ATTACK` | `"IndirectAttack"` |
| `XPIA` | `"XPIA"` |

## Usage Example

```python
import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    RedTeam,
    AzureOpenAIModelConfiguration,
    AttackStrategy,
    RiskCategory,
)

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
):
    # Create red team scan
    red_team = project_client.red_teams.create(
        red_team=RedTeam(
            display_name="Safety Test",
            target=AzureOpenAIModelConfiguration(
                model_deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            ),
            risk_categories=[
                RiskCategory.VIOLENCE,
                RiskCategory.HATE_UNFAIRNESS,
                RiskCategory.SEXUAL,
                RiskCategory.SELF_HARM,
            ],
            attack_strategies=[
                AttackStrategy.EASY,
                AttackStrategy.JAILBREAK,
            ],
            num_turns=3,
            simulation_count=10,
        ),
    )
    print(f"Created: {red_team.name}, Status: {red_team.status}")

    # Poll for completion
    import time
    while True:
        red_team = project_client.red_teams.get(name=red_team.name)
        print(f"Status: {red_team.status}")
        if red_team.status in ("Completed", "Failed"):
            break
        time.sleep(30)

    # List all red team scans
    for rt in project_client.red_teams.list():
        print(f"{rt.name}: {rt.status}")
```

## Async Pattern

```python
import asyncio
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import (
    RedTeam, AzureOpenAIModelConfiguration, AttackStrategy, RiskCategory,
)

async def main():
    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        red_team = await project_client.red_teams.create(
            red_team=RedTeam(
                display_name="Safety Test",
                target=AzureOpenAIModelConfiguration(
                    model_deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
                ),
                risk_categories=[RiskCategory.VIOLENCE, RiskCategory.HATE_UNFAIRNESS],
                attack_strategies=[AttackStrategy.EASY],
                num_turns=3,
                simulation_count=5,
            ),
        )

        red_team = await project_client.red_teams.get(name=red_team.name)
        print(red_team.status)

        async for rt in project_client.red_teams.list():
            print(rt.name, rt.status)

asyncio.run(main())
```
