"""Rebuild the small CC BY 4.0 speech fixture and its synthetic-noise pair."""

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import wave

import numpy as np
import requests


REVISION = "fe61c4ba0d9ac8dd7e23d719cc79f8947e1dc742"
SOURCE_FILES = [f"clean_train/p234_{index:03d}.wav" for index in (4, 5, 6)]
SLUG = "mai-transcribe-2-noisy-audio"
DATA_DIR = Path(__file__).resolve().parent
MEDIA_DIR = DATA_DIR.parents[1] / "media" / SLUG
SEED = 42
SNR_DB = 10.0
SAMPLE_RATE = 16000


def read_pcm(content: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(content), "rb") as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (
            1, 2, SAMPLE_RATE
        ):
            raise ValueError("Expected mono, 16-bit, 16 kHz source audio.")
        return np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(
            np.float64
        ) / 32768


def write_pcm(path: Path, samples: np.ndarray) -> None:
    if not np.isfinite(samples).all() or np.max(np.abs(samples)) >= 1:
        raise ValueError("Refusing to write non-finite or clipped audio.")
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(np.rint(samples * 32767).astype("<i2").tobytes())


def prepare_audio(snr_db: float, media_dir: Path, manifest_path: Path) -> dict:
    if not math.isfinite(snr_db):
        raise ValueError("SNR must be a finite number.")
    clips = []
    sources = []
    for filename in SOURCE_FILES:
        url = f"https://raw.githubusercontent.com/microsoft/MS-SNSD/{REVISION}/{filename}"
        response = requests.get(url, timeout=(10, 60))
        response.raise_for_status()
        clips.append(read_pcm(response.content))
        sources.append({
            "path": filename,
            "url": url,
            "sha256": hashlib.sha256(response.content).hexdigest(),
        })

    silence = np.zeros(SAMPLE_RATE // 2, dtype=np.float64)
    clean = np.concatenate([clips[0], silence, clips[1], silence, clips[2]])
    noise = np.random.default_rng(SEED).standard_normal(clean.size)
    noise -= noise.mean()
    noise *= np.sqrt(np.mean(clean ** 2) / np.mean(noise ** 2)) / 10 ** (snr_db / 20)
    noisy = clean + noise
    gain = 0.9 / max(np.max(np.abs(clean)), np.max(np.abs(noisy)))
    clean *= gain
    noisy *= gain

    media_dir.mkdir(parents=True, exist_ok=True)
    clean_path = media_dir / "01-clean-speech.wav"
    noisy_path = media_dir / "02-noisy-speech.wav"
    write_pcm(clean_path, clean)
    write_pcm(noisy_path, noisy)
    manifest = {
        "dataset": "Microsoft Scalable Noisy Speech Dataset (MS-SNSD)",
        "revision": REVISION,
        "sources": sources,
        "speech_dataset_creator": "Cassia Valentini-Botinhao",
        "speech_source": "https://doi.org/10.7488/ds/2117",
        "original_corpus_creators": [
            "Christophe Veaux", "Junichi Yamagishi", "Kirsten MacDonald"
        ],
        "original_corpus_source": "https://doi.org/10.7488/ds/1994",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "source_license_url": (
            "https://datashare.ed.ac.uk/bitstream/handle/10283/2791/"
            "license_text?sequence=11&isAllowed=y"
        ),
        "changes": (
            "Concatenated three complete MS-SNSD 16 kHz utterances with two "
            "0.5-second gaps; applied a shared gain to both outputs; added "
            "seeded synthetic Gaussian white noise to the second output."
        ),
        "noise": {"kind": "synthetic Gaussian white noise", "seed": SEED},
        "snr_db": snr_db,
        "snr_measurement": "whole-recording RMS, including inserted silence",
        "shared_gain": float(gain),
        "sample_rate_hz": SAMPLE_RATE,
        "duration_seconds": clean.size / SAMPLE_RATE,
        "outputs": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (clean_path, noisy_path)
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Prepared {manifest['duration_seconds']:.2f} seconds per clip at {snr_db:g} dB SNR.")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snr-db", type=float, default=SNR_DB)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or MEDIA_DIR
    manifest_path = (
        DATA_DIR / "audio-provenance.json"
        if args.output_dir is None
        else output_dir / "audio-provenance.json"
    )
    prepare_audio(args.snr_db, output_dir, manifest_path)
