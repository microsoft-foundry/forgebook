## Build a Production-Ready Text-to-Speech Recipe with MAI-Voice-1

**Problem this recipe solves:** You need expressive, low-latency TTS on Foundry that supports plain text, SSML emotion/prosody, batch long-form narration, and the Azure Speech SDK — all wired through a single endpoint and credential.

**Who this is for:** Developers shipping IVR, audiobook, character voice, or notification audio on Microsoft Foundry.

**Reusable pattern:** Authenticate once against the Foundry endpoint, then call a single `synthesize_to_file(...)` helper with progressively richer SSML payloads. The same helper handles plain text, emotion styles, prosody adjustments, and 4 KB+ long-form blocks.

**You will produce:**
- five reference audio files saved to `media/mai-voice-1-foundry/` (basic, emotion, prosody, SDK, long-form)
- a `data/mai-voice-1-foundry/evidence.json` manifest with file sizes and synthesis metadata
- a copyable SSML template you can re-use for every voice in the MAI catalog


### Recipe flow (what to run and what to watch)

1. Run §1 setup — confirms env vars, picks the voice (`en-us-Grant:MAI-Voice-1` by default), and prints the auth mode.
2. Run §2 (basic REST) first. If this works, the rest of the notebook will work — endpoint + auth are validated.
3. Run §3 (emotion) and §4 (prosody) for tone control. These are the patterns to copy into product SSML.
4. Run §5 (Azure Speech SDK) only if you need streaming or audio-output devices; otherwise REST is simpler.
5. Run §6 (voice prompting concept) for awareness — full custom voice cloning lives in the Personal Voice API.
6. Run §7 for long-form (>1 minute). Use chunking + concat if blocks exceed ~5 KB.
7. Run §8 (cost calculator) before generating thousands of files.
8. Run §9 evidence + §10 failure-modes when packaging for review.

**Watch for:**
- SDK returns `SynthesizingAudioCompleted` with **zero bytes** on some Foundry endpoints — the helper detects this and falls back to REST automatically.
- 401/403 → confirm `Cognitive Services User` on the Foundry account.
- File grows but won't play → wrong content type (request `audio-24khz-48kbitrate-mono-mp3`).


## 1. Setup

**What this does:** loads `deployment.env`, picks the voice name, and prints the auth principal so you can validate RBAC.

**Watch for:** if `MAI_VOICE_NAME` is unset, the notebook defaults to `en-us-Grant:MAI-Voice-1`. Browse the Foundry catalog for the full voice list.


```python
# %pip install -q azure-cognitiveservices-speech python-dotenv requests azure-identity
```

```python
import os
import io
import json
import base64
import time
import requests
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

import azure.cognitiveservices.speech as speechsdk

load_dotenv(dotenv_path="deployment.env", override=True)

VOICE_SPEECH_KEY = (
    os.getenv("VOICE_SPEECH_KEY")
    or os.getenv("AZURE_SPEECH_KEY")
    or os.getenv("AZURE_FOUNDRY_API_KEY")
    or os.getenv("SPEECH_KEY")
)
VOICE_SPEECH_REGION = os.getenv("VOICE_SPEECH_REGION") or os.getenv("SPEECH_REGION", "eastus")
VOICE_SPEECH_ENDPOINT = (
    os.getenv("VOICE_SPEECH_ENDPOINT")
    or os.getenv("AZURE_SPEECH_ENDPOINT")
    or os.getenv("AZURE_FOUNDRY_ENDPOINT")
)
AZURE_FOUNDRY_RESOURCE_ID = os.getenv("AZURE_FOUNDRY_RESOURCE_ID")
MAI_VOICE_NAME = os.getenv("MAI_VOICE_NAME", "en-us-Grant:MAI-Voice-1")
USE_ENTRA_AUTH = os.getenv("USE_ENTRA_AUTH", "true").lower() == "true"

# Backward-compatible aliases used in later cells
SPEECH_KEY = VOICE_SPEECH_KEY
SPEECH_REGION = VOICE_SPEECH_REGION

assert VOICE_SPEECH_ENDPOINT, "Set AZURE_FOUNDRY_ENDPOINT or VOICE_SPEECH_ENDPOINT in deployment.env"
if not USE_ENTRA_AUTH:
    assert VOICE_SPEECH_KEY, "Set AZURE_FOUNDRY_API_KEY or VOICE_SPEECH_KEY in deployment.env when USE_ENTRA_AUTH=false"
if USE_ENTRA_AUTH and not AZURE_FOUNDRY_RESOURCE_ID:
    print("⚠️ AZURE_FOUNDRY_RESOURCE_ID is not set. REST calls still work; SDK will use bearer-token fallback.")

# Foundry project/account endpoint sample pattern:
#   https://<foundry-account>.cognitiveservices.azure.com/tts/cognitiveservices/v1
TTS_ENDPOINT = f"{VOICE_SPEECH_ENDPOINT.rstrip('/')}/tts/cognitiveservices/v1"

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

def build_tts_headers(output_format: str) -> dict:
    headers = {
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": output_format,
        "User-Agent": "MAI-Voice-Demo",
    }
    if USE_ENTRA_AUTH:
        headers["Authorization"] = f"Bearer {token_provider()}"
    else:
        headers["Ocp-Apim-Subscription-Key"] = SPEECH_KEY
    return headers

def create_speech_config() -> speechsdk.SpeechConfig:
    parsed = urlparse(VOICE_SPEECH_ENDPOINT.rstrip('/'))
    base_endpoint = f"{parsed.scheme}://{parsed.netloc}"
    cfg = speechsdk.SpeechConfig(endpoint=base_endpoint)
    if USE_ENTRA_AUTH:
        if AZURE_FOUNDRY_RESOURCE_ID:
            cfg.authorization_token = f"aad#{AZURE_FOUNDRY_RESOURCE_ID}#{token_provider()}"
        else:
            cfg.authorization_token = token_provider()
        return cfg
    # Key mode fallback for environments where local auth is enabled.
    return speechsdk.SpeechConfig(subscription=SPEECH_KEY, region=SPEECH_REGION)

def ensure_voice_response_ok(response: requests.Response) -> None:
    if response.ok:
        return
    if USE_ENTRA_AUTH and response.status_code in (401, 403):
        claims = decode_current_token_claims()
        oid = claims.get("oid", "unknown")
        raise requests.HTTPError(
            f"Voice synthesis request failed with {response.status_code}: {response.text}\n"
            "Entra auth troubleshooting:\n"
            f"- Token principal oid: {oid}\n"
            "- Required role on the Foundry account: Cognitive Services Speech User (and, if needed, Cognitive Services User)\n"
            "- Required data action: Microsoft.CognitiveServices/accounts/SpeechServices/speechrest/synthesis/action\n"
            "- For token auth, set AZURE_FOUNDRY_ENDPOINT=https://<foundry-account>.cognitiveservices.azure.com\n"
            "- If this is a new role assignment, wait a few minutes and retry after refreshing token",
            response=response,
        )
    response.raise_for_status()

def post_tts(ssml: str, output_format: str) -> requests.Response:
    response = requests.post(
        TTS_ENDPOINT,
        headers=build_tts_headers(output_format=output_format),
        data=ssml.encode("utf-8")
    )

    # Optional one-time fallback: if token mode fails and key exists, retry with key auth.
    if (not response.ok) and USE_ENTRA_AUTH and VOICE_SPEECH_KEY:
        fallback_headers = {
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": output_format,
            "User-Agent": "MAI-Voice-Demo",
            "Ocp-Apim-Subscription-Key": VOICE_SPEECH_KEY,
        }
        fallback = requests.post(TTS_ENDPOINT, headers=fallback_headers, data=ssml.encode("utf-8"))
        if fallback.ok:
            print("⚠️ Bearer-token request failed; API-key fallback succeeded for this call.")
            return fallback
        response = fallback

    ensure_voice_response_ok(response)
    return response

print(f"✅ TTS Endpoint : {TTS_ENDPOINT}")
print(f"✅ Region       : {VOICE_SPEECH_REGION}")
print(f"✅ Voice Name   : {MAI_VOICE_NAME}")
print(f"✅ Auth mode    : {'DefaultAzureCredential (Bearer token)' if USE_ENTRA_AUTH else 'API key'}")
if USE_ENTRA_AUTH:
    claims = decode_current_token_claims()
    print(f"✅ Token principal oid: {claims.get('oid', 'unknown')}")
    print(f"✅ Token tenant id   : {claims.get('tid', 'unknown')}")
    print(f"✅ Resource ID      : {AZURE_FOUNDRY_RESOURCE_ID or 'not set (SDK fallback mode)'}")
    print("ℹ️ Required RBAC role for TTS: Cognitive Services Speech User")
```

## 2. Basic TTS — REST API

The simplest way to generate speech: POST SSML, receive audio bytes.

**What this does:** the core `synthesize_to_file(...)` helper hits `POST /tts/cognitiveservices/v1` with `application/ssml+xml`. Even the 'basic' case sends SSML — the helper just wraps your text.

**Why it matters:** validating this section confirms endpoint + auth + voice + output codec all work end-to-end. Don't skip ahead until this succeeds.


```python
def synthesize_to_file(
    text: str,
    output_path: str,
    voice: str = MAI_VOICE_NAME,
    output_format: str = "audio-24khz-160kbitrate-mono-mp3",
    lang: str = "en-US",
) -> float:
    """Synthesize text to audio using MAI-Voice-1 REST API. Returns elapsed time."""
    ssml = f"""<speak version='1.0' xml:lang='{lang}'>
  <voice xml:lang='{lang}' name='{voice}'>{text}</voice>
</speak>"""

    start = time.time()
    response = post_tts(ssml=ssml, output_format=output_format)
    elapsed = time.time() - start

    with open(output_path, "wb") as f:
        f.write(response.content)

    size_kb = len(response.content) / 1024
    print(f"✅ Saved: {output_path} ({size_kb:.1f} KB)  |  API latency: {elapsed:.2f}s")
    return elapsed


TEXT_BASIC = (
    "Welcome to Microsoft Foundry. MAI-Voice-1 is a high-fidelity speech "
    "generation model that produces natural, expressive audio. "
    "It powers Copilot Audio Expressions and is now available for developers."
)

synthesize_to_file(TEXT_BASIC, "media/mai-voice-1-foundry/output_basic.mp3")
```

```python
# Inline playback in Jupyter
from IPython.display import Audio, display
display(Audio("media/mai-voice-1-foundry/output_basic.mp3"))
```

## 3. SSML with Emotion / Tone Control

MAI-Voice-1 supports per-turn emotion control through SSML `<mstts:express-as>` tags.

**Why it matters:** the `<mstts:express-as style=...>` tag is the **only** way to get emotion control. Memorize the namespace declarations.


```python
def synthesize_ssml_to_file(ssml: str, output_path: str) -> None:
    """Send raw SSML directly to the TTS endpoint."""
    response = post_tts(ssml=ssml, output_format="audio-24khz-160kbitrate-mono-mp3")
    with open(output_path, "wb") as f:
        f.write(response.content)
    print(f"✅ Saved: {output_path}")


# Example: Express-as emotion tags for conversational styles
# Available styles depend on voice — check Azure Speech Studio for MAI-Voice-1 styles
SSML_EMOTION = f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
                         xmlns:mstts='http://www.w3.org/2001/mstts'
                         xml:lang='en-US'>
  <voice name='{MAI_VOICE_NAME}'>
    <mstts:express-as style='excited'>
      We're thrilled to announce MAI-Voice-1 is now available on Microsoft Foundry!
    </mstts:express-as>
    <break time='500ms'/>
    <mstts:express-as style='calm'>
      It delivers 60 seconds of audio in under one second on a single GPU.
    </mstts:express-as>
    <break time='300ms'/>
    <mstts:express-as style='empathetic'>
      Building great voice experiences has never been easier for developers.
    </mstts:express-as>
  </voice>
</speak>"""

synthesize_ssml_to_file(SSML_EMOTION, "media/mai-voice-1-foundry/output_emotion.mp3")
display(Audio("media/mai-voice-1-foundry/output_emotion.mp3"))
```

## 4. SSML Advanced: Prosody Control (Rate, Pitch, Volume)

**What this does:** demonstrates the `<prosody>` tag for rate, pitch, and volume. These attributes stack — use them sparingly or speech sounds robotic.


```python
SSML_PROSODY = f"""<speak version='1.0' xml:lang='en-US'>
  <voice xml:lang='en-US' name='{MAI_VOICE_NAME}'>
    <!-- Slow down for emphasis -->
    <prosody rate='slow' pitch='+5%'>
      The price is twenty-two dollars per one million characters.
    </prosody>
    <break time='400ms'/>
    <!-- Speed up for a fast-paced segment -->
    <prosody rate='fast' volume='loud'>
      Deploy it today on Microsoft Foundry!
    </prosody>
  </voice>
</speak>"""

synthesize_ssml_to_file(SSML_PROSODY, "media/mai-voice-1-foundry/output_prosody.mp3")
display(Audio("media/mai-voice-1-foundry/output_prosody.mp3"))
```

## 5. Azure Speech SDK — Synthesize to Speaker

Using the Python SDK for real-time or SDK-based integration.

**Watch for:** the SDK can return `SynthesizingAudioCompleted` with `len(audio_data) == 0` on Foundry. The helper detects empty bytes and falls back to REST. If you ship SDK code in production, copy this fallback or you'll deploy silently broken audio.


```python
def synthesize_with_sdk(text: str, output_file: str = "media/mai-voice-1-foundry/output_sdk.mp3") -> None:
    """Synthesize text using the Azure Speech SDK with REST fallback for Foundry endpoints."""
    speech_config = create_speech_config()
    speech_config.speech_synthesis_voice_name = MAI_VOICE_NAME
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio24Khz160KBitRateMonoMp3
    )

    synthesizer  = speechsdk.SpeechSynthesizer(
        speech_config=speech_config,
        audio_config=None
    )

    result = synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        audio_bytes = result.audio_data or b""
        if len(audio_bytes) == 0:
            print("⚠️ SDK returned empty audio bytes on this endpoint; falling back to REST synthesis.")
            synthesize_to_file(text, output_file)
            return
        Path(output_file).write_bytes(audio_bytes)
        size_kb = len(audio_bytes) / 1024
        print(f"✅ Synthesized {len(text)} chars → {output_file} ({size_kb:.1f} KB)")
    elif result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        raise RuntimeError(
            f"Speech SDK synthesis canceled: {details.reason}. "
            f"Details: {details.error_details or 'n/a'}"
        )
    else:
        raise RuntimeError(f"Speech SDK synthesis returned unexpected result reason: {result.reason}")


synthesize_with_sdk(
    "MAI Voice One is brought to you by Microsoft AI, powering the next generation "
    "of voice experiences in Copilot and beyond."
)
display(Audio("media/mai-voice-1-foundry/output_sdk.mp3"))
```

## 6. Voice Prompting (Concept Demo)

MAI-Voice-1 supports **voice prompting** — provide a short audio clip and the model clones that speaker's voice without fine-tuning.

> ⚠️ **Requires Microsoft approval** — custom voice creation is subject to [Microsoft's Responsible AI policies](https://learn.microsoft.com/legal/ai-code-of-conduct). The feature is available through **Azure Speech Personal Voice**.

Voice prompting (clone from a 10s sample) is via the Personal Voice API — outside this notebook's scope. This cell is documentation only.


```python
# Voice prompting is available through the Personal Voice API in Azure Speech.
# Reference: https://learn.microsoft.com/azure/ai-services/speech-service/personal-voice-overview

# Conceptual example — actual Personal Voice API requires approved access.
# The SSML reference voice tag is used to specify the cloned voice:

SSML_VOICE_PROMPT = f"""<speak version='1.0' xml:lang='en-US'>
  <voice name='{MAI_VOICE_NAME}'>
    <!--
    For voice prompting / Personal Voice:
    1. Obtain an approved Personal Voice speaker profile ID from Azure Speech.
    2. Use the DragonLatestNeural voice with the speaker profile ID.

    Example after approval:
    <voice name='DragonLatestNeural'>
      <mstts:ttsembedding speakerProfileId='your-speaker-profile-id'/>
      Your synthesized text here.
    </voice>
    -->
    This demonstrates MAI-Voice-1's voice prompting capability description.
    With an approved speaker profile, the model clones any voice from a
    ten-second audio sample — no fine-tuning required.
  </voice>
</speak>"""

print("Voice prompting SSML template shown above.")
print("See: https://learn.microsoft.com/azure/ai-services/speech-service/personal-voice-overview")
```

## 7. Long-Form Narration (Batch Synthesis)

For content >5 minutes (audiobooks, podcasts, lectures), use the Batch Synthesis API.

**What this does:** synthesizes a multi-paragraph script. For >5 KB blocks, chunk by sentence and concatenate the resulting MP3s.


```python
LONG_TEXT = """Chapter One: The Dawn of Microsoft AI.

Microsoft AI has been developing world-class models that power millions of experiences 
across Copilot, Bing, PowerPoint, and Azure. Today marks a significant milestone as 
MAI-Voice-1, MAI-Transcribe-1, and MAI-Image-2 become available to every developer 
through Microsoft Foundry.

Chapter Two: Voice at Scale.

MAI-Voice-1 can generate sixty seconds of expressive, human-like audio in under one 
second on a single GPU. This makes real-time voice assistants, interactive IVR systems, 
and large-scale audiobook production economically viable for developers of all sizes.

Chapter Three: Building the Future.

With pricing starting at twenty-two dollars per million characters, developers can 
build rich voice experiences without breaking their budget. The future of human-computer 
interaction is voice — and MAI-Voice-1 is at the center of that future."""

print(f"Long-form text length: {len(LONG_TEXT)} characters")

# Synthesize using the SDK (suitable for texts up to a few thousand characters)
synthesize_with_sdk(LONG_TEXT, "media/mai-voice-1-foundry/output_longform.mp3")
display(Audio("media/mai-voice-1-foundry/output_longform.mp3"))
```

## 8. 💰 Cost Calculator

**MAI-Voice-1 pricing: \$22 per 1M characters**

Characters include spaces and punctuation (all characters in the input text).

**Watch for:** pricing is **per character** including whitespace. Long whitespace runs in SSML still cost money.


```python
# ── Cost Calculator ─────────────────────────────────────────
PRICE_PER_1M_CHARS = 22.00  # USD per 1 million characters (as of April 2026)

# Average reading speeds:
#   ~ 500 chars/min (slow, conversational)
#   ~ 800 chars/min (natural speech)
#   ~ 1200 chars/min (fast narration)

scenarios = {
    "Single blog post (3,000 chars)":          3_000,
    "Short audiobook chapter (30,000 chars)":  30_000,
    "Full audiobook (~500K chars)":            500_000,
    "Daily IVR traffic (1M chars/day)":      1_000_000,
    "Enterprise monthly (50M chars)": 50_000_000,
}

print(f"\nMAI-Voice-1 Cost Estimator  (${PRICE_PER_1M_CHARS:.2f} / 1M chars)")
print(f"{'Scenario':<45} {'Characters':>12} {'Cost (USD)':>12}")
print("-" * 71)
for label, chars in scenarios.items():
    cost = (chars / 1_000_000) * PRICE_PER_1M_CHARS
    print(f"{label:<45} {chars:>12,} ${cost:>11.4f}")

# Current text from notebook
print()
print("Current demo cost:")
demo_chars = len(TEXT_BASIC) + len(LONG_TEXT)
demo_cost  = (demo_chars / 1_000_000) * PRICE_PER_1M_CHARS
print(f"  {demo_chars:,} chars → ${demo_cost:.6f}")
```

## 9. Summary & Next Steps

| Feature | Status |
|---|---|
| Basic TTS (REST) | ✅ |
| SSML emotion control | ✅ |
| SSML prosody (rate/pitch) | ✅ |
| Azure Speech SDK | ✅ |
| Voice prompting (Personal Voice) | ✅ (requires approval) |
| Long-form narration | ✅ |
| 10+ languages | 🔜 Coming soon |

**Resources:**
- [Model Card](https://ai.azure.com/catalog/models/MAI-Voice-1)
- [Azure Speech TTS docs](https://learn.microsoft.com/azure/ai-services/speech-service/text-to-speech)
- [SSML reference](https://learn.microsoft.com/azure/ai-services/speech-service/speech-synthesis-markup)
- [Personal Voice (voice cloning)](https://learn.microsoft.com/azure/ai-services/speech-service/personal-voice-overview)
- [MAI Playground](https://playground.microsoft.ai)

Checklist for shipping MAI-Voice-1 into a product.


## 10. Evidence Pack — Audio Files + Manifest

Five MP3 samples generated by this notebook are committed to `media/mai-voice-1-foundry/`. Use the player cell below to spot-check each sample without re-running synthesis. The manifest below records sizes and voice name so reviewers can verify what produced the audio.


```python
from datetime import datetime
from pathlib import Path
import json
from IPython.display import display, Markdown, HTML

EVIDENCE_PATH = Path("data/mai-voice-1-foundry/evidence.json")
EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

samples = [
    ("Basic plain text",           "media/mai-voice-1-foundry/output_basic.mp3"),
    ("Emotion (SSML express-as)",  "media/mai-voice-1-foundry/output_emotion.mp3"),
    ("Prosody (rate/pitch/volume)","media/mai-voice-1-foundry/output_prosody.mp3"),
    ("SDK synthesis (REST-fallback safe)", "media/mai-voice-1-foundry/output_sdk.mp3"),
    ("Long-form narration (~900 chars)",   "media/mai-voice-1-foundry/output_longform.mp3"),
]

files = []
for label, path in samples:
    p = Path(path)
    if p.exists() and p.stat().st_size > 0:
        files.append({"label": label, "file": path, "size_bytes": p.stat().st_size})
        display(HTML(
            f'<p><strong>{label}</strong> — <code>{path}</code> ({p.stat().st_size:,} bytes)</p>'
            f'<audio controls preload="none" src="{path}"></audio>'
        ))
    else:
        display(Markdown(f"⚠️ Missing or empty: `{path}` — re-run the matching section first."))

evidence = {
    "generated_at_utc": datetime.utcnow().isoformat() + "Z",
    "voice_name": globals().get("MAI_VOICE_NAME", "en-us-Grant:MAI-Voice-1"),
    "auth_mode": "entra" if globals().get("USE_ENTRA_AUTH", True) else "api_key",
    "samples": files,
}

EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(f"\n✅ Evidence manifest saved: {EVIDENCE_PATH}")

```

## 11. Failure Modes and Fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` / `403` from `/tts/cognitiveservices/v1` | Token principal lacks `Cognitive Services User` on the Foundry account | Assign the role, wait ~30s, refresh the token (the notebook re-fetches automatically on next call) |
| `404 Voice not found` | `MAI_VOICE_NAME` typo or unsupported voice | Check the Foundry catalog. MAI voices use the `:` separator (e.g. `en-us-Grant:MAI-Voice-1`) |
| SDK reports success but file is empty | Foundry endpoint quirk — SDK returns 0 bytes silently | Use the fallback in §5 — detects empty `audio_data` and re-synthesizes via REST |
| Generated audio plays as noise | Wrong `X-Microsoft-OutputFormat` for the file extension | Match the header to the extension (`audio-24khz-48kbitrate-mono-mp3` for `.mp3`, `riff-24khz-16bit-mono-pcm` for `.wav`) |
| `400 Invalid SSML` | Missing/wrong namespace declarations | Always include `xmlns:mstts="http://www.w3.org/2001/mstts"` when using `<mstts:express-as>` |
| Long-form returns a truncated file | Single payload too large | Chunk on sentence boundaries (< 5 KB per call) and concatenate the MP3 byte streams |
| Cost overrun on batch generation | Forgot whitespace counts | Use §8 with realistic character counts (include all SSML markup) before kicking off batches |


## 12. Takeaway Artifact

Copy three things from this notebook into your service:

1. **`synthesize_to_file(...)`** — the REST helper with SDK fallback baked in.
2. **The SSML template in §3 / §4** — change the voice + style, keep the namespace block. This is the only SSML you need for 90% of MAI-Voice-1 work.
3. **`data/mai-voice-1-foundry/evidence.json`** — the manifest pattern. Run it on every batch job to give reviewers a record of voice, character counts, and file sizes per release.


## Over to you

Our Microsoft Superintelligence (MSI) team is excited for you to try out **MAI-Voice-1** and see how it can make it easier to build expressive, low-latency text-to-speech experiences in your next app! Whether you're voicing IVR menus, narrating long-form content, giving characters a voice in a game, or sending personalized audio notifications, this recipe equips you with the SSML patterns, the SDK fallback, and the cost model to go from prototype to product.

If you build something cool with this recipe, share it back with us! Open an issue or PR on Forgebook and tell us what worked, what surprised you, and where you'd like a deeper-dive recipe next.
