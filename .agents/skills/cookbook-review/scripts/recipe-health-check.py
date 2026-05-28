#!/usr/bin/env python3
"""Static health checks for Forgebook cookbook notebooks.

This script is intentionally conservative. It reports objective signals that help
reviewers focus; it does not replace the human/agent rubric review.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LOCAL_ASSET_PATTERN = re.compile(r"""(?:\(|["'])(?P<path>(?:media|data)/[^)"']+)""")
SITE_METADATA_KEYS = {
    "forgebook",
    "registry",
    "slug",
    "authors",
    "tags",
    "description",
    "site",
    "publish",
    "published",
}


def load_notebook(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def source_text(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    return str(source)


def infer_slug(notebook: Path) -> str:
    return notebook.stem.lower().replace("_", "-")


def result(name: str, passed: bool, evidence: str, severity: str = "info") -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "severity": severity,
        "evidence": evidence,
    }


def check_notebook(path: Path, slug: str | None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    if not path.exists():
        return {
            "notebook": str(path),
            "slug": slug,
            "checks": [result("notebook_exists", False, f"{path} does not exist", "critical")],
            "warnings": [],
        }

    checks.append(result("notebook_extension", path.suffix == ".ipynb", "Notebook path should end with .ipynb", "critical"))

    notebook_slug = slug or infer_slug(path)
    checks.append(
        result(
            "slug_format",
            bool(SLUG_PATTERN.match(notebook_slug)),
            f"Slug candidate: {notebook_slug}",
            "critical",
        )
    )

    notebook = load_notebook(path)
    cells = notebook.get("cells", [])
    checks.append(result("has_cells", bool(cells), f"Notebook has {len(cells)} cells", "critical"))

    first_markdown = next((cell for cell in cells if cell.get("cell_type") == "markdown"), None)
    if first_markdown is None:
        checks.append(result("has_markdown_intro", False, "No markdown intro cell found", "required"))
    else:
        first_text = source_text(first_markdown).lstrip()
        checks.append(
            result(
                "no_leading_h1",
                not first_text.startswith("# "),
                "First markdown cell should not start with # H1; title comes from registry.yaml",
                "required",
            )
        )

    metadata = notebook.get("metadata", {})
    suspicious_metadata = sorted(SITE_METADATA_KEYS.intersection(metadata.keys()))
    checks.append(
        result(
            "no_site_metadata",
            not suspicious_metadata,
            "Suspicious notebook metadata keys: " + ", ".join(suspicious_metadata) if suspicious_metadata else "No site-specific metadata keys found",
            "critical",
        )
    )

    code_cells = [cell for cell in cells if cell.get("cell_type") == "code"]
    empty_code_cells = [index for index, cell in enumerate(cells, start=1) if cell.get("cell_type") == "code" and not source_text(cell).strip()]
    outputless_cells = [
        index
        for index, cell in enumerate(cells, start=1)
        if cell.get("cell_type") == "code"
        and source_text(cell).strip()
        and not cell.get("outputs")
        and not source_text(cell).strip().startswith(("#", "%pip", "pip "))
    ]
    checks.append(result("has_code", bool(code_cells), f"Notebook has {len(code_cells)} code cells", "required"))
    checks.append(result("no_empty_code_cells", not empty_code_cells, f"Empty code cells: {empty_code_cells}", "required"))

    if outputless_cells:
        warnings.append(f"Code cells without outputs or obvious setup-only marker: {outputless_cells}")

    all_text = "\n".join(source_text(cell) for cell in cells)
    asset_paths = [match.group("path") for match in LOCAL_ASSET_PATTERN.finditer(all_text)]
    wrong_slug_assets = [
        asset_path for asset_path in asset_paths if not asset_path.startswith(f"media/{notebook_slug}/") and not asset_path.startswith(f"data/{notebook_slug}/")
    ]
    checks.append(
        result(
            "asset_paths_use_slug",
            not wrong_slug_assets,
            "All local media/data paths use the slug directory" if not wrong_slug_assets else "Paths not under media/data slug directory: " + ", ".join(wrong_slug_assets),
            "required",
        )
    )

    ai_phrases = [
        "delve into",
        "leverage",
        "robust",
        "seamlessly",
        "unlock the power",
        "it is important to note",
        "in conclusion",
    ]
    found_phrases = sorted({phrase for phrase in ai_phrases if phrase in all_text.lower()})
    if found_phrases:
        warnings.append("Potential AI/prose filler phrases: " + ", ".join(found_phrases))

    return {
        "notebook": str(path),
        "slug": notebook_slug,
        "checks": checks,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run static Forgebook notebook health checks.")
    parser.add_argument("notebook", help="Path to the notebook to inspect")
    parser.add_argument("--slug", help="Expected registry slug")
    parser.add_argument("--repo-root", default=".", help="Repository root. Reserved for future registry cross-checks.")
    args = parser.parse_args()

    notebook_path = Path(args.notebook)
    if not notebook_path.is_absolute():
        notebook_path = Path(args.repo_root) / notebook_path

    report = check_notebook(notebook_path, args.slug)
    print(json.dumps(report, indent=2))

    failed_critical = any(not check["passed"] and check["severity"] == "critical" for check in report["checks"])
    return 1 if failed_critical else 0


if __name__ == "__main__":
    sys.exit(main())
