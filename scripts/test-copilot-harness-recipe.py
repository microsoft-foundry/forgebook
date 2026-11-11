"""Offline wiring tests; fake SDK answers are not live service evidence.

Run from the repo root: python scripts/test-copilot-harness-recipe.py
Requires IPython (included with the notebook's Jupyter environment).
"""

import ast
import copy
import csv
import hashlib
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
from collections import Counter

from IPython.core.inputtransformer2 import TransformerManager


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "copilot-harness-foundry-fabric-iq.ipynb"
DATA_DIR = ROOT / "notebooks" / "data" / "copilot-harness-foundry-fabric-iq"
DOCUMENT = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
CELLS = {
    cell["id"]: "".join(cell["source"])
    for cell in DOCUMENT["cells"] if cell["cell_type"] == "code"
}
FIXTURE = json.loads((DATA_DIR / "offline-fixture.json").read_text(encoding="utf-8"))
REPORTS = [
    json.loads(line) for line in (DATA_DIR / "reports.jsonl").read_text(encoding="utf-8").splitlines()
]
CONFIG = {
    "IQ_RUN_NAME": "customer-iq-offline-test",
    "FOUNDRY_PROJECT_ID": (
        "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/demo-rg"
        "/providers/Microsoft.CognitiveServices/accounts/demo-foundry/projects/demo-project"
    ),
    "FOUNDRY_PROJECT_ENDPOINT": "https://demo-foundry.services.ai.azure.com/api/projects/demo-project",
    "FOUNDRY_MODEL_DEPLOYMENT": "demo-model",
    "FOUNDRY_IQ_KB_MCP_URL": (
        "https://demo-search.search.windows.net/knowledgebases/demo-kb/mcp?api-version=2026-08-01-preview"
    ),
    "FABRIC_WORKSPACE_ID": "00000000-0000-0000-0000-000000000002",
    "FABRIC_ONTOLOGY_ID": "00000000-0000-0000-0000-000000000003",
}
TOOL_NAMES = ("skill", "fabriciq-ontology___ask_ontology", "field-sales-reports___knowledge_base_retrieve")


class FakeItem:
    def __init__(self, **values):
        self.values = values
        self.type = values["type"]

    def model_dump(self):
        return self.values


class FakeServices:
    """Only implement the SDK and CLI operations used by this recipe."""

    def __init__(self):
        self.commands = []
        self.fail_command = None
        self.deployed = {
            "versions": {"latest": {
                "version": "1", "status": "active",
                "definition": {
                    "kind": "prompt", "harness": {"type": "microsoft_copilot_preview"},
                    "tools": [{
                        "type": "microsoft_copilot_toolset_preview",
                        "default_config": {"enabled": False},
                        "configs": [{"name": "filesystem_read", "enabled": True}],
                    }],
                    "skills": [{"name": f'{CONFIG["IQ_RUN_NAME"]}-investigate', "version": "1"}],
                },
            }},
        }
        self.questions = {}
        self.report_url = "https://example.test/CUST-001-field-sales-report.pdf"
        self.answers = {"meeting": FIXTURE["known"]["answer"] + f" [Report]({self.report_url})"}
        self.retrieval_output = json.dumps([{"text": json.dumps({
            "kind": "reference",
            "sourceData": {
                "snippet": " ".join(REPORTS[0][field] for field in (
                    "customer_id", "report_reference", "report_date", "documented_action",
                )),
                "doc_url": self.report_url,
            },
        })}])
        self.status = "completed"
        self.response_error = None
        self.tool_error = None
        self.fail_response = False
        self.trace_id = None
        self.resolution_name = None
        self.omit_resolution = False
        self.omit_record_lookup = False
        self.retrieval_count = 1
        self.missing_output_name = None
        self.empty_output_name = None
        self.incomplete_tool_name = None
        self.data_as_functions = False
        self.tool_names = TOOL_NAMES
        self.shell = False
        self.denied_read = False
        self.embedded_error = None
        self.progress = ""
        self.conversation_number = 0
        self.openai = SimpleNamespace(
            conversations=SimpleNamespace(
                create=Mock(side_effect=self.create_conversation),
                items=SimpleNamespace(list=Mock(side_effect=self.list_items)),
            ),
            responses=SimpleNamespace(create=Mock(side_effect=self.create_response)),
        )
        self.project = SimpleNamespace(get_openai_client=Mock(return_value=self.openai))
        self.project_factory = Mock(return_value=self.project)
        self.credential_factory = Mock()

    def system(self, command):
        """Expand notebook variables and fake the transformed !azd command."""
        args = shlex.split(command.format_map(self.namespace))
        assert args[:2] == ["azd", "--cwd"], args
        directory = Path(args[2])
        args = [args[0], *args[3:]]
        if self.fail_command and args[1:1 + len(self.fail_command)] == self.fail_command:
            self.commands.append(args)
            self.namespace["_exit_code"] = 17
            return
        if ">" in args:
            redirect = args.index(">")
            assert args[1:4] == ["ai", "agent", "show"], args
            assert len(args) == redirect + 2, args
            Path(args[-1]).write_text(self.show(args[:redirect], cwd=directory), encoding="utf-8")
        else:
            self.run(args, cwd=directory, check=True)
        self.namespace["_exit_code"] = 0

    def run(self, args, **kwargs):
        self.commands.append(args)
        if args[1:4] == ["ai", "agent", "init"]:
            directory = Path(kwargs["cwd"]) / args[4]
            directory.mkdir()
            (directory / "azure.yaml").write_text("name: fake-init\n", encoding="utf-8")
        else:
            assert args[1:4] == ["ai", "connection", "create"] or args[1] == "deploy", args
        assert kwargs["check"] is True
        assert os.environ["AZD_ALPHA_ENABLE_AGENTS_MANAGED_HARNESS"] == "true"
        return subprocess.CompletedProcess(args, 0)

    def show(self, args, **kwargs):
        self.commands.append(args)
        assert args[1:5] == ["ai", "agent", "show", CONFIG["IQ_RUN_NAME"]], args
        return json.dumps(self.deployed)

    def create_conversation(self):
        self.conversation_number += 1
        return SimpleNamespace(id=f"synthetic-conversation-{self.conversation_number}")

    def create_response(self, *, conversation, input):
        if self.fail_response:
            raise RuntimeError("Synthetic service failure")
        assert "Adatum Corporation" in input, f"Unexpected question: {input}"
        self.questions[conversation] = input
        message = SimpleNamespace(
            type="message", role="assistant",
            content=[SimpleNamespace(type="output_text", text=self.answers["meeting"])],
        )
        return SimpleNamespace(
            status=self.status, error=self.response_error,
            output_text=self.progress + self.answers["meeting"], output=[message],
        )

    def list_items(self, *, conversation_id, order):
        assert order == "asc"
        assert conversation_id in self.questions
        identifier = self.trace_id if self.trace_id is not None else FIXTURE["known_id"]
        calls = []
        for name in self.tool_names:
            if name == "fabriciq-ontology___ask_ontology" and not self.omit_resolution:
                customer_name = self.resolution_name or FIXTURE["known"]["ontology"]["customer_name"]
                calls.append((name, customer_name))
            if name == "fabriciq-ontology___ask_ontology" and self.omit_record_lookup:
                continue
            for _ in range(self.retrieval_count if name == TOOL_NAMES[2] else 1):
                calls.append((name, identifier))
        items = []
        for index, (name, query) in enumerate(calls):
            kind = "mcp_call" if name in TOOL_NAMES[1:] and not self.data_as_functions else "function_call"
            call_id = f"synthetic-call-{index}"
            values = {
                "type": kind, "name": name, "arguments": json.dumps({"query": query}),
                "call_id": call_id, "status": "in_progress" if name == self.incomplete_tool_name else "completed",
                "error": self.tool_error if name == TOOL_NAMES[1] else None,
            }
            output = " " if name == self.empty_output_name else "Synthetic tool result, not live evidence."
            if name == TOOL_NAMES[2] and name != self.empty_output_name:
                output = self.retrieval_output
            if name == TOOL_NAMES[1] and self.embedded_error is not None:
                output = json.dumps(self.embedded_error)
            if kind == "mcp_call" and name != self.missing_output_name:
                values["output"] = output
            items.append(FakeItem(**values))
            if kind == "function_call" and name != self.missing_output_name:
                items.append(FakeItem(
                    type="function_call_output", call_id=call_id, status="completed", output=output,
                ))
        if self.shell:
            items.append(FakeItem(type="shell_call"))
        if self.denied_read:
            items.extend([
                FakeItem(
                    type="function_call", name="view", arguments='{"path": "/synthetic/staged-output.txt"}',
                    call_id="synthetic-denied-read", status="completed",
                ),
                FakeItem(
                    type="function_call_output", call_id="synthetic-denied-read", status="completed",
                    output=json.dumps({"error": {
                        "code": "denied",
                        "message": "file access is limited to the session workspace and configured read-only skills",
                    }}),
                ),
            ])
        # A generator exercises iteration, rather than assuming a single page's .data.
        return iter(items)


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="iq offline ")
        self.addCleanup(self.temp.cleanup)
        self.services = FakeServices()
        self.namespace = {}

    def execute(self, stop=None, directory=None):
        self.services.namespace = self.namespace
        self.namespace["get_ipython"] = lambda: self.services
        modules = {name: ModuleType(name) for name in ("azure", "azure.ai", "azure.ai.projects", "azure.identity")}
        modules["azure.ai.projects"].AIProjectClient = self.services.project_factory
        modules["azure.identity"].AzureCliCredential = self.services.credential_factory
        with ExitStack() as stack:
            previous_directory = Path.cwd()
            stack.callback(os.chdir, previous_directory)
            os.chdir(directory or ROOT / "notebooks")
            stack.enter_context(patch.dict(os.environ, CONFIG, clear=True))
            stack.enter_context(patch.dict(sys.modules, modules))
            stack.enter_context(patch("tempfile.gettempdir", return_value=self.temp.name))
            stack.enter_context(patch("shutil.which", return_value="azd"))
            stack.enter_context(patch("subprocess.run", side_effect=AssertionError("External process forbidden")))
            stack.enter_context(patch("subprocess.check_output", side_effect=AssertionError("External process forbidden")))
            stack.enter_context(patch("socket.create_connection", side_effect=AssertionError("Network forbidden")))
            stack.enter_context(redirect_stdout(io.StringIO()))
            for identifier, source in CELLS.items():
                python_source = TransformerManager().transform_cell(source)
                exec(compile(python_source, f"{NOTEBOOK.name}:{identifier}", "exec"), self.namespace)
                if identifier == stop:
                    break

    def test_runs_every_cell_without_custom_runtime(self):
        self.execute()
        self.services.openai.responses.create.assert_called_once()
        self.assertEqual(self.namespace["response"].output_text, self.services.answers["meeting"])
        self.assertFalse((DATA_DIR / "recipe_support.py").exists())
        for source in CELLS.values():
            tree = ast.parse(TransformerManager().transform_cell(source))
            self.assertFalse(any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree)))

    def test_supports_both_documented_launch_directories(self):
        for directory in (ROOT, ROOT / "notebooks"):
            with self.subTest(directory=directory):
                self.services = FakeServices()
                self.namespace = {}
                self.execute(directory=directory)
                self.assertEqual(self.namespace["REPO_ROOT"], ROOT)
                self.assertEqual(self.namespace["FIXTURE_DIR"], DATA_DIR)
                self.assertEqual(self.namespace["report"], REPORTS[0])

    def test_rejects_missing_fixtures_before_cloud_operations(self):
        original = Path.is_file
        for name in ("customers.csv", "knowledge-bases.csv", "telemetry-samples.csv", "reports.jsonl"):
            with self.subTest(name=name):
                missing = DATA_DIR / name
                with patch.object(Path, "is_file", lambda path: path != missing and original(path)):
                    with self.assertRaisesRegex(AssertionError, "Missing fixture"):
                        self.execute()
                self.assertEqual(self.services.commands, [])
                self.services.project_factory.assert_not_called()
                self.services.openai.responses.create.assert_not_called()

    def test_rejects_wrong_launch_directory_before_cloud_operations(self):
        with self.assertRaisesRegex(AssertionError, "Launch Jupyter"):
            self.execute(directory=self.temp.name)
        self.assertEqual(self.services.commands, [])
        self.services.project_factory.assert_not_called()

    def test_rejects_missing_account_fixture_before_cloud_operations(self):
        original = Path.read_text
        def read_text(path, *args, **kwargs):
            if path == DATA_DIR / "reports.jsonl":
                return json.dumps({"customer_id": "CUST-002"})
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", read_text):
            with self.assertRaisesRegex(AssertionError, "Missing CUST-001 writeup fixture"):
                self.execute()
        self.assertEqual(self.services.commands, [])
        self.services.openai.responses.create.assert_not_called()

    def test_uses_direct_azd_commands_without_python_subprocess_wrappers(self):
        previous_directory = Path.cwd()
        self.execute()
        for identifier in ("init-project", "connect-search", "connect-fabric", "deploy"):
            self.assertIn("!azd --cwd", CELLS[identifier])
            self.assertIn("_exit_code == 0", CELLS[identifier])
        self.assertNotIn("subprocess", "\n".join(CELLS.values()))
        for identifier in ("sdk-client", "ask-question", "inspect-trace"):
            self.assertNotIn("!azd", CELLS[identifier])
        self.assertEqual(self.namespace["deployed"], self.services.deployed)
        self.assertEqual(Path.cwd(), previous_directory)

    def test_cli_failures_stop_before_data_plane_calls(self):
        agent = CONFIG["IQ_RUN_NAME"]
        for prefix in (
            ["ai", "agent", "init"],
            ["ai", "connection", "create", f"{agent}-kb"],
            ["ai", "connection", "create", f"{agent}-ontology"],
            ["deploy"],
            ["ai", "agent", "show"],
        ):
            with self.subTest(command=prefix):
                self.services.fail_command = prefix
                with self.assertRaisesRegex(AssertionError, "azd .*failed"):
                    self.execute()
                self.services.project_factory.assert_not_called()

    def test_uses_official_agent_scoped_sdk_for_one_question_and_conversation(self):
        self.execute()
        self.services.project_factory.assert_called_once_with(
            endpoint=CONFIG["FOUNDRY_PROJECT_ENDPOINT"],
            credential=self.services.credential_factory.return_value, allow_preview=True,
        )
        self.services.project.get_openai_client.assert_called_once_with(agent_name=CONFIG["IQ_RUN_NAME"])
        self.services.openai.conversations.create.assert_called_once_with()
        self.services.openai.responses.create.assert_called_once_with(
            conversation=self.namespace["conversation"].id, input=self.namespace["question"],
        )
        self.assertIn("account brief", self.namespace["question"])
        self.assertIn("what's recorded for the account", self.namespace["question"])
        self.assertNotIn("CUST-", self.namespace["question"])

    def test_deploys_existing_project_and_keeps_distinct_tool_identities(self):
        self.execute()
        commands = self.services.commands
        self.assertTrue(any(command[1:] == ["deploy", "--all", "--no-prompt"] for command in commands))
        self.assertFalse(any("up" in command or "down" in command for command in commands))
        connections = [command for command in commands if command[1:4] == ["ai", "connection", "create"]]
        self.assertEqual(len(connections), 2)
        search, fabric = connections
        self.assertIn("project-managed-identity", search)
        self.assertIn("https://search.azure.com/", search)
        self.assertIn("user-entra-token", fabric)
        self.assertIn("https://analysis.windows.net/powerbi/api", fabric)
        self.assertNotIn("--scopes", fabric)
        self.assertIn(CONFIG["FOUNDRY_PROJECT_ID"], commands[0])

    def test_writes_copyable_skill_and_manifest(self):
        self.execute()
        namespace = self.namespace
        self.assertEqual((namespace["skill_dir"] / "SKILL.md").read_text(encoding="utf-8"), namespace["skill_text"])
        manifest = (namespace["PROJECT_DIR"] / "azure.yaml").read_text(encoding="utf-8")
        for text in (
            "type: microsoft_copilot_preview", "type: fabric_iq_preview",
            "server_label: field-sales-reports", "knowledge_base_retrieve",
            "enabled: false", f'- {namespace["SKILL"]}',
            "- name: filesystem_read", "enabled: true",
            json.dumps(CONFIG["FOUNDRY_IQ_KB_MCP_URL"]),
        ):
            self.assertIn(text, manifest)
        self.assertIn("Linked KnowledgeBase records do not change the retrieval target.", namespace["skill_text"])

    def test_rejects_wrong_harness(self):
        self.services.deployed["versions"]["latest"]["definition"]["harness"]["type"] = "default"
        with self.assertRaises(AssertionError):
            self.execute()

    def test_only_enables_read_only_workspace_tools(self):
        toolset = self.services.deployed["versions"]["latest"]["definition"]["tools"][0]
        for field, value in (
            ("default_config", {"enabled": True}),
            ("configs", []),
            ("configs", [{"name": "shell", "enabled": True}]),
        ):
            with self.subTest(field=field, value=value):
                original = copy.deepcopy(toolset)
                toolset[field] = value
                with self.assertRaises(AssertionError):
                    self.execute()
                toolset.clear()
                toolset.update(original)

    def test_allows_read_only_staged_output_inspection(self):
        self.services.tool_names = (*TOOL_NAMES, "view", "grep", "glob")
        self.execute()

    def test_rejects_unpinned_skill(self):
        original = copy.deepcopy(self.services.deployed)
        for value in (None, "", " ", "latest", "default", 1, True):
            with self.subTest(version=value):
                self.services.deployed = copy.deepcopy(original)
                self.services.deployed["versions"]["latest"]["definition"]["skills"][0]["version"] = value
                with self.assertRaises(AssertionError):
                    self.execute()

    def test_stops_on_incomplete_response(self):
        self.services.status = "incomplete"
        with self.assertRaisesRegex(AssertionError, "failed response"):
            self.execute()
        self.services.openai.conversations.items.list.assert_called_once_with(
            conversation_id=self.namespace["conversation"].id, order="asc",
        )
        self.assertTrue(self.namespace["items"])

    def test_stops_on_response_error(self):
        self.services.response_error = {"code": "synthetic_error"}
        with self.assertRaisesRegex(AssertionError, "failed response"):
            self.execute()

    def test_surfaces_actual_tool_error_before_reporting_missing_tools(self):
        self.services.tool_error = {"code": "failure", "message": "mcp_upstream_timeout"}
        self.services.tool_names = TOOL_NAMES[:2]
        with self.assertRaisesRegex(AssertionError, "mcp_upstream_timeout"):
            self.execute()

    def test_records_conversation_before_failed_invocation(self):
        self.services.fail_response = True
        with self.assertRaisesRegex(RuntimeError, "Synthetic service failure"):
            self.execute()
        inventory = self.namespace["WORK_ROOT"] / "conversations.txt"
        self.assertEqual(inventory.read_text(encoding="utf-8").splitlines(), ["synthetic-conversation-1"])

    def test_rejects_wrong_missing_and_near_match_customer_arguments(self):
        for value in ("CUST-0010", "CUST-002", "", "CUST-001 and CUST-0010"):
            with self.subTest(arguments=value):
                self.services.trace_id = value
                with self.assertRaisesRegex(AssertionError, "unobservable customer ID|name resolution"):
                    self.execute()

    def test_allows_name_resolution_before_stable_id_lookups(self):
        self.execute()
        calls = [item.model_dump() for item in self.namespace["items"]]
        queries = [
            json.loads(call["arguments"])["query"]
            for call in calls if call.get("name") == "fabriciq-ontology___ask_ontology"
        ]
        self.assertEqual(queries, ["Adatum Corporation", "CUST-001"])

    def test_rejects_missing_separate_name_resolution(self):
        self.services.omit_resolution = True
        with self.assertRaisesRegex(AssertionError, "name resolution"):
            self.execute()

    def test_rejects_repeated_writeup_retrieval(self):
        self.services.retrieval_count = 2
        with self.assertRaisesRegex(AssertionError, "one writeup retrieval"):
            self.execute()

    def test_requires_nonempty_outputs_for_each_required_tool(self):
        for name in TOOL_NAMES:
            for field in ("missing_output_name", "empty_output_name"):
                with self.subTest(name=name, field=field):
                    self.services.missing_output_name = None
                    self.services.empty_output_name = None
                    setattr(self.services, field, name)
                    with self.assertRaisesRegex(AssertionError, "Missing/empty tool output"):
                        self.execute()

    def test_rejects_incomplete_tool_calls(self):
        self.services.incomplete_tool_name = TOOL_NAMES[1]
        with self.assertRaisesRegex(AssertionError, "Incomplete tool"):
            self.execute()

    def test_pairs_function_outputs_by_call_id(self):
        self.services.data_as_functions = True
        self.execute()
        self.assertEqual(len(self.namespace["outputs"]), 4)

    def test_surfaces_additional_tool_diagnostic_without_rejecting_supported_brief(self):
        self.services.denied_read = True
        self.execute(stop="ask-question")
        output = io.StringIO()
        with redirect_stdout(output):
            exec(CELLS["inspect-trace"], self.namespace)
            exec(CELLS["check-report"], self.namespace)
        self.assertIn("Additional tool diagnostic: view", output.getvalue())
        self.assertIn("denied", output.getvalue())
        self.assertIn("Source document (retrieval metadata):", output.getvalue())
        self.assertIn("view", [call["name"] for call in self.namespace["calls"]])
        self.assertEqual(len(self.namespace["procedure"]), 4)

    def test_additional_tool_failure_does_not_make_an_unsupported_brief_pass(self):
        self.services.denied_read = True
        self.services.answers["meeting"] = self.services.answers["meeting"].replace(
            REPORTS[0]["documented_action"], "A recommendation with no source.",
        )
        with self.assertRaisesRegex(AssertionError, "No quoted next-action"):
            self.execute()

    def test_rejects_embedded_data_tool_errors(self):
        for error in ({"error": {"code": "failed"}}, {"isError": True}):
            with self.subTest(error=error):
                self.services.embedded_error = error
                with self.assertRaisesRegex(AssertionError, "Tool failed: fabriciq"):
                    self.execute()

    def test_prints_only_final_answer_not_progress(self):
        self.services.progress = "Synthetic progress should not be part of the final answer."
        self.execute()
        self.assertNotIn(self.services.progress, self.namespace["answer"])
        self.assertEqual(self.namespace["answer"], self.services.answers["meeting"])

    def test_requires_exact_account_action_passage_and_matching_report_metadata(self):
        for source in (
            {"snippet": "CUST-002 " + REPORTS[0]["documented_action"], "doc_url": self.services.report_url},
            {"snippet": "CUST-0010 " + REPORTS[0]["documented_action"], "doc_url": self.services.report_url},
            {"snippet": "CUST-001 No recommended action.", "doc_url": self.services.report_url},
            {"snippet": "CUST-001 " + REPORTS[0]["documented_action"], "doc_url": self.services.report_url},
            {"snippet": "CUST-001 FSR-CUST-001-20261105 2026-11-05 " + REPORTS[0]["documented_action"]},
        ):
            with self.subTest(source=source):
                self.services.retrieval_output = json.dumps([{"text": json.dumps({
                    "kind": "reference", "sourceData": source,
                })}])
                with self.assertRaisesRegex(AssertionError, "No account-matching source passage"):
                    self.execute()

    def test_displays_source_link_from_retrieval_without_changing_the_answer(self):
        self.services.answers["meeting"] = FIXTURE["known"]["answer"]
        self.execute(stop="inspect-trace")
        output = io.StringIO()
        with redirect_stdout(output):
            exec(CELLS["check-report"], self.namespace)
        self.assertNotIn(self.services.report_url, self.namespace["answer"])
        self.assertEqual(self.namespace["answer"], FIXTURE["known"]["answer"])
        self.assertIn("Source document (retrieval metadata): " + self.services.report_url, output.getvalue())

    def test_accepts_another_genuine_next_action_sentence_with_matching_source(self):
        alternate = (
            "The seller would first confirm the business question and the content owner, "
            "then agree on a reviewer-scored answer-quality check."
        )
        self.services.answers["meeting"] = self.services.answers["meeting"].replace(
            REPORTS[0]["documented_action"], alternate,
        )
        self.services.retrieval_output = self.services.retrieval_output.replace(
            REPORTS[0]["documented_action"], alternate,
        )
        self.execute()
        self.assertEqual(self.namespace["quote"], alternate)

    def test_rejects_a_real_quote_from_outside_the_next_actions_section(self):
        self.services.answers["meeting"] = self.services.answers["meeting"].replace(
            REPORTS[0]["documented_action"],
            "The account team wants a concise answer with a useful source, not a longer list of documents.",
        )
        with self.assertRaisesRegex(AssertionError, "No quoted next-action"):
            self.execute()

    def test_action_and_report_header_must_refer_to_the_same_source_document(self):
        source = json.loads(json.loads(self.services.retrieval_output)[0]["text"])["sourceData"]
        header = {**source, "snippet": "CUST-001 FSR-CUST-001-20261105 2026-11-05"}
        action = {
            "snippet": "CUST-001 " + REPORTS[0]["documented_action"],
            "doc_url": "https://example.test/unrelated-report.pdf",
        }
        self.services.retrieval_output = json.dumps([
            {"text": json.dumps({"kind": "reference", "sourceData": item})}
            for item in (header, action)
        ])
        with self.assertRaisesRegex(AssertionError, "No account-matching source passage"):
            self.execute()

    def test_displays_only_an_action_paired_with_its_actual_source(self):
        unsupported_quote = (
            "The seller would first confirm the business question and the content owner, "
            "then agree on a reviewer-scored answer-quality check."
        )
        self.services.answers["meeting"] = (
            f'"{unsupported_quote}"\n' + self.services.answers["meeting"]
        )
        self.execute()
        self.assertEqual(self.namespace["quote"], REPORTS[0]["documented_action"])

    def test_partial_brief_is_not_accepted_as_verified_happy_path(self):
        self.services.answers["meeting"] = (
            "Customer: found. CUST-001, KB-001-01, TS-009967, 2026-11-05. "
            "Report: not found. Documented action:"
        )
        self.execute(stop="inspect-trace")
        self.assertIn("TS-009967", self.namespace["response"].output_text)
        with self.assertRaises(AssertionError):
            exec(CELLS["check-report"], self.namespace)

    def test_rejects_similar_company_name_during_resolution(self):
        self.services.resolution_name = "Adatum Research Labs"
        with self.assertRaisesRegex(AssertionError, "name resolution"):
            self.execute()

    def test_rejects_missing_exact_id_record_lookup(self):
        self.services.omit_record_lookup = True
        with self.assertRaisesRegex(AssertionError, "exact customer record"):
            self.execute()

    def test_rejects_retrieval_before_record_lookup(self):
        self.services.tool_names = (TOOL_NAMES[0], TOOL_NAMES[2], TOOL_NAMES[1])
        with self.assertRaisesRegex(AssertionError, "exact customer record"):
            self.execute()

    def test_rejects_data_calls_before_loading_the_skill(self):
        self.services.tool_names = (TOOL_NAMES[1], TOOL_NAMES[0], TOOL_NAMES[2])
        with self.assertRaisesRegex(AssertionError, "Load the investigation skill"):
            self.execute()

    def test_rejects_missing_or_unexpected_tools(self):
        for names in (TOOL_NAMES[1:], (*TOOL_NAMES, "unexpected_tool")):
            with self.subTest(names=names):
                self.services.tool_names = names
                with self.assertRaisesRegex(AssertionError, "missing/unexpected"):
                    self.execute()

    def test_rejects_shell_call(self):
        self.services.shell = True
        with self.assertRaisesRegex(AssertionError, "Unexpected shell"):
            self.execute()

    def test_rejects_incorrect_report_fields_or_quote(self):
        original = self.services.answers["meeting"]
        report = REPORTS[0]
        for field in ("report_reference", "report_date", "documented_action"):
            with self.subTest(field=field):
                self.services.answers["meeting"] = original.replace(report[field], "wrong")
                with self.assertRaises(AssertionError):
                    self.execute()

    def test_rejects_empty_response(self):
        self.services.answers["meeting"] = " \n"
        with self.assertRaisesRegex(AssertionError, "No answer returned"):
            self.execute()

    def test_customer_and_knowledge_base_fixtures_match_the_source_scope(self):
        with (DATA_DIR / "customers.csv").open(encoding="utf-8", newline="") as handle:
            customers = {row["customer_id"]: row for row in csv.DictReader(handle)}
        with (DATA_DIR / "knowledge-bases.csv").open(encoding="utf-8", newline="") as handle:
            bases = {row["knowledge_base_id"]: row for row in csv.DictReader(handle)}
        identifier = FIXTURE["known_id"]
        ontology = FIXTURE["known"]["ontology"]
        self.assertEqual(set(customers), {identifier})
        self.assertEqual(customers[identifier]["customer_name"], ontology["customer_name"])
        self.assertEqual(int(customers[identifier]["knowledge_base_count"]), 2)
        self.assertEqual(int(customers[identifier]["index_count"]), 2)
        self.assertEqual(set(bases), {base["id"] for base in ontology["knowledge_bases"]})
        for base in ontology["knowledge_bases"]:
            self.assertEqual(bases[base["id"]]["knowledge_base_name"], base["name"])
            self.assertEqual(bases[base["id"]]["customer_id"], identifier)
        self.assertEqual({row["customer_id"] for row in REPORTS}, {identifier})
        expected = FIXTURE["known"]["retrieval"]
        report = next(row for row in REPORTS if row["customer_id"] == FIXTURE["known_id"])
        for field in ("report_reference", "report_date", "documented_action"):
            self.assertEqual(report[field], expected[field])

    def test_complete_sample_scope_reproduces_the_synthetic_report_facts(self):
        with (DATA_DIR / "telemetry-samples.csv").open(encoding="utf-8", newline="") as handle:
            samples = list(csv.DictReader(handle))
        ontology = FIXTURE["known"]["ontology"]
        self.assertEqual(len(samples), ontology["sample_count"])
        self.assertEqual(len({row["telemetry_id"] for row in samples}), len(samples))
        self.assertEqual({row["customer_id"] for row in samples}, {FIXTURE["known_id"]})
        self.assertEqual({row["knowledge_base_id"] for row in samples}, {"KB-001-01", "KB-001-02"})
        self.assertEqual({row["index_name"] for row in samples}, {"idx-001-01", "idx-001-02"})
        self.assertEqual(Counter(row["status"] for row in samples),
                         {"Healthy": 269, "Degraded": 3, "Throttled": 11})
        for field, expected in (("requests_5m", 4825), ("errors_5m", 111), ("throttled_requests_5m", 30)):
            self.assertEqual(sum(int(row[field]) for row in samples), expected)
        for row in samples:
            self.assertIsNotNone(datetime.fromisoformat(row["event_time_utc"].replace("Z", "+00:00")).tzinfo)
        peak = max(samples, key=lambda row: int(row["p95_latency_ms"]))
        self.assertEqual(peak["telemetry_id"], ontology["highest_p95_sample_id"])
        self.assertEqual(peak["p95_latency_ms"], "4609")
        self.assertEqual(peak["event_time_utc"], "2026-10-16T19:15:00Z")
        latest = {
            max((row for row in samples if row["knowledge_base_id"] == base),
                key=lambda row: row["event_time_utc"])["telemetry_id"]
            for base in ("KB-001-01", "KB-001-02")
        }
        self.assertEqual(latest, set(ontology["latest_sample_ids"]))
        content = REPORTS[0]["content"]
        self.assertIn("fictional demo content", content)
        self.assertIn("not a claim that the organization has purchased", content)
        self.assertIn("Expansion remains conditional", content)
        self.assertIn(REPORTS[0]["documented_action"], content)

    def test_skill_keeps_meeting_scope_and_evidence_boundaries(self):
        self.execute(stop="write-skill")
        skill = " ".join(self.namespace["skill_text"].split())
        for text in (
            "stable customer_id", "hasKnowledgeBase", "hasTelemetrySample",
            "event_time_utc", "historical concern is not a current incident",
            "recommended action is not completed work", "numeric health score",
            "do not guess", "Schema discovery is not record evidence",
            "recorded, concerns to discuss", "Prepare a customer meeting brief",
            "Do not return the full history", "average p95 values into a global percentile",
            "Do not fetch KBs or samples in this first call",
            "make a SEPARATE ask_ontology call with the literal customer_id",
            "ONLY after the exact-ID record call returns",
            "query_variants; never retrieve by company name alone",
            "Use the returned tool answers to write the brief",
            "document links separately from retrieval reference metadata",
            "Call a degraded sample an observation, not an incident or outage",
            "Retrieve once; report a missing writeup or tool failure",
            "do not re-query for citation tokens",
            "proposed next step verbatim in double quotes",
            "Cite the report passage for its proposed action, not the underlying CSV",
            "Do not ask for sources cited inside the writeup",
            "Show timestamps in UTC and latency in milliseconds",
            "Do not label a sample severe without a defined threshold",
            "an ontology timeout does not establish that the account report is missing",
            "A failed or uncalled lookup is unavailable, not evidence of absence",
        ):
            self.assertIn(text, skill)
        self.assertNotIn("stages output in a file", skill)
        intro = "".join(DOCUMENT["cells"][0]["source"])
        self.assertLess(intro.index("Copilot harness"), intro.index("Fabric IQ"))
        self.assertIn("your application does not dispatch them in a loop", intro)
        self.assertIn("**Make it yours**", intro)

    def test_one_plain_text_playground_prompt_matches_the_sdk_question(self):
        self.execute()
        markdown = next("".join(cell["source"]) for cell in DOCUMENT["cells"] if cell["id"] == "playground-example")
        prompts = re.findall(r"```text\n(.*?)\n```", markdown, re.DOTALL)
        self.assertEqual(prompts, [self.namespace["question"]])
        self.assertIn("\n### Try the same question in the playground\n", "\n" + markdown)
        self.assertIn("https://ai.azure.com/", markdown)
        self.assertIn("same agent, pinned skill, and two connections", markdown)

    def test_distinguishes_mock_wiring_from_live_source_verification(self):
        markdown = "\n".join("".join(cell["source"]) for cell in DOCUMENT["cells"] if cell["cell_type"] == "markdown")
        self.assertIn("not a link generated by the agent", markdown)
        self.assertIn("ran from a clean clone, launched in `notebooks/`", markdown)
        self.assertIn("separately from earlier saved-response replays", markdown)
        self.assertIn("This evidence paragraph was added after the recorded run", markdown)
        self.assertIn("Native citation navigation remains unverified", markdown)
        self.assertIn("Treat those details as unknown, not established absent", markdown)
        self.assertNotIn("Current validation: blocked", markdown)
        self.assertNotIn("denied staged", markdown)
        self.assertNotIn("JSONL adaptation", markdown)
        self.assertIn("verified source path", markdown)
        self.assertIn("matching synthetic OneLake field-sales PDF", markdown)
        self.assertIn("One successful flow is not an accuracy benchmark", markdown)
        self.assertIn("actual tool outputs", markdown)
        self.assertIn("pivots=sdk&tabs=python", markdown)
        self.assertIn("not real outputs or model-quality evidence", markdown)
        self.assertIn("All customers, dates, and observations in the shipped fixtures are fictional", markdown)
        self.assertTrue(all(not cell.get("outputs") and cell.get("execution_count") is None
                            for cell in DOCUMENT["cells"] if cell["cell_type"] == "code"))

    def test_documents_restricted_pdf_and_separate_displayed_citation_review(self):
        markdown = "\n".join("".join(cell["source"]) for cell in DOCUMENT["cells"] if cell["cell_type"] == "markdown")
        self.assertIn("**PDF access is restricted.**", markdown)
        self.assertIn("Before creating connections or deploying, obtain access", markdown)
        self.assertIn("Without that access, you cannot reproduce this exact example", markdown)
        self.assertIn("Passing this cell does not verify the agent's displayed citation", markdown)
        self.assertIn("An opaque, missing, or mismatched citation remains unverified", markdown)
        self.assertIn("highest p95 among the account's sampled intervals", markdown)

    def test_retained_evidence_distinguishes_live_and_revised_code(self):
        evidence = json.loads((DATA_DIR / "live-evidence.json").read_text(encoding="utf-8"))
        code = [
            {"id": cell["id"], "source": "".join(cell["source"])}
            for cell in DOCUMENT["cells"] if cell["cell_type"] == "code"
        ]
        digest = hashlib.sha256(
            json.dumps(code, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(evidence["revision_review"]["code_cells_sha256"], digest)
        self.assertNotEqual(evidence["checkout"]["code_cells_sha256"], digest)
        self.assertEqual(evidence["revision_review"]["validation"], "offline-wiring-and-saved-service-replay; no-new-live-deployment")
        self.assertEqual(evidence["output_audit"]["status"], "blocked")
        attempts = evidence["output_audit"]["attempts"]
        self.assertEqual(len(attempts), 3)
        self.assertTrue(all(attempt["cells_attempted"] == 12 for attempt in attempts))
        self.assertNotEqual(attempts[-1]["code_cells_sha256"], digest)
        self.assertEqual(attempts[-1]["cells_with_errors"], ["inspect-trace", "check-report"])
        self.assertEqual(attempts[-1]["references_matching_actual_pdf"], 24)
        self.assertEqual(
            set(evidence["fixture_sha256"]),
            {"customers.csv", "knowledge-bases.csv", "telemetry-samples.csv", "reports.jsonl"},
        )
        for name, expected in evidence["fixture_sha256"].items():
            self.assertEqual(hashlib.sha256((DATA_DIR / name).read_bytes()).hexdigest(), expected)
        replay = evidence["revision_review"]["saved_service_replay"]
        self.assertEqual(replay["code_cells_sha256"], digest)
        self.assertEqual(replay["cells_replayed"], ["inspect-trace", "check-report"])
        self.assertEqual(replay["result"], "passed")
        self.assertEqual(replay["source_link_origin"], "SDK-returned retrieval reference metadata, not the generated answer")

    def test_clean_live_capture_matches_executable_cells_and_preserves_audit_limits(self):
        evidence = json.loads((DATA_DIR / "live-evidence.json").read_text(encoding="utf-8"))
        live = evidence["publication_candidate_run"]
        self.assertEqual(live["code_cells_sha256"], evidence["revision_review"]["code_cells_sha256"])
        self.assertEqual(live["code_cells_completed"], len(CELLS))
        self.assertEqual(live["code_cell_errors"], [])
        self.assertTrue(live["checkout_clean_before_execution"])
        self.assertTrue(live["checkout_clean_after_execution"])
        self.assertEqual(
            live["required_call_sequence"],
            [TOOL_NAMES[0], TOOL_NAMES[1], TOOL_NAMES[1], TOOL_NAMES[2]],
        )
        audit = live["independent_output_audit"]
        with (DATA_DIR / "telemetry-samples.csv").open(encoding="utf-8", newline="") as handle:
            samples = list(csv.DictReader(handle))
        self.assertEqual(audit["account_sample_rows_recomputed"], len(samples))
        self.assertEqual(audit["returned_references"], audit["references_matching_actual_pdf"])
        self.assertEqual(audit["model_answer_qualification"]["status"], "overstates-source")
        self.assertEqual(audit["native_displayed_citation"]["status"], "unverified")
        markdown = "\n".join("".join(cell["source"]) for cell in DOCUMENT["cells"] if cell["cell_type"] == "markdown")
        self.assertIn(live["tested_commit"], markdown)
        self.assertNotEqual(live["source_notebook_sha256"], hashlib.sha256(NOTEBOOK.read_bytes()).hexdigest())

    def test_retained_live_evidence_has_source_review_and_redaction(self):
        evidence = json.loads((DATA_DIR / "live-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["kind"], "sanitized-live-validation")
        self.assertEqual(
            [call["name"] for call in evidence["trace"]],
            [TOOL_NAMES[0], TOOL_NAMES[1], TOOL_NAMES[1], TOOL_NAMES[2]],
        )
        self.assertTrue(all(call["status"] == "completed" and not call["error"] for call in evidence["trace"]))
        sources = evidence["verified_sources"]
        report = REPORTS[0]
        self.assertEqual(sources["source_report_reference"], report["report_reference"])
        self.assertEqual(sources["source_report_date"], report["report_date"])
        self.assertIn(report["documented_action"], evidence["final_answer"])
        self.assertIn(report["documented_action"], " ".join(sources["action_reference"]["sourceData"]["snippet"].split()))
        self.assertIn("CUST-001", sources["action_reference"]["sourceData"]["snippet"])
        self.assertIn("[SOURCE_PDF_URL_REDACTED]", evidence["final_answer"])
        self.assertEqual(sources["action_reference"]["sourceData"]["doc_url"], "[SOURCE_PDF_URL_REDACTED]")
        self.assertTrue(all(sources["checks"].values()))
        self.assertLess(evidence["final_answer_word_count_before_redaction"], 250)
        serialized = json.dumps(evidence)
        self.assertNotRegex(serialized, r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")
        for private_value in ("services.ai.azure.com", "search.windows.net", "blob.fabric.microsoft.com", "/home/session/"):
            self.assertNotIn(private_value, serialized)

    def test_embeds_one_playground_screenshot_with_its_data_boundary(self):
        markdown = "\n".join("".join(cell["source"]) for cell in DOCUMENT["cells"] if cell["cell_type"] == "markdown")
        images = re.findall(r"!\[[^\]]+\]\(([^)]+)\)", markdown)
        self.assertEqual(images, ["media/copilot-harness-foundry-fabric-iq/01-meeting-preparation-playground.png"])
        self.assertTrue((ROOT / "notebooks" / images[0]).is_file())
        self.assertIn("Playground example with the matching Adatum fixtures", markdown)
        self.assertIn("from an earlier agent version", markdown)
        self.assertIn("omits project details and the source panel", markdown)
        self.assertNotIn("Illustrative brief", markdown)
        self.assertLess(markdown.index("Excerpts from a live account brief"), markdown.index("## Prerequisites and setup"))
        self.assertNotIn("Replace it with", markdown)

    def test_walkthrough_follows_explanatory_three_step_format(self):
        markdown = "\n".join("".join(cell["source"]) for cell in DOCUMENT["cells"] if cell["cell_type"] == "markdown")
        headings = re.findall(r"^## (.+)$", markdown, re.MULTILINE)
        self.assertEqual(
            headings,
            [
                "Prerequisites and setup",
                "1. Connect the sources",
                "2. Give the harness a procedure",
                "3. Ask for an account brief",
                "Make it yours",
                "What this does and doesn't do",
                "Clean up",
                "References",
            ],
        )
        self.assertIn("**How it works:**", markdown)
        playground = "".join(next(cell["source"] for cell in DOCUMENT["cells"] if cell["id"] == "playground-example"))
        self.assertIn("```text\nI'm meeting Adatum Corporation tomorrow.", playground)
        self.assertIn("![Foundry playground brief", playground)

    def test_failure_diagnostics_can_be_fetched_without_resubmitting(self):
        source = CELLS["ask-question"]
        self.assertLess(source.index("items = list("), source.index("assert response.status"))
        markdown = "".join(next(cell["source"] for cell in DOCUMENT["cells"] if cell["id"] == "verify-and-reuse"))
        recovery = re.search(r"```python\n(.*?)\n```", markdown, re.DOTALL).group(1)
        self.execute()
        self.services.openai.responses.create.reset_mock()
        self.services.openai.conversations.items.list.reset_mock()
        exec(recovery, self.namespace)
        self.services.openai.responses.create.assert_not_called()
        self.services.openai.conversations.items.list.assert_called_once_with(
            conversation_id=self.namespace["conversation"].id, order="asc",
        )

    def test_opening_excerpts_are_from_the_retained_real_answer(self):
        evidence = json.loads((DATA_DIR / "live-evidence.json").read_text(encoding="utf-8"))
        intro = "".join(DOCUMENT["cells"][0]["source"])
        excerpts = [line[2:] for line in intro.splitlines() if line.startswith("> ")]
        self.assertEqual(len(excerpts), 3)
        for excerpt in excerpts:
            self.assertIn(excerpt, evidence["functional_example"]["final_answer"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
