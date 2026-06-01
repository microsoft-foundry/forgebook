## MAI-Voice-2-Preview: Multilingual Prompted Text-to-Speech

**Model card reference:** MAI-Voice-2 (Foundry) latest update

MAI-Voice-2-Preview is a high-fidelity, expressive, prompted TTS model across 15 languages and 18 locales.
This notebook demonstrates REST call patterns, multilingual synthesis, expressive SSML, and practical implementation notes.


## 1. Setup


### Environment variables

| Variable | Required | Secret | Purpose |
|---|---|---|---|
| `MAI_VOICE_2_ENDPOINT` | Optional | No | Voice endpoint (falls back to East US TTS endpoint). |
| `MAI_VOICE_2_KEY` | Optional* | **Yes** | API key when key-based auth is used. |
| `USE_ENTRA_AUTH` | Optional | No | Set `true` to use Entra auth, `false` to force key auth. |
| `MAI_VOICE_2_OUTPUT_DIR` | Optional | No | Output directory for generated audio; defaults to `media/mai-voice-2`. |

\* Required when `USE_ENTRA_AUTH=false`.

Do not commit `.env` or `deployment.env` files with secrets.


```python
# %pip install -q requests python-dotenv azure-identity

```

```python
import os
from pathlib import Path
import requests
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

ENV_PATH = 'deployment.env' if os.path.exists('deployment.env') else os.path.join('..', 'deployment.env')
load_dotenv(ENV_PATH, override=True)

VOICE2_ENDPOINT = (
    os.getenv('MAI_VOICE_2_ENDPOINT')
    or os.getenv('VOICE_SPEECH_ENDPOINT')
    or 'https://eastus.tts.speech.microsoft.com/'
)
VOICE2_KEY = (
    os.getenv('MAI_VOICE_2_KEY')
    or os.getenv('VOICE_SPEECH_KEY')
    or os.getenv('AZURE_SPEECH_KEY')
)
USE_ENTRA_AUTH = os.getenv('USE_ENTRA_AUTH', 'true').lower() == 'true'
if not VOICE2_KEY:
    USE_ENTRA_AUTH = True

voice_output_env = os.getenv('MAI_VOICE_2_OUTPUT_DIR')
OUT_DIR = Path(voice_output_env) if voice_output_env else Path('media') / 'mai-voice-2'
OUT_DIR.mkdir(parents=True, exist_ok=True)

token_provider = None
if USE_ENTRA_AUTH:
    for env_var in ('AZURE_TENANT_ID', 'AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET'):
        if os.getenv(env_var) == '':
            os.environ.pop(env_var, None)
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        'https://cognitiveservices.azure.com/.default',
    )

print(f'Endpoint: {VOICE2_ENDPOINT}')
print(f'Auth mode: {'Entra ID' if USE_ENTRA_AUTH else 'API key'}')
print('Default sample voice: en-US-Harper:MAI-Voice-2-Preview')
print('Output target: 24kHz MP3')

```

## 2. Model Card Highlights


- High-fidelity natural voice synthesis with expressive control.
- Generate speech from short audio prompts (5-60 seconds).
- Multilingual support across **15 languages and 18 locales**.
- Supports long-form content generation via chunking with context carryover.
- Output format is 24kHz mono audio.
- Served globally via East US, Sweden Central, and Southeast Asia.
- Pricing reference: **$22 per 1M characters**.
- Out-of-scope note: optimized for naturalness/expressivity over ultra-low-latency scenarios.


## 3. Reference HTTP Pattern


```python
reference_ssml = '''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US">
  <voice name="en-US-Harper:MAI-Voice-2-Preview">
    Hello, this is test text-to-speech model
  </voice>
</speak>'''

reference_url = f"{VOICE2_ENDPOINT.rstrip('/')}/cognitiveservices/v1"
reference_headers = {
    'Content-Type': 'application/ssml+xml',
    'X-Microsoft-OutputFormat': 'audio-24khz-160kbitrate-mono-mp3',
    'User-Agent': 'mai-voice-2-notebook-reference',
}
if USE_ENTRA_AUTH:
    reference_headers['Authorization'] = f"Bearer {token_provider()}"
else:
    reference_headers['Ocp-Apim-Subscription-Key'] = VOICE2_KEY

RUN_REFERENCE_CALL = False
if RUN_REFERENCE_CALL:
    response = requests.post(
        reference_url,
        headers=reference_headers,
        data=reference_ssml.encode('utf-8'),
        timeout=180,
    )
    response.raise_for_status()
    out_file = OUT_DIR / 'speech-voice-en.mp3'
    out_file.write_bytes(response.content)
    print(f'Wrote {out_file} ({out_file.stat().st_size:,} bytes)')
else:
    safe_headers = {
        k: ('<bearer token>' if k == 'Authorization' else '<subscription key>' if k == 'Ocp-Apim-Subscription-Key' else v)
        for k, v in reference_headers.items()
    }
    print('Set RUN_REFERENCE_CALL=True to execute this Python HTTP sample.')
    print('URL:', reference_url)
    print('Headers:', safe_headers)

```

## 4. Helper: Synthesize SSML to File


```python
def headers() -> dict:
    h = {
        'Content-Type': 'application/ssml+xml',
        'X-Microsoft-OutputFormat': 'audio-24khz-160kbitrate-mono-mp3',
        'User-Agent': 'mai-voice-2-notebook',
    }
    if USE_ENTRA_AUTH:
        h['Authorization'] = f"Bearer {token_provider()}"
    else:
        h['Ocp-Apim-Subscription-Key'] = VOICE2_KEY
    return h

def synthesize_to_file(ssml: str, out_file: str) -> Path:
    url = f"{VOICE2_ENDPOINT.rstrip('/')}/cognitiveservices/v1"
    resp = requests.post(url, headers=headers(), data=ssml.encode('utf-8'), timeout=180)
    if not resp.ok:
        raise requests.HTTPError(f'TTS request failed with {resp.status_code}: {resp.text}', response=resp)
    p = OUT_DIR / out_file
    p.write_bytes(resp.content)
    print(f'Wrote {p} ({p.stat().st_size:,} bytes)')
    return p

```

## 5. Multilingual Synthesis Samples


Illustrative sample audio from one run:

<audio controls src="media/mai-voice-2/01-mai-voice2-en.mp3"></audio>

- [Download sample (`01-mai-voice2-en.mp3`)](media/mai-voice-2/01-mai-voice2-en.mp3)

Audio style and prosody can vary between runs and model updates.


```python
samples = [
    {'lang': 'en-US', 'voice': 'en-US-Harper:MAI-Voice-2-Preview', 'text': 'Hello from MAI Voice 2 in English.', 'out': 'mai_voice2_en.mp3'},
    {'lang': 'es-MX', 'voice': 'es-MX-Valeria:MAI-Voice-2-Preview', 'text': 'Hola, esta es una muestra de MAI Voice 2.', 'out': 'mai_voice2_es.mp3'},
    {'lang': 'fr-FR', 'voice': 'fr-FR-Soleil:MAI-Voice-2-Preview', 'text': 'Bonjour, ceci est un exemple MAI Voice 2.', 'out': 'mai_voice2_fr.mp3'},
    {'lang': 'de-DE', 'voice': 'de-DE-Klaus:MAI-Voice-2-Preview', 'text': 'Hallo, dies ist eine MAI Voice 2 Probe.', 'out': 'mai_voice2_de.mp3'},
]

for s in samples:
    ssml = f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="{s['lang']}">
  <voice name="{s['voice']}">{s['text']}</voice>
</speak>'''
    try:
        synthesize_to_file(ssml, s['out'])
    except Exception as ex:
        print(f"{s['voice']} failed: {ex}")

```

## 6. Voice Prompting Note (Gated Access)


Voice prompting (personal voice cloning) is gated and requires Microsoft approval plus consent safeguards.

Implementation reminders from the model card:
1. Apply for limited access approval.
2. Upload consent audio + prompt.
3. Use Personal Voice APIs to create voice profile.
4. Synthesize with approved voice profile.


## 7. Next Steps

1. Set MAI_VOICE_2_PRICE_PER_1M_CHAR after MAI-Voice-2 pricing is published.
2. Replace sample voices with the final published MAI-Voice-2 voice list.
3. Add latency benchmarking if your scenario is latency-sensitive.
