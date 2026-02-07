# Image API quick reference

## Endpoints
- Generate: `POST /v1/images/generations` (`client.images.generate(...)`)
- Edit: `POST /v1/images/edits` (`client.images.edit(...)`)

Both use the OpenAI-compatible client obtained from Azure AI Projects SDK:
```python
from azure.ai.projects import AIProjectClient
from azure.core.credentials import AzureKeyCredential

project_client = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],
    credential=AzureKeyCredential(os.environ["API_KEY"]),
)
client = project_client.get_openai_client()
```

## Models
- Default: `gpt-image-1.5`

## Core parameters (generate + edit)
- `prompt`: text prompt
- `model`: image model
- `n`: number of images (1-10)
- `size`: `1024x1024`, `1536x1024`, `1024x1536`, or `auto`
- `quality`: `low`, `medium`, `high`, or `auto`
- `background`: `transparent`, `opaque`, or `auto` (transparent requires `png`/`webp`)
- `output_format`: `png` (default), `jpeg`, `webp`
- `output_compression`: 0-100 (jpeg/webp only)
- `moderation`: `auto` (default) or `low`

## Edit-specific parameters
- `image`: one or more input images (first image is primary)
- `mask`: optional mask image (same size, alpha channel required)
- `input_fidelity`: `low` (default) or `high` (support varies by model) - set it to `high` if the user needs a very specific edit and you can't achieve it with the default `low` fidelity.

## Output
- `data[]` list with `b64_json` per image

## Limits & notes
- Input images and masks must be under 50MB.
- Use edits endpoint when the user requests changes to an existing image.
- Masking is prompt-guided; exact shapes are not guaranteed.
- Large sizes and high quality increase latency and cost.
- For fast iteration or latency-sensitive runs, start with `quality=low`; raise to `high` for text-heavy or detail-critical outputs.
- Use `input_fidelity=high` for strict edits (identity preservation, layout lock, or precise compositing).
