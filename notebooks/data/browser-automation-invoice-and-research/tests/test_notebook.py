import json
from datetime import date
from pathlib import Path
import runpy
import sys
from unittest.mock import Mock

import pytest

from bat_recipe.paths import RECIPE_ROOT
from bat_recipe.runner import Runner


NOTEBOOK = RECIPE_ROOT.parents[1] / "browser-automation-invoice-and-research.ipynb"


@pytest.mark.parametrize("start", [RECIPE_ROOT.parents[2], NOTEBOOK.parent, RECIPE_ROOT])
def test_notebook_run_all_is_offline_from_documented_locations(start, monkeypatch):
    monkeypatch.chdir(start)
    monkeypatch.setenv("LIVE_APPROVED", "1")
    create_runner = Mock(side_effect=AssertionError("Offline notebook created a live client"))
    monkeypatch.setattr(Runner, "__init__", create_runner)
    import subprocess
    import dotenv

    run_process = Mock(side_effect=AssertionError("Offline notebook launched a subprocess"))
    load_config = Mock(side_effect=AssertionError("Offline notebook loaded live configuration"))
    monkeypatch.setattr(subprocess, "run", run_process)
    monkeypatch.setattr(dotenv, "load_dotenv", load_config)
    namespace = {"__name__": "__main__"}
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] == "code":
            exec(compile("".join(cell["source"]), f"notebook-cell-{index}", "exec"), namespace)
    assert namespace["recipe_root"] == RECIPE_ROOT
    assert Path.cwd() == start
    assert namespace["RUN_LIVE"] is False
    create_runner.assert_not_called()
    run_process.assert_not_called()
    load_config.assert_not_called()


def test_live_cli_rejects_missing_approval_before_creating_runner(monkeypatch):
    monkeypatch.delenv("LIVE_APPROVED", raising=False)
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args: None)
    monkeypatch.setattr(sys, "argv", ["diagnose_bat", "probe"])
    create_runner = Mock(side_effect=AssertionError("Unapproved CLI created an agent client"))
    monkeypatch.setattr(Runner, "__init__", create_runner)
    with pytest.raises(RuntimeError, match="before creating an agent"):
        runpy.run_path(str(RECIPE_ROOT / "scripts" / "diagnose_bat.py"), run_name="__main__")
    create_runner.assert_not_called()


@pytest.mark.parametrize("invalid", ["research_window", "artifact_directory"])
def test_opted_in_notebook_checks_configuration_before_probe(monkeypatch, tmp_path, invalid):
    import subprocess
    import dotenv

    monkeypatch.setenv("LIVE_APPROVED", "1")
    monkeypatch.setenv("RESEARCH_WINDOW_START",
                       "not-a-date" if invalid == "research_window" else date.today().isoformat())
    monkeypatch.setenv("ARTIFACT_DIR",
                       str(RECIPE_ROOT if invalid == "artifact_directory" else tmp_path))
    monkeypatch.setattr(dotenv, "load_dotenv", Mock())
    run_process = Mock()
    monkeypatch.setattr(subprocess, "run", run_process)
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cell = next(cell for cell in notebook["cells"] if cell["id"] == "opt-in-cloud")
    source = "".join(cell["source"]).replace("RUN_LIVE = False", "RUN_LIVE = True", 1)
    with pytest.raises(ValueError, match="RESEARCH_WINDOW_START|ARTIFACT_DIR"):
        exec(compile(source, "opt-in-cloud", "exec"), {"recipe_root": RECIPE_ROOT, "sys": sys})
    run_process.assert_not_called()
