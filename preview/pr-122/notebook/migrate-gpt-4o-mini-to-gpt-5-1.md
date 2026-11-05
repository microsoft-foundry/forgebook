## Overview

Moving a working app from `gpt-4o-mini` to `gpt-5.1` is mostly a *code* change, not a prompt change. `gpt-5.1` is a reasoning model, so the request shape is different: a few Chat Completions parameters were renamed, some sampling knobs are no longer accepted, and there are new controls (`reasoning_effort`, `verbosity`) plus a new token category (`reasoning_tokens`) to account for.

One nuance makes `gpt-5.1` a friendly target for `gpt-4o-mini` users: its `reasoning_effort` defaults to `none`. Left at the default it behaves like a fast, low-latency chat model — close to what you had — and you dial reasoning up only where a task needs it.

This recipe walks the exact code diff. It keeps your existing messages and system prompt untouched and only changes how you *call* the model. Prompt rewriting is deliberately out of scope here — use your prompt-optimization tool for that.

**Who this is for:** Developers with a `gpt-4o-mini` Chat Completions integration who want the smallest reliable code change to run on `gpt-5.1`.

**By the end, you can:**
- Map every `gpt-4o-mini` request parameter to its `gpt-5.1` equivalent.
- Replace `max_tokens` with `max_completion_tokens` and drop the parameters `gpt-5.1` rejects.
- Use `reasoning_effort` and `verbosity` to trade latency for depth, and read `reasoning_tokens` to keep cost accounting correct.
- Wrap it all in one compatibility shim so you can migrate incrementally.

**Prerequisites:**
- Azure subscription with access to Azure OpenAI in Microsoft Foundry.
- A `gpt-5.1` deployment on your resource.
- Optionally, your existing `gpt-4o-mini` deployment to compare side by side.
- Your identity has `Foundry User` (or equivalent data-plane access) on the resource.
- Azure CLI signed in locally (`az login`) if you use `DefaultAzureCredential`.
- Local environment variables:
  - `AZURE_OPENAI_ENDPOINT`, for example `https://<resource>.openai.azure.com`
  - `TARGET_DEPLOYMENT`, for example `gpt-5.1`
  - `SOURCE_DEPLOYMENT` (optional), for example `gpt-4o-mini`

**Time estimate:** ~15 minutes once the `gpt-5.1` deployment exists.

---

## Outline

1. What actually changes in the code.
2. Setup and a keyless client.
3. The "before": your existing `gpt-4o-mini` call.
4. Why a copy-paste port fails.
5. The "after": the minimal migrated call.
6. A compatibility shim for incremental migration.
7. Account for reasoning tokens in usage.
8. Optional: adopt the Responses API.

## 1. What actually changes in the code

Only the call site changes. Your `messages` list — system prompt included — stays exactly as it is. Here is the full parameter map for a Chat Completions migration:

| `gpt-4o-mini` (Chat Completions) | `gpt-5.1` | What to do |
|---|---|---|
| `max_tokens` | `max_completion_tokens` | Rename the key; the value semantics are the same output-token budget. |
| `temperature` (custom value) | not supported | Remove it. `gpt-5.1` runs at the default temperature. |
| `top_p` | not supported | Remove it. |
| `presence_penalty`, `frequency_penalty` | not supported | Remove them. |
| `logit_bias`, `logprobs`, `top_logprobs` | not supported | Remove them. |
| *(none)* | `reasoning_effort` | New. `none`, `minimal`, `low`, `medium`, `high`. On `gpt-5.1` the default is `none`, which stays closest to `gpt-4o-mini` (no reasoning tokens); raise it to turn reasoning on. |
| *(none)* | `verbosity` | New. `low`, `medium`, `high` — controls answer length without editing the prompt. |
| `usage.completion_tokens` | same, plus `completion_tokens_details.reasoning_tokens` | Hidden reasoning tokens are billed as output tokens — include them in cost math. |
| `"role": "system"` | still accepted | System messages work, so you do not have to switch to `developer` messages to migrate. |

The two client-facing shapes, side by side:

```python
# BEFORE — gpt-4o-mini
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages,
    max_tokens=800,
    temperature=0.2,
    top_p=0.9,
)

# AFTER — gpt-5.1
resp = client.chat.completions.create(
    model="gpt-5.1",
    messages=messages,            # unchanged
    max_completion_tokens=800,    # renamed from max_tokens
    reasoning_effort="none",      # default; keeps behavior closest to gpt-4o-mini
    verbosity="low",              # new knob (optional)
)
```

## 2. Setup and a keyless client

Both models are reached through the same Azure OpenAI v1 endpoint, so the client itself does not change during migration — only the deployment name you pass per call. Install the SDK and configure keyless auth with `DefaultAzureCredential`.

```python
%pip install openai azure-identity python-dotenv --quiet
```

```python
import os

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
source_deployment = os.environ.get("SOURCE_DEPLOYMENT", "")
target_deployment = os.environ.get("TARGET_DEPLOYMENT", "gpt-5.1")

if not endpoint:
    raise ValueError(
        "Set AZURE_OPENAI_ENDPOINT to your resource endpoint, for example https://<resource>.openai.azure.com"
    )

# Azure OpenAI accepts Microsoft Entra bearer tokens for this audience.
token_provider = get_bearer_token_provider(
    DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
)

client = OpenAI(
    base_url=f"{endpoint}/openai/v1/",
    api_key=token_provider,
)

print(f"Endpoint:          {endpoint}")
print(f"Source deployment: {source_deployment}")
print(f"Target deployment: {target_deployment}")
```

## 3. The "before": your existing `gpt-4o-mini` call

This is a typical `gpt-4o-mini` Chat Completions call. It uses `max_tokens` and custom sampling parameters (`temperature`, `top_p`) — all valid for `gpt-4o-mini`. Notice the `messages` list; it does not change anywhere in this recipe.

The deployment name comes from a constant, not a string literal, so switching models later is a one-line change.

```python
messages = [
    {"role": "system", "content": "You are a concise assistant for release notes."},
    {"role": "user", "content": "Summarize: we shipped SSO, fixed a billing race condition, and added dark mode."},
]


def call_gpt_4o_mini(client, deployment, messages):
    """The original call shape written for gpt-4o-mini."""
    return client.chat.completions.create(
        model=deployment,
        messages=messages,
        max_tokens=800,
        temperature=0.2,
        top_p=0.9,
    )


# Run this only if the source deployment still exists.
if source_deployment:
    before = call_gpt_4o_mini(client, source_deployment, messages)
    print(before.choices[0].message.content)
```

## 4. Why a copy-paste port fails

**When you hit this:** you change only the `model` argument to `gpt-5.1` and rerun.

Sending the same keyword arguments to `gpt-5.1` returns a `400` because the request carries parameters the model does not accept. The two you will see first:

```text
Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.
Unsupported value: 'temperature' does not support 0.2 with this model. Only the default (1) value is supported.
```

So the migration is mechanical: rename `max_tokens`, and remove the sampling parameters `gpt-5.1` rejects. Run the next cell to see that `400` firsthand; then section 5 shows the finished shape.

```python
# Demonstrate the failure: send the gpt-4o-mini call shape unchanged to gpt-5.1.
# call_gpt_4o_mini() is the exact function from section 3 -- only the deployment changes.
from openai import BadRequestError

try:
    naive = call_gpt_4o_mini(client, target_deployment, messages)
    print(naive.choices[0].message.content)
except BadRequestError as err:
    print("gpt-5.1 rejected the gpt-4o-mini call shape:")
    print(err)

```

## 5. The "after": the minimal migrated call

**What changed:** `max_tokens` became `max_completion_tokens`; `temperature` and `top_p` are gone; `reasoning_effort` and `verbosity` are added as optional controls. The `messages` list is byte-for-byte identical to the `gpt-4o-mini` version.

**How to adapt:** `gpt-5.1` defaults `reasoning_effort` to `none`. For the closest latency match to `gpt-4o-mini`, leave it at `none` (or omit it) and raise it (`low` → `medium` → `high`) only on tasks that need deeper reasoning. Lower `verbosity` to keep answers short without touching the prompt.

```python
def call_gpt_5_1(client, deployment, messages):
    """The same request, migrated to gpt-5.1."""
    return client.chat.completions.create(
        model=deployment,
        messages=messages,                 # unchanged from gpt-4o-mini
        max_completion_tokens=800,         # renamed from max_tokens
        reasoning_effort="none",            # none | minimal | low | medium | high (default: none)
        verbosity="low",                   # low | medium | high
    )


after = call_gpt_5_1(client, target_deployment, messages)
print(after.choices[0].message.content)
```

## 6. A compatibility shim for incremental migration

**When to use:** you cannot flip every call site at once, or you route the same request to `gpt-4o-mini` and `gpt-5.1` behind a flag.

**What it does:** the caller always passes a plain output-token budget plus optional `reasoning_effort` / `verbosity`. The shim translates those into the right keyword arguments for whichever model family it targets, dropping parameters the target rejects.

**How to adapt:** this helper deliberately targets `gpt-5.1`, whose `none` effort and `verbosity` controls it uses. Add an explicit capability entry before routing another model family through it. Keep `reasoning_effort="none"` for a low-latency default and raise it per route.

```python
GPT_5_1_PREFIXES = ("gpt-5.1",)

# Sampling parameters that gpt-5.1 rejects.
UNSUPPORTED_ON_REASONING = {
    "temperature",
    "top_p",
    "presence_penalty",
    "frequency_penalty",
    "logit_bias",
    "logprobs",
    "top_logprobs",
}


def is_gpt_5_1(deployment_family: str) -> bool:
    """Recognize the only model family this helper supports."""
    return deployment_family.lower().startswith(GPT_5_1_PREFIXES)


def build_request(
    deployment: str,
    family: str,
    messages: list,
    max_output_tokens: int,
    reasoning_effort: str = "none",
    verbosity: str = "medium",
    **legacy_params,
) -> dict:
    """Return kwargs for client.chat.completions.create for either model family."""
    request = {"model": deployment, "messages": messages}

    if is_gpt_5_1(family):
        request["max_completion_tokens"] = max_output_tokens
        request["reasoning_effort"] = reasoning_effort
        request["verbosity"] = verbosity
        # Silently drop anything gpt-5.1 would reject.
        for key, value in legacy_params.items():
            if key not in UNSUPPORTED_ON_REASONING:
                request[key] = value
    else:
        request["max_tokens"] = max_output_tokens
        request.update(legacy_params)

    return request


def call_model(client, deployment, family, messages, **kwargs):
    request = build_request(deployment, family, messages, **kwargs)
    return client.chat.completions.create(**request)


# Same caller code works for both models — only `family` differs.
response = call_model(
    client,
    target_deployment,
    family="gpt-5.1",
    messages=messages,
    max_output_tokens=800,
    reasoning_effort="none",
    verbosity="low",
    temperature=0.2,  # accepted for gpt-4o-mini, dropped for gpt-5.1
)
print(response.choices[0].message.content)
```

```python
# Credential-free checks for the reusable request translator.
gpt_5_1_request = build_request(
    deployment="target-deployment",
    family="gpt-5.1",
    messages=messages,
    max_output_tokens=800,
    reasoning_effort="minimal",
    verbosity="low",
    temperature=0.2,
    top_p=0.9,
 )
assert gpt_5_1_request["max_completion_tokens"] == 800
assert gpt_5_1_request["reasoning_effort"] == "minimal"
assert gpt_5_1_request["verbosity"] == "low"
assert "max_tokens" not in gpt_5_1_request
assert "temperature" not in gpt_5_1_request and "top_p" not in gpt_5_1_request

legacy_request = build_request(
    deployment="source-deployment",
    family="gpt-4o-mini",
    messages=messages,
    max_output_tokens=800,
    temperature=0.2,
 )
assert legacy_request["max_tokens"] == 800
assert legacy_request["temperature"] == 0.2
assert "reasoning_effort" not in legacy_request
print("Request translation checks passed.")
```

## 7. Account for reasoning tokens in usage

When `reasoning_effort` is above `none`, `gpt-5.1` spends hidden **reasoning tokens** before it writes the visible answer. They are not returned in the message content, but they are billed as output tokens and they add latency. If your dashboards or budgets only track `completion_tokens`, they were already counting reasoning tokens — but the new `completion_tokens_details.reasoning_tokens` field lets you separate thinking from output.

Because the migrated calls in this recipe use the default `none`, the breakdown below shows `0` reasoning tokens — the same as `gpt-4o-mini`. Raise `reasoning_effort` and that number climbs; turning it back down (toward `none`) is the lever if reasoning tokens dominate cost.

```python
usage = after.usage
details = usage.completion_tokens_details
reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0
visible_output_tokens = usage.completion_tokens - reasoning_tokens

print(f"Prompt tokens:          {usage.prompt_tokens}")
print(f"Completion tokens:      {usage.completion_tokens}")
print(f"  - reasoning tokens:   {reasoning_tokens}")
print(f"  - visible output:     {visible_output_tokens}")
print(f"Total tokens:           {usage.total_tokens}")
```

## 8. Optional: adopt the Responses API

Chat Completions is enough to migrate and keeps the diff tiny. If you also want the forward-looking surface for reasoning models, the Responses API exposes the same controls under slightly different names:

| Chat Completions | Responses API |
|---|---|
| `max_completion_tokens` | `max_output_tokens` |
| `reasoning_effort="none"` | `reasoning={"effort": "none"}` |
| `verbosity="low"` | `text={"verbosity": "low"}` |
| `messages=[...]` | `input=[...]` |

This is an optional second step, not part of the minimal migration.

```python
responses_result = client.responses.create(
    model=target_deployment,
    input=messages,
    max_output_tokens=800,
    reasoning={"effort": "none", "summary": "auto"},
    text={"verbosity": "low"},
)
print(responses_result.output_text)
```

## Takeaways and next steps

**What you changed in code:**
- `max_tokens` → `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses).
- Removed `temperature`, `top_p`, and the penalty / logprob / logit_bias parameters.
- Added `reasoning_effort` (default `none` on `gpt-5.1`) and `verbosity` as the new control surface.
- Started reading `completion_tokens_details.reasoning_tokens` for accurate accounting.
- Left every prompt and `messages` list untouched.

**Reusable shim to drop into your project:**

```python
GPT_5_1_PREFIXES = ("gpt-5.1",)
UNSUPPORTED_ON_GPT_5_1 = {
    "temperature", "top_p", "presence_penalty", "frequency_penalty",
    "logit_bias", "logprobs", "top_logprobs",
}

def build_request(deployment, family, messages, max_output_tokens,
                  reasoning_effort="none", verbosity="medium", **legacy):
    req = {"model": deployment, "messages": messages}
    if family.lower().startswith(GPT_5_1_PREFIXES):
        req["max_completion_tokens"] = max_output_tokens
        req["reasoning_effort"] = reasoning_effort
        req["verbosity"] = verbosity
        req.update({key: value for key, value in legacy.items()
                    if key not in UNSUPPORTED_ON_GPT_5_1})
    else:
        req["max_tokens"] = max_output_tokens
        req.update(legacy)
    return req
```

**Common failure modes:**

| Symptom | Likely cause | Fix |
|---|---|---|
| `400 Unsupported parameter: 'max_tokens'` | Left the old key in the request | Rename to `max_completion_tokens`. |
| `400 ... 'temperature' does not support 0.2` | Sent a custom sampling value | Remove `temperature` / `top_p` / penalties. |
| `400 ... 'reasoning_effort' ...` | Used an effort value unsupported by the deployed model | On `gpt-5.1`, use `none`, `minimal`, `low`, `medium`, or `high`. |
| Answers feel shallower than expected | `reasoning_effort` left at the `none` default | Raise it to `low`/`medium`/`high` for that route. |
| Cost per call jumped | Reasoning tokens counted as output | Inspect `reasoning_tokens`; lower `reasoning_effort`. |
| `401` from the client | Wrong token audience or no sign-in | Use `https://cognitiveservices.azure.com/.default` and run `az login`. |

**Next steps:**
- Sweep `reasoning_effort` and `verbosity` on your own evals to find the cost/quality point for each route.
- Once behavior is verified, run your prompt-optimization pass to tune the (still unchanged) prompts for the new model.
- Consider migrating the highest-traffic path to the Responses API for reasoning summaries and streaming.