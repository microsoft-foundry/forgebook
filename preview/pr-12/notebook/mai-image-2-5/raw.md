## MAI Image 2.5 (Private Preview) — Edit + Generate Notebook

**Model card date:** May 2026  
**Release date:** June 2, 2026

MAI-Image-2.5 is a next-generation image model for both:
- high-quality **text-to-image generation**, and
- precise, controllable **image-to-image editing**.

Model-card highlights reflected in this notebook:
- Model behavior: supports text-to-image generation and image-to-image editing
- Inputs: text, plus image input for editing
- Context length: 32K tokens
- Output limit: total pixels must be <= 1,048,576 (equivalent to 1024x1024). Either dimension may exceed 1024 if total stays within budget.
- Strong focus areas: surgical edits, layout preservation, text updates, artifact cleanup, portrait/product quality
- Quality signal: see the MAI-Image-2.5 model page for current quality information.

## Private Preview Terms (must follow)
- Internal-only use; no external end-user access.
- Private preview models are not for production deployments.
- Follow Microsoft license terms and Generative AI code of conduct.
- Abuse monitoring and content filtering remain enabled.
- Preview is as-is and may change or be discontinued without notice.
- Do not send regulated personal data in preview feedback.


## 1. Setup

```python
# %pip install -q requests python-dotenv pillow

```

```python
import os
import base64
import mimetypes
import socket
from urllib.parse import urlparse
from pathlib import Path
import requests
from dotenv import load_dotenv
from IPython.display import Image as IPImage, display

ENV_PATH = 'deployment.env' if os.path.exists('deployment.env') else os.path.join('..', 'deployment.env')
load_dotenv(ENV_PATH, override=True)

MAI_IMAGE_25_SUBSCRIPTION_ID = os.getenv('MAI_IMAGE_25_SUBSCRIPTION_ID', '5f237684-e1fd-4442-8359-6e202031c45b')
MAI_IMAGE_25_ACCOUNT = os.getenv('MAI_IMAGE_25_ACCOUNT', 'maiimagefoundry5f237684a')
MAI_IMAGE_25_ENDPOINT = os.getenv('MAI_IMAGE_25_ENDPOINT', 'https://westcentralus.api.cognitive.microsoft.com/')
MAI_IMAGE_25_DEPLOYMENT_NAME = os.getenv('MAI_IMAGE_25_DEPLOYMENT_NAME', 'maiimage25')
MAI_IMAGE_25_API_KEY = os.getenv('MAI_IMAGE_25_API_KEY')

IMAGE_OUTPUT_DIR = Path(os.getenv('IMAGE_OUTPUT_DIR', r'..\images'))
IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
INPUT_IMAGE_PATH = Path(os.getenv('MAI_IMAGE_25_INPUT_IMAGE', r'..\images\image.png'))
DEFAULT_EDIT_SIZE = os.getenv('MAI_IMAGE_25_EDIT_SIZE', '1024x1024')

assert MAI_IMAGE_25_ENDPOINT, 'Set MAI_IMAGE_25_ENDPOINT in deployment.env'
assert MAI_IMAGE_25_API_KEY, 'Set MAI_IMAGE_25_API_KEY in deployment.env (MAI Image 2.5 currently uses API key auth in preview)'

def auth_headers(content_type: str | None = None) -> dict:
    h = {'api-key': MAI_IMAGE_25_API_KEY}
    if content_type:
        h['Content-Type'] = content_type
    return h

def preflight_endpoint_dns(endpoint: str) -> None:
    host = urlparse(endpoint).hostname
    try:
        socket.getaddrinfo(host, 443)
    except Exception as ex:
        raise RuntimeError(
            f'Endpoint DNS resolution failed for {host}: {ex}. '
            'Use the Cognitive endpoint format (e.g. https://westcentralus.api.cognitive.microsoft.com/).'
        )

preflight_endpoint_dns(MAI_IMAGE_25_ENDPOINT)

print('Subscription:', MAI_IMAGE_25_SUBSCRIPTION_ID)
print('Endpoint:', MAI_IMAGE_25_ENDPOINT)
print('Deployment:', MAI_IMAGE_25_DEPLOYMENT_NAME)
print('Auth mode: API key')
print('Output dir:', IMAGE_OUTPUT_DIR)
print('Default edit size:', DEFAULT_EDIT_SIZE)

```

## 2. API behavior note (important)

- **Image edit endpoint** (`/mai/v1/images/edits`) uses **`size`** (for example, `1024x1024`).
- **Text-to-image generation endpoint** (`/mai/v1/images/generations`) uses **`width`** and **`height`**.
- For both paths, keep total pixel budget <= **1,048,576**.


## 3. Text-to-Image Helper (`width` + `height`)

```python
def _validate_pixel_budget(width: int, height: int, source: str) -> None:
    assert width > 0 and height > 0, f'{source}: width and height must be positive'
    assert width * height <= 1_048_576, f'{source}: width*height must be <= 1,048,576'


def generate_image_25(prompt: str, out_file: str, width: int = 1024, height: int = 1024) -> Path:
    _validate_pixel_budget(width, height, 'generation')

    url = f"{MAI_IMAGE_25_ENDPOINT.rstrip('/')}/mai/v1/images/generations"
    payload = {
        'model': MAI_IMAGE_25_DEPLOYMENT_NAME,
        'prompt': prompt,
        'width': width,
        'height': height,
    }
    resp = requests.post(url, headers=auth_headers('application/json'), json=payload, timeout=180)
    if not resp.ok:
        raise requests.HTTPError(f'Generation failed with {resp.status_code}: {resp.text}', response=resp)
    data = resp.json().get('data', [])
    assert data and data[0].get('b64_json'), f'No image output in response: {resp.text[:500]}'
    out_path = IMAGE_OUTPUT_DIR / out_file
    out_path.write_bytes(base64.b64decode(data[0]['b64_json']))
    return out_path

```

## 4. Image Edit Helper (`size`)

```python
def _parse_size(size: str) -> tuple[int, int]:
    parts = size.lower().split('x')
    assert len(parts) == 2, "size must be in '<width>x<height>' format, e.g. 1024x1024"
    w, h = int(parts[0]), int(parts[1])
    return w, h


def edit_image_25(prompt: str, input_image: Path, out_file: str, size: str = DEFAULT_EDIT_SIZE) -> Path:
    w, h = _parse_size(size)
    _validate_pixel_budget(w, h, 'edit')

    url = f"{MAI_IMAGE_25_ENDPOINT.rstrip('/')}/mai/v1/images/edits"
    mime = mimetypes.guess_type(str(input_image))[0] or 'image/png'
    assert input_image.exists(), f'Input image not found: {input_image}'

    headers = auth_headers()
    with input_image.open('rb') as f:
        files = {'image': (input_image.name, f, mime)}
        form = {
            'prompt': prompt,
            'model': MAI_IMAGE_25_DEPLOYMENT_NAME,
            'size': size,
        }
        resp = requests.post(url, headers=headers, files=files, data=form, timeout=300)

    if not resp.ok:
        raise requests.HTTPError(f'Edit failed with {resp.status_code}: {resp.text}', response=resp)
    data = resp.json().get('data', [])
    assert data and data[0].get('b64_json'), 'b64_json missing or null (common with bad decoding flow)'
    out_path = IMAGE_OUTPUT_DIR / out_file
    out_path.write_bytes(base64.b64decode(data[0]['b64_json']))
    return out_path

```

## 5. Run a generation sample

```python
generated = generate_image_25(
    prompt='A photorealistic concept art poster of an Azure AI lab at sunset, cinematic lighting',
    out_file='mai_image25_generation.png',
    width=1024,
    height=1024,
)
print('Generated image:', generated)
display(IPImage(filename=str(generated), width=512))
INPUT_IMAGE_PATH=generated
```

## 6. Run an edit sample (requires input image)

```python
if INPUT_IMAGE_PATH.exists():
    edited = edit_image_25(
        prompt='Turn this into a clean futuristic product shot with studio lighting',
        input_image=INPUT_IMAGE_PATH,
        out_file='mai_image25_edited.png',
        size=DEFAULT_EDIT_SIZE,
    )
    print('Edited image:', edited)
    display(IPImage(filename=str(edited), width=512))
else:
    print(f'Skipping edit run: input image not found at {INPUT_IMAGE_PATH}')

```

## 7. Troubleshooting

| Error | Resolution |
|---|---|
| `DeploymentModelNotSupported` | Subscription not whitelisted or model name/version mismatch. Verify deployment and model availability. |
| Output image is 0-3 bytes | `b64_json` is null or decode flow is wrong. Save response JSON first, then decode. |
| `base64: unrecognized option --ignore-garbage` | On macOS use `base64 -d` instead of GNU flags. |
| `401/403` | Invalid/expired API key or wrong endpoint. Re-check `MAI_IMAGE_25_API_KEY` and `MAI_IMAGE_25_ENDPOINT`. |


## 8. Usage, safety, and out-of-scope reminders

**Primary use cases aligned to model card:**
- Creative text-to-image generation
- Surgical image editing (object removal/replacement, inpainting, text updates, attribute changes)
- Product/branding visuals, portraits, and production design workflows

**Out-of-scope / not allowed:**
- Deceptive impersonation or misleading identity content
- Illegal or policy-violating content generation
- Harmful or abusive content generation

**Responsible AI notes:**
- This model includes layered safety guardrails (prompt and output filtering) in deployed systems.
- Continue to review outputs and prompts for policy compliance before downstream use.
