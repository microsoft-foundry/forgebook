"""Offline tests: python -m unittest discover -s notebooks\\data\\mai-transcribe-2-noisy-audio."""

import ast
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
import wave
from time import perf_counter
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

import nbformat
import numpy as np
import requests

from prepare_audio import prepare_audio, read_pcm


NOTEBOOK_DIR = Path(__file__).resolve().parents[2]
SLUG = "mai-transcribe-2-noisy-audio"
NOTEBOOK = nbformat.read(NOTEBOOK_DIR / f"{SLUG}.ipynb", as_version=4)
CELLS = {cell.id: cell.source for cell in NOTEBOOK.cells}
MEDIA_DIR = NOTEBOOK_DIR / "media" / SLUG
DATA_DIR = NOTEBOOK_DIR / "data" / SLUG


def load_namespace() -> dict:
    namespace = {
        "Path": Path, "re": re, "urlsplit": urlsplit, "json": json,
        "requests": requests, "credential": Mock(),
        "ENDPOINT": "https://example.cognitiveservices.azure.com",
        "API_VERSION": "2025-10-15",
        "DEFINITION": {"enhancedMode": {"enabled": True, "model": "MAI-Transcribe-2"}},
    }
    config = ast.parse(CELLS["configuration"])
    endpoint_function = next(node for node in config.body if isinstance(node, ast.FunctionDef))
    exec(compile(ast.Module(body=[endpoint_function], type_ignores=[]), "<endpoint>", "exec"), namespace)
    exec(CELLS["transcribe"], namespace)
    return namespace


class FixtureTests(unittest.TestCase):
    def test_notebook_schema_and_python_syntax(self):
        nbformat.validate(NOTEBOOK)
        for cell in NOTEBOOK.cells:
            if cell.cell_type == "code" and cell.id != "install":
                compile(cell.source, f"<{cell.id}>", "exec")
            if cell.cell_type == "code":
                self.assertIsNone(cell.execution_count)
                if cell.id == "compare":
                    self.assertEqual(len(cell.outputs), 1)
                    self.assertEqual(cell.outputs[0].output_type, "stream")
                    self.assertIn("Exact transcript match: True", cell.outputs[0].text)
                else:
                    self.assertEqual(cell.outputs, [])

    def test_hashes_duration_and_snr(self):
        manifest = json.loads((DATA_DIR / "audio-provenance.json").read_text())
        clips = []
        for filename, expected in manifest["outputs"].items():
            content = (MEDIA_DIR / filename).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), expected)
            samples = read_pcm(content)
            self.assertLess(float(np.max(np.abs(samples))), 0.901)
            clips.append(samples)
        clean, noisy = clips
        self.assertEqual(clean.shape, noisy.shape)
        self.assertGreater(clean.size / 16000, 10)
        self.assertLess(clean.size / 16000, 30)
        self.assertAlmostEqual(clean.size / 16000, manifest["duration_seconds"])
        snr = 10 * np.log10(np.mean(clean ** 2) / np.mean((noisy - clean) ** 2))
        self.assertAlmostEqual(float(snr), 10, delta=0.01)

    def test_paths_resolve_from_root_and_notebooks(self):
        for cwd in (NOTEBOOK_DIR.parent, NOTEBOOK_DIR):
            with self.subTest(cwd=cwd), patch.object(Path, "cwd", return_value=cwd):
                namespace = {}
                exec(CELLS["assets"], namespace)
                self.assertEqual(namespace["CLEAN_AUDIO"], MEDIA_DIR / "01-clean-speech.wav")

    def test_native_audio_markup(self):
        self.assertEqual(CELLS["listen"].count("<audio controls"), 2)
        for filename in ("01-clean-speech.wav", "02-noisy-speech.wav"):
            self.assertIn(f'media/{SLUG}/{filename}', CELLS["listen"])
        self.assertIn("CC BY 4.0", CELLS["listen"])

    def test_snr_experiment_writes_to_separate_directory(self):
        original_hashes = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in MEDIA_DIR.glob("*.wav")
        }
        source_samples = np.arange(16000, dtype="<i2")
        source_buffer = io.BytesIO()
        with wave.open(source_buffer, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(source_samples.tobytes())
        response = Mock(content=source_buffer.getvalue())
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "prepare_audio.requests.get", return_value=response
        ):
            experiment_dir = Path(temp_dir) / "snr-5"
            manifest = prepare_audio(
                5,
                experiment_dir,
                experiment_dir / "audio-provenance.json",
            )
            self.assertEqual(manifest["snr_db"], 5)
            self.assertTrue((experiment_dir / "audio-provenance.json").is_file())
            self.assertEqual(
                {
                    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in MEDIA_DIR.glob("*.wav")
                },
                original_hashes,
            )


class TranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.namespace = load_namespace()
        self.transcribe = self.namespace["transcribe"]
        self.audio = MEDIA_DIR / "01-clean-speech.wav"

    def response(self, payload):
        response = Mock(status_code=200)
        response.json.return_value = payload
        return response

    def test_endpoint_guard(self):
        validate = self.namespace["validate_endpoint"]
        self.assertEqual(validate("https://example.cognitiveservices.azure.com/"), self.namespace["ENDPOINT"])
        for endpoint in (
            "", "http://example.cognitiveservices.azure.com",
            "https://example.cognitiveservices.azure.com.attacker.test",
            "https://user:password@example.cognitiveservices.azure.com",
            "https://example.cognitiveservices.azure.com:443",
            "https://example.cognitiveservices.azure.com/api/projects/foo",
            "https://example.cognitiveservices.azure.com?query=1",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                validate(endpoint)

    def test_multipart_contract_and_token_refresh(self):
        payload = {"combinedPhrases": [{"text": "Test speech."}]}
        with patch.object(requests, "post", return_value=self.response(payload)) as post:
            for _ in range(2):
                self.assertEqual(self.transcribe(self.audio), ("Test speech.", payload))
            self.assertEqual(post.call_count, 2)
            kwargs = post.call_args.kwargs
            self.assertEqual(json.loads(kwargs["data"]["definition"]), self.namespace["DEFINITION"])
            self.assertEqual(kwargs["params"], {"api-version": "2025-10-15"})
            self.assertEqual(kwargs["files"]["audio"][2], "audio/wav")
            self.assertTrue(kwargs["files"]["audio"][1].closed)
            self.assertEqual(kwargs["timeout"], (10, 180))
            self.assertFalse(kwargs["allow_redirects"])
            self.assertEqual(self.namespace["credential"].get_token.call_count, 2)
            self.namespace["credential"].get_token.assert_called_with(
                "https://cognitiveservices.azure.com/.default"
            )

    def test_malformed_and_empty_results_fail_explicitly(self):
        for payload in ({}, [], {"combinedPhrases": []}, {"combinedPhrases": [{"text": 12}]}):
            with self.subTest(payload=payload):
                with patch.object(requests, "post", return_value=self.response(payload)):
                    with self.assertRaises(ValueError):
                        self.transcribe(self.audio)

    def test_errors_do_not_retry_or_change_model(self):
        response = self.response({})
        response.raise_for_status.side_effect = requests.HTTPError("HTTP 400")
        for failure in (response, requests.Timeout("timeout")):
            kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
            with patch.object(requests, "post", **kwargs) as post:
                with self.assertRaises(requests.RequestException):
                    self.transcribe(self.audio)
                self.assertEqual(post.call_count, 1)
                self.assertEqual(json.loads(post.call_args.kwargs["data"]["definition"]),
                                 self.namespace["DEFINITION"])

    def test_measurement_shape_and_exact_price(self):
        namespace = self.namespace
        namespace.update({"wave": wave, "perf_counter": perf_counter})
        namespace["transcribe"] = Mock(return_value=("Test", {}))
        exec(CELLS["measurement"], namespace)
        with patch.dict(namespace, {"perf_counter": Mock(side_effect=[10.0, 12.0])}):
            text, result, metrics = namespace["transcribe_measured"](self.audio)
        self.assertEqual((text, result), ("Test", {}))
        self.assertEqual(metrics["size_bytes"], self.audio.stat().st_size)
        self.assertEqual(metrics["client_elapsed_seconds"], 2.0)
        self.assertAlmostEqual(metrics["speed_factor"], metrics["audio_seconds"] / 2.0)
        self.assertAlmostEqual(metrics["real_time_factor"], 2.0 / metrics["audio_seconds"])
        self.assertAlmostEqual(metrics["estimated_cost_usd"], metrics["audio_seconds"] / 3600 * 0.10)
        table = namespace["metrics_table"](metrics, metrics)
        self.assertIn("Client time (s)", table)
        self.assertEqual(table.count(self.audio.name), 2)

    def test_redirect_is_not_followed(self):
        with patch.object(requests, "post", return_value=Mock(status_code=302)) as post:
            with self.assertRaisesRegex(RuntimeError, "redirect"):
                self.transcribe(self.audio)
            self.assertEqual(post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
