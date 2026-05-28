## MAI-Voice-2: Multilingual Prompted Text-to-Speech

**Model card date:** May 19, 2026

MAI-Voice-2 is a high-fidelity, expressive, prompted TTS model across 10+ languages.
This notebook demonstrates the REST call pattern, multilingual synthesis, expressive SSML, and practical implementation notes.

## 1. Setup

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

OUT_DIR = Path(os.getenv('MAI_VOICE_2_OUTPUT_DIR', r'..\\audio'))
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
print('Default sample voice: en-US-Harper:MAI-Voice-2')
print('Output target: 24kHz MP3')

```

## 2. Model Card Highlights

- High-fidelity natural voice synthesis with expressive control.
- Voice prompting supported with short clips (10-120 seconds), subject to gated access and consent safeguards.
- Multilingual support across 10+ languages.
- Long-form generation and multi-speaker generation support.
- Out-of-scope note: model prioritizes naturalness and expressivity over latency-critical scenarios.

## 3. Reference HTTP Pattern

```python
reference_ssml = '''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US">
  <voice name="en-US-Harper:MAI-Voice-2">
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

```python
samples = [
    {'lang': 'en-US', 'voice': 'en-US-Harper:MAI-Voice-2', 'text': 'Hello from MAI Voice 2 in English.', 'out': 'mai_voice2_en.mp3'},
    {'lang': 'es-MX', 'voice': 'es-MX-Valeria:MAI-Voice-2', 'text': 'Hola, esta es una muestra de MAI Voice 2.', 'out': 'mai_voice2_es.mp3'},
    {'lang': 'fr-FR', 'voice': 'fr-FR-Soleil:MAI-Voice-2', 'text': 'Bonjour, ceci est un exemple MAI Voice 2.', 'out': 'mai_voice2_fr.mp3'},
    {'lang': 'de-DE', 'voice': 'de-DE-Klaus:MAI-Voice-2', 'text': 'Hallo, dies ist eine MAI Voice 2 Probe.', 'out': 'mai_voice2_de.mp3'},
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

## 6. Expressive Control with SSML

```python
STYLE_SSML = '''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US">
  <voice name="en-US-Harper:MAI-Voice-2">
    <mstts:express-as style="happiness" styledegree="1.2">
      Welcome to Microsoft Build. MAI Voice 2 supports multilingual expressive synthesis.
    </mstts:express-as>
  </voice>
</speak>'''

try:
    synthesize_to_file(STYLE_SSML, 'mai_voice2_style.mp3')
except Exception as ex:
    print(f'Styled synthesis failed: {ex}')

```

## 7. Voice Prompting Note (Gated Access)

Voice prompting (personal voice cloning) is gated and requires Microsoft approval plus consent safeguards.

Implementation reminders from the model card:
1. Apply for limited access approval.
2. Upload consent audio + prompt.
3. Use Personal Voice APIs to create voice profile.
4. Synthesize with approved voice profile.

## 8. Next Steps

1. Set MAI_VOICE_2_PRICE_PER_1M_CHAR after MAI-Voice-2 pricing is published.
2. Replace sample voices with the final published MAI-Voice-2 voice list.
3. Add latency benchmarking if your scenario is latency-sensitive.
