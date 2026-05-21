## MAI-Transcribe-1: Build a Robust Speech-to-Text Recipe

**Problem this recipe solves:** You need a production-ready transcription pipeline that handles diarization, prompt-tuning, translation, and clear failure modes — without trial-and-error against an unfamiliar endpoint. The wrapper degrades gracefully when the endpoint rejects newer payload options.

**Who this is for:** Developers shipping voice-of-customer, contact-center, or media-indexing workloads on Microsoft Foundry.

**Reusable pattern:** Wrap the Foundry `speechtotext/transcriptions:transcribe` REST call once with progressive `enhancedMode` fallback, then layer on diarization, lexical mode, domain prompting, and translation by injecting `extra_definition` overrides.

**You will produce:**
- a `transcribe_audio(...)` helper that survives endpoint capability differences across `enhancedMode.model`, `enhancedMode`, and plain mode payloads
- side-by-side results: basic vs lexical vs domain-tuned vs translated
- a cached evidence artifact at `data/mai-transcribe-1-foundry/evidence.json`


### Recipe flow (what to run and what to watch)

1. Run setup + auth (cells in §1). Confirm `Auth mode` printout and that token claims show your `oid` / `tid`.
2. Pick a local audio file (§2). The recipe expects 16 kHz mono WAV/MP3/FLAC under ~70 MB.
3. Run §3 (basic transcript) first — this validates endpoint, auth, file format, and capability fallbacks before you spend time on advanced options.
4. Layer §4 (segments + timestamps), §5 (diarization), §6 (prompt-tuning), §7 (translation). Each section is independent; you can pick and choose.
5. Run §8 (Entra auth), §9 (cost), §10 (evidence) before opening a PR or sharing results.

**Watch for:**
- `401/403` → your Entra principal lacks `Cognitive Services User` on the Foundry account.
- `400 Enhanced mode … not supported` → the wrapper auto-retries without `enhancedMode.model`, then without `enhancedMode` entirely.
- Empty `combinedPhrases` → the audio file may be silent, mono-only, or in a sample rate the service refuses.
- Costs creeping in batch jobs → run §9 first so you know exactly what 100 audio hours costs.


## 1. Setup

Install dependencies and load environment variables from `deployment.env`.

**What this does:** loads env vars from `deployment.env`, builds the request headers, and prints the auth principal so you can verify RBAC quickly.

**Watch for:** if `oid` prints `unknown`, your token didn't carry an object ID — re-run `az login` and clear any stale service principal env vars.


```python
# Install dependencies (run once)
# %pip install -q requests python-dotenv azure-identity
```

```python
import os
import base64
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

# Load credentials from deployment.env
load_dotenv(dotenv_path="deployment.env", override=True)

TRANSCRIBE_SPEECH_KEY = (
    os.getenv("TRANSCRIBE_SPEECH_KEY")
    or os.getenv("AZURE_SPEECH_KEY")
    or os.getenv("AZURE_FOUNDRY_API_KEY")
    or os.getenv("SPEECH_KEY")
)
TRANSCRIBE_SPEECH_REGION = os.getenv("TRANSCRIBE_SPEECH_REGION") or os.getenv("SPEECH_REGION", "eastus")
TRANSCRIBE_SPEECH_ENDPOINT = (
    os.getenv("TRANSCRIBE_SPEECH_ENDPOINT")
    or os.getenv("AZURE_SPEECH_ENDPOINT")
    or os.getenv("AZURE_FOUNDRY_ENDPOINT")
)
USE_ENTRA_AUTH = os.getenv("USE_ENTRA_AUTH", "true").lower() == "true"

# Backward-compatible aliases used in later cells
SPEECH_KEY = TRANSCRIBE_SPEECH_KEY
SPEECH_REGION = TRANSCRIBE_SPEECH_REGION

assert TRANSCRIBE_SPEECH_ENDPOINT, "Set AZURE_FOUNDRY_ENDPOINT or TRANSCRIBE_SPEECH_ENDPOINT in deployment.env"
if not USE_ENTRA_AUTH:
    assert TRANSCRIBE_SPEECH_KEY, "Set AZURE_FOUNDRY_API_KEY or TRANSCRIBE_SPEECH_KEY in deployment.env when USE_ENTRA_AUTH=false"

# Foundry project/account endpoint sample pattern:
#   https://<foundry-account>.cognitiveservices.azure.com/speechtotext/transcriptions:transcribe?api-version=2025-10-15
TRANSCRIBE_URL = (
    f"{TRANSCRIBE_SPEECH_ENDPOINT.rstrip('/')}"
    "/speechtotext/transcriptions:transcribe"
    "?api-version=2025-10-15"
)

token_provider = None
if USE_ENTRA_AUTH:
    for env_var in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"):
        if os.getenv(env_var) == "":
            os.environ.pop(env_var, None)
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default"
    )

def decode_current_token_claims() -> dict:
    if not USE_ENTRA_AUTH:
        return {}
    token = token_provider()
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))

def build_auth_headers() -> dict:
    if USE_ENTRA_AUTH:
        return {"Authorization": f"Bearer {token_provider()}"}
    return {"Ocp-Apim-Subscription-Key": TRANSCRIBE_SPEECH_KEY}

print(f"✅ Endpoint : {TRANSCRIBE_URL}")
print(f"✅ Region   : {TRANSCRIBE_SPEECH_REGION}")
print(f"✅ Auth mode: {'DefaultAzureCredential (Bearer token)' if USE_ENTRA_AUTH else 'API key'}")
if USE_ENTRA_AUTH:
    claims = decode_current_token_claims()
    print(f"✅ Token principal oid: {claims.get('oid', 'unknown')}")
    print(f"✅ Token tenant id   : {claims.get('tid', 'unknown')}")
    print("ℹ️ Required RBAC role on Foundry account: Cognitive Services Speech User")
```

## 2. Helper: Use Local Audio Files

Use local WAV files from the folder configured in `deployment.env` as `TRANSCRIBE_LOCAL_AUDIO_DIR`.
Example: `TRANSCRIBE_LOCAL_AUDIO_DIR=C:\Flutter\azure-transcription\demodata`
Set `AUDIO_FILE` manually if you want to force a specific file.

**What this does:** picks a real `.wav` from a local folder so you have a deterministic input across runs. Set `TRANSCRIBE_LOCAL_AUDIO_DIR` in `deployment.env`.


```python
from pathlib import Path
import os

LOCAL_AUDIO_DIR_ENV = os.getenv("TRANSCRIBE_LOCAL_AUDIO_DIR")
assert LOCAL_AUDIO_DIR_ENV, (
    "Set TRANSCRIBE_LOCAL_AUDIO_DIR in deployment.env, e.g. C:\\Flutter\\azure-transcription\\demodata"
 )

LOCAL_AUDIO_DIR = Path(LOCAL_AUDIO_DIR_ENV).expanduser()
PREFERRED_FILES = [
    "sampledata_audiofiles_katiesteve.wav",
    "conversationrecording_new.wav",
]

assert LOCAL_AUDIO_DIR.exists(), f"Local audio folder not found: {LOCAL_AUDIO_DIR}"

available_wavs = sorted(LOCAL_AUDIO_DIR.glob("*.wav"))
assert available_wavs, f"No .wav files found in: {LOCAL_AUDIO_DIR}"

# Prefer known demo files, then fall back to the first WAV in the folder.
selected_audio = None
for name in PREFERRED_FILES:
    candidate = LOCAL_AUDIO_DIR / name
    if candidate.exists():
        selected_audio = candidate
        break
if selected_audio is None:
    selected_audio = available_wavs[0]

AUDIO_FILE = str(selected_audio)
file_size_mb = selected_audio.stat().st_size / (1024 * 1024)

print(f"✅ Using local audio: {AUDIO_FILE} ({file_size_mb:.2f} MB)")
print("Available WAV files:")
for wav in available_wavs:
    print(f" - {wav.name}")
```

## 3. Basic Transcription with MAI-Transcribe-1

The simplest call: send an audio file → receive a full transcript.

**What this does:** the core `transcribe_audio(...)` helper. It tries the rich payload first, then falls back when the endpoint rejects `enhancedMode.model` or `enhancedMode`. This is the reusable pattern — keep this helper, layer different `extra_definition` dicts on top.


```python
import mimetypes
from copy import deepcopy

def transcribe_audio(audio_path: str, extra_definition: dict | None = None) -> dict:
    """Transcribe an audio file with robust fallback for endpoint capability differences."""
    definition = {
        "locales": ["en-US"],
        "diarization": {
            "enabled": True,
            "maxSpeakers": 2,
        },
        "enhancedMode": {
            "enabled": True,
            "model": "mai-transcribe-1"
        }
    }
    if extra_definition:
        definition.update(extra_definition)

    audio_path_obj = Path(audio_path)
    file_size_bytes = audio_path_obj.stat().st_size
    if file_size_bytes > 70 * 1024 * 1024:
        raise ValueError(f"Audio file exceeds 70MB limit for mai-transcribe-1: {audio_path_obj} ({file_size_bytes / (1024*1024):.2f} MB)")

    mime_type = mimetypes.guess_type(audio_path_obj.name)[0] or "application/octet-stream"

    def _call(headers: dict, request_definition: dict):
        with open(audio_path, "rb") as audio_file:
            return requests.post(
                TRANSCRIBE_URL,
                headers=headers,
                files={
                    "audio":      (audio_path_obj.name, audio_file, mime_type),
                    "definition": (None, json.dumps(request_definition), "application/json"),
                },
            )

    active_definition = definition
    response = _call(build_auth_headers(), active_definition)

    # Foundry endpoint compatibility fallback:
    # some endpoints reject enhancedMode.model or enhancedMode entirely.
    if (
        (not response.ok)
        and response.status_code == 400
        and "Enhanced mode with model is currently not supported yet" in response.text
        and isinstance(active_definition.get("enhancedMode"), dict)
        and active_definition["enhancedMode"].get("model")
    ):
        active_definition = deepcopy(active_definition)
        active_definition["enhancedMode"].pop("model", None)
        print("⚠️ Endpoint does not support enhancedMode.model yet; retrying without model.")
        response = _call(build_auth_headers(), active_definition)

    # Some endpoints reject enhancedMode altogether.
    if (
        (not response.ok)
        and response.status_code == 400
        and "Enhanced mode is currently not supported yet" in response.text
        and isinstance(active_definition.get("enhancedMode"), dict)
    ):
        active_definition = deepcopy(active_definition)
        active_definition.pop("enhancedMode", None)
        print("⚠️ Endpoint does not support enhancedMode; retrying with standard transcription definition.")
        response = _call(build_auth_headers(), active_definition)

    # Optional safety fallback: if token mode fails and key is present, retry once with key.
    if (not response.ok) and USE_ENTRA_AUTH and TRANSCRIBE_SPEECH_KEY:
        fallback = _call({"Ocp-Apim-Subscription-Key": TRANSCRIBE_SPEECH_KEY}, active_definition)
        if fallback.ok:
            print("⚠️ Bearer-token request failed; API-key fallback succeeded for this call.")
            return fallback.json()
        response = fallback

    if not response.ok:
        if USE_ENTRA_AUTH and response.status_code in (401, 403):
            claims = decode_current_token_claims()
            oid = claims.get("oid", "unknown")
            raise requests.HTTPError(
                f"Transcription request failed with {response.status_code}: {response.text}\n"
                "Entra auth troubleshooting:\n"
                f"- Token principal oid: {oid}\n"
                "- Required role on the Foundry account: Cognitive Services Speech User\n"
                "- Required data action: Microsoft.CognitiveServices/accounts/SpeechServices/speechrest/transcriptions/action\n"
                "- For token auth, set AZURE_FOUNDRY_ENDPOINT (or TRANSCRIBE_SPEECH_ENDPOINT) to https://<foundry-account>.cognitiveservices.azure.com",
                response=response,
            )
        raise requests.HTTPError(
            f"Transcription request failed with {response.status_code}: {response.text}",
            response=response,
        )

    return response.json()


result = transcribe_audio(AUDIO_FILE)

print("=" * 60)
print("TRANSCRIPT")
print("=" * 60)
for phrase in result.get("combinedPhrases", []):
    print(phrase["text"])

duration_ms = result.get("durationMilliseconds", 0)
print(f"\nAudio duration: {duration_ms / 1000:.2f}s")
```

## 4. Segment-Level Details (Words + Timestamps)

The `phrases` array gives per-segment detail with word-level timestamps.

**Why it matters:** segment-level timings drive captions, search, and clip extraction. Use the `phrases` array for timestamps; use `combinedPhrases` for the full transcript.


```python
phrases = result.get("phrases", [])

for i, phrase in enumerate(phrases, 1):
    offset  = phrase.get("offsetMilliseconds", 0) / 1000
    dur     = phrase.get("durationMilliseconds", 0) / 1000
    text    = phrase.get("text", "")
    words   = phrase.get("words", [])

    print(f"[{offset:.2f}s – {offset + dur:.2f}s] {text}")
    for w in words[:5]:          # show first 5 words per phrase
        w_off = w["offsetMilliseconds"] / 1000
        w_dur = w["durationMilliseconds"] / 1000
        print(f"  {w['text']!r:20s}  @{w_off:.3f}s  ({w_dur*1000:.0f}ms)")
    if len(words) > 5:
        print(f"  ... and {len(words) - 5} more words")
```

## 5. Speaker Diarization

Identify who is speaking. Enable `diarization` in the request definition.

**Watch for:** diarization is **not** supported with `mai-transcribe-1` directly. Omit the `model` key (defaults to LLM speech) when you need speaker labels.


```python
# Note: diarization is NOT supported with mai-transcribe-1 model directly.
# Use the standard LLM speech (enhanced mode) for diarization.

diarization_definition = {
    "enhancedMode": {
        "enabled": True,
        "task": "transcribe"
        # model key omitted → uses default LLM speech (not mai-transcribe-1)
        # Add  "model": "mai-transcribe-1"  to use MAI model (diarization unsupported)
    },
    "diarization": {
        "enabled": True,
        "maxSpeakers": 2
    },
    "profanityFilterMode": "Masked"
}

diar_result = transcribe_audio(AUDIO_FILE, extra_definition=diarization_definition)

for phrase in diar_result.get("phrases", []):
    speaker = phrase.get("speaker", "?")
    offset  = phrase.get("offsetMilliseconds", 0) / 1000
    text    = phrase.get("text", "")
    print(f"Speaker {speaker}  [{offset:.2f}s]  {text}")
```

## 6. Prompt-Tuning for Custom Output

Guide output style with a prompt — enforce lexical format, highlight phrases, etc.

**Why it matters:** prompts steer formatting (lexical vs display) and recognize domain terms (`Azure`, `Foundry`, `MAI`, custom acronyms). Combine prompt + lexical for raw downstream NLP.


```python
# Lexical format: raw words without punctuation/capitalization
lexical_definition = {
    "enhancedMode": {
        "enabled": True,
        "model": "mai-transcribe-1",
        "task": "transcribe",
        "prompt": ["Output must be in lexical format."]
    }
}

lexical_result = transcribe_audio(AUDIO_FILE, extra_definition=lexical_definition)

print("Lexical output:")
for phrase in lexical_result.get("combinedPhrases", []):
    print(phrase["text"])
```

```python
# Highlight specific domain terms / acronyms for better recognition
domain_definition = {
    "enhancedMode": {
        "enabled": True,
        "model": "mai-transcribe-1",
        "task": "transcribe",
        "prompt": [
            "Pay attention to Azure, Microsoft Foundry, MAI, Copilot, LLM."
        ]
    }
}

domain_result = transcribe_audio(AUDIO_FILE, extra_definition=domain_definition)

print("Domain-tuned transcript:")
for phrase in domain_result.get("combinedPhrases", []):
    print(phrase["text"])
```

## 7. Translation to Another Language

LLM Speech can translate audio directly to a target language.

**What this does:** swaps `task` to `translate` and sets `targetLanguage`. Supported: `en, zh, de, fr, it, ja, es, pt, ko`.


```python
# Translate audio to Korean
translate_definition = {
    "enhancedMode": {
        "enabled": True,
        "task": "translate",
        "targetLanguage": "ko"
        # Supported: en, zh, de, fr, it, ja, es, pt, ko
    }
}

translate_result = transcribe_audio(AUDIO_FILE, extra_definition=translate_definition)

print("Korean translation:")
for phrase in translate_result.get("combinedPhrases", []):
    print(phrase["text"])
```

## 8. Using Microsoft Entra ID Authentication (Production)

For production workloads, use managed identity instead of API keys.

**Why it matters:** API keys work in dev, but production should use `DefaultAzureCredential` + RBAC on the Foundry account.


```python
print("✅ This notebook now uses DefaultAzureCredential by default.")
print("Set USE_ENTRA_AUTH=false in deployment.env to force API key mode.")
```

## 9. 💰 Cost Calculator

**MAI-Transcribe-1 pricing: \$0.36 per audio hour**

This is approximately **50% lower** than comparable alternatives.

**Watch for:** the calculator uses `$0.36 / audio hour`. Run this **before** processing large archives.


```python
# ── Cost Calculator ─────────────────────────────────────────
PRICE_PER_HOUR = 0.36   # USD per audio hour (as of April 2026)

# Edit the inputs below:
scenarios = {
    "1-hour call center recording": 1.0,
    "Full workday meetings (8 hrs)":   8.0,
    "Video archive batch (100 hrs)":  100.0,
    "Annual call center (~5000 hrs)": 5000.0,
}

print(f"{'Scenario':<45} {'Audio Hours':>12} {'Cost (USD)':>12}")
print("-" * 71)
for label, hours in scenarios.items():
    cost = hours * PRICE_PER_HOUR
    print(f"{label:<45} {hours:>12.1f} ${cost:>11.2f}")

print()
print("Comparison vs. leading alternatives (~$0.72/hr)")
alt_price = 0.72
print(f"{'Scenario':<45} {'Saving (USD)':>12} {'Saving %':>10}")
print("-" * 69)
for label, hours in scenarios.items():
    saving = hours * (alt_price - PRICE_PER_HOUR)
    pct    = (1 - PRICE_PER_HOUR / alt_price) * 100
    print(f"{label:<45} ${saving:>11.2f} {pct:>9.0f}%")
```

## 10. Summary & Next Steps

| Feature | Status |
|---|---|
| Basic transcription | ✅ |
| Word-level timestamps | ✅ |
| Speaker diarization | ✅ (LLM speech mode) |
| Prompt-tuning | ✅ |
| Translation | ✅ |
| Real-time transcription | 🔜 Coming soon |
| Context biasing | 🔜 Coming soon |

**Resources:**
- [Model Card](https://ai.azure.com/catalog/models/MAI-Transcribe-1)
- [LLM Speech API docs](https://learn.microsoft.com/azure/ai-services/speech-service/llm-speech)
- [Azure Speech regions](https://learn.microsoft.com/azure/ai-services/speech-service/regions)
- [MAI Playground](https://playground.microsoft.ai)

Use this checklist when promoting the helper into your own service.


## 11. Evidence Pack

This cell captures a reproducible manifest so reviewers can verify which transcript fragments your run produced. The sample audio used in this notebook is included for reference at `media/mai-transcribe-1-foundry/sampledata_audiofiles_katiesteve.wav`.

**What to watch:** if a sample is empty, that section of the notebook errored or returned no phrases — re-run that cell before publishing.


```python
from datetime import datetime
from pathlib import Path
import json

def _first_phrase(payload):
    if not payload:
        return ""
    phrases = payload.get("combinedPhrases", [])
    if not phrases:
        return ""
    return phrases[0].get("text", "")

EVIDENCE_PATH = Path("data/mai-transcribe-1-foundry/evidence.json")
EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

evidence = {
    "generated_at_utc": datetime.utcnow().isoformat() + "Z",
    "sample_audio": "media/mai-transcribe-1-foundry/sampledata_audiofiles_katiesteve.wav",
    "basic_transcript_sample": _first_phrase(globals().get("result")),
    "lexical_sample": _first_phrase(globals().get("lexical_result")),
    "domain_tuned_sample": _first_phrase(globals().get("domain_result")),
    "translation_sample": _first_phrase(globals().get("translate_result")),
    "diarization_speakers_detected": sorted({
        p.get("speaker")
        for p in (globals().get("diar_result", {}).get("phrases", []))
        if p.get("speaker") is not None
    }),
}

EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

print(f"✅ Evidence saved: {EVIDENCE_PATH}")
print("\nBefore/after sample:")
print(f"- Basic   : {evidence['basic_transcript_sample'][:160]}")
print(f"- Lexical : {evidence['lexical_sample'][:160]}")
print(f"- Domain  : {evidence['domain_tuned_sample'][:160]}")
print(f"- Korean  : {evidence['translation_sample'][:160]}")
print(f"- Speakers: {evidence['diarization_speakers_detected']}")

```

## 12. Failure Modes and Fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` / `403` from the transcribe endpoint | Token principal lacks `Cognitive Services User` on the Foundry account | Assign the role on the Foundry account, then re-run after the token refreshes (`az logout && az login` if needed) |
| `400 Enhanced mode with model is currently not supported yet` | Endpoint version doesn't accept `enhancedMode.model` | The wrapper auto-retries without the `model` key — no change required |
| `400 Enhanced mode is currently not supported yet` | Endpoint rejects `enhancedMode` entirely | Wrapper retries with the plain payload — verify your deployment region supports the rich mode you actually need |
| `404` for the audio file | Path issue in `TRANSCRIBE_LOCAL_AUDIO_DIR` | Confirm the file is `.wav`/`.mp3`/`.flac`, under ~70 MB, and reachable from the notebook working directory |
| Empty `combinedPhrases` | Silent file, unsupported sample rate, or wrong language | Convert to 16 kHz mono PCM; double-check the `locales` list matches the spoken language |
| Surprise bills on backfill jobs | Forgot to run §9 first | Run the cost calculator with your real audio-hour estimate before launching the batch |
| Diarization missing speaker labels | `mai-transcribe-1` doesn't support diarization | Omit `model` (falls back to LLM speech) when you need speaker IDs |


## 13. Takeaway Artifact

Reuse two things from this recipe in your own services:

1. **`transcribe_audio(...)`** — the helper with progressive `enhancedMode` fallback. Drop it in your codebase as-is; only change the headers / endpoint resolution.
2. **`data/mai-transcribe-1-foundry/evidence.json`** — the cached manifest pattern. Replicate it for every transcription job to give reviewers and downstream teams a paper trail of what you ran and what came back.
