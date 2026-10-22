## MAI-Transcribe-1.5 (Speech API multipart patterns)

This notebook follows the Speech REST pattern you specified:
- `POST /speechtotext/transcriptions:transcribe?api-version=2025-10-15`
- multipart form with `audio` + `definition`
- key auth via `Ocp-Apim-Subscription-Key`


## 1. Setup

### Environment variables

| Variable | Required | Secret | Purpose |
|---|---|---|---|
| `MAI_TRANSCRIBE_15_ENDPOINT` | Optional | No | Speech endpoint (defaults to East US Speech endpoint). |
| `MAI_TRANSCRIBE_15_KEY` | Yes | **Yes** | Subscription key used in `Ocp-Apim-Subscription-Key`. |
| `TRANSCRIBE_LOCAL_AUDIO_DIR` | Optional | No | Folder containing local WAV/MP3/FLAC files; defaults to `media/mai-transcribe-1-5`. |

Do not commit `.env` or `deployment.env` files with secrets.


```python
# %pip install -q requests python-dotenv
```

```python
import os
import json
from copy import deepcopy
from pathlib import Path
import requests
from dotenv import load_dotenv

ENV_PATH = 'deployment.env' if os.path.exists('deployment.env') else os.path.join('..', 'deployment.env')
load_dotenv(ENV_PATH, override=True)

SPEECH_ENDPOINT = os.getenv('MAI_TRANSCRIBE_15_ENDPOINT', 'https://eastus.api.cognitive.microsoft.com/').rstrip('/')
SPEECH_KEY = os.getenv('MAI_TRANSCRIBE_15_KEY')
TRANSCRIBE_URL = f"{SPEECH_ENDPOINT}/speechtotext/transcriptions:transcribe?api-version=2025-10-15"
assert SPEECH_KEY, 'Set MAI_TRANSCRIBE_15_KEY in deployment.env'

audio_dir_env = os.getenv('TRANSCRIBE_LOCAL_AUDIO_DIR')
LOCAL_AUDIO_DIR = Path(audio_dir_env) if audio_dir_env else Path('media') / 'mai-transcribe-1-5'
assert LOCAL_AUDIO_DIR.exists(), f'Audio folder not found: {LOCAL_AUDIO_DIR}'
candidates = sorted(LOCAL_AUDIO_DIR.glob('*.wav')) + sorted(LOCAL_AUDIO_DIR.glob('*.mp3')) + sorted(LOCAL_AUDIO_DIR.glob('*.flac'))
non_empty = [p for p in candidates if p.stat().st_size > 0]
assert non_empty, f'No non-empty WAV/MP3/FLAC files found in: {LOCAL_AUDIO_DIR}'
AUDIO_FILE = str(max(non_empty, key=lambda p: p.stat().st_size))
print('Endpoint:', SPEECH_ENDPOINT)
print('Audio file:', AUDIO_FILE)

def _mime_for(path: Path) -> str:
    s = path.suffix.lower()
    if s == '.wav':
        return 'audio/wav'
    if s == '.mp3':
        return 'audio/mpeg'
    if s == '.flac':
        return 'audio/flac'
    return 'application/octet-stream'

def transcribe_with_definition(audio_path: str, definition: dict) -> dict:
    p = Path(audio_path)
    with p.open('rb') as f:
        files = {
            'audio': (p.name, f, _mime_for(p)),
            'definition': (None, json.dumps(definition), 'application/json'),
        }
        resp = requests.post(
            TRANSCRIBE_URL,
            headers={'Ocp-Apim-Subscription-Key': SPEECH_KEY},
            files=files,
            timeout=300,
        )
    if resp.ok:
        return resp.json()

    # Compatibility fallback for backends that reject enhancedMode/model
    txt = (resp.text or '').lower()
    if resp.status_code == 400 and 'enhanced mode with model' in txt:
        fb = deepcopy(definition)
        fb.get('enhancedMode', {}).pop('model', None)
        return transcribe_with_definition(audio_path, fb)
    if resp.status_code == 400 and 'enhanced mode is currently not supported' in txt:
        fb = deepcopy(definition)
        fb.pop('enhancedMode', None)
        return transcribe_with_definition(audio_path, fb)

    raise requests.HTTPError(f'Transcription failed with {resp.status_code}: {resp.text}', response=resp)

```

Illustrative sample audio used in this recipe:

- [Sample audio (`sample-en.mp3`)](media/mai-transcribe-1-5/sample-en.mp3)

Transcription results are illustrative and may vary by model updates, locale detection, and audio quality.


## 2. General Speech-to-Text transcription

```python
general_definition = {
    'enhancedMode': {
        'enabled': True,
        'model': 'mai-transcribe-1.5'
    }
}
general_result = transcribe_with_definition(AUDIO_FILE, general_definition)
print(json.dumps(general_result, indent=2)[:2000])

```

Example response shape:

```json
{
  "id": "<redacted>",
  "status": "succeeded",
  "combinedPhrases": [
    {"text": "..."}
  ],
  "phrases": [
    {"offsetMilliseconds": 0, "text": "..."}
  ]
}
```


## 3. Speech-to-Text with verbatim mode

```python
verbatim_definition = {
    'enhancedMode': {
        'enabled': True,
        'model': 'mai-transcribe-1.5',
        'transcribeStyle': 'verbatim'
    }
}
verbatim_result = transcribe_with_definition(AUDIO_FILE, verbatim_definition)
print(json.dumps(verbatim_result, indent=2)[:2000])

```

Example response shape:

```json
{
  "id": "<redacted>",
  "status": "succeeded",
  "combinedPhrases": [
    {"text": "..."}
  ],
  "phrases": [
    {"offsetMilliseconds": 0, "text": "..."}
  ]
}
```


## 4. Entity biasing example (PhraseList)

`PhraseList` can increase accuracy in specialized domains by passing important names and terms via `phraseList.phrases`. This implements entity biasing.


```python
phrase_list_definition = {
    'phraseList': {
        'phrases': ['MAI', 'Microsoft Build', 'Azure Speech', 'Foundry', 'Copilot']
    },
    'enhancedMode': {
        'enabled': True,
        'model': 'mai-transcribe-1.5'
    }
}
phrase_list_result = transcribe_with_definition(AUDIO_FILE, phrase_list_definition)
print(json.dumps(phrase_list_result, indent=2)[:2000])

```

Example response shape:

```json
{
  "id": "<redacted>",
  "status": "succeeded",
  "combinedPhrases": [
    {"text": "..."}
  ],
  "phrases": [
    {"offsetMilliseconds": 0, "text": "..."}
  ]
}
```


## 5. Additional example — Automatic language identification

Imported from your additional notebook examples.

```python
lid_definition = {
    'locales': ['en-US', 'es-ES', 'fr-FR', 'de-DE'],
    'enhancedMode': {
        'enabled': True,
        'model': 'mai-transcribe-1.5'
    },
}
lid_result = transcribe_with_definition(AUDIO_FILE, lid_definition)
print(json.dumps(lid_result, indent=2)[:2000])

```

Example response shape:

```json
{
  "id": "<redacted>",
  "status": "succeeded",
  "combinedPhrases": [
    {"text": "..."}
  ],
  "phrases": [
    {"offsetMilliseconds": 0, "text": "..."}
  ]
}
```


## 6. Notes from model card (v2)

- **Language coverage expanded**: MAI-Transcribe-1.5 supports the current Learn language table, including additions such as Assamese, Bulgarian, Bengali, Catalan, Greek, Estonian, Gujarati, Kannada, Lithuanian, Malayalam, Marathi, Odia, Punjabi (Gurmukhi script), Slovak, Slovenian, Tamil, Telugu, and Ukrainian. See [MAI-Transcribe language support](https://learn.microsoft.com/azure/ai-services/speech-service/mai-transcribe#language-support).
- **Faster long-form inference**: up to **5.7x** faster than MAI-Transcribe-1 on long audio.
- **PhraseList/entity biasing** can increase accuracy in specialized domains (up to **200 keywords**) via `phraseList.phrases`.
- **Transcribe style** is supported through `enhancedMode.transcribeStyle`; use `verbatim` to preserve filler words and disfluencies.
- **Automatic language identification** is supported.
- **Current limitation**: diarization is not supported yet (planned for an upcoming release).
- **Input formats**: WAV, MP3, FLAC.
- **Input limits**: up to **300 MB** and **2 hours** of audio.
- **Serving regions (global routing)**: Central US, Sweden Central, and Southeast Asia.


## 7. Troubleshooting

| Error | Resolution |
|---|---|
| `Enhanced mode ... not supported` | Backend limitation; helper auto-falls back by removing model/enhancedMode. |
| `InvalidLocale` | Add/adjust locale in `definition` if required by your backend. |
| `EmptyAudioFile` | Use a non-empty file; notebook auto-picks largest non-empty local audio file. |
| `401/403` | Verify `MAI_TRANSCRIBE_15_KEY` and endpoint in `deployment.env`. |
