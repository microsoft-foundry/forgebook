"""Turn the tutorial's three synthetic team files into small, traceable chunks."""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEAM_FILES = ("app-profile.yaml", "team-standards.md", "troubleshooting.md")


def load_team_documents() -> list[dict]:
    documents = []
    for name in TEAM_FILES:
        text = (ROOT / "team-docs" / name).read_text(encoding="utf-8")
        sections = re.split(r"(?m)(?=^## )", text) if name.endswith(".md") else [text]
        for section in sections:
            content = section.strip()
            if not content:
                continue
            if len(content) > 2000:
                raise ValueError(f"{name}: split sections longer than 2,000 characters before indexing")
            digest = hashlib.sha256(f"{name}\n{content}".encode()).hexdigest()[:16]
            heading = content.splitlines()[0].lstrip("# ") if content.startswith("## ") else name
            documents.append({
                "id": f"team-{digest}",
                "title": f"{name}: {heading}",
                "content": content,
                "source_path": f"team-docs/{name}",
                "application": "Atlas support app",
                "environment": "staging",
            })
    return documents
