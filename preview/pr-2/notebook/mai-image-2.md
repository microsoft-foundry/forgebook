## Build a Production-Ready Text-to-Image Recipe with MAI-Image-2 and MAI-Image-2e

**Problem this recipe solves:** You need a single endpoint + helper to generate, A/B compare, and batch images across MAI-Image-2 and MAI-Image-2e, with cost visibility and failure-mode awareness — before you wire it into a product.

**Who this is for:** Developers shipping creative tools, marketing automation, e-commerce visualization, or content moderation pipelines on Microsoft Foundry.

**Reusable pattern:** Wrap the Foundry `/mai/v1/images/generations` REST call once. Layer different prompts, dimensions, and deployments (`mai-image-2` vs `mai-image-2e`) on top of the same helper. Save every image to a deterministic file name so PR reviewers can browse the gallery.

**You will produce:**
- a `generate_image(...)` helper with retry-friendly status handling
- 17 reference images saved to `media/mai-image-2/` covering basic generation, text rendering, creative styles, dimension presets, batch pipelines, and 2 vs 2e comparison
- a `data/mai-image-2/evidence.json` manifest with deployment names and file metadata


### Recipe flow (what to run and what to watch)

1. Run §1 setup + §2 helper. Validates endpoint, auth, and the wrapper function.
2. Run §3 (basic generation) first — confirms your deployment name and that a single image lands on disk.
3. Run §4 (text rendering) and §5 (creative styles) for prompt-engineering reference points.
4. Run §6 (2 vs 2e comparison) when deciding which deployment to default to in production.
5. Run §7 (custom dimensions) to learn the resolution constraints first-hand.
6. Run §8 (batch pipeline) only after §3 succeeded — batch failures are expensive to debug.
7. Run §10 (cost calculator) before any batch workload.
8. Run §11 (evidence) and §12 (failure modes) when packaging the PR.

**Watch for:**
- Total pixels must be ≤ 1,048,576 and each side ≥ 768.
- `MAI_IMAGE_2_DEPLOYMENT_NAME` and `MAI_IMAGE_2E_DEPLOYMENT_NAME` must match exactly what you deployed.
- Prompt quality dominates output quality — vague prompts return generic stock-photo results.
- Cost is per **image token**, not per image; large images burn more tokens.


> **Note on rendered output.** Each `generate_image(...)` call writes its PNG to `media/mai-image-2/`. The embedded base64 image previews were stripped from this committed notebook so the site renderer doesn't OOM on multi-MB image blobs. Re-run any cell locally to regenerate the inline preview, or browse the PNG files directly in the repo.


## 1. Setup

**What this does:** loads env, builds auth headers, prints deployment names so you can confirm `mai-image-2` vs `mai-image-2e` are reachable.


```python
# %pip install -q requests python-dotenv Pillow azure-identity
```

```python
import os
import base64
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from IPython.display import Image as IPImage, display
from PIL import Image
import io

load_dotenv(dotenv_path="deployment.env", override=True)

AZURE_FOUNDRY_ENDPOINT = os.getenv("AZURE_FOUNDRY_ENDPOINT")
AZURE_FOUNDRY_API_KEY  = os.getenv("AZURE_FOUNDRY_API_KEY")
USE_ENTRA_AUTH = os.getenv("USE_ENTRA_AUTH", "true").lower() == "true"
DEPLOYMENT_MAI_IMAGE_2  = os.getenv("MAI_IMAGE_2_DEPLOYMENT_NAME", "mai-image-2")
DEPLOYMENT_MAI_IMAGE_2E = os.getenv("MAI_IMAGE_2E_DEPLOYMENT_NAME", "mai-image-2e")

assert AZURE_FOUNDRY_ENDPOINT, "Set AZURE_FOUNDRY_ENDPOINT in your .env file"
if not USE_ENTRA_AUTH:
    assert AZURE_FOUNDRY_API_KEY, "Set AZURE_FOUNDRY_API_KEY in your .env file when USE_ENTRA_AUTH=false"

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

def build_image_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if USE_ENTRA_AUTH:
        headers["Authorization"] = f"Bearer {token_provider()}"
    else:
        headers["api-key"] = AZURE_FOUNDRY_API_KEY
    return headers

IMAGES_API_URL = f"{AZURE_FOUNDRY_ENDPOINT.rstrip('/')}/mai/v1/images/generations"

print(f"✅ Images API URL      : {IMAGES_API_URL}")
print(f"✅ MAI-Image-2 deployment  : {DEPLOYMENT_MAI_IMAGE_2}")
print(f"✅ MAI-Image-2e deployment : {DEPLOYMENT_MAI_IMAGE_2E}")
print(f"✅ Auth mode           : {'DefaultAzureCredential (Bearer token)' if USE_ENTRA_AUTH else 'API key'}")
if USE_ENTRA_AUTH:
    claims = decode_current_token_claims()
    print(f"✅ Token principal oid: {claims.get('oid', 'unknown')}")
    print(f"✅ Token tenant id   : {claims.get('tid', 'unknown')}")
    print("ℹ️ Required RBAC role for image generation: Cognitive Services User")
```

## 2. Core Helper Function

**What this does:** defines `generate_image(...)` — the single function the rest of this recipe layers on top of. Copy this verbatim into your service.


```python
def generate_image(
    prompt: str,
    output_path: str,
    deployment: str = DEPLOYMENT_MAI_IMAGE_2,
    width: int = 1024,
    height: int = 1024,
) -> dict:
    """
    Generate an image with MAI-Image-2 or MAI-Image-2e.
    Returns the raw API response dict.
    Constraints: width >= 768, height >= 768, width*height <= 1,048,576
    """
    assert width >= 768 and height >= 768, "Both width and height must be ≥ 768"
    assert width * height <= 1_048_576,    "width × height must not exceed 1,048,576"

    payload = {
        "model":  deployment,
        "prompt": prompt,
        "width":  width,
        "height": height,
    }

    headers = build_image_headers()

    start    = time.time()
    response = requests.post(IMAGES_API_URL, headers=headers, json=payload)
    elapsed  = time.time() - start

    if not response.ok:
        if USE_ENTRA_AUTH and response.status_code in (401, 403):
            claims = decode_current_token_claims()
            oid = claims.get("oid", "unknown")
            raise requests.HTTPError(
                f"Image generation request failed with {response.status_code}: {response.text}\n"
                "Entra auth troubleshooting:\n"
                f"- Token principal oid: {oid}\n"
                "- Required role on the Foundry account: Cognitive Services User\n"
                "- Verify AZURE_FOUNDRY_ENDPOINT points to the target account\n"
                "- If role was just assigned, wait a few minutes and retry with a fresh token",
                response=response,
            )
        response.raise_for_status()
    result = response.json()

    # Decode and save image
    image_data = [item for item in result.get("data", []) if "b64_json" in item]
    if image_data:
        img_bytes = base64.b64decode(image_data[0]["b64_json"])
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        size_kb = len(img_bytes) / 1024
        print(f"✅ Saved: {output_path} ({size_kb:.0f} KB)  |  {width}×{height}  |  {elapsed:.1f}s")
    else:
        print("⚠️ No image data in response:", result)

    return result


def show_image(path: str, title: str = "") -> None:
    """Display a saved image inline in Jupyter."""
    img = Image.open(path)
    print(f"{title} ({img.size[0]}×{img.size[1]})")
    display(IPImage(filename=path, width=512))
```

## 3. Basic Image Generation

**What this does:** generates a banner and a clean product shot. Both are saved locally and re-referenced from the evidence gallery later.

**Watch for:** if this step fails with `404`, the deployment name is wrong — fix `MAI_IMAGE_2_DEPLOYMENT_NAME` in `deployment.env`.


```python
result = generate_image(
    prompt="A photorealistic mountain lake at sunrise, misty atmosphere, "
           "golden hour lighting, crystal clear water reflecting snow-capped peaks",
    output_path="media/mai-image-2/img_landscape.png",
)
show_image("media/mai-image-2/img_landscape.png", "Photorealistic Landscape")
```

```python
# Product shot: clean studio style
generate_image(
    prompt="Professional product photography of a sleek midnight-blue wireless headphone "
           "on a white marble surface, soft studio lighting, subtle shadow",
    output_path="media/mai-image-2/img_product.png",
)
show_image("media/mai-image-2/img_product.png", "Product Photography")
```

## 4. Text Rendering in Images

MAI-Image-2 excels at in-image text for infographics, banners, and diagrams.

**Why it matters:** MAI-Image-2 renders clear in-image text — diagrams, posters, charts. Make sure to quote the exact text in the prompt.


```python
generate_image(
    prompt="A modern tech conference banner with large bold text: 'Microsoft Foundry 2026' "
           "on a deep blue gradient background with subtle circuit-board patterns, "
           "professional design, clean typography",
    output_path="media/mai-image-2/img_banner.png",
)
show_image("media/mai-image-2/img_banner.png", "Conference Banner with Text")
```

```python
# Infographic with data labels
generate_image(
    prompt="A clean flat-style infographic showing three icons side by side: "
           "a microphone labeled 'Transcribe', a speaker labeled 'Voice', "
           "and an image frame labeled 'Image'. Minimal white background, "
           "blue and orange accent colors, modern sans-serif font",
    output_path="media/mai-image-2/img_infographic.png",
)
show_image("media/mai-image-2/img_infographic.png", "Infographic with Labels")
```

## 5. Creative & Stylized Outputs

**Why it matters:** demonstrates anime / cinematic / portrait styles so you can calibrate prompts before shipping a creative tool.


```python
# Anime/illustration style
generate_image(
    prompt="Anime-style illustration of a futuristic AI assistant floating above a city "
           "at night, glowing teal circuits, vibrant neon colors, detailed background, "
           "Studio Ghibli aesthetic",
    output_path="media/mai-image-2/img_anime.png",
)
show_image("media/mai-image-2/img_anime.png", "Anime Style")
```

```python
# Cinematic portrait
generate_image(
    prompt="Cinematic portrait of a software engineer at a futuristic holographic workstation, "
           "dramatic side lighting, shallow depth of field, photorealistic, "
           "8K resolution quality, cinematic color grading",
    output_path="media/mai-image-2/img_portrait.png",
)
show_image("media/mai-image-2/img_portrait.png", "Cinematic Portrait")
```

## 6. Deployment Comparison (MAI-Image-2 vs MAI-Image-2e)

This section runs the same prompt on both deployments so you can compare latency and output style.

**Watch for:** the timing comparison is a single sample, not a benchmark. Use it as a sanity check; run a proper load test for production decisions. MAI-Image-2e is the efficient variant — faster, lower cost per image, slight quality trade-off.


```python
import time

prompt = (
    "Professional product shot of a smartphone with a vibrant abstract wallpaper, "
    "white background, clean studio lighting"
)

results = []
for dep, out in [
    (DEPLOYMENT_MAI_IMAGE_2,  "media/mai-image-2/img_image2_compare.png"),
    (DEPLOYMENT_MAI_IMAGE_2E, "media/mai-image-2/img_image2e_compare.png"),
]:
    t0 = time.time()
    generate_image(prompt, out, deployment=dep)
    latency = time.time() - t0
    results.append((dep, latency, out))

print(f"\n{'Deployment':<28} {'Latency':>10}")
print("-" * 42)
for dep, latency, _ in results:
    print(f"{dep:<28} {latency:>9.2f}s")

for dep, _, out in results:
    show_image(out, f"Output: {dep}")
```

```python
# Optional second render with MAI-Image-2e (useful for fast prompt iteration)
variant_prompt = (
    "Professional product shot of a smartphone with a vibrant abstract wallpaper, "
    "dark graphite background, dramatic rim lighting, premium advertising style"
 )

generate_image(
    variant_prompt,
    "media/mai-image-2/img_image2e_variant.png",
    deployment=DEPLOYMENT_MAI_IMAGE_2E,
 )
show_image("media/mai-image-2/img_image2e_variant.png", "Variant Render (MAI-Image-2e)")
```

## 7. Custom Dimensions

Generate landscape, portrait, or square images. Constraint: `width × height ≤ 1,048,576`, both ≥ 768.

**Watch for:** each side must be ≥ 768 and total pixels ≤ 1,048,576. The cell renders four common ratios so you can pick deterministic preset sizes.


```python
dimension_configs = [
    ("Square 1024×1024",   1024, 1024),
    ("Landscape 1024×768", 1024, 768),
    ("Portrait 768×1024",  768,  1024),
    ("Wide 1365×768",      1365, 768),   # 1365*768 = 1,048,320 ✅ just under limit
]

prompt_dim = "A serene Japanese zen garden with raked gravel, moss-covered stones, and a single cherry blossom tree"

for label, w, h in dimension_configs:
    out = f"img_dim_{w}x{h}.png"
    print(f"\n{label} ({w*h:,} total pixels)")
    generate_image(prompt_dim, out, deployment=DEPLOYMENT_MAI_IMAGE_2E, width=w, height=h)
    show_image(out, label)
```

## 8. Batch Generation Pipeline

Generate multiple images from a list of prompts — useful for marketing campaigns or content pipelines.

**What this does:** parallel pipeline using `concurrent.futures`. Use a small thread pool — Foundry rate-limits per deployment.


```python
import concurrent.futures

BATCH_PROMPTS = [
    ("A warm cozy café interior with exposed brick, morning light through tall windows", "media/mai-image-2/batch_cafe.png"),
    ("Futuristic electric sports car on a coastal highway at dusk, dramatic sky",       "media/mai-image-2/batch_car.png"),
    ("Overhead flat-lay of a healthy meal prep with colorful vegetables and grains",    "media/mai-image-2/batch_food.png"),
    ("Abstract geometric art in navy, gold, and cream, suitable for office wall decor", "media/mai-image-2/batch_art.png"),
]

def generate_batch_item(args):
    prompt, output_path = args
    try:
        generate_image(prompt, output_path, deployment=DEPLOYMENT_MAI_IMAGE_2E)
        return output_path, None
    except Exception as e:
        return output_path, str(e)

print(f"Generating {len(BATCH_PROMPTS)} images (using MAI-Image-2e for cost efficiency)...")
t_start = time.time()

# Sequential generation (rate limit friendly)
results = []
for args in BATCH_PROMPTS:
    path, err = generate_batch_item(args)
    results.append((path, err))

total_time = time.time() - t_start
succeeded  = sum(1 for _, e in results if e is None)
print(f"\n✅ {succeeded}/{len(BATCH_PROMPTS)} images generated in {total_time:.1f}s")

# Display all
for path, err in results:
    if err is None:
        show_image(path, path)
```

## 9. Microsoft Entra ID Authentication (Production)

**Why it matters:** API keys for dev, Entra for production. The helper supports both via `USE_ENTRA_AUTH`.


```python
print("✅ This notebook now uses DefaultAzureCredential by default.")
print("Set USE_ENTRA_AUTH=false in .env to force API key mode.")
```

## 10. 💰 Cost Calculator

**MAI-Image-2 pricing:**
- Text input: **\$5 per 1M tokens**
- Image output: **\$33 per 1M image tokens**

**MAI-Image-2e** (efficient) is approximately 4× more cost-efficient for image output.

**Token estimation:**
- Text input: ~1 token per 4 chars (standard GPT tokenization). A 100-word prompt ≈ 133 tokens.
- Image output tokens: each image is counted as a fixed number of tokens based on resolution.

**Watch for:** image-token output cost dominates — keep dimensions modest unless the use case demands large outputs.


```python
# ── Cost Calculator ─────────────────────────────────────────
PRICE_TEXT_PER_1M   = 5.00   # USD per 1M text input tokens
PRICE_IMAGE_PER_1M  = 33.00  # USD per 1M image output tokens (MAI-Image-2)

# Approximate image output tokens per image (based on Azure image token counting):
# 1024×1024 ~ 1,056 tokens (approximate; consult Azure pricing page for exact)
IMAGE_TOKENS_PER_IMAGE = 1056  # approximate for 1024×1024

# Approximate text tokens for a typical prompt
AVG_PROMPT_TOKENS = 75  # ~75 tokens per prompt (300 chars)

scenarios = {
    "Prototype / 10 images":          10,
    "Daily marketing batch (100)":    100,
    "Weekly pipeline (1,000)":      1_000,
    "Monthly production (10,000)": 10_000,
    "Enterprise scale (100,000)": 100_000,
}

print(f"\nMAI-Image-2 Cost Estimator")
print(f"  Text input : ${PRICE_TEXT_PER_1M}/1M tokens")
print(f"  Image output: ${PRICE_IMAGE_PER_1M}/1M tokens (~{IMAGE_TOKENS_PER_IMAGE} tokens/image at 1024×1024)")
print()
print(f"{'Scenario':<35} {'Images':>8} {'Text cost':>12} {'Image cost':>12} {'Total':>12}")
print("-" * 81)

for label, n_images in scenarios.items():
    text_cost  = (n_images * AVG_PROMPT_TOKENS / 1_000_000) * PRICE_TEXT_PER_1M
    image_cost = (n_images * IMAGE_TOKENS_PER_IMAGE / 1_000_000) * PRICE_IMAGE_PER_1M
    total      = text_cost + image_cost
    print(f"{label:<35} {n_images:>8,} ${text_cost:>11.4f} ${image_cost:>11.4f} ${total:>11.4f}")

print()
print("Note: MAI-Image-2e is 4× more efficient — image output cost ~75% lower.")
print(f"{'Scenario':<35} {'Images':>8} {'Image cost (2e)':>16} {'Total (2e)':>12}")
print("-" * 73)
for label, n_images in scenarios.items():
    text_cost   = (n_images * AVG_PROMPT_TOKENS / 1_000_000) * PRICE_TEXT_PER_1M
    image_cost_e = (n_images * IMAGE_TOKENS_PER_IMAGE / 1_000_000) * PRICE_IMAGE_PER_1M * 0.25  # ~4× cheaper
    total_e      = text_cost + image_cost_e
    print(f"{label:<35} {n_images:>8,} ${image_cost_e:>15.4f} ${total_e:>11.4f}")
```

## 11. Summary & Next Steps

| Feature | MAI-Image-2 | MAI-Image-2e |
|---|---|---|
| Photorealistic synthesis | ✅ | ✅ |
| In-image text rendering | ✅ | ✅ (short text) |
| Complex multi-subject layouts | ✅ | ✅ |
| Anime / illustration styles | ✅ | ✅ |
| Batch pipeline | ✅ | ✅ (recommended) |
| Custom dimensions | ✅ | ✅ |
| Speed | High | 22% faster |
| Efficiency | — | 4× more efficient |

**Resources:**
- [Model Card: MAI-Image-2](https://ai.azure.com/catalog/models/MAI-Image-2)
- [MS Docs: Use Foundry MAI Models](https://learn.microsoft.com/azure/foundry/foundry-models/how-to/use-foundry-models-mai)
- [Deploy MAI-Image-2 in Foundry portal](https://learn.microsoft.com/azure/foundry/foundry-models/how-to/deploy-foundry-models)
- [Arena.ai leaderboard](https://arena.ai/leaderboard/text-to-image)
- [MAI Playground](https://playground.microsoft.ai)
- [Pricing details](https://azure.microsoft.com/pricing/details/cognitive-services)

Checklist for promoting this helper into a service.


## 12. Evidence Pack — Image Gallery + Manifest

The 19 images below are committed to `media/mai-image-2/` so reviewers can verify what this notebook produces without rerunning generations.


```python
from datetime import datetime
from pathlib import Path
import json
from IPython.display import display, Markdown, Image as IPyImage

MEDIA_DIR = Path("media/mai-image-2/")
EVIDENCE_PATH = Path("data/mai-image-2/evidence.json")
EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)

gallery = sorted(MEDIA_DIR.glob("*.png"))
files = []
for p in gallery:
    files.append({"file": p.as_posix(), "size_bytes": p.stat().st_size})
    display(Markdown(f"**{p.name}** — {p.stat().st_size:,} bytes"))
    display(IPyImage(filename=str(p), width=320))

evidence = {
    "generated_at_utc": datetime.utcnow().isoformat() + "Z",
    "deployment_image_2": globals().get("DEPLOYMENT_NAME") or "mai-image-2",
    "image_count": len(files),
    "images": files,
}

EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
print(f"\n✅ Evidence saved: {EVIDENCE_PATH} ({len(files)} images)")

```

## 13. Failure Modes and Fixes

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` / `403` | Token principal lacks `Cognitive Services User` on the Foundry account | Assign the role, refresh the token, re-run |
| `404 Deployment not found` | `MAI_IMAGE_2_DEPLOYMENT_NAME` / `MAI_IMAGE_2E_DEPLOYMENT_NAME` mismatch | Compare with `az cognitiveservices account deployment list`; update `deployment.env` |
| `400 invalid dimensions` | Width × height > 1,048,576 or any side < 768 | Pick from the §7 preset table; this is a hard constraint |
| Generic / stock-looking images | Weak prompt | Add subject, style, lighting, camera, and composition cues. See §5 for examples |
| Garbled text in-image | Prompt didn't quote the exact text | Wrap the literal text in double quotes inside the prompt |
| Batch job partial failures | Pool size too high, hit rate limits | Drop concurrency to 2–3 in §8 and add retries |
| Cost surprise | Image-token output dominates | Run §10 first; default to MAI-Image-2e for high-volume scenarios |
| Wrong aspect ratio | Forgot width/height defaults | Always pass `width` and `height` explicitly — the helper defaults to 1024×1024 |


## 14. Takeaway Artifact

Reuse three things from this recipe:

1. **`generate_image(...)`** — the single helper that every other section layers on top of.
2. **The dimension table in §7** — gives you four production-safe aspect ratios that respect the 1,048,576 total-pixel cap.
3. **`data/mai-image-2/evidence.json`** — the manifest pattern. Commit one per batch release.


## Over to you

Our Microsoft Superintelligence (MSI) team is excited for you to try out **MAI-Image-2** and **MAI-Image-2e** and see how easy it is to build high-fidelity, fast, and cost-aware text-to-image experiences in your next app! Whether you're powering a creative tool, generating marketing assets at scale, illustrating storyboards, or building product visualization workflows, this recipe hands you the helper, the dimension table, the 2-vs-2e tradeoff, and the failure-mode playbook to ship with confidence.

If you build something cool with this recipe, share it back with us! Open an issue or PR on Forgebook and tell us what worked, what surprised you, and where you'd like a deeper-dive recipe next.
