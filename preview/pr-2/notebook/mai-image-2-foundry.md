## Build a Direct Foundry Image Generation Recipe with MAI-Image-2

**Problem this recipe solves:** You need the leanest possible MAI-Image-2 integration against the raw Foundry REST endpoint, with both single-shot and batch prompts demonstrated, plus saved evidence the technique works.

**Who this is for:** Developers integrating Foundry image generation into apps that don't have the Azure OpenAI SDK and want to call the REST endpoint directly.

**Reusable pattern:** Authenticate once with `DefaultAzureCredential`, build the headers, then call a single `generate_image(...)` helper. Run a baseline single-image first; only after that succeeds, expand to a batch with `MAI-Image-2e` (the efficient variant) for throughput-oriented scenarios.

**You will produce:**
- a baseline single image (Elizabeth Tower / Westminster, London)
- 8 batch images with MAI-Image-2e covering landscapes, portraits, surrealism, and street photography
- a `data/mai-image-2-foundry/evidence.json` manifest committed alongside the gallery


### Recipe flow (what to run and what to watch)

1. Run §1 (deps) + §2 (auth) + §3 (config). Validates env, prints token principal + deployment names.
2. Run §4 (baseline single image). If this fails, the rest will fail — fix here first.
3. Run §5 (batch with MAI-Image-2e). Confirms multi-prompt throughput pattern.
4. Run §6 (evidence pack) to write the manifest.
5. Review §7 (failure modes) before opening a PR.

**Watch for:**
- The endpoint is `{endpoint}/mai/v1/images/generations`, **not** an OpenAI-style path.
- `model` in the JSON body is the **deployment name**, not the model ID.
- The first image returned can be very large in base64 — don't paste it into chat logs.
- MAI-Image-2e is faster and cheaper — default to it for batch / interactive UX.

**References:**
- [MAI announcement](https://microsoft.ai/news/today-were-announcing-3-new-world-class-mai-models-available-in-foundry/)
- [MAI-Image-2 model card PDF](https://microsoft.ai/pdf/MAI-Image-2-Model-Card.pdf)
- [Foundry usage docs](https://learn.microsoft.com/azure/foundry/foundry-models/how-to/use-foundry-models-mai?tabs=python)


> **Note on rendered output.** Each generation call writes its PNG to `media/mai-image-2-foundry/`. The embedded base64 image previews were stripped from this committed notebook so the site renderer doesn't OOM on multi-MB image blobs. Re-run any cell locally to regenerate the inline preview, or browse the PNG files directly in the repo.


## 1. Install dependencies

**What to run:** these imports once per environment. The `dotenv` + `azure.identity` stack reads `deployment.env` and powers Entra auth.


```python
import base64
import io
import math
import matplotlib.pyplot as plt
import os
import requests
import json
import sys

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path
from PIL import Image
```

## 2. Authenticate to Foundry

**What this does:** picks `DefaultAzureCredential` by default; falls back to API key when `USE_ENTRA_AUTH=false`. Empty SPN env vars are intentionally cleared because `DefaultAzureCredential` errors on empty `AZURE_CLIENT_ID`.


```python
# Auth configuration: DefaultAzureCredential by default, API key fallback
from azure.core.exceptions import ClientAuthenticationError

load_dotenv("deployment.env", override=True)

scope = "https://cognitiveservices.azure.com/.default"
USE_ENTRA_AUTH = os.getenv("USE_ENTRA_AUTH", "true").lower() == "true"
foundry_api_key = os.getenv("AZURE_FOUNDRY_API_KEY")
token_provider = None
token = None

if USE_ENTRA_AUTH:
    try:
        for env_var in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"):
            if os.getenv(env_var) == "":
                os.environ.pop(env_var, None)
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(credential, scope)
        token = token_provider()
    except ClientAuthenticationError as ex:
        raise RuntimeError(
            "DefaultAzureCredential failed. Run 'az login' (or configure managed identity/service principal) and retry."
        ) from ex
else:
    if not foundry_api_key:
        raise RuntimeError("Set AZURE_FOUNDRY_API_KEY when USE_ENTRA_AUTH=false")

def decode_current_token_claims() -> dict:
    if not USE_ENTRA_AUTH:
        return {}
    parts = token.split(".")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))

request_headers = {"Content-Type": "application/json"}
if USE_ENTRA_AUTH:
    request_headers["Authorization"] = f"Bearer {token}"
else:
    request_headers["api-key"] = foundry_api_key

print(f"Auth mode: {'DefaultAzureCredential (Bearer token)' if USE_ENTRA_AUTH else 'API key'}")
if USE_ENTRA_AUTH:
    claims = decode_current_token_claims()
    print(f"Token principal oid: {claims.get('oid', 'unknown')}")
    print(f"Token tenant id   : {claims.get('tid', 'unknown')}")
    print("Required RBAC role for image generation: Cognitive Services User")
```

## 3. Load endpoint + deployment config

**Watch for:** `MAI_IMAGE_2_DEPLOYMENT_NAME` and `MAI_IMAGE_2E_DEPLOYMENT_NAME` must match `az cognitiveservices account deployment list`.


```python
load_dotenv("deployment.env", override=True)  # Adjust the path if your .env file is located elsewhere

endpoint = os.getenv("AZURE_FOUNDRY_ENDPOINT")
deployment_name_image2 = os.getenv("MAI_IMAGE_2_DEPLOYMENT_NAME", "mai-image-2")
deployment_name_image2e = os.getenv("MAI_IMAGE_2E_DEPLOYMENT_NAME", "mai-image-2e")

print(f"MAI-Image-2 deployment : {deployment_name_image2}")
print(f"MAI-Image-2e deployment: {deployment_name_image2e}")
```

```python
IMAGES_DIR = "images"

os.makedirs(IMAGES_DIR, exist_ok=True)
```

## 4. Baseline generation (single prompt)

**What this does:** validates endpoint + auth + deployment with one round-trip. Always run this before scaling up.


```python
width, height = 768, 768

response = requests.post(
    url=f"{endpoint}/mai/v1/images/generations",
    headers=request_headers,
    json={
        "model": deployment_name_image2,
        "prompt": "A photorealistic image of Elizabeth Tower and Westminster Bridge in London, UK",
        "width": width,
        "height": height,
    },
)

if not response.ok:
    if USE_ENTRA_AUTH and response.status_code in (401, 403):
        claims = decode_current_token_claims()
        oid = claims.get("oid", "unknown")
        raise requests.HTTPError(
            f"Image generation request failed with {response.status_code}: {response.text}\n"
            "Entra auth troubleshooting:\n"
            f"- Token principal oid: {oid}\n"
            "- Required role on the Foundry account: Cognitive Services User\n"
            "- Verify AZURE_FOUNDRY_ENDPOINT and deployment name are in the same account\n"
            "- If role was just assigned, wait a few minutes and retry with a fresh token",
            response=response,
        )
    response.raise_for_status()
result = response.json()
```

```python
print(result["data"][0]["revised_prompt"])
```

```python
print(result["model"])
```

```python
print(result["size"])
```

```python
print(datetime.fromtimestamp(result["created"], tz=timezone.utc))
```

```python
image_data = next(
    (output for output in result.get("data", []) if "b64_json" in output),
    None,
)
```

```python
if image_data:
    output_path = os.path.join(IMAGES_DIR, "image.png")
    image_bytes = base64.b64decode(image_data["b64_json"])
    Path(output_path).write_bytes(image_bytes)
    print(f"Image saved to {output_path}")
    display(Image.open(io.BytesIO(image_bytes)))
else:
    print(f"Unexpected response format: {result}")
```

## 5. Batch Generation with MAI-Image-2e


**What this does:** loops the same helper across 8 prompts using MAI-Image-2e for cost-efficient batch throughput.

**Watch for:** if Foundry rate-limits, drop concurrency or add exponential backoff.


```python
def generate_image(
    endpoint: str,
    auth_headers: dict,
    deployment_name: str,
    prompt: str,
    output_path: str = "image.png",
    width: int = 1024,
    height: int = 1024,
) -> Path | None:
    """Generate an image from a text prompt using the MAI image generation API.

    Args:
        endpoint: Base URL of the API endpoint.
        auth_headers: Authorization headers for requests (Bearer or api-key).
        deployment_name: Name of the model deployment to use.
        prompt: Text description of the image to generate.
        output_path: File path where the generated image will be saved.
        width: Width of the generated image in pixels.
        height: Height of the generated image in pixels.

    Returns:
        Path to the saved image, or None if the response format was unexpected.
    """
    response = requests.post(
        url=f"{endpoint}/mai/v1/images/generations",
        headers=auth_headers,
        json={
            "model": deployment_name,
            "prompt": prompt,
            "width": width,
            "height": height,
        },
    )
    if not response.ok:
        if USE_ENTRA_AUTH and response.status_code in (401, 403):
            claims = decode_current_token_claims()
            oid = claims.get("oid", "unknown")
            raise requests.HTTPError(
                f"Image generation request failed with {response.status_code}: {response.text}\n"
                "Entra auth troubleshooting:\n"
                f"- Token principal oid: {oid}\n"
                "- Required role on the Foundry account: Cognitive Services User\n"
                "- Verify AZURE_FOUNDRY_ENDPOINT and deployment name are in the same account\n"
                "- If role was just assigned, wait a few minutes and retry with a fresh token",
                response=response,
            )
        response.raise_for_status()
    result = response.json()

    image_data = next(
        (output for output in result.get("data", []) if "b64_json" in output),
        None,
    )

    if not image_data:
        print(f"Unexpected response format: {result}")
        return None

    image_bytes = base64.b64decode(image_data["b64_json"])
    image_file = Path(output_path)
    image_file.write_bytes(image_bytes)
    
    print(f"Image saved to {image_file}")

    return image_file
```

```python
prompts = [
    "A vast desert landscape with towering red rock formations at golden hour",
    "A minimalist modernist villa perched on a cliff overlooking the Mediterranean sea",
    "A majestic snow leopard",
    "People walking through a lively London street near Covent Garden, UK",
    "Beautiful Na'vi, avatar, photorealistic, james cameron, insane details",
    "A surrealist melting clock landscape inspired by Salvador Dali in photorealistic style",
    "A photorealistic close-up portrait of a weathered 70-year-old fisherman with deep blue eyes, grey stubble, and sun-beaten skin, shot on a Hasselblad with shallow depth of field",
    "A photorealistic studio portrait of a young woman with freckles and curly auburn hair",
]
```

```python
for prompt in prompts:
    generate_image(
        endpoint=endpoint,
        auth_headers=request_headers,
        deployment_name=deployment_name_image2e,
        prompt=prompt,
        output_path=os.path.join(IMAGES_DIR, f"{'_'.join(prompt[:30].split())}.png"),
    )
```

```python
image_files = [
    os.path.join(IMAGES_DIR, f)
    for f in sorted(os.listdir(IMAGES_DIR))
    if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff"))
]

num_images = len(image_files)
ncols = 3
nrows = math.ceil(num_images / ncols)
fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 5 * nrows))
axes = axes.flatten()

for ax, img_path in zip(axes, image_files):
    img = Image.open(img_path)
    ax.imshow(img)
    ax.axis("off")
    ax.set_title(os.path.basename(img_path), fontsize=12)

for ax in axes[num_images:]:
    ax.axis("off")

plt.tight_layout()
plt.show()
```

## 6. Evidence Pack — Image Gallery + Manifest

Nine images generated by this recipe are saved under `media/mai-image-2-foundry/`. The cell below displays them inline and writes a manifest so reviewers can verify file sizes and run metadata.


```python
from datetime import datetime
from pathlib import Path
import json
from IPython.display import display, Markdown, HTML

MEDIA_DIR = Path("media/mai-image-2-foundry/")
EVIDENCE_PATH = Path("data/mai-image-2-foundry/evidence.json")
EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

gallery = sorted(MEDIA_DIR.glob("*.png"))
files = []
for p in gallery:
    files.append({"file": p.as_posix(), "size_bytes": p.stat().st_size})
    display(HTML(
        f'<p><strong>{p.name}</strong> — {p.stat().st_size:,} bytes</p>'
        f'<img src="media/mai-image-2-foundry/{p.name}" width="320" alt="{p.name}" />'
    ))

evidence = {
    "generated_at_utc": datetime.utcnow().isoformat() + "Z",
    "endpoint": globals().get("endpoint", ""),
    "deployment_image_2": globals().get("deployment_name_image2", ""),
    "deployment_image_2e": globals().get("deployment_name_image2e", ""),
    "image_count": len(files),
    "images": files,
}

EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(f"\n✅ Evidence saved: {EVIDENCE_PATH} ({len(files)} images)")

```

## 7. Failure Modes and Fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` / `403` | Principal lacks `Cognitive Services User` on Foundry account | Assign the role, refresh token |
| `404 Model not found` | `MAI_IMAGE_2_DEPLOYMENT_NAME` mismatch | Run `az cognitiveservices account deployment list` and update `deployment.env` |
| `400 Invalid size` | Width × height > 1,048,576 or any side < 768 | Stick to 768 × 768 or 1024 × 1024 for safe defaults |
| Returns generic photo | Weak prompt | Add subject, lighting, camera, composition. See §5 prompt list for examples |
| Empty `data` array in response | Content filter triggered | Soften / rephrase the prompt; check Foundry safety logs |
| Batch hits rate limit | Sequential loop too aggressive | Add backoff between calls or drop concurrency |
| Cost surprise | Image tokens dominate | Use MAI-Image-2e (cheaper, faster) for batch / iterative scenarios |


## 8. Takeaway Artifact

Two artifacts to reuse:

1. **`generate_image(endpoint, auth_headers, deployment_name, prompt, ...)`** — copy verbatim. The headers param keeps it auth-agnostic.
2. **`data/mai-image-2-foundry/evidence.json`** — drop into every release branch to give reviewers a deterministic gallery + manifest pair.


## Over to you

Our Microsoft Superintelligence (MSI) team is excited for you to try out **MAI-Image-2** on Microsoft Foundry and see how easy it is to wire direct REST image generation into your next app! Whether you're integrating image generation into a backend service, building a developer tool, or experimenting with batch creative pipelines, this recipe gives you the minimal helper, the deployment routing, and the evidence pack to confidently take it from notebook to production.

If you build something cool with this recipe, share it back with us! Open an issue or PR on Forgebook and tell us what worked, what surprised you, and where you'd like a deeper-dive recipe next.
