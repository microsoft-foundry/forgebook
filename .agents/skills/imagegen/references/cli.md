# CLI reference (`scripts/image_gen.py`)

This file contains the "command catalog" for the bundled image generation CLI. Keep `SKILL.md` as overview-first; put verbose CLI details here.

## What this CLI does
- `generate`: generate new images from a prompt
- `edit`: edit an existing image (optionally with a mask) — inpainting / background replacement / "change only X"
- `generate-batch`: run many jobs from a JSONL file (one job per line)

Real API calls require **network access** + `PROJECT_ENDPOINT` + `API_KEY`. `--dry-run` does not.

## Quick start

Set the CLI path:

```
export IMAGE_GEN=".agents/skills/imagegen/scripts/image_gen.py"
```

Dry-run (no API call; no network required; does not require Azure SDK):

```
python3 "$IMAGE_GEN" generate --prompt "Test" --dry-run
```

Generate (requires `PROJECT_ENDPOINT` + `API_KEY` + network):

```
uv run --with azure-ai-projects --with azure-identity --with openai \
  python3 "$IMAGE_GEN" generate \
  --prompt "A cozy alpine cabin at dawn" --size 1024x1024
```

Or with packages already installed:

```
python3 "$IMAGE_GEN" generate --prompt "A cozy alpine cabin at dawn" --size 1024x1024
```

The script auto-loads `.env` from the repo root, so you can put credentials there:
```
PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
API_KEY=<your-api-key>
```

## Guardrails (important)
- Use `python3 "$IMAGE_GEN" ...` (or equivalent full path) for generations/edits/batch work.
- Do **not** create one-off runners (e.g. `gen_images.py`) unless the user explicitly asks for a custom wrapper.
- **Never modify** `scripts/image_gen.py`. If something is missing, ask the user before doing anything else.

## Defaults (unless overridden by flags)
- Model: `gpt-image-1.5`
- Size: `1024x1024`
- Quality: `auto`
- Output format: `png`
- Background: unspecified (API default). If you set `--background transparent`, also set `--output-format png` or `webp`.

## Quality + input fidelity
- `--quality` works for `generate`, `edit`, and `generate-batch`: `low|medium|high|auto`.
- `--input-fidelity` is **edit-only**: `low|high` (use `high` for strict edits like identity or layout lock).

Example:
```
python3 "$IMAGE_GEN" edit --image input.png --prompt "Change only the background" --quality high --input-fidelity high
```

## Masks (edits)
- Use a **PNG** mask; an alpha channel is strongly recommended.
- The mask should match the input image dimensions.
- In the edit prompt, repeat invariants (e.g., "change only the background; keep the subject unchanged") to reduce drift.

## Optional deps
Prefer `uv run --with ...` for an out-of-the-box run without changing the current project env; otherwise install into your active env:

```
uv pip install azure-ai-projects azure-identity openai
```

## Common recipes

Generate + also write a downscaled copy for fast web loading:

```
uv run --with azure-ai-projects --with azure-identity --with openai --with pillow \
  python3 "$IMAGE_GEN" generate \
  --prompt "A cozy alpine cabin at dawn" \
  --size 1024x1024 \
  --downscale-max-dim 1024
```

Notes:
- Downscaling writes an extra file next to the original (default suffix `-web`, e.g. `output-web.png`).
- Downscaling requires Pillow (use `uv run --with pillow ...` or install it into your env).

Generate with augmentation fields:

```
python3 "$IMAGE_GEN" generate \
  --prompt "A minimal hero image of a ceramic coffee mug" \
  --use-case "landing page hero" \
  --style "clean product photography" \
  --composition "centered product, generous negative space" \
  --constraints "no logos, no text"
```

Generate multiple prompts concurrently (async batch):

```
mkdir -p tmp/imagegen
cat > tmp/imagegen/prompts.jsonl << 'EOF'
{"prompt":"Cavernous hangar interior with a compact shuttle parked center-left, open bay door","use_case":"game concept art environment","composition":"wide-angle, low-angle, cinematic framing","lighting":"volumetric light rays through drifting fog","constraints":"no logos or trademarks; no watermark","size":"1536x1024"}
{"prompt":"Gray wolf in profile in a snowy forest, crisp fur texture","use_case":"wildlife photography print","composition":"100mm, eye-level, shallow depth of field","constraints":"no logos or trademarks; no watermark","size":"1024x1024"}
EOF

python3 "$IMAGE_GEN" generate-batch --input tmp/imagegen/prompts.jsonl --out-dir out --concurrency 5

# Cleanup (recommended)
rm -f tmp/imagegen/prompts.jsonl
```

Edit:

```
python3 "$IMAGE_GEN" edit --image input.png --mask mask.png --prompt "Replace the background with a warm sunset"
```

## CLI notes
- Supported sizes: `1024x1024`, `1536x1024`, `1024x1536`, or `auto`.
- Transparent backgrounds require `output_format` to be `png` or `webp`.
- Default output is `output.png`; multiple images become `output-1.png`, `output-2.png`, etc.
- Use `--no-augment` to skip prompt augmentation.

## See also
- API parameter quick reference: `references/image-api.md`
- Prompt examples: `references/sample-prompts.md`
