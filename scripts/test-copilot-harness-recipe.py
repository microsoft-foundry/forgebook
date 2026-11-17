"""Offline snippet tests; synthetic answers are not live service evidence.

Run from the repo root: python scripts/test-copilot-harness-recipe.py
Requires IPython (included with the notebook's Jupyter environment).
"""

import ast
import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import ExitStack, redirect_stdout
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from IPython.core.inputtransformer2 import TransformerManager


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "copilot-harness-foundry-fabric-iq.ipynb"
DATA_DIR = ROOT / "notebooks" / "data" / "copilot-harness-foundry-fabric-iq"
DOCUMENT = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
CELLS = {
    cell["id"]: "".join(cell["source"])
    for cell in DOCUMENT["cells"] if cell["cell_type"] == "code"
}
MARKDOWN = "\n\n".join(
    "".join(cell["source"]) for cell in DOCUMENT["cells"] if cell["cell_type"] == "markdown"
)
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
    "IQ_REPORT_URL": "https://raw.githubusercontent.com/example/public-demo/fixture/account-report.md",
}
TOOL_NAMES = ("skill", "fabriciq-ontology___ask_ontology", "field-sales-reports___knowledge_base_retrieve")
REPORT_TEXT = (DATA_DIR / "account-report.md").read_text(encoding="utf-8")
CHECK_SPEC = importlib.util.spec_from_file_location("recipe_source_checks", DATA_DIR / "source_checks.py")
SOURCE_CHECKS = importlib.util.module_from_spec(CHECK_SPEC)
CHECK_SPEC.loader.exec_module(SOURCE_CHECKS)


class FakeItem:
    def __init__(self, **values):
        self.values = values

    def model_dump(self):
        return self.values

    def __getattr__(self, name):
        return self.values[name]


class FakeServices:
    """Implement only the external operations used by these snippets."""

    def __init__(self):
        self.commands = []
        self.fail_command = None
        self.deployed = {
            "versions": {"latest": {
                "version": "1",
                "definition": {
                    "kind": "prompt",
                    "harness": {"type": "microsoft_copilot_preview"},
                    "skills": [{"name": f'{CONFIG["IQ_RUN_NAME"]}-investigate', "version": "1"}],
                },
            }},
        }
        self.status = "completed"
        self.response_error = None
        self.fail_response = False
        self.answer = FIXTURE["known"]["answer"]
        self.progress = "Synthetic progress, not the final answer."
        self.function_data = False
        self.tool_error = None
        self.payloads = [
            "Skill loaded successfully.",
            json.dumps({"customer_id": "CUST-001", "customer_name": "Adatum Corporation"}),
            json.dumps({
                **FIXTURE["known"]["ontology"],
                "sampled_latencies_ms": [455, 471, 4609],
            }),
            json.dumps([{"type": "text", "text": json.dumps({
                "kind": "reference", "ref_id": 0, "sourceData": {
                    "content": REPORT_TEXT, "url": CONFIG["IQ_REPORT_URL"],
                },
            })}]),
        ]
        self.questions = {}
        self.openai = SimpleNamespace(
            conversations=SimpleNamespace(
                create=Mock(return_value=SimpleNamespace(id="synthetic-conversation")),
                items=SimpleNamespace(list=Mock(side_effect=self.list_items)),
            ),
            responses=SimpleNamespace(create=Mock(side_effect=self.create_response)),
        )
        self.project = SimpleNamespace(get_openai_client=Mock(return_value=self.openai))
        self.project_factory = Mock(return_value=self.project)
        self.credential_factory = Mock()

    def system(self, command):
        args = shlex.split(command.format_map(self.namespace))
        assert args[:2] == ["azd", "--cwd"], args
        directory = Path(args[2])
        args = [args[0], *args[3:]]
        self.commands.append(args)
        if self.fail_command and args[1:1 + len(self.fail_command)] == self.fail_command:
            self.namespace["_exit_code"] = 17
            return
        if args[1:4] == ["ai", "agent", "init"]:
            project = directory / args[4]
            project.mkdir()
            (project / "azure.yaml").write_text("name: fake-init\n", encoding="utf-8")
        elif ">" in args:
            assert args[1:4] == ["ai", "agent", "show"], args
            Path(args[-1]).write_text(json.dumps(self.deployed), encoding="utf-8")
        else:
            assert args[1:4] == ["ai", "connection", "create"] or args[1] == "deploy", args
        assert os.environ["AZD_ALPHA_ENABLE_AGENTS_MANAGED_HARNESS"] == "true"
        self.namespace["_exit_code"] = 0

    def create_response(self, *, conversation, input):
        if self.fail_response:
            raise RuntimeError("Synthetic service failure")
        self.questions[conversation] = input
        return SimpleNamespace(
            status=self.status, error=self.response_error,
            output=[
                SimpleNamespace(
                    type="message", role="assistant",
                    content=[FakeItem(type="output_text", text=text, annotations=[{
                        "type": "url_citation", "url": CONFIG["IQ_REPORT_URL"],
                        "title": "Synthetic report",
                    }])],
                )
                for text in (self.progress, self.answer)
            ],
        )

    def list_items(self, *, conversation_id, order):
        assert order == "asc"
        assert conversation_id in self.questions
        items = []
        queries = [
            (TOOL_NAMES[0], "Read the investigation skill"),
            (TOOL_NAMES[1], "Adatum Corporation"),
            (TOOL_NAMES[1], "CUST-001"),
            (TOOL_NAMES[2], "CUST-001"),
        ]
        for index, (name, query) in enumerate(queries):
            kind = "function_call" if index == 0 or self.function_data else "mcp_call"
            call_id = f"synthetic-call-{index}"
            error = self.tool_error if index == 1 else None
            values = {
                "type": kind, "name": name, "arguments": json.dumps({"query": query}),
                "call_id": call_id, "status": "completed", "error": error,
            }
            output = self.payloads[index]
            if kind == "mcp_call":
                values["output"] = output
            else:
                items.insert(0, FakeItem(
                    type="function_call_output", call_id=call_id,
                    output=output, error=error,
                ))
            items.append(FakeItem(**values))
        return iter(items)


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="iq offline ")
        self.addCleanup(self.temp.cleanup)
        self.services = FakeServices()
        self.namespace = {}
        self.output = ""

    def execute(self, stop=None):
        self.services.namespace = self.namespace
        self.namespace["get_ipython"] = lambda: self.services
        modules = {name: ModuleType(name) for name in ("azure", "azure.ai", "azure.ai.projects", "azure.identity")}
        modules["azure.ai.projects"].AIProjectClient = self.services.project_factory
        modules["azure.identity"].AzureCliCredential = self.services.credential_factory
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, CONFIG, clear=True))
            stack.enter_context(patch.dict(sys.modules, modules))
            stack.enter_context(patch("tempfile.gettempdir", return_value=self.temp.name))
            stack.enter_context(patch("shutil.which", return_value="azd"))
            stack.enter_context(patch("subprocess.run", side_effect=AssertionError("External process forbidden")))
            stack.enter_context(patch("subprocess.check_output", side_effect=AssertionError("External process forbidden")))
            stack.enter_context(patch("socket.create_connection", side_effect=AssertionError("Network forbidden")))
            output = stack.enter_context(redirect_stdout(io.StringIO()))
            try:
                for identifier, source in CELLS.items():
                    python_source = TransformerManager().transform_cell(source)
                    exec(compile(python_source, f"{NOTEBOOK.name}:{identifier}", "exec"), self.namespace)
                    if identifier == stop:
                        break
            finally:
                self.output = output.getvalue()

    def printed_trace(self):
        self.execute(stop="ask-question")
        output = io.StringIO()
        with redirect_stdout(output):
            exec(CELLS["inspect-trace"], self.namespace)
        text = output.getvalue().strip()
        records = []
        while text:
            record, end = json.JSONDecoder().raw_decode(text)
            if "tool" in record:
                records.append(record)
            text = text[end:].lstrip()
        return records

    def test_runs_every_cell_without_custom_runtime_or_dispatch_loop(self):
        self.execute()
        self.services.openai.responses.create.assert_called_once()
        self.assertEqual(self.namespace["answer"], self.services.answer)
        for source in CELLS.values():
            tree = ast.parse(TransformerManager().transform_cell(source))
            self.assertFalse(any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree)))

    def test_cli_failures_stop_before_sdk_invocation(self):
        agent = CONFIG["IQ_RUN_NAME"]
        for prefix in (
            ["ai", "agent", "init"],
            ["ai", "connection", "create", f"{agent}-kb"],
            ["ai", "connection", "create", f"{agent}-ontology"],
            ["deploy"], ["ai", "agent", "show"],
        ):
            with self.subTest(command=prefix):
                self.services.fail_command = prefix
                with self.assertRaises(AssertionError):
                    self.execute()
                self.services.openai.responses.create.assert_not_called()

    def test_rejects_invalid_run_name_before_cloud_operations(self):
        for name in ("Uppercase", "-leading", "a" * 42, "has spaces"):
            with self.subTest(name=name), patch.dict(CONFIG, IQ_RUN_NAME=name):
                with self.assertRaisesRegex(AssertionError, "run name"):
                    self.execute()
                self.assertEqual(self.services.commands, [])

    def test_lists_every_missing_variable_before_cloud_operations(self):
        absent = ("FABRIC_ONTOLOGY_ID", "FOUNDRY_IQ_KB_MCP_URL")
        reduced = {key: value for key, value in CONFIG.items() if key not in absent}
        with patch.dict(os.environ, {**reduced, "IQ_RUN_NAME": " "}, clear=True):
            with self.assertRaises(RuntimeError) as raised:
                exec(CELLS["setup"], {"__builtins__": __builtins__})
        for name in (*absent, "IQ_RUN_NAME"):
            self.assertIn(name, str(raised.exception))
        self.assertEqual(self.services.commands, [])

    def test_requires_azd_before_cloud_operations(self):
        with patch.dict(os.environ, CONFIG), patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(AssertionError, "Install azd"):
                exec(CELLS["setup"], {"__builtins__": __builtins__})

    def test_uses_direct_azd_commands_with_failure_checks(self):
        self.execute()
        for identifier in ("init-project", "connect-search", "connect-fabric", "deploy"):
            self.assertIn("!azd --cwd", CELLS[identifier])
            self.assertIn("_exit_code == 0", CELLS[identifier])
        self.assertNotIn("subprocess", "\n".join(CELLS.values()))

    def test_uses_existing_project_and_distinct_tool_identities(self):
        self.execute()
        commands = self.services.commands
        self.assertIn(CONFIG["FOUNDRY_PROJECT_ID"], commands[0])
        self.assertTrue(any(command[1:] == ["deploy", "--all", "--no-prompt"] for command in commands))
        self.assertFalse(any("up" in command or "down" in command for command in commands))
        connections = [command for command in commands if command[1:4] == ["ai", "connection", "create"]]
        self.assertEqual(len(connections), 2)
        self.assertIn("project-managed-identity", connections[0])
        self.assertIn("https://search.azure.com/", connections[0])
        self.assertIn("user-entra-token", connections[1])
        self.assertIn("https://analysis.windows.net/powerbi/api", connections[1])

    def test_writes_copyable_skill_and_read_only_manifest(self):
        self.execute()
        namespace = self.namespace
        self.assertEqual((namespace["skill_dir"] / "SKILL.md").read_text(encoding="utf-8"), namespace["skill_text"])
        manifest = (namespace["PROJECT_DIR"] / "azure.yaml").read_text(encoding="utf-8")
        self.assertEqual(manifest, namespace["manifest"])
        self.assertIn("defaultConfig:\n          enabled: false", manifest)
        self.assertIn("- name: filesystem_read\n            enabled: true", manifest)
        self.assertIn(json.dumps(CONFIG["FOUNDRY_IQ_KB_MCP_URL"]), manifest)
        self.assertIn("type: microsoft_copilot_preview", manifest)

    def test_readback_rejects_wrong_agent_kind_harness_or_skill(self):
        definition = self.services.deployed["versions"]["latest"]["definition"]
        for field, value in (("kind", "hosted"), ("harness", {"type": "default"}), ("skills", [{"name": "other"}])):
            with self.subTest(field=field):
                original = definition[field]
                definition[field] = value
                with self.assertRaises(AssertionError):
                    self.execute()
                definition[field] = original

    def test_uses_agent_scoped_sdk_and_one_ordinary_question(self):
        self.execute()
        self.services.project_factory.assert_called_once_with(
            endpoint=CONFIG["FOUNDRY_PROJECT_ENDPOINT"],
            credential=self.services.credential_factory.return_value, allow_preview=True,
        )
        self.services.project.get_openai_client.assert_called_once_with(agent_name=CONFIG["IQ_RUN_NAME"])
        self.services.openai.responses.create.assert_called_once_with(
            conversation=self.namespace["conversation"].id, input=self.namespace["question"],
        )
        self.assertIn("what's recorded for the account", self.namespace["question"])
        self.assertNotIn("CUST-", self.namespace["question"])
        self.assertNotIn("Adatum", CELLS["ask-question"])
        self.assertIn(self.namespace["EXPECTED_FACTS"]["customer_name"], self.namespace["question"])

    def test_records_conversation_before_failed_invocation(self):
        self.services.fail_response = True
        with self.assertRaisesRegex(RuntimeError, "Synthetic service failure"):
            self.execute()
        inventory = self.namespace["WORK_ROOT"] / "conversations.txt"
        self.assertEqual(inventory.read_text(encoding="utf-8").splitlines(), ["synthetic-conversation"])

    def test_stops_on_incomplete_or_error_response_after_fetching_items(self):
        for status, error in (("incomplete", None), ("completed", {"code": "synthetic_error"})):
            with self.subTest(status=status, error=error):
                self.services.status = status
                self.services.response_error = error
                self.services.openai.conversations.items.list.reset_mock()
                with self.assertRaisesRegex(AssertionError, "response failed"):
                    self.execute()
                self.services.openai.conversations.items.list.assert_called_once_with(
                    conversation_id=self.namespace["conversation"].id, order="asc",
                )

    def test_prints_only_final_answer_and_rejects_empty_output(self):
        self.execute()
        self.assertNotIn(self.services.progress, self.namespace["answer"])
        self.services.answer = " \n"
        with self.assertRaisesRegex(AssertionError, "No answer text"):
            self.execute()

    def test_pairs_function_and_mcp_outputs_by_call_id(self):
        for functions in (False, True):
            with self.subTest(functions=functions):
                self.services.function_data = functions
                records = self.printed_trace()
                self.assertEqual([row["tool"] for row in records], [
                    TOOL_NAMES[0], TOOL_NAMES[1], TOOL_NAMES[1], TOOL_NAMES[2],
                ])
                for index, record in enumerate(records):
                    self.assertEqual(record["output"], self.services.payloads[index])
                self.assertEqual(json.loads(records[1]["arguments"])["query"], "Adatum Corporation")
                self.assertEqual(json.loads(records[2]["arguments"])["query"], "CUST-001")

    def test_trace_keeps_errors_visible_for_manual_review(self):
        self.services.tool_error = {"code": "mcp_upstream_timeout", "message": "Synthetic timeout"}
        with self.assertRaisesRegex(AssertionError, "Required source checks failed"):
            self.execute()
        records = self.namespace["trace"]
        self.assertEqual(records[1]["error"], self.services.tool_error)
        self.assertEqual(records[1]["source_state"], "unavailable")
        self.assertIn("PARTIAL / UNVERIFIED", self.output)
        self.assertNotIn("sample source checks passed", self.output)

    def test_completed_response_rejects_embedded_errors_empty_results_and_missing_calls(self):
        failures = (
            json.dumps({"content": [{"type": "text", "text": '{"isError":true,"error":"403 Forbidden"}'}]}),
            json.dumps({"content": [{"type": "text", "text": '{"error":{"code":"Forbidden"}}'}]}),
            json.dumps({"errorCode": "PermissionDenied", "message": "Synthetic denial"}),
            json.dumps({"text": "403 Forbidden"}),
            json.dumps({"rows": []}),
            "",
        )
        for output in failures:
            with self.subTest(output=output):
                self.services.payloads[2] = output
                with self.assertRaisesRegex(AssertionError, "Required source checks failed"):
                    self.execute()
                self.assertIn("UNVERIFIED candidate", self.output)
                expected_state = "no-match" if output == '{"rows": []}' else "unavailable"
                self.assertEqual(self.namespace["trace"][2]["source_state"], expected_state)
        self.services = FakeServices()
        self.execute()
        for missing in range(4):
            records = [r for i, r in enumerate(self.namespace["trace"]) if i != missing]
            checks = SOURCE_CHECKS.verify_sample(self.services.answer, records, REPORT_TEXT, CONFIG["IQ_REPORT_URL"])
            self.assertTrue(checks["problems"], f"Missing required call {missing} accepted")

    def test_mcp_calls_without_call_ids_and_native_annotations_survive(self):
        self.execute()
        raw = self.namespace["trace_items"]
        for item in raw:
            if item["type"] == "mcp_call":
                del item["call_id"]
        records = SOURCE_CHECKS.inspect_trace(raw)
        checks = SOURCE_CHECKS.verify_sample(self.services.answer, records, REPORT_TEXT, CONFIG["IQ_REPORT_URL"])
        self.assertEqual(checks["problems"], [])
        self.assertEqual(self.namespace["native_annotations"][0]["url"], CONFIG["IQ_REPORT_URL"])

    def test_source_reference_must_match_local_quote_account_and_expected_url(self):
        self.execute()
        original = self.services.payloads[3]
        for output in (
            original.replace(CONFIG["IQ_REPORT_URL"], "https://example.com/unrelated"),
            original.replace("reviewer-scored", "unverified"),
            original.replace("CUST-001", "CUST-999"),
            json.dumps({"text": self.services.answer}),
        ):
            with self.subTest(output=output):
                records = [dict(r) for r in self.namespace["trace"]]
                records[3]["output"] = output
                checks = SOURCE_CHECKS.verify_sample(self.services.answer, records, REPORT_TEXT, CONFIG["IQ_REPORT_URL"])
                self.assertTrue(checks["problems"])

    def test_brief_word_limit_is_checked_before_success(self):
        self.execute()
        answer = self.services.answer
        words = len(answer.split())
        for count, rejected in ((249, False), (250, True)):
            candidate = answer + " detail" * (count - words)
            checks = SOURCE_CHECKS.verify_sample(
                candidate, self.namespace["trace"], REPORT_TEXT, CONFIG["IQ_REPORT_URL"],
            )
            self.assertEqual(bool(checks["problems"]), rejected)

    def test_structural_checks_are_separate_from_customer_facts(self):
        self.execute()
        trace, answer = self.namespace["trace"], self.services.answer
        url = CONFIG["IQ_REPORT_URL"]
        other = dict(SOURCE_CHECKS.EXPECTED_FACTS, customer_id="CUST-002", brief_must_mention=["CUST-002"])
        checks = SOURCE_CHECKS.verify_sample(answer, trace, REPORT_TEXT, url, facts=other)
        self.assertEqual(checks["structural_problems"], [])
        self.assertTrue(checks["fact_problems"])
        self.assertEqual(checks["problems"], checks["fact_problems"])

        checks = SOURCE_CHECKS.verify_sample(answer, trace, REPORT_TEXT, url, annotations=[])
        self.assertTrue(checks["structural_problems"])
        self.assertEqual(checks["fact_problems"], [])
        annotations = [{"type": "url_citation", "url": url}]
        checks = SOURCE_CHECKS.verify_sample(answer, trace, REPORT_TEXT, url, annotations=annotations)
        self.assertEqual(checks["problems"], [])

    def run_search_setup(self, action, *, collision=False, upload_succeeds=True):
        requests = ModuleType("requests")
        credential = ModuleType("azure.identity")
        credential.AzureCliCredential = Mock(return_value=SimpleNamespace(
            get_token=Mock(return_value=SimpleNamespace(token="synthetic-test-token")),
        ))

        def response(status=200, payload=None, text=""):
            result = SimpleNamespace(
                status_code=status, text=text, content=b"{}" if payload is not None else b"",
                json=lambda: payload,
            )
            result.raise_for_status = Mock(
                side_effect=RuntimeError(f"Synthetic HTTP {status}") if status >= 400 else None,
            )
            return result

        requests.get = Mock(side_effect=[
            response(text=REPORT_TEXT),
            response(200 if collision else 404), response(404), response(404),
        ])
        requests.request = Mock(side_effect=[
            response(), response(payload={"value": [{"status": upload_succeeds}]}),
            response(), response(),
        ] if action == "create" else [response()])
        modules = {name: ModuleType(name) for name in ("azure", "azure.identity")}
        modules.update({"azure.identity": credential, "requests": requests})
        config = {
            **CONFIG, "AZURE_SEARCH_ENDPOINT": "https://demo-search.search.windows.net",
        }
        spec = importlib.util.spec_from_file_location("recipe_search_setup", DATA_DIR / "prepare-search.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules), patch.dict(os.environ, config, clear=True), \
                patch("tempfile.gettempdir", return_value=self.temp.name), \
                patch.object(sys, "argv", ["prepare-search.py", action]), redirect_stdout(io.StringIO()):
            spec.loader.exec_module(module)
            self.search_transport = requests
            module.main()
        return requests

    def test_search_setup_refuses_preexisting_objects_before_any_write(self):
        with self.assertRaises(FileExistsError):
            self.run_search_setup("create", collision=True)
        self.search_transport.request.assert_not_called()

    def test_search_setup_returns_grounding_without_a_second_model(self):
        transport = self.run_search_setup("create")
        calls = transport.request.call_args_list
        self.assertEqual(len(calls), 4)
        knowledge_base = calls[-1].kwargs["json"]
        self.assertEqual(knowledge_base["outputMode"], "extractiveData")
        self.assertEqual(knowledge_base["retrievalReasoningEffort"], {"kind": "minimal"})
        self.assertNotIn("models", knowledge_base)
        source_fields = calls[-2].kwargs["json"]["searchIndexParameters"]["sourceDataFields"]
        self.assertIn({"name": "url"}, source_fields)
        self.assertIn({"name": "content"}, source_fields)

    def test_search_upload_failure_preserves_cleanup_inventory_and_stops_before_kb(self):
        with self.assertRaisesRegex(RuntimeError, "Report upload failed"):
            self.run_search_setup("create", upload_succeeds=False)
        calls = self.search_transport.request.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("knowledgebases/" not in str(call) for call in calls))
        state_path = Path(self.temp.name) / "forgebook-iq" / CONFIG["IQ_RUN_NAME"] / "search-sources.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["created"], [f'indexes/{CONFIG["IQ_RUN_NAME"]}-reports'])
        transport = self.run_search_setup("delete")
        self.assertEqual(transport.request.call_args.args[0], "DELETE")
        self.assertIn(state["created"][0], transport.request.call_args.args[1])
        self.assertEqual(json.loads(state_path.read_text(encoding="utf-8"))["created"], [])

    def test_recovery_fetches_existing_conversation_without_resubmitting(self):
        recovery = MARKDOWN.split("## Troubleshooting", 1)[1]
        source = re.search(r"```python\n(.*?)\n```", recovery, re.DOTALL)[1]
        self.execute()
        self.services.openai.responses.create.reset_mock()
        self.services.openai.conversations.items.list.reset_mock()
        exec(source, self.namespace)
        self.services.openai.responses.create.assert_not_called()
        self.services.openai.conversations.items.list.assert_called_once_with(
            conversation_id=self.namespace["conversation"].id, order="asc",
        )

    def test_playground_prompt_matches_sdk_question(self):
        self.execute()
        prompts = re.findall(r"```text\n(.*?)\n```", MARKDOWN, re.DOTALL)
        self.assertEqual(prompts, [self.namespace["question"]])

    def test_current_snippets_have_separate_evidence_provenance(self):
        evidence = json.loads((DATA_DIR / "live-evidence.json").read_text(encoding="utf-8"))
        code = [{"id": name, "source": source} for name, source in CELLS.items()]
        digest = hashlib.sha256(json.dumps(code, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(evidence["review_revision"]["code_cells_sha256"], digest)
        self.assertNotEqual(evidence["prior_review_revision"]["code_cells_sha256"], digest)
        self.assertNotEqual(evidence["copy_revision"]["code_cells_sha256"], digest)
        self.assertNotEqual(evidence["publication_candidate_run"]["code_cells_sha256"], digest)
        self.assertEqual(evidence["output_audit"]["status"], "blocked")
        self.assertEqual(evidence["publication_candidate_run"]["independent_output_audit"]
                         ["model_answer_qualification"]["status"], "overstates-source")
        self.assertEqual(evidence["publication_candidate_run"]["independent_output_audit"]
                         ["native_displayed_citation"]["status"], "unverified")
        for name, expected in evidence["canonical_fixture_sha256"].items():
            contents = (DATA_DIR / name).read_text(encoding="utf-8")
            for newline in ("\n", "\r\n"):
                with self.subTest(file=name, checkout_line_endings=repr(newline)):
                    checkout = contents.replace("\n", newline).encode("utf-8")
                    canonical = checkout.decode("utf-8").replace("\r\n", "\n").encode("utf-8")
                    self.assertEqual(hashlib.sha256(canonical).hexdigest(), expected)
        for name, historical_crlf_hash in evidence["fixture_sha256"].items():
            # Preserve the old execution's byte hashes, not claim they used canonical LF.
            historical_bytes = (DATA_DIR / name).read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
            self.assertEqual(hashlib.sha256(historical_bytes).hexdigest(), historical_crlf_hash)
        serialized = json.dumps(evidence)
        self.assertNotRegex(serialized, r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")
        for private_value in ("services.ai.azure.com", "search.windows.net", "blob.fabric.microsoft.com"):
            self.assertNotIn(private_value, serialized)

    def test_customer_and_knowledge_base_fixtures_match_the_source_scope(self):
        with (DATA_DIR / "customers.csv").open(encoding="utf-8", newline="") as handle:
            customers = {row["customer_id"]: row for row in csv.DictReader(handle)}
        with (DATA_DIR / "knowledge-bases.csv").open(encoding="utf-8", newline="") as handle:
            bases = {row["knowledge_base_id"]: row for row in csv.DictReader(handle)}
        identifier = FIXTURE["known_id"]
        ontology = FIXTURE["known"]["ontology"]
        self.assertEqual(set(customers), {identifier})
        self.assertEqual(customers[identifier]["customer_name"], ontology["customer_name"])
        self.assertEqual(set(bases), {base["id"] for base in ontology["knowledge_bases"]})
        for base in ontology["knowledge_bases"]:
            self.assertEqual(bases[base["id"]]["knowledge_base_name"], base["name"])
            self.assertEqual(bases[base["id"]]["customer_id"], identifier)
        for field in ("report_reference", "report_date", "documented_action"):
            self.assertEqual(REPORTS[0][field], FIXTURE["known"]["retrieval"][field])

    def test_complete_sample_scope_reproduces_the_synthetic_report_facts(self):
        with (DATA_DIR / "telemetry-samples.csv").open(encoding="utf-8", newline="") as handle:
            samples = list(csv.DictReader(handle))
        ontology = FIXTURE["known"]["ontology"]
        self.assertEqual(len(samples), ontology["sample_count"])
        self.assertEqual(len({row["telemetry_id"] for row in samples}), len(samples))
        self.assertEqual({row["customer_id"] for row in samples}, {FIXTURE["known_id"]})
        self.assertEqual(Counter(row["status"] for row in samples), {"Healthy": 269, "Degraded": 3, "Throttled": 11})
        for field, expected in (("requests_5m", 4825), ("errors_5m", 111), ("throttled_requests_5m", 30)):
            self.assertEqual(sum(int(row[field]) for row in samples), expected)
        for row in samples:
            self.assertIsNotNone(datetime.fromisoformat(row["event_time_utc"].replace("Z", "+00:00")).tzinfo)
        peak = max(samples, key=lambda row: int(row["p95_latency_ms"]))
        self.assertEqual(peak["telemetry_id"], ontology["highest_p95_sample_id"])
        self.assertEqual(peak["p95_latency_ms"], "4609")
        latest = {
            max((row for row in samples if row["knowledge_base_id"] == base),
                key=lambda row: row["event_time_utc"])["telemetry_id"]
            for base in ("KB-001-01", "KB-001-02")
        }
        self.assertEqual(latest, set(ontology["latest_sample_ids"]))
        self.assertIn(REPORTS[0]["documented_action"], REPORTS[0]["content"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
