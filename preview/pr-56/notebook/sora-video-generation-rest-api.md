## Overview

Sora 2 is easiest to trust when you treat it like an iteration loop, not a one-shot prompt box. Start with a baseline render, decide what should stay anchored, reuse a frame as the image reference, then add audio only after the visual is working.

This recipe shows that loop with Azure OpenAI REST calls: create a video job, poll it, download the MP4, extract a reference frame, create a follow-up clip from that image, and add ambient audio without changing the scene.

**Who this is for:** Developers who want to call Sora 2 from Azure OpenAI in Microsoft Foundry using REST.

**By the end, you can:**
- Build the Sora 2 create → poll → download loop with REST.
- Use a baseline render to choose the visual anchors you want to preserve.
- Reuse an extracted frame as an image reference for a follow-up clip.
- Add scene-grounded audio cues without changing the visual concept.

**Prerequisites:**
- Azure subscription with access to Azure OpenAI in Microsoft Foundry.
- Azure OpenAI or Foundry resource in a region where `sora-2` is available.
- A `sora-2` deployment on that resource.
- Your identity has the `Cognitive Services OpenAI User` or equivalent data-plane access.
- Azure CLI signed in locally if you use `DefaultAzureCredential`.
- `ffmpeg` available on your PATH for extracting a reference frame. The notebook includes a Python fallback for local environments that do not expose the `ffmpeg` executable directly.
- Local environment variables:
  - `AZURE_OPENAI_ENDPOINT`, for example `https://<resource>.openai.azure.com`
  - `AZURE_OPENAI_DEPLOYMENT_NAME`, for example `sora-2`

**Cost and quota note:** Sora 2 generation consumes paid Azure OpenAI capacity. This notebook can submit three video jobs if you run every generation cell. If you only want to inspect the pattern, use the checked-in sample media instead of rerunning the generation cells.

**Time estimate:** ~15 minutes after the model deployment exists. Video generation can take a few minutes.

---

## Outline

1. Install dependencies and configure the endpoint.
2. Get a bearer token for the Azure OpenAI v1 API.
3. Create a baseline Sora 2 video job with a focused prompt.
4. Poll until the job completes.
5. Download and review the MP4.
6. Extract a reference image from the baseline clip.
7. Use the image reference as the source for a follow-up Sora 2 video.
8. Add ambient audio while keeping the same visual reference.

## 1. Setup and Dependencies

This notebook uses direct HTTP calls so you can see the REST contract clearly. The only Azure SDK dependency is `azure-identity`, which provides `DefaultAzureCredential` for keyless authentication.

```python
%pip install azure-identity requests python-dotenv imageio imageio-ffmpeg --quiet
```

```python
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import imageio.v3 as iio
import requests
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from IPython.display import Image as DisplayImage
from IPython.display import Video, display

load_dotenv()

endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "sora-2")

if not endpoint:
    raise ValueError("Set AZURE_OPENAI_ENDPOINT to your Azure OpenAI v1 endpoint, for example https://<resource>.openai.azure.com")

notebook_relative_video = Path("media/sora-video-generation-rest-api/01-generated-sora-sample.mp4")
repo_relative_video = Path("notebooks") / notebook_relative_video
output_video = repo_relative_video if Path("notebooks").exists() else notebook_relative_video
output_dir = output_video.parent
output_dir.mkdir(parents=True, exist_ok=True)

reference_image = output_dir / "02-paper-boat-reference.png"
image_reference_video = output_dir / "03-image-reference-sora-sample.mp4"
audio_video = output_dir / "04-audio-sora-sample.mp4"

print(f"Endpoint: {endpoint}")
print(f"Sora deployment: {deployment_name}")
```

## 2. Authenticate with Microsoft Entra ID

The Azure OpenAI v1 API accepts bearer tokens. For keyless local development, `DefaultAzureCredential` can use your Azure CLI sign-in. The token audience for this API is `https://ai.azure.com/.default`.

```python
credential = DefaultAzureCredential()
token = credential.get_token("https://ai.azure.com/.default")

headers = {
    "Authorization": f"Bearer {token.token}",
    "Content-Type": "application/json",
}

models_response = requests.get(f"{endpoint}/openai/v1/models", headers=headers, timeout=30)
models_response.raise_for_status()

available_models = [item.get("id") for item in models_response.json().get("data", [])]
print(f"Connected. Models visible on this resource: {len(available_models)}")
print(f"Sora deployment listed: {deployment_name in available_models}")
```

## 3. Write a prompt like a shot brief

**When to use:** Start here when you need a first render and do not yet know what Sora will preserve or drift on.

**What it does:** The prompt gives Sora one scene, one camera setup, one motion, and a few explicit constraints.

**How to adapt:** Change the subject, framing, motion, or duration. Keep one clear action for the first pass.

A useful Sora prompt reads less like a keyword list and more like a brief for a short shot. For the baseline, keep the action small so you can tell what changed in later iterations.

```python
prompt = """
A tiny paper boat glides across a blue tabletop under soft studio light.

Cinematography:
Camera shot: locked-off close-up, eye level with the tabletop
Motion: the boat drifts slowly from left to right; gentle ripples follow it
Lighting + palette: softbox reflection, clean blue background, calm product-demo look
Constraints: no people, no faces, no text, no logos, no copyrighted characters
Background sound: quiet water ripple only
""".strip()

video_request = {
    "model": deployment_name,
    "prompt": prompt,
    "size": "720x1280",
    "seconds": "4",
}

print(json.dumps(video_request, indent=2))
```

## 4. Create the video job

Running the next cell submits a paid Sora 2 generation job. Skip it if you only want to read the pattern and inspect the checked-in sample media.

Sora 2 generation is asynchronous. The create call returns a video object with an `id` and an initial status such as `queued` or `in_progress`. Save the `id`; every later operation uses it.

```python
create_response = requests.post(
    f"{endpoint}/openai/v1/videos",
    headers=headers,
    json=video_request,
    timeout=60,
)

if not create_response.ok:
    print(create_response.status_code)
    print(create_response.text)
create_response.raise_for_status()

video = create_response.json()
video_id = video["id"]
print(f"Video job created: {video_id}")
print(f"Initial status: {video.get('status')}")
```

Expected result: the create call returns a JSON object with a video `id`, `status`, `model`, `seconds`, and `size`. A successful first status is usually `queued` or `in_progress`.

## 5. Poll for Completion

Poll at a reasonable interval. For notebook demos, a simple loop is enough. In an app, use a background worker, webhook, or queue so a user request does not block while the render finishes.

```python
terminal_statuses = {"completed", "failed", "cancelled"}
poll_interval_seconds = 10
timeout_seconds = 10 * 60
started = time.time()

while video.get("status") not in terminal_statuses:
    if time.time() - started > timeout_seconds:
        raise TimeoutError(f"Timed out waiting for {video_id}; last status={video.get('status')}")

    time.sleep(poll_interval_seconds)
    status_response = requests.get(
        f"{endpoint}/openai/v1/videos/{video_id}",
        headers={"Authorization": headers["Authorization"]},
        timeout=60,
    )
    status_response.raise_for_status()
    video = status_response.json()
    print(f"Status: {video.get('status')} | progress: {video.get('progress')}")

if video.get("status") != "completed":
    raise RuntimeError(json.dumps(video, indent=2))

print("Video completed.")
```

Expected result: polling prints status updates such as `in_progress | progress: 0` and eventually `completed | progress: 100`. If the job fails, inspect the returned `error` object before retrying.

## 6. Download the MP4

Download the finished video immediately and copy it to durable storage. Generated assets expire on the service side, so your application should treat the download step as part of the job pipeline rather than a manual afterthought.

```python
download_response = requests.get(
    f"{endpoint}/openai/v1/videos/{video_id}/content",
    headers={"Authorization": headers["Authorization"]},
    timeout=180,
)
download_response.raise_for_status()

output_video.write_bytes(download_response.content)
print(f"Saved {output_video} ({output_video.stat().st_size:,} bytes)")
```

Expected result: the download call returns `video/mp4` content and writes a file named `01-generated-sora-sample.mp4` under the recipe media folder. The checked-in sample in this recipe is about 1.9 MB.

## 7. Reuse the job loop

The baseline cells showed the raw REST shape. For the next examples, keep the same behavior but move the repeated poll and download code into helpers. This is the part worth copying into an app or batch pipeline.

```python
def poll_video(video_id: str, *, timeout_seconds: int = 600, poll_interval_seconds: int = 10) -> dict:
    """Poll a Sora video job until it reaches a terminal state."""
    started = time.time()

    while True:
        if time.time() - started > timeout_seconds:
            raise TimeoutError(f"Timed out waiting for {video_id}")

        response = requests.get(
            f"{endpoint}/openai/v1/videos/{video_id}",
            headers={"Authorization": headers["Authorization"]},
            timeout=60,
        )
        response.raise_for_status()
        video = response.json()
        print(f"Status: {video.get('status')} | progress: {video.get('progress')}")

        if video.get("status") in {"completed", "failed", "cancelled"}:
            if video.get("status") != "completed":
                raise RuntimeError(json.dumps(video, indent=2))
            return video

        time.sleep(poll_interval_seconds)


def download_video(video_id: str, output_path: Path) -> Path:
    """Download a completed Sora video to disk."""
    response = requests.get(
        f"{endpoint}/openai/v1/videos/{video_id}/content",
        headers={"Authorization": headers["Authorization"]},
        timeout=180,
    )
    response.raise_for_status()
    output_path.write_bytes(response.content)
    print(f"Saved {output_path} ({output_path.stat().st_size:,} bytes)")
    return output_path


def create_video_from_reference(reference_path: Path, prompt: str, output_path: Path) -> dict:
    """Create, poll, and download a Sora video that starts from an image reference."""
    with reference_path.open("rb") as image_file:
        response = requests.post(
            f"{endpoint}/openai/v1/videos",
            headers={"Authorization": headers["Authorization"]},
            data={
                "model": deployment_name,
                "prompt": prompt,
                "size": "720x1280",
                "seconds": "4",
            },
            files={"input_reference": (reference_path.name, image_file, "image/png")},
            timeout=60,
        )

    if not response.ok:
        print(response.status_code)
        print(response.text)
    response.raise_for_status()

    video = response.json()
    print(f"Video job created: {video['id']}")
    poll_video(video["id"])
    download_video(video["id"], output_path)
    return video
```

## 8. Review the baseline clip

Before adding an image reference, look at the first result and decide what should stay consistent. In this example, the reusable visual anchors are the tiny paper boat, blue tabletop, soft studio light, and calm product-demo framing.

The checked-in media files are sample outputs. Run the notebook to regenerate them, or inspect the samples if you do not want to spend Sora quota.

```python
display(Video(str(output_video), embed=False, html_attributes="controls muted loop width=360"))
```

The checked-in sample below is the baseline paper-boat clip generated from the text prompt. If your notebook viewer does not render the player, open the file directly: [media/sora-video-generation-rest-api/01-generated-sora-sample.mp4](media/sora-video-generation-rest-api/01-generated-sora-sample.mp4).

<video controls muted loop playsinline width="360" src="media/sora-video-generation-rest-api/01-generated-sora-sample.mp4">
  Your browser does not support the video tag.
</video>

## 9. Extract an image reference from the baseline clip

**When to use:** Use an image reference when the first clip is close, but follow-up clips drift in subject, palette, or framing.

**What it does:** A still frame becomes the opening visual anchor for the next Sora job.

**How to adapt:** Pick a different frame, or use your own source image, as long as it matches the target video dimensions.

Instead of changing concepts, extract a still from the baseline paper-boat clip: same tiny boat, same blue tabletop, same soft studio lighting. The next prompt can focus on motion instead of re-describing every visual detail.

> **Tip:** If you do not have a source image yet, Azure OpenAI `gpt-image-2` can synthesize one. Generate a still frame with the same subject, composition, and aspect ratio you plan to use for Sora 2, then pass that image as the reference source.

```python
if not output_video.exists():
    raise FileNotFoundError(f"Run the baseline video download step first: {output_video}")

ffmpeg_path = shutil.which("ffmpeg")

if ffmpeg_path:
    subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-ss",
            "00:00:01",
            "-i",
            str(output_video),
            "-frames:v",
            "1",
            str(reference_image),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
else:
    # Portable fallback for notebook environments where ffmpeg is available
    # through imageio-ffmpeg but not exposed as a shell executable.
    frame = iio.imread(output_video, index=24)
    reference_image.write_bytes(iio.imwrite("<bytes>", frame, extension=".png"))

print(f"Saved reference image: {reference_image} ({reference_image.stat().st_size:,} bytes)")
display(DisplayImage(filename=str(reference_image), width=240))
```

Expected result: the frame extraction writes `02-paper-boat-reference.png`, a still from the baseline paper-boat clip. This image becomes the visual source for the next Sora request.

## 10. Use the image reference as the Sora source

**When to use:** Use this after you have a frame that captures the composition you want to preserve.

**What it does:** The image anchors the opening frame; the prompt describes the motion.

**How to adapt:** Keep the reference stable and change one motion instruction at a time.

```python
image_reference_prompt = """
Use the reference image as the opening frame. Keep the same tiny paper boat, blue tabletop, and soft studio lighting.
Animate only a subtle drift: the boat glides forward a few centimeters, small ripples spread outward, and the camera remains locked off.
No people, no faces, no text, no logos, no copyrighted characters.
""".strip()

image_video = create_video_from_reference(reference_image, image_reference_prompt, image_reference_video)
display(Video(str(image_reference_video), embed=False, html_attributes="controls muted loop width=360"))
```

Expected result: the follow-up video keeps the composition from the reference image while adding only the motion described in the prompt. If the output drifts too far, simplify the motion instruction before changing the visual reference.

The sample below was generated from the extracted paper-boat reference image.

<video controls muted loop playsinline width="360" src="media/sora-video-generation-rest-api/03-image-reference-sora-sample.mp4">
  Your browser does not support the video tag.
</video>

## 11. Add ambient audio

**When to use:** Add audio after the visual clip is working. If the picture is still drifting, fix that first.

**What it does:** Sora generates a new clip from the same reference image with audio cues in the prompt.

**How to adapt:** Name concrete sounds, set volume intent, and say what to avoid. Broad requests like "make it cinematic" are usually too vague.

For this paper-boat shot, the audio target is crisp water ripples, a light paper flutter, and a small tabletop splash. Same scene, one new dimension.

```python
audio_prompt = """
Use the reference image as the opening frame. Keep the same tiny paper boat, blue tabletop, and soft studio lighting.
The boat drifts forward slowly while small ripples spread outward. Keep the camera locked off.
Add clearly audible generated ambient audio at normal listening volume: crisp water ripples, a light paper-boat flutter, and a soft tabletop splash when the boat moves.
No music, no speech, no people, no faces, no text, no logos, no copyrighted characters.
""".strip()

audio_job = create_video_from_reference(reference_image, audio_prompt, audio_video)
display(Video(str(audio_video), embed=False, html_attributes="controls width=360"))
```

Expected result: the final clip preserves the same reference image and motion, with an added ambient sound bed. The sample below was generated with the audio prompt above. Use the player controls and make sure the video is unmuted when previewing it.

<video controls playsinline width="360" src="media/sora-video-generation-rest-api/04-audio-sora-sample.mp4">
  Your browser does not support the video tag.
</video>

## What changed across the three outputs

| Step | Input | Output | What changed | What stayed anchored |
| --- | --- | --- | --- | --- |
| Baseline | Text shot brief | `01-generated-sora-sample.mp4` | First Sora render | Paper boat, blue tabletop, soft light |
| Image reference | Extracted frame | `03-image-reference-sora-sample.mp4` | Motion is constrained by the still frame | Subject, palette, framing |
| Audio | Same reference image plus audio prompt | `04-audio-sora-sample.mp4` | Ambient sound is added | Visual concept and camera setup |

This is the pattern to copy: get one good visual anchor, then change one variable per follow-up job.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `401 Unauthorized` | Missing or expired token | Run `az login` and make sure `DefaultAzureCredential` can access your tenant. |
| `403 Forbidden` | Your identity lacks data-plane access | Assign `Cognitive Services OpenAI User` or equivalent at the resource scope. |
| `404 Not Found` on `/openai/v1/videos` | Endpoint host or deployment is wrong | Use the Azure OpenAI v1 endpoint shape, such as `https://<resource>.openai.azure.com`. |
| `400 invalid_value` for `seconds` or `size` | Unsupported Sora 2 parameter | Start with `seconds="4"` and `size="720x1280"` or another supported value. |
| Image-reference request fails with a size error | Reference image dimensions do not match the requested video size | Extract or resize the reference image to the exact target size before calling Sora 2. |
| Audio is missing or not what you expected | Audio cue was vague or competed with visual instructions | Keep audio short and concrete: source, texture, and what to avoid. |
| `429 Too Many Requests` | Sora 2 job quota or deployment capacity is exhausted | Wait, reduce concurrency, or increase deployment capacity/quota. |
| Job ends as `failed` | Content policy, prompt ambiguity, or service issue | Inspect the `error` field, simplify the prompt, and avoid real people, copyrighted characters, logos, and unsafe content. |

## Takeaways and next steps

You built the full Sora 2 REST loop: create the job, poll it, and download the MP4. That is the core app pattern.

You used the baseline render to choose visual anchors: paper boat, blue tabletop, soft light, locked-off camera. That gave the second job something concrete to preserve.

You extracted one frame and reused it as the image reference. The important bit is not the paper boat; it is the habit of changing one variable at a time.

You added audio last. That keeps debugging sane: first get the picture stable, then add scene-grounded sounds.

**Try next:**
- Extract a different frame from the baseline video and compare which one anchors the follow-up better.
- Replace the extracted still with your own product photo or storyboard frame.
- Create two audio variants from the same image reference: one quiet product-demo take and one more atmospheric take.
- Move `poll_video` and `download_video` into a queue-backed worker for production apps.