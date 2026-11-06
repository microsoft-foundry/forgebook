import argparse
import json
from pathlib import Path
import secrets


def render(directory: Path) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    metadata = directory / "hosted-marker.json"
    if metadata.exists():
        raise FileExistsError("Refusing to replace this run's hosted marker")
    marker = secrets.token_hex(16)
    source = Path(__file__).resolve().parents[1] / "demo-form" / "invoice-entry.html"
    html = source.read_text(encoding="utf-8")
    if html.count("__DEMO_MARKER__") != 1:
        raise ValueError("Expected exactly one marker placeholder")
    (directory / "invoice-entry.html").write_text(
        html.replace("__DEMO_MARKER__", marker), encoding="utf-8"
    )
    metadata.write_text(json.dumps({"marker": marker}), encoding="utf-8")
    return marker


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=Path)
    args = parser.parse_args()
    render(args.artifact_dir.resolve())
    print("Rendered the synthetic form and saved its expected marker locally.")
