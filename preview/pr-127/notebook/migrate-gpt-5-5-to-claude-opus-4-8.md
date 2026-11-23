> **Migrate a Chat Completions workload from `gpt-5.5` to `claude-opus-4-8` on Microsoft Foundry, behind one adapter, with eval gates.**

Anthropic's Claude models are now hosted on Azure as first-class Foundry deployments, billed through Azure Marketplace in Claude Consumption Units. For teams running gpt-5.x today, the engineering move is small (one adapter, two SDKs, one extra Entra audience), but the request shape, the response shape, and the gating contract are all different from a same-family upgrade.

This recipe walks the move end-to-end on a **single Foundry resource** that hosts both `gpt-5.5` and `claude-opus-4-8`. Both are first-class Foundry deployments: one served via the OpenAI Chat Completions path, the other via the Anthropic Messages path. You build the adapter, prove parity on a small eval set, and decide whether to flip.

**The rollout pattern this notebook teaches: test side by side first, then switch users over.** Instead of swapping the model in one risky step, you do it in two phases:

1. **Test side by side (users don't see Claude yet).** Your app still serves every user request from `gpt-5.5`. For some fraction of those same requests, you also send the prompt to `claude-opus-4-8` in the background and log the result. The user never sees the Claude response; it's compared against the gpt-5.5 response and scored offline against your eval gates. Production behavior is unchanged; you're just collecting evidence on real traffic.
2. **Switch users over.** Once the side-by-side data shows Claude is meeting your gates, you flip a single environment variable (`PROVIDER=anthropic`) so user-facing responses now come from `claude-opus-4-8`. The gpt-5.5 deployment stays alive so you can roll back instantly if anything regresses.

The adapter you build below makes both phases the same code path. The only difference between them is which provider's output is shown to the user.

**What this recipe is not.** It doesn't change your business prompts (defer per-provider prompt optimization to a separate pass), and it doesn't pick a router. The aim is to give you the code-level changes and eval gates needed to adopt `claude-opus-4-8` safely, not to argue for one model over another.

**How to run.** Run cells top to bottom on a fresh kernel; later cells depend on classes defined earlier. This notebook itself calls both adapters explicitly so you can compare them side by side. The `PROVIDER` env var described in the rollout pattern is what *your application* reads in production to pick which adapter handles real user traffic.

## Configure

**Prerequisites.** One Foundry resource in the same Azure subscription with both deployments below created and the Anthropic Marketplace agreement accepted for your tenant. If you don't have that yet, the [Microsoft Learn quickstart](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-claude?tabs=python) and the [`Azure-Samples/claude`](https://github.com/Azure-Samples/claude) `azd up` starter (linked again at the end) walk you through it.

You'll need one Foundry resource with two deployments connected to its project:

- `gpt-5.5`: OpenAI Chat Completions on Foundry (the baseline)
- `claude-opus-4-8`: Anthropic on Foundry (the candidate)

Both deployments must be in a region where the model is available and have enough quota for a small eval set. If your gpt-5.5 deployment is PTU-only and you have no PAYG opus quota yet, the eval cell will rate-limit on the Anthropic side, so request quota from your Foundry portal before continuing.

A single Foundry role can get you through this notebook, `Foundry Owner`. Or you can use two Foundry roles with separated control and data plane permissions: `Foundry User` on the Foundry resource for inference (data plane), and the corresponding `Foundry Account Owner` role for deployment changes (control plane).

Put these in a `.env` next to the notebook (or in your shell). Substitute your actual resource and deployment names:

```bash
# Baseline: gpt-5.5 (OpenAI on Foundry, Chat Completions path)
OPENAI_ENDPOINT=https://<your-foundry-resource>.services.ai.azure.com
OPENAI_DEPLOYMENT=gpt-5.5
OPENAI_API_KEY=<key>              # or omit and use DefaultAzureCredential
OPENAI_API_VERSION=2024-10-21

# Candidate: claude-opus-4-8 (Anthropic on Foundry, Messages path)
ANTH_BASE_URL=https://<your-foundry-resource>.services.ai.azure.com/anthropic
ANTH_DEPLOYMENT=claude-opus-4-8
ANTH_API_KEY=<key>                # or omit and use DefaultAzureCredential
```

```python
%%capture
%pip install --quiet \
    "openai>=1.50.0" \
    "anthropic>=0.55.0" \
    "azure-identity>=1.19.0" \
    "httpx>=0.27.0" \
    "jsonschema>=4.22.0" \
    "python-dotenv>=1.0.1"
```

```python
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv(override=True)

OPENAI_ENDPOINT       = os.environ["OPENAI_ENDPOINT"].rstrip("/")
OPENAI_DEPLOYMENT     = os.environ.get("OPENAI_DEPLOYMENT", "gpt-5.5")
OPENAI_API_KEY        = os.environ.get("OPENAI_API_KEY")        # None → use Entra
OPENAI_API_VERSION    = os.environ.get("OPENAI_API_VERSION", "2024-10-21")

ANTH_BASE_URL         = os.environ["ANTH_BASE_URL"].rstrip("/")
ANTH_DEPLOYMENT       = os.environ.get("ANTH_DEPLOYMENT", "claude-opus-4-8")
ANTH_API_KEY          = os.environ.get("ANTH_API_KEY")          # None → use Entra

def _redact_ai_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.endswith(".services.ai.azure.com"):
        path = "/anthropic" if parsed.path.rstrip("/") == "/anthropic" else ""
        return f"{parsed.scheme}://<your-foundry-resource>.services.ai.azure.com{path}"
    return "<configured endpoint>"

print(f"OpenAI endpoint   : {_redact_ai_url(OPENAI_ENDPOINT)}")
print(f"OpenAI deployment : {OPENAI_DEPLOYMENT}  (api-version {OPENAI_API_VERSION})")
print(f"Anthropic base    : {_redact_ai_url(ANTH_BASE_URL)}")
print(f"Anthropic model   : {ANTH_DEPLOYMENT}")
```

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI
from anthropic import AnthropicFoundry

# Two audiences, one credential. Build separate token providers so the right scope
# travels with the right client.
_cred = DefaultAzureCredential()
openai_token_provider = get_bearer_token_provider(
    _cred, "https://cognitiveservices.azure.com/.default"
)
anth_token_provider = get_bearer_token_provider(
    _cred, "https://ai.azure.com/.default"
)

# Baseline client: OpenAI on Foundry (Chat Completions path).
openai_client = AzureOpenAI(
    azure_endpoint=OPENAI_ENDPOINT,
    api_version=OPENAI_API_VERSION,
    **({"api_key": OPENAI_API_KEY} if OPENAI_API_KEY is not None else {"azure_ad_token_provider": openai_token_provider}),
)

# Candidate client: Anthropic on Foundry. base_url ends in /anthropic;
# the SDK appends /v1/messages itself.
anth_client = AnthropicFoundry(
    base_url=ANTH_BASE_URL,
    **({"api_key": ANTH_API_KEY} if ANTH_API_KEY
       else {"azure_ad_token_provider": anth_token_provider}),
)

print("clients built. openai:", type(openai_client).__name__,
      "| anthropic:", type(anth_client).__name__)
```

```python
import httpx
from urllib.parse import urlparse

# Reachability probe only. The Foundry host root doesn't serve a meaningful endpoint
# for HEAD, so a 404 or 405 here is normal; it confirms DNS, TLS, and routing work.
# We're not exercising the OpenAI or Anthropic API path; that happens in later cells.
# Any 2xx/3xx/4xx response = host is reachable. Only ERR (timeout / DNS) is a real failure.
def _host(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"

for label, url in [("OpenAI", OPENAI_ENDPOINT),
                   ("Anthropic-on-Foundry", _host(ANTH_BASE_URL))]:
    display_url = _redact_ai_url(url)
    try:
        r = httpx.head(url, timeout=5.0)
        print(f"  {label:<22} {display_url:<60}  {r.status_code}")
    except Exception as exc:
        print(f"  {label:<22} {display_url:<60}  ERR {type(exc).__name__}: {exc}")
```

## The call you make today

This is the gpt-5.5 call you almost certainly have in production. The shape is the same regardless of which framework wraps it: a `messages[]` array (with `system` as the first message), `tools=[{type:"function",...}]`, `response_format={"type":"json_schema","strict":true,...}`, and `reasoning_effort` + `max_completion_tokens` on the 5.x line.

`model=` is the *deployment* name on Azure, not the model id.

> **On the Foundry Responses API?** If your gpt-5.5 calls already go through `client.responses.create(...)` against a project-scoped endpoint, only this cell's request shape swaps; the Anthropic side of the notebook and the adapter contract are unchanged. The four differences worth knowing:
>
> 1. **`input=`** (a string or a list of typed input items) replaces `messages=`. `system` becomes `instructions=` at the top level.
> 2. **`max_output_tokens`** replaces `max_completion_tokens`.
> 3. **Tools are flat**: `{type:"function", name, description, parameters}` instead of `{type:"function", function:{name, ...}}`. The JSON Schema itself is unchanged.
> 4. **Reading the response**: `resp.output_text` is the convenience accessor; structured outputs land in `resp.output[*]` items rather than `choices[0].message`.
>
> In the adapter built later, this maps to a second `OpenAIResponsesAdapter` that swaps these four call-shape details and returns the same `Response` dataclass. Every other section (tools, structured outputs, streaming, eval, gates) continues to work as written.

```python
baseline_resp = openai_client.chat.completions.create(
    model=OPENAI_DEPLOYMENT,
    messages=[
        {"role": "system", "content": "You are a careful research assistant."},
        {"role": "user",   "content": "In one sentence: what does Microsoft Foundry do?"},
    ],
    max_completion_tokens=200,
)

print("=== gpt-5.5 (OpenAI on Foundry) ===")
print(baseline_resp.choices[0].message.content)
print()
print("usage:", baseline_resp.usage)
```

## The call you make on Anthropic

Same prompt, same Foundry resource, different path. The host is `<your-foundry-resource>.services.ai.azure.com`; the SDK takes a `base_url` ending in `/anthropic` and appends `/v1/messages` itself. Three shape changes worth noting up front:

1. **`system` is a top-level argument**, not a message inside the `messages[]` array.
2. **Content is blocks**: a user turn's `content` may be a plain string *or* a list of typed blocks (`{type:"text",...}`, `{type:"image",...}`, `{type:"tool_result",...}`).
3. **`max_tokens` (not `max_completion_tokens`).** Anthropic also uses `stop_sequences` (not `stop`).

This first call is intentionally bare on both sides (no reasoning knobs, just provider defaults) so you can see the shape difference without other variables moving. We turn on reasoning where the eval (later in the notebook) shows it actually helps.

### Reasoning effort: where the comparison isn't apples-to-apples

This is the most common source of misleading A/B numbers when migrating, and it's worth being precise about:

| | **gpt-5.5** | **claude-opus-4-8** |
|---|---|---|
| Knob | `reasoning_effort` | `thinking={"type":"adaptive"}` + `output_config.effort` |
| Levels | `minimal`, `low`, `medium`, `high` | off (default) and `low`, `medium`, `high` (confirm any higher tiers against your model version's [Foundry docs](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models?tabs=pay-go)) |
| Default | `medium`; **always reasons** internally | **off**; no extended thinking unless you opt in |
| Output | Reasoning is internal; you never see the tokens | Surfaces as separate `thinking` content blocks (don't show users) |

The honest read: **provider defaults are not equivalent.** gpt-5.5 at its default does silent internal reasoning; claude-opus-4-8 at its default does not. So "default vs default" measures *what production code typically does*, not equal reasoning budget.

Three sensible comparison modes, pick the one that matches what you're evaluating:

- **Production parity (recommended for migration eval).** Mirror whatever your live gpt-5.5 call sets, and on the Claude side opt into thinking only where the eval shows a quality lift. This is the version users actually experience.
- **Reasoning-budget parity.** gpt-5.5 default (`medium`) vs Claude with `thinking={"type":"adaptive"}` and `output_config={"effort":"medium"}`. Useful for capability comparison, but not 1:1; the providers spend the budget differently.
- **Latency / cost floor.** gpt-5.5 with `reasoning_effort="minimal"` vs Claude with no `thinking`. Useful when you need to know the fastest, cheapest each can serve at acceptable quality.

For the hello-world baseline below, defaults are the right call (that's what most readers' production code looks like), but don't read parity into the numbers. The eval cells that follow are where you'd pin reasoning effort to a fixed setting.

```python
candidate_resp = anth_client.messages.create(
    model=ANTH_DEPLOYMENT,
    system="You are a careful research assistant.",
    messages=[
        {"role": "user", "content": "In one sentence: what does Microsoft Foundry do?"},
    ],
    max_tokens=200,
)

# Anthropic returns content as a list of typed blocks. The assistant's text lives in
# `text` blocks; any `thinking` blocks (when extended thinking is enabled) should not
# be rendered to end users.
text_blocks = [b.text for b in candidate_resp.content if b.type == "text"]
print("=== claude-opus-4-8 (Anthropic on Foundry) ===")
print("\n".join(text_blocks))
print()
print("usage:", candidate_resp.usage)
```

## What needs to change in your code

When you adopt `claude-opus-4-8` alongside `gpt-5.5` on the same Foundry resource, these are the places your code touches the wire. Review each one and decide where the change lands (typically inside the adapter you build in the next section). Anything not listed here is unchanged.

**Endpoint & auth**
- Add a second base URL: `https://<your-resource>.services.ai.azure.com/anthropic`. The SDK appends `/v1/messages` itself.
- For API-key calls, let `AnthropicFoundry` set its supported authentication header rather than constructing one yourself.
- Entra-ID calls use the audience `https://ai.azure.com/.default`, which is a different audience from the OpenAI path (`https://cognitiveservices.azure.com/.default`). Build a separate token provider per audience.
- No `?api-version=` query string; version is set by the `anthropic-version: 2023-06-01` header (the SDK handles this).

**SDK & client class**
- Install `anthropic>=0.55` and import `from anthropic import AnthropicFoundry` (not the stock `Anthropic` class).
- Continue using `from openai import AzureOpenAI` for the gpt-5.5 path.

**Request shape**
- `model=` still takes the **deployment** name (same convention as today).
- Move the system prompt out of `messages[]` into the top-level `system=` argument.
- Rename the token cap: `max_completion_tokens` becomes `max_tokens`.
- Rename stop sequences: `stop` becomes `stop_sequences`.
- User content can be a plain string *or* a list of typed blocks (`{type:"text"}`, `{type:"image"}`, `{type:"tool_result"}`). Image blocks differ from OpenAI's `image_url` shape.

**Reasoning controls**
- Opt in per call with `thinking={"type":"adaptive"}` and steer with `output_config={"effort":"low|medium|high"}` (confirm whether higher tiers are available for your model version against the [Foundry Claude docs](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models?tabs=pay-go)). There's no equivalent of `reasoning_effort` as a single argument.

**Tools**
- Tool declaration changes wrapper: `{type:"function","function":{name, description, parameters}}` becomes `{name, description, input_schema}`. The JSON Schema itself passes through.
- Tool **results** are not `role:"tool"` messages; they're user messages whose content is `[{type:"tool_result", tool_use_id, content}]`.

**Structured outputs**
- There is no `strict: true` JSON-schema mode. Replace it with **validate post-hoc and retry once** (full pattern in the structured outputs section).

**Streaming**
- Event shape is different: typed events with `delta.type` set to `text_delta`, `input_json_delta`, or `thinking_delta`. Wrap both providers behind a single normalized event stream so downstream UI code doesn't need to know.

**Billing**
- Claude usage rolls up under **Azure Marketplace** as Claude Consumption Units, a separate report from your existing OpenAI-on-Foundry consumption. Plan to reconcile both during migration.

The next section turns this list into ~80 lines of adapter code.

## The adapter

**When to use:** Use this when the app already has OpenAI-style chat call sites and you want to test Claude without rewriting business logic.

**What it does:** It creates one provider-neutral contract for prompts, tools, structured outputs, usage, and streaming so only the adapter knows which SDK is underneath.

**How to adapt:** Keep `Conversation` and `Response` stable, then add or swap provider-specific adapters behind the same `run()` method.

Don't sprinkle `if PROVIDER == "anthropic"` through your app. Build one boundary, put both SDKs behind it, and let every call site speak the same shape.

The contract:

- A `Conversation` dataclass holds `system`, `messages[]`, `tools[]`, and the optional thinking/effort knobs. Tools use the OpenAI strict shape as the canonical form (most apps already have it that way).
- `OpenAIAdapter.run(conv, deployment)` and `AnthropicAdapter.run(conv, deployment)` both return a provider-neutral `Response(text, tool_calls, usage, raw)`.
- A tiny `openai_tools_to_anthropic()` helper translates schemas one way; tool results get wrapped by the adapter on the way back.

Everything below the `Conversation` boundary is the adapter's problem. Above it, your app does not change.

```python
import json
from dataclasses import dataclass, field
from typing import Any, Optional
from jsonschema import Draft202012Validator, ValidationError

# ---------- Canonical types ----------

@dataclass
class Message:
    role: str                            # "system" | "user" | "assistant" | "tool"
    content: Any                         # str or list of typed blocks
    tool_call_id: Optional[str] = None   # only when role == "tool"

@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict                     # JSON Schema (OpenAI strict shape)

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict                      # parsed JSON

@dataclass
class Conversation:
    system: str
    messages: list[Message] = field(default_factory=list)
    tools: list[ToolSpec] = field(default_factory=list)
    thinking: bool = False               # turn on adaptive thinking (Anthropic only)
    effort: str = "medium"               # low | medium | high (confirm any higher tiers in the Foundry Claude docs for your model version)
    max_tokens: int = 1024
    json_schema: Optional[dict] = None   # when set, output is validated against this schema

@dataclass
class Response:
    text: str
    tool_calls: list[ToolCall]
    usage: dict
    raw: Any
    retries: int = 0                     # JSON-schema retry count (0 for OpenAI strict; 0 or 1 for Anthropic)

# ---------- Helpers ----------

def openai_tools_to_anthropic(tools: list[ToolSpec]) -> list[dict]:
    """OpenAI function tools -> Anthropic tool blocks. The JSON Schema passes through;
    only the wrapper shape changes."""
    return [
        {"name": t.name, "description": t.description, "input_schema": t.parameters}
        for t in tools
    ]

def _strip_json_fences(raw: str) -> str:
    """Remove a ```json ... ``` wrapper if the model insisted on one."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return raw

def _anthropic_content(content: Any) -> Any:
    """Convert SDK content blocks to plain dictionaries when a prior response is reused."""
    if not isinstance(content, list):
        return content
    return [block.model_dump() if hasattr(block, "model_dump") else block for block in content]

def anthropic_messages(messages: list[Message]) -> list[dict]:
    """Translate canonical history, including tool results, to Anthropic message blocks."""
    translated = []
    for message in messages:
        if message.role in ("user", "assistant"): 
            translated.append({"role": message.role,
                               "content": _anthropic_content(message.content)})
        elif message.role == "tool":
            if not message.tool_call_id:
                raise ValueError("tool messages require tool_call_id")
            translated.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id,
                    "content": _anthropic_content(message.content),
                }],
            })
        else:
            raise ValueError(f"Unsupported canonical role: {message.role}")
    return translated

def tool_calls_meet_contract(tools: list[ToolSpec], expected_name: str, calls: list,
                            error: Optional[str] = None) -> bool:
    """Fail closed unless every tool call has the expected name and valid arguments."""
    tools_by_name = {tool.name: tool for tool in tools}
    if error or not calls:
        return False
    for name, arguments in calls:
        if name != expected_name or name not in tools_by_name:
            return False
        try:
            Draft202012Validator(tools_by_name[name].parameters).validate(arguments)
        except (ValidationError, TypeError):
            return False
    return True

# ---------- Adapters ----------

class OpenAIAdapter:
    def __init__(self, client): self.client = client

    def run(self, conv: Conversation, deployment: str) -> Response:
        msgs = [{"role": "system", "content": conv.system}]
        for m in conv.messages:
            entry = {"role": m.role, "content": m.content}
            if m.tool_call_id is not None:
                entry["tool_call_id"] = m.tool_call_id
            msgs.append(entry)
        kwargs: dict = {"model": deployment, "messages": msgs,
                        "max_completion_tokens": conv.max_tokens}
        if conv.tools:
            kwargs["tools"] = [
                {"type": "function",
                 "function": {"name": t.name, "description": t.description,
                              "parameters": t.parameters}}
                for t in conv.tools
            ]
        if conv.json_schema is not None:
            # strict:true is the hard guarantee; retries are always 0 on this path.
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "strict": True, "schema": conv.json_schema},
            }
        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        calls = [
            ToolCall(id=tc.id, name=tc.function.name,
                     arguments=json.loads(tc.function.arguments or "{}"))
            for tc in (msg.tool_calls or [])
        ]
        return Response(
            text=msg.content or "",
            tool_calls=calls,
            usage={"input":  resp.usage.prompt_tokens,
                   "output": resp.usage.completion_tokens},
            raw=resp,
            retries=0,
        )


class AnthropicAdapter:
    def __init__(self, client): self.client = client

    def run(self, conv: Conversation, deployment: str) -> Response:
        if conv.json_schema is not None:
            return self._run_with_json_schema(conv, deployment)

        msgs = anthropic_messages(conv.messages)
        kwargs: dict = {"model": deployment, "system": conv.system,
                        "messages": msgs, "max_tokens": conv.max_tokens}
        if conv.tools:
            kwargs["tools"] = openai_tools_to_anthropic(conv.tools)
        if conv.thinking:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": conv.effort}
        resp = self.client.messages.create(**kwargs)
        return self._build_response(resp, retries=0)

    def _run_with_json_schema(self, conv: Conversation, deployment: str) -> Response:
        """Validate-and-retry once. Anthropic has no strict JSON-schema mode, so we
        instruct, parse, validate, and retry exactly once on failure."""
        schema_text = json.dumps(conv.json_schema, indent=2)
        msgs = anthropic_messages(conv.messages)
        # Augment the final user turn with the schema. Preserves the caller's prompt.
        if msgs and msgs[-1]["role"] == "user" and isinstance(msgs[-1]["content"], str):
            msgs[-1] = {"role": "user",
                        "content": f"{msgs[-1]['content']}\n\n"
                                   f"Return JSON only matching this schema:\n{schema_text}"}
        system = conv.system + "\n\nReturn JSON only. No prose. No markdown fences."

        last_exc: Exception = RuntimeError("no attempts ran")
        for attempt in range(2):
            resp = self.client.messages.create(
                model=deployment, system=system, messages=msgs,
                max_tokens=conv.max_tokens,
            )
            raw = "".join(b.text for b in resp.content if b.type == "text")
            raw = _strip_json_fences(raw)
            try:
                parsed = json.loads(raw)
                Draft202012Validator(conv.json_schema).validate(parsed)
                return Response(
                    text=json.dumps(parsed),
                    tool_calls=[],
                    usage=self._usage(resp),
                    raw=resp,
                    retries=attempt,
                )
            except (json.JSONDecodeError, ValidationError) as exc:
                last_exc = exc
                msgs.append({"role": "assistant", "content": raw})
                msgs.append({"role": "user",
                             "content": f"That did not match the schema ({exc}). "
                                        "Re-emit valid JSON only."})
        raise RuntimeError(f"Anthropic structured output failed twice: {last_exc}")

    def _build_response(self, resp, retries: int) -> Response:
        text = "".join(b.text for b in resp.content if b.type == "text")
        calls = [
            ToolCall(id=b.id, name=b.name, arguments=b.input or {})
            for b in resp.content if b.type == "tool_use"
        ]
        return Response(text=text, tool_calls=calls,
                        usage=self._usage(resp), raw=resp, retries=retries)

    @staticmethod
    def _usage(resp) -> dict:
        u = resp.usage
        return {
            "input":        u.input_tokens,
            "output":       u.output_tokens,
            "cache_read":   getattr(u, "cache_read_input_tokens", 0),
            "cache_create": getattr(u, "cache_creation_input_tokens", 0),
        }

openai_adapter = OpenAIAdapter(openai_client)
anth_adapter   = AnthropicAdapter(anth_client)
print("adapters ready")
```

```python
# Credential-free assertion: retain the assistant tool_use block and translate the
 # canonical tool result into the Anthropic user-message shape.
history = [
    Message(role="user", content="What is the weather in Seattle?"),
    Message(
        role="assistant",
        content=[{
            "type": "tool_use",
            "id": "call_weather",
            "name": "get_weather",
            "input": {"city": "Seattle", "units": "f"},
        }],
    ),
    Message(
        role="tool",
        tool_call_id="call_weather",
        content="{\"temperature\": 62, \"units\": \"f\"}",
    ),
]
translated = anthropic_messages(history)
assert translated[1]["role"] == "assistant"
assert translated[1]["content"][0]["type"] == "tool_use"
assert translated[2] == {
    "role": "user",
    "content": [{
        "type": "tool_result",
        "tool_use_id": "call_weather",
        "content": "{\"temperature\": 62, \"units\": \"f\"}",
    }],
}
weather_schema = ToolSpec(
    name="get_weather",
    description="Get weather.",
    parameters={"type": "object", "properties": {"city": {"type": "string"}},
                "required": ["city"], "additionalProperties": False},
)
assert tool_calls_meet_contract([weather_schema], "get_weather",
                                [("get_weather", {"city": "Seattle"})])
assert not tool_calls_meet_contract([weather_schema], "get_weather",
                                    [("get_weather", {"city": 42})])
assert not tool_calls_meet_contract([weather_schema], "get_weather", [],
                                    error="JSONDecodeError: malformed arguments")
print("Anthropic translation and tool-contract checks passed.")
```

## Tools end-to-end

Declare a tool once in the canonical (OpenAI strict) shape. Both adapters pick it up; both responses parse into the same `ToolCall`.

This is the **schema-parity contract** the promotion gate later in this notebook checks. If the Anthropic path doesn't produce a `ToolCall` with the same `name` and a JSON body that validates against the same `parameters` schema, the migration fails closed *regardless* of how good the prose is.

> **Heads up: empty `text` is expected here.** When the model decides to call a tool, it returns a `tool_call` instead of prose, so `text` will be `''` on the gpt-5.5 row and `tool_calls` will be populated. That's the model saying "don't make up the weather, call `get_weather` and feed me the result." In a real agent loop you'd run the tool, append a `tool` message with the result, and call the model again; that second response is where the user-facing text comes from. Claude sometimes emits a short narrating text block alongside the `tool_use` block, so the Claude row may show both. That's a known provider difference, not a bug, and the promotion gate ignores it.


```python
GET_WEATHER = ToolSpec(
    name="get_weather",
    description="Get the current weather for a city.",
    parameters={
        "type": "object",
        "properties": {
            "city":  {"type": "string", "description": "City name, e.g. 'Seattle'"},
            "units": {"type": "string", "enum": ["c", "f"]},
        },
        "required": ["city"],
        "additionalProperties": False,
    },
)

conv = Conversation(
    system="You can call tools when you need real-world data.",
    messages=[Message(role="user", content="What's the weather in Seattle in Fahrenheit?")],
    tools=[GET_WEATHER],
)

for label, adapter, deployment in [
    ("gpt-5.5",          openai_adapter, OPENAI_DEPLOYMENT),
    ("claude-opus-4-8",  anth_adapter,   ANTH_DEPLOYMENT),
]:
    r = adapter.run(conv, deployment)
    print(f"--- {label} ---")
    print(f"  text       : {r.text[:80]!r}")
    print(f"  tool_calls : {[(c.name, c.arguments) for c in r.tool_calls]}")
    print()
```

```python
# Complete the Claude tool round trip. Preserve the assistant's tool_use block, then
 # append the canonical tool result; AnthropicAdapter turns it into a user tool_result block.
first_turn = anth_adapter.run(conv, ANTH_DEPLOYMENT)
if not first_turn.tool_calls:
    raise RuntimeError("Claude did not request get_weather; retry with a more explicit tool instruction.")
weather_call = first_turn.tool_calls[0]
continuation = Conversation(
    system=conv.system,
    messages=[
        *conv.messages,
        Message(role="assistant", content=_anthropic_content(first_turn.raw.content)),
        Message(
            role="tool",
            tool_call_id=weather_call.id,
            content=json.dumps({"city": "Seattle", "temperature": 62, "units": "f"}),
        ),
    ],
    tools=[GET_WEATHER],
)
completed_turn = anth_adapter.run(continuation, ANTH_DEPLOYMENT)
print(completed_turn.text)
```

## Structured outputs

**When to use:** Use this when your OpenAI path depends on `strict: true` JSON Schema outputs and the Claude path must satisfy the same downstream parser.

**What it does:** OpenAI enforces the schema at generation time; Claude is validated after generation and gets one retry if the response does not match.

**How to adapt:** Replace `TICKET_SCHEMA` with your production schema and track `Response.retries` as a portability signal in evals.

OpenAI's `strict: true` `json_schema` is a *hard* guarantee: the model cannot emit invalid JSON. Anthropic has no equivalent. The portable pattern is **validate post-hoc, retry once** with a "your previous response did not match this schema, re-emit valid JSON only" follow-up.

The adapter handles this for you. Set `Conversation.json_schema` and call `adapter.run(conv)`. `OpenAIAdapter` sets `response_format` strict mode (zero retries by construction), `AnthropicAdapter` instructs, parses, validates, and retries once on failure. The retry count is returned on `Response.retries`. Call-site code looks the same on both providers.

**Retry rate is itself a signal.** If `Response.retries` is `1` on more than ~5% of your eval set, the prompt likely needs an Anthropic-specific compile. That's a separate pass (per-provider prompt portability). Don't paper over it here.

```python
TICKET_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string",
                     "enum": ["hardware", "software", "billing", "other"]},
        "priority": {"type": "string", "enum": ["low", "med", "high"]},
    },
    "required": ["category", "priority"],
    "additionalProperties": False,
}

# Same Conversation -> both adapters. No side-channel helpers, no provider branching
# in user code. The adapter handles strict-mode (OpenAI) vs. validate-and-retry (Anthropic).
conv = Conversation(
    system="Classify support tickets.",
    messages=[Message(role="user",
                      content="Classify this support ticket: 'My laptop won't charge.'")],
    json_schema=TICKET_SCHEMA,
)

r_oai  = openai_adapter.run(conv, OPENAI_DEPLOYMENT)
r_anth = anth_adapter.run(conv,   ANTH_DEPLOYMENT)

print(f"gpt-5.5         -> {r_oai.text}   (retries: {r_oai.retries})")
print(f"claude-opus-4-8 -> {r_anth.text}  (retries: {r_anth.retries})")
```

## Streaming, normalized

**When to use:** Use this when your UI, logs, or agent loop already consumes streaming events and should not care which provider generated them.

**What it does:** It maps OpenAI chunks and Anthropic typed events into one `StreamEvent` shape for text, tool calls, thinking, and completion.

**How to adapt:** Add only the event kinds your app consumes, and keep provider-only fields inside the normalizer.

Both SDKs stream, but the events look different. OpenAI sends SSE chunks with `choices[0].delta.content`; Anthropic sends typed events whose `delta.type` is `text_delta`, `input_json_delta`, or `thinking_delta`. Wrap both in a single `StreamEvent` interface and downstream UI code stops caring which provider is on.

```python
from typing import Iterator, Literal

@dataclass
class StreamEvent:
    kind: Literal["text", "tool_call_start", "tool_call_args", "thinking", "done"]
    data: dict

def normalize_openai_stream(resp) -> Iterator[StreamEvent]:
    for chunk in resp:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield StreamEvent("text", {"text": delta.content})
        for tc in (delta.tool_calls or []):
            if tc.function and tc.function.name:
                yield StreamEvent("tool_call_start",
                                  {"id": tc.id, "name": tc.function.name})
            if tc.function and tc.function.arguments:
                yield StreamEvent("tool_call_args", {"args": tc.function.arguments})
    yield StreamEvent("done", {})

def normalize_anthropic_stream(resp) -> Iterator[StreamEvent]:
    for event in resp:
        t = getattr(event, "type", None)
        if t == "content_block_start":
            block = event.content_block
            if block.type == "tool_use":
                yield StreamEvent("tool_call_start",
                                  {"id": block.id, "name": block.name})
        elif t == "content_block_delta":
            d = event.delta
            if d.type == "text_delta":
                yield StreamEvent("text", {"text": d.text})
            elif d.type == "input_json_delta":
                yield StreamEvent("tool_call_args", {"args": d.partial_json})
            elif d.type == "thinking_delta":
                yield StreamEvent("thinking", {"text": d.thinking})
    yield StreamEvent("done", {})

# Same prompt AND same system message on both sides. What we're showing is the
# difference in event shape, so anything that changes output length (like only one
# side getting a "be concise" instruction) would muddy the comparison.
SYSTEM = "Be concise."
prompt = "List three things to do in Seattle in summer."

print("--- gpt-5.5 stream ---")
oai_stream = openai_client.chat.completions.create(
    model=OPENAI_DEPLOYMENT,
    messages=[{"role": "system", "content": SYSTEM},
              {"role": "user",   "content": prompt}],
    max_completion_tokens=200, stream=True,
)
for i, ev in enumerate(normalize_openai_stream(oai_stream)):
    if i >= 25: break
    print(f"  {ev.kind:<16} {str(ev.data)[:60]}")

print("\n--- claude-opus-4-8 stream ---")
anth_stream = anth_client.messages.create(
    model=ANTH_DEPLOYMENT, system=SYSTEM,
    messages=[{"role": "user", "content": prompt}],
    max_tokens=200, stream=True,
)
for i, ev in enumerate(normalize_anthropic_stream(anth_stream)):
    if i >= 25: break
    print(f"  {ev.kind:<16} {str(ev.data)[:60]}")
```

## Run the eval set

An inline 8-row eval set (mix of plain text, tool-use, and JSON shape) so this notebook runs in under a minute. For production, **create your own eval file** with 50–100 prompts that look like your real traffic and load it in place of the inline list. `azure-ai-evaluation`'s `SimilarityEvaluator` / `RelevanceEvaluator` plug straight into the same loop. The harness, gates, and code path don't change; only the data does.

Scoring is three layers, in this order of strictness:

1. **Schema parity** (hard): every row that produced a tool call on gpt-5.5 must produce a `ToolCall` with the same `name` and a JSON body that validates against the same schema on claude-opus-4-8. Argument *values* may differ; structure must not.
2. **Structured-output retry rate** (hard): JSON-mode rows must succeed in ≤1 retry on the Anthropic path. >10% retry rate is a smell, not a soft fail.
3. **Quality** (soft): Jaccard token overlap vs `expected` for plain-text rows. Swap in `SimilarityEvaluator` for production. Gate: candidate ≥ baseline − 0.05.

Plus a latency check in the promotion gate below.

```python
import time, re

EVAL_ROWS = [
    {"id": "text-1",
     "prompt": "In one sentence, what does Microsoft Foundry do?",
     "expected": "Microsoft Foundry is a platform for building, deploying, and managing AI agents and models on Azure."},
    {"id": "text-2",
     "prompt": "Name two benefits of multi-provider model access.",
     "expected": "Avoiding vendor lock-in and matching the best model to each task."},
    {"id": "text-3",
     "prompt": "What is prompt caching used for?",
     "expected": "Reusing long static prompt prefixes to cut input cost and latency."},
    {"id": "tool-1",
     "prompt": "What's the weather in Seattle?",
     "tools": [GET_WEATHER],
     "expected_tool": "get_weather"},
    {"id": "tool-2",
     "prompt": "Tell me the weather in Tokyo in Celsius.",
     "tools": [GET_WEATHER],
     "expected_tool": "get_weather"},
    {"id": "json-1",
     "prompt": "Classify this support ticket: 'My laptop won't charge.'",
     "json_schema": TICKET_SCHEMA},
    {"id": "json-2",
     "prompt": "Classify this support ticket: 'I was double-billed last month.'",
     "json_schema": TICKET_SCHEMA},
    {"id": "text-4",
     "prompt": "What does the Claude `tool_result` content block do?",
     "expected": "Returns the result of a tool call back to the model inside a user message."},
]

def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))

def jaccard(a: str, b: str) -> float:
    A, B = _tokens(a), _tokens(b)
    return len(A & B) / max(1, len(A | B))

def run_row(adapter, deployment, row) -> dict:
    """Every row builds a Conversation and calls adapter.run(). No provider branching."""
    t0 = time.perf_counter()
    if "tools" in row:
        conv = Conversation(
            system="You can call tools when you need real-world data.",
            messages=[Message(role="user", content=row["prompt"])],
            tools=row["tools"],
        )
        try:
            r = adapter.run(conv, deployment)
            out = {"tool_calls": [(c.name, c.arguments) for c in r.tool_calls],
                   "usage": r.usage}
        except Exception as exc:
            # A malformed tool-call payload is a failed contract, not a crashed gate.
            out = {"tool_calls": [], "usage": {},
                   "error": f"{type(exc).__name__}: {exc}"}
    elif "json_schema" in row:
        conv = Conversation(
            system="Be concise and accurate.",
            messages=[Message(role="user", content=row["prompt"])],
            json_schema=row["json_schema"],
        )
        r = adapter.run(conv, deployment)
        out = {"json": json.loads(r.text), "retries": r.retries, "usage": r.usage}
    else:
        conv = Conversation(
            system="Be concise and accurate.",
            messages=[Message(role="user", content=row["prompt"])],
        )
        r = adapter.run(conv, deployment)
        out = {"text": r.text, "usage": r.usage}
    out["latency_s"] = round(time.perf_counter() - t0, 2)
    return out

results = {"openai": {}, "anthropic": {}}
for row in EVAL_ROWS:
    results["openai"][row["id"]]    = run_row(openai_adapter, OPENAI_DEPLOYMENT, row)
    results["anthropic"][row["id"]] = run_row(anth_adapter,   ANTH_DEPLOYMENT,    row)

print(f"{'id':<8} {'kind':<6} {'gpt-5.5 lat':<13} {'opus-4-8 lat':<14} preview (candidate)")
print("-" * 80)
for row in EVAL_ROWS:
    o = results["openai"][row["id"]]
    a = results["anthropic"][row["id"]]
    kind = "tool" if "tools" in row else "json" if "json_schema" in row else "text"
    preview = a.get("text") or a.get("json") or a.get("tool_calls", "")
    print(f"{row['id']:<8} {kind:<6} {o['latency_s']:<13} {a['latency_s']:<14} {str(preview)[:55]}")
```

## Promotion gate, cost, and latency

**When to use:** Use this before any user-facing traffic moves from `gpt-5.5` to `claude-opus-4-8`.

**What it does:** It blocks promotion on parsed-shape regressions first, then checks structured-output retries, quality, and latency.

**How to adapt:** Keep schema/tool parity as hard gates, but replace the toy quality metric and latency threshold with workload-specific evals before production rollout.

The cross-provider gate is stricter than a same-family upgrade. *Parsed-shape parity* fails closed before quality is even considered.

| Gate | Threshold | Why |
|---|---|---|
| Schema parity | 100% on tool rows | If 3% of tool calls parse wrong, a 10% quality lift is worthless |
| Structured retry rate | ≤10% | Higher = prompt needs an Anthropic-specific compile, not a model swap |
| Quality (Jaccard) | candidate ≥ baseline − 0.05 | Same as a within-family upgrade |
| P90 latency | ≤ baseline × 1.3 | Budget headroom for the candidate path |

**Cost is intentionally not auto-computed here.** Claude is metered in **Claude Consumption Units** through Azure Marketplace, on a separate page from your OpenAI consumption on Foundry. Fetch your current Foundry-issued rates and plug them in. Run both reports side by side during migration so total spend stays visible.

```python
import statistics

# 1. Schema parity (hard): both providers must emit the expected tool with
# arguments that validate against its declared JSON Schema.
tool_rows = [r for r in EVAL_ROWS if "tools" in r]
schema_parity_hits = []

for row in tool_rows:
    o_names = {n for n, _ in results["openai"][row["id"]]["tool_calls"]}
    a_names = {n for n, _ in results["anthropic"][row["id"]]["tool_calls"]}
    openai_result = results["openai"][row["id"]]
    anthropic_result = results["anthropic"][row["id"]]
    openai_contract = tool_calls_meet_contract(
        row["tools"], row["expected_tool"], openai_result.get("tool_calls", []),
        openai_result.get("error"),
    )
    anthropic_contract = tool_calls_meet_contract(
        row["tools"], row["expected_tool"], anthropic_result.get("tool_calls", []),
        anthropic_result.get("error"),
    )
    schema_parity_hits.append(openai_contract and anthropic_contract and o_names == a_names)
schema_parity_rate = (sum(schema_parity_hits) / len(schema_parity_hits)
                      if schema_parity_hits else 1.0)

# 2. Structured-output retry rate (hard).
json_rows = [r for r in EVAL_ROWS if "json_schema" in r]
retry_rate = (
    sum(results["anthropic"][r["id"]].get("retries", 0) for r in json_rows)
    / max(1, len(json_rows))
)

# 3. Quality on plain text (soft): Jaccard token overlap vs `expected`.
text_rows = [r for r in EVAL_ROWS if "expected" in r]
baseline_q  = statistics.mean(
    jaccard(results["openai"][r["id"]]["text"], r["expected"]) for r in text_rows
)
candidate_q = statistics.mean(
    jaccard(results["anthropic"][r["id"]]["text"], r["expected"]) for r in text_rows
)

# 4. Latency P90 across all rows.
def p90(xs): return sorted(xs)[max(0, int(0.9 * len(xs)) - 1)]
base_p90 = p90([results["openai"][r["id"]]["latency_s"]    for r in EVAL_ROWS])
cand_p90 = p90([results["anthropic"][r["id"]]["latency_s"] for r in EVAL_ROWS])

gates = [
    ("Schema parity (tool rows)",       schema_parity_rate == 1.0,
     f"{schema_parity_rate*100:.0f}% match"),
    ("Structured retry rate (cap 10%)", retry_rate <= 0.10,
     f"{retry_rate*100:.0f}% retries"),
    ("Quality (>= baseline - 0.05)",    candidate_q >= baseline_q - 0.05,
     f"baseline {baseline_q:.2f} | candidate {candidate_q:.2f}"),
    ("P90 latency (<= 1.3x baseline)",  cand_p90 <= base_p90 * 1.3,
     f"baseline {base_p90:.2f}s | candidate {cand_p90:.2f}s"),
]

print("=" * 72)
print(f"  {'GATE':<36} {'STATUS':<8} DETAIL")
print("-" * 72)
for name, passed, detail in gates:
    print(f"  {name:<36} {'PASS' if passed else 'FAIL':<8} {detail}")
print("-" * 72)
overall = all(p for _, p, _ in gates)
print(f"  OVERALL: {'PASS. Safe to start the side-by-side test on real traffic.' if overall else 'FAIL. Do not promote.'}")
print("=" * 72)
```

## How to read the gate output

A FAIL on this 8-row demo set is *usually* one of three things: small-sample noise, prompt overhead the adapter adds, or a genuine model-behavior difference. Each gate has a typical failure mode and a specific triage step. Run the diagnostic cell below first for any latency FAIL, then use this table for the rest.

| Gate that failed | Most common cause on N=8 | What to do |
|---|---|---|
| **Schema parity** | Claude returned a prose hedge instead of calling the tool (e.g. "I don't have access to live weather…") | Real provider-behavior difference. Tighten the user prompt with an explicit "use the tool" instruction, or accept and add a 1-retry budget on tool rows in production. |
| **Structured retry rate** | One JSON row came back with a stray code fence or extra prose | Inspect `results["anthropic"]["json-X"]["retries"]`. >0 retries on >5% of rows means the prompt needs an Anthropic-specific compile (separate pass). |
| **Quality (Jaccard)** | Only 4 text rows; one different word choice swings the mean by 0.05+ | Re-run the eval cell. If quality flips between PASS and FAIL on three back-to-back runs, it's noise; move to a 50–100 row set and swap in `azure-ai-evaluation.SimilarityEvaluator`. If the gap is consistent, it's real. |
| **P90 latency** | N=8 means P90 = the 7th-slowest row. One cold start or the heavier JSON prompt dominates. | Run the diagnostic cell below. If P50 is within 1.5× but P90 is over 1.3×, it's tail noise. If P50 is also high, it's a real workload-shape issue (see "Making a real promotion decision" below). |

### Why this notebook trips its own gates more than you'd expect

Two structural reasons, both worth understanding before you change the thresholds:

**1. N=8 is below the noise floor of these metrics.** P90 of 8 samples is "the 7th-slowest row"; a single slow response can flip it. Jaccard averaged over 4 rows shifts by 0.05+ when Claude picks "platform" vs "service." This is a teaching set, not a production set. The fix is more rows, not looser thresholds.

**2. The Anthropic JSON path is genuinely heavier than the OpenAI one.** Because Anthropic has no `strict:true` mode, the adapter appends the JSON schema text to the user message and adds a "return JSON only" suffix to the system prompt. That's typically **+150–400 input tokens per JSON row** vs the OpenAI `response_format` path. With 2 of 8 rows being JSON, the extra tokens drag P90 on the Claude side. In production you'd pin the schema text behind `cache_control` so it's effectively free after the first call.

The diagnostic cell below prints **per-row latency for both providers** plus **P50 vs P90 side by side**. Use it to separate the two situations above before deciding whether the FAIL is noise or signal.

```python
# Latency diagnostic: if the P90 gate failed, find which row dominates.
# Shows per-row latency for both providers plus the P50/P90 spread.

print(f"  {'id':<8} {'kind':<6} {'gpt-5.5':<10} {'opus-4-8':<10} ratio")
print("-" * 50)
for row in EVAL_ROWS:
    rid  = row["id"]
    o    = results["openai"][rid]["latency_s"]
    a    = results["anthropic"][rid]["latency_s"]
    kind = "tool" if "tools" in row else "json" if "json_schema" in row else "text"
    ratio = a / o if o > 0 else float("inf")
    print(f"  {rid:<8} {kind:<6} {o:<10.2f} {a:<10.2f} {ratio:.1f}x")

# Compare medians to means: if P50 is fine but P90 fails, the tail is the problem.
import statistics
oai_lat  = [results["openai"][r["id"]]["latency_s"]    for r in EVAL_ROWS]
anth_lat = [results["anthropic"][r["id"]]["latency_s"] for r in EVAL_ROWS]
print()
print(f"  P50  gpt-5.5 {statistics.median(oai_lat):.2f}s   opus-4-8 {statistics.median(anth_lat):.2f}s")
print(f"  P90  gpt-5.5 {base_p90:.2f}s              opus-4-8 {cand_p90:.2f}s")
print(f"  Ratio P50 = {statistics.median(anth_lat)/statistics.median(oai_lat):.1f}x   "
      f"Ratio P90 = {cand_p90/base_p90:.1f}x")

```

## Making a real promotion decision

If this notebook says **PASS** on a clean run, that means `claude-opus-4-8` cleared every gate on **8 toy prompts**. It does **not** yet mean it's a good fit for your workload. To turn this notebook into a real decision, do these four things in order:

**1. Run a bigger eval set.** Eight rows is not enough for a stable P90; one slow row dominates the metric. Replace `EVAL_ROWS` in the eval-set cell above with **50–100 prompts** that look like your production traffic. The harness, gates, and code path stay the same; only the data changes. For larger sets, create your own eval file (e.g. an `eval.jsonl` next to the notebook) and load it in place of the inline list.

**2. Use prompts that match your actual workload.** If you run a chatbot doing one-line replies, an 8-row long-context legal-analysis eval will mislead you. If you run an agent loop with heavy tool use, gating on plain-text Jaccard won't tell you what you need to know. Bring your real prompts to this harness.

**3. If opus still misses the latency gate, decide consciously, don't auto-fail.** `claude-opus-4-8` is a heavier model than `gpt-5.5`; on short prompts it tends to be noticeably slower per call without extended thinking. Measure your own workload; the gap varies materially by prompt shape, region, and load. Whether that's a blocker depends on workload shape:

| Workload | What usually happens | Path forward |
|---|---|---|
| Short prompts, short answers | opus loses on latency | Relax the gate (e.g. `<= 2.0×`), keep gpt-5.5 for this path, or accept the trade-off |
| Long context (10K+ input tokens) | gap closes; often within 1.2× | Pass as-is |
| Heavy reasoning where gpt-5.5 already runs `reasoning_effort=high` | roughly a wash | Pass as-is |
| Tool-heavy agent loops | comparable end-to-end; opus often faster | Pass as-is |
| Streaming chat UX | time-to-first-token is close; only total time differs | Gate on TTFT, not total |

**4. Test streaming separately when UX is what's actually on the line.** For any user-facing chat, perceived latency is **time-to-first-token**, not total response time. Use the streaming cell earlier in this notebook to measure TTFT directly; the streaming gap between providers is much smaller than the total-time gap.

**Bottom line:** a green gate on these 8 demo rows is permission to start a real side-by-side test with your own prompts. It is not permission to flip `PROVIDER=anthropic` in production.

## Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `401` on Anthropic calls | Wrong Entra audience (`cognitiveservices.azure.com` instead of `ai.azure.com`) | Build a separate token provider per audience (see the "Configure" code cell that builds the two clients) |
| `404` from Anthropic SDK | Used the stock `Anthropic` class against the Foundry URL | Use `AnthropicFoundry` |
| `Marketplace agreement required` on first deploy | Tenant has not accepted the Anthropic Marketplace agreement | Have an admin accept once for the tenant |
| `429` storms | PAYG opus baseline starts low (single-digit RPM range in many regions) | Request an increase from your Foundry portal's quota page; SDK retries from your OpenAI wrapper do **not** carry over |
| Anthropic returns prose, not JSON | No strict mode | Use the validate-and-retry helper from the structured outputs section |
| `thinking` block leaks to end users | Rendering the whole `content` array | Filter `b.type == "text"` before display |
| Tool calls silently dropped after porting | `tool_result` sent as `role:"tool"` instead of a user message with a `tool_result` block | Use the adapter; never wrap tool results by hand |

## Best practices

- **Keep the adapter even after you've fully switched over.** The next provider arrives faster than the last one did.
- **Don't optimize the prompt yet.** Prove parity on the unchanged prompt first; per-provider prompt tuning is a separate pass.
- **Use `cache_control` on system prompts >2K tokens.** Cache reads are excluded from input-TPM and are significantly cheaper than uncached input on hits. Confirm the exact discount in your current Foundry pricing for Claude.
- **Start `output_config.effort` at `medium`.** Raise to `high` for agent loops; only raise further if your eval shows a measurable quality lift; thinking tokens are billed.
- **Strip `thinking` blocks before render.** They are for the model, not the user.
- **Run two cost reports during migration.** Claude rolls up under Azure Marketplace (CCU); your OpenAI deployments on Foundry roll up under Foundry consumption. Reconcile both.

## Rollout

A four-stage rollout, with explicit rollback triggers:

1. **Side-by-side test.** Adapter live, `PROVIDER=openai` everywhere (users still see gpt-5.5). Send every Nth request *also* to claude-opus-4-8 in the background; score offline. Run ≥ 1 week. No customer impact.
2. **Gradual switch.** Start sending real user traffic to `PROVIDER=anthropic`: 5% → 25% → 50% → 100%, ≥ 1 week per step. Watch the gates from the promotion-gate section *plus* operational metrics.
3. **New default.** Flip the cohort default to `claude-opus-4-8`. Keep the gpt-5.5 deployment alive as the rollback target.
4. **Retire.** After 30 clean days at 100%, delete or repurpose the gpt-5.5 deployment.

**Roll back if:** tool-shape parity <99.5% over any hour, structured-output retry rate >10% over any hour, P99 latency >2× baseline for >15 minutes, or any 5xx rate >0.5% over 5 minutes.

## Hand it to a coding agent

When you're ready to apply this to a real codebase, paste this into your agent:

> You are migrating this app from `gpt-5.5` to `claude-opus-4-8`. Both are Foundry deployments on the same resource. Do the smallest set of changes that lets `PROVIDER=anthropic` work end-to-end behind a feature flag.
>
> 1. Add `anthropic>=0.55` to requirements; do not bump other versions. `AnthropicFoundry` ships in that package.
> 2. Introduce a `Conversation` dataclass (system, messages[], tools[], optional thinking + effort) and refactor every chat completion call site to build one and call `adapter.run(conv)`.
> 3. Add `OpenAIAdapter` and `AnthropicAdapter` behind a `PROVIDER` env var. Default `PROVIDER=openai`.
> 4. Translate tool schemas using `openai_tools_to_anthropic()`; wrap tool results per provider.
> 5. Post-hoc JSON-schema validation on the Anthropic path with a retry budget of 1.
> 6. Route all stream consumers through the `StreamEvent` normalizer.
> 7. Add a second Entra token provider with audience `https://ai.azure.com/.default` for the Anthropic path. Keep the existing `cognitiveservices.azure.com` provider for the OpenAI path.
> 8. Update network allowlists for the Foundry host.
> 9. Run this notebook in CI; gate merges on PASS.
>
> Do **not**: modify business prompts, change retry/timeout defaults, touch the gpt-5.5 deployment, delete `gpt-5.5`, or use the stock `Anthropic` SDK class (use `AnthropicFoundry`).

## Cleanup

Nothing in this notebook created resources. **Do not delete the `gpt-5.5` deployment yet.** Keep it alive as the rollback target through the four-stage rollout above. Once you have 30 clean days at 100% on claude-opus-4-8, decommission `gpt-5.5` and update cost dashboards to drop the OpenAI-on-Foundry columns in favor of the Marketplace / CCU column.

---

### Takeaway

A cross-provider migration is one adapter, two SDKs, and one extra Entra audience. The adapter is the artifact worth keeping; the next provider arrives faster than the last one did.

### See also

- [Microsoft Learn: Use Claude models in Foundry Models](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-claude?tabs=python)
- [Microsoft Learn: Claude models in Foundry Models (concepts)](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models?tabs=pay-go)
- [Azure-Samples/claude](https://github.com/Azure-Samples/claude): `azd up` starter that provisions the resource, deployments, and Entra wiring