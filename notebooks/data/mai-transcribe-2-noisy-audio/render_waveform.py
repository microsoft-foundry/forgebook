"""Generate original waveform art from the bundled licensed audio, with a matching crop."""

from pathlib import Path
import wave

import numpy as np


MEDIA = Path(__file__).resolve().parents[2] / "media" / "mai-transcribe-2-noisy-audio"


def samples(filename: str) -> np.ndarray:
    with wave.open(str(MEDIA / filename), "rb") as audio:
        return np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2") / 32768


def envelope(data: np.ndarray, x: int, y: int, width: int, height: int, color: str) -> str:
    bins = np.array_split(data, width)
    segments = []
    for index, chunk in enumerate(bins):
        low, high = chunk.min(), chunk.max()
        segments.append(f"M{x + index},{y - high * height / 2:.2f}V{y - low * height / 2:.2f}")
    return f'<path d="{" ".join(segments)}" stroke="{color}" stroke-width="1" fill="none"/>'


def main() -> None:
    clean = samples("01-clean-speech.wav")
    noisy = samples("02-noisy-speech.wav")
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="480" viewBox="0 0 1000 480" role="img" aria-labelledby="title description">',
        '<title id="title">Clean and noisy audio with matching one-second detail</title>',
        '<desc id="description">Waveform amplitude overview and a crop from 8 to 9 seconds. Both clips share the same scale; the noisy clip adds synthetic white noise at 10 dB whole-recording SNR. This is input evidence, not an accuracy result.</desc>',
        '<rect width="1000" height="480" rx="18" fill="#f3f6fa"/>',
        '<g font-family="Arial, sans-serif" fill="#172b4d">',
        '<text x="25" y="35" font-size="23" font-weight="700">Same speech. One controlled input change.</text>',
        '<text x="25" y="64" font-size="15">16.107 seconds | 16 kHz mono PCM | Shared amplitude scale</text>',
        '<text x="25" y="105" font-size="16">Clean</text>',
        '<text x="25" y="205" font-size="16">+ noise</text>',
        '<text x="25" y="302" font-size="17" font-weight="700">Matching crop: 8.0-9.0 seconds</text>',
        '<text x="25" y="343" font-size="15">Clean</text>',
        '<text x="515" y="343" font-size="15">+ synthetic noise (10 dB SNR)</text>',
    ]
    parts += [
        envelope(clean, 120, 115, 850, 90, "#0067b8"),
        envelope(noisy, 120, 215, 850, 90, "#a33b00"),
        envelope(clean[8 * 16000:9 * 16000], 25, 389, 450, 70, "#0067b8"),
        envelope(noisy[8 * 16000:9 * 16000], 515, 389, 450, 70, "#a33b00"),
        '<text x="25" y="451" font-size="13">Speech: Valentini-Botinhao (2017), CSTR/VCTK via MS-SNSD, CC BY 4.0. See notebook for full attribution.</text>',
        '</g></svg>',
    ]
    (MEDIA / "04-audio-waveform-detail.svg").write_text("\n".join(parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
