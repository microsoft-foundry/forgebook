from pathlib import Path


RECIPE_ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_ROOT = RECIPE_ROOT.parents[2]
ASSETS = RECIPE_ROOT / "assets"


def artifact_directory(value: str) -> Path:
    if not value.strip():
        raise ValueError("ARTIFACT_DIR must name a directory outside the Forgebook checkout")
    path = Path(value).expanduser().resolve()
    if path.is_relative_to(CHECKOUT_ROOT):
        raise ValueError("ARTIFACT_DIR must be outside the Forgebook checkout")
    return path
