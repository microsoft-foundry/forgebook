"""Exercise the actual notebook functions without calling Azure."""

import ast
import hashlib
import json
import logging
import math
import os
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import httpx
from azure.core.exceptions import AzureError
from azure.search.documents.knowledgebases.models import (
    KnowledgeBaseMessage,
    KnowledgeBaseMessageTextContent,
    KnowledgeBaseRetrievalRequest,
    KnowledgeRetrievalLowReasoningEffort,
    KnowledgeRetrievalMediumReasoningEffort,
    KnowledgeRetrievalOutputMode,
    McpServerKnowledgeSourceParams,
    SearchIndexKnowledgeSourceParams,
)
from openai import OpenAIError

DATA = Path(__file__).resolve().parent
NOTEBOOK = DATA.parents[1] / "foundry-iq-decision-1-gate.ipynb"
DOC = {"id": "guide-1", "title": "Guide", "content": "Documented facts."}


def notebook_functions():
    sys.path.insert(0, str(DATA))
    from gate_helpers import normalize_references, require_complete

    namespace = {
        name: value for name, value in globals().items()
        if name in (
            "json", "logging", "re", "httpx", "AzureError", "OpenAIError",
            "KnowledgeBaseMessage", "KnowledgeBaseMessageTextContent",
            "KnowledgeBaseRetrievalRequest", "KnowledgeRetrievalLowReasoningEffort",
            "KnowledgeRetrievalMediumReasoningEffort", "KnowledgeRetrievalOutputMode",
            "SearchIndexKnowledgeSourceParams", "McpServerKnowledgeSourceParams",
        )
    }
    namespace.update(normalize_references=normalize_references, require_complete=require_complete)
    import os
    namespace["os"] = os
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for cell in notebook["cells"]:
        source = "".join(cell["source"])
        if cell["cell_type"] != "code" or source.startswith("%"):
            continue
        for node in ast.parse(source).body:
            selected_assignment = isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name)
                and target.id in ("SUFFICIENT", "ANSWER_THRESHOLD", "logger")
                for target in node.targets
            )
            if isinstance(node, ast.FunctionDef) or selected_assignment:
                exec(compile(ast.Module(body=[node], type_ignores=[]), str(NOTEBOOK), "exec"), namespace)
    return namespace


class GateTests(unittest.TestCase):
    def setUp(self):
        self.ns = notebook_functions()
        self.retrieve = self.ns["retrieve"] = Mock(return_value={"docs": [DOC], "queries": []})
        self.score = self.ns["score_sufficiency"] = Mock(return_value=0.999)
        self.generate = self.ns["generate_answer"] = Mock(return_value="Documented [guide-1].")
        self.gate = self.ns["answer_or_handoff"]

    def test_boundary_passes_and_generates_once(self):
        self.score.return_value = 0.99
        result = self.gate("Question?", threshold=0.99, retry=True)
        self.assertEqual(result["decision"], "answer")
        self.retrieve.assert_called_once_with("Question?", "low", True)
        self.score.assert_called_once()
        self.generate.assert_called_once()

    def test_below_threshold_hands_off_without_generating(self):
        self.score.return_value = 0.9
        result = self.gate("Question?", threshold=0.99)
        self.assertEqual((result["decision"], result["reason"]), ("handoff", "below_threshold"))
        self.assertEqual(result["sources"], [DOC])
        self.generate.assert_not_called()

    def test_retry_is_bounded_and_rescores_new_evidence(self):
        self.score.side_effect = [0.8, 0.999]
        result = self.gate("Question?", retry=True)
        self.assertEqual(result["decision"], "answer")
        self.assertEqual(self.retrieve.call_args_list[1].args, ("Question?", "medium", True))
        self.assertEqual(self.score.call_count, 2)
        self.generate.assert_called_once()

    def test_two_low_scores_stop_after_two_attempts(self):
        self.score.return_value = 0.1
        result = self.gate("Question?", retry=True)
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(result["decision"], "handoff")
        self.generate.assert_not_called()

    def test_empty_evidence_is_not_scored_or_generated(self):
        self.retrieve.return_value = {"docs": [], "queries": []}
        result = self.gate("Question?")
        self.assertEqual(result["reason"], "no_evidence")
        self.assertIsNone(result["attempts"][0]["p_sufficient"])
        self.score.assert_not_called()
        self.generate.assert_not_called()

    def test_empty_first_attempt_can_retry(self):
        self.retrieve.side_effect = [{"docs": [], "queries": []}, {"docs": [DOC], "queries": []}]
        self.assertEqual(self.gate("Question?", retry=True)["decision"], "answer")
        self.score.assert_called_once()

    def test_retrieval_failure_is_logged_and_does_not_retry(self):
        self.retrieve.side_effect = AzureError("test failure")
        with self.assertLogs("evidence-support", level="ERROR"):
            result = self.gate("Question?", retry=True)
        self.assertEqual(result["reason"], "service_error")
        self.assertEqual(result["error_stage"], "retrieval")
        self.assertEqual(result["error_type"], "AzureError")
        self.retrieve.assert_called_once()
        self.generate.assert_not_called()

    def test_scoring_failure_is_not_an_answer(self):
        self.score.side_effect = httpx.ReadTimeout("test timeout")
        with self.assertLogs("evidence-support", level="ERROR"):
            result = self.gate("Question?", retry=True)
        self.assertEqual(result["reason"], "service_error")
        self.assertEqual(result["error_stage"], "decision")
        self.retrieve.assert_called_once()
        self.generate.assert_not_called()

    def test_generation_failure_does_not_return_an_answer(self):
        self.generate.side_effect = ValueError("invalid citations")
        with self.assertLogs("evidence-support", level="ERROR"):
            result = self.gate("Question?", retry=True)
        self.assertEqual(result["decision"], "handoff")
        self.assertEqual(result["reason"], "answer_validation_failed")
        self.assertEqual(result["error_stage"], "answer")
        self.assertEqual(result["error_type"], "ValueError")
        self.assertEqual(result["sources"], [DOC])
        self.assertIn("validation", result["message"])
        self.retrieve.assert_called_once()
        self.generate.assert_called_once()
        self.assertNotIn("answer", result)

    def test_generation_service_failure_is_not_a_validation_failure(self):
        self.generate.side_effect = OpenAIError("service failure")
        with self.assertLogs("evidence-support", level="ERROR"):
            result = self.gate("Question?", retry=True)
        self.assertEqual(result["reason"], "service_error")
        self.assertEqual(result["error_stage"], "answer")
        self.retrieve.assert_called_once()
        self.generate.assert_called_once()
        self.assertNotIn("answer", result)

    def test_invalid_score_is_not_an_answer_validation_failure(self):
        self.score.side_effect = ValueError("invalid probability")
        with self.assertLogs("evidence-support", level="ERROR"):
            result = self.gate("Question?")
        self.assertEqual(result["reason"], "service_error")
        self.assertEqual(result["error_stage"], "decision")
        self.generate.assert_not_called()

    def test_frozen_bundle_is_scored_and_generated_without_retrieving(self):
        activity = [{"type": "searchIndex", "warning": "bounded evidence"}]
        bundle = {"question": "Question?", "docs": [DOC], "activity": activity}
        result = self.gate("Question?", evidence=bundle)
        self.retrieve.assert_not_called()
        self.score.assert_called_once_with("Question?", bundle["docs"])
        self.generate.assert_called_once_with("Question?", bundle["docs"])
        self.assertIs(result["sources"], bundle["docs"])
        self.assertEqual(result["attempts"][0]["activity"], activity)

    def test_frozen_bundle_rejects_a_different_question(self):
        with self.assertRaises(ValueError):
            self.gate("Different?", evidence={"question": "Original?", "docs": [DOC]})
        self.retrieve.assert_not_called()
        self.score.assert_not_called()

    def test_retry_preserves_both_activity_records(self):
        self.retrieve.side_effect = [
            {"docs": [DOC], "activity": [{"type": "searchIndex", "count": 1}]},
            {"docs": [DOC], "activity": [{"type": "mcpServer", "count": 2}]},
        ]
        self.score.side_effect = [0.1, 0.99]
        result = self.gate("Question?", retry=True)
        self.assertEqual([a["activity"][0]["count"] for a in result["attempts"]], [1, 2])

    def test_invalid_input_raises_explicitly(self):
        for question, threshold in [("", 0.9), ("  ", 0.9), ("Q", -0.1), ("Q", 1.1), ("Q", float("nan")), ("Q", True)]:
            with self.subTest(question=question, threshold=threshold), self.assertRaises(ValueError):
                self.gate(question, threshold=threshold)
        self.retrieve.assert_not_called()


class IntegrationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.ns = notebook_functions()

    def test_configuration_uses_foundry_endpoint(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        configure = next(cell for cell in notebook["cells"]
                         if "configure" in cell.get("metadata", {}).get("tags", []))
        environment = {
            "FOUNDRY_ENDPOINT": "https://example.services.ai.azure.com",
            "DECISION_ENDPOINT": "https://decision.services.ai.azure.com",
            "CHAT_DEPLOYMENT": "test-chat",
            "SEARCH_ENDPOINT": "https://example.search.windows.net",
            "KB_NAME": "example-kb",
            "LEARN_SOURCE": "example-learn",
            "TEAM_SOURCE": "example-team",
        }
        previous_directory = Path.cwd()
        try:
            os.chdir(NOTEBOOK.parent)
            with patch.dict(os.environ, environment, clear=True), \
                    patch("dotenv.load_dotenv"), \
                    patch("azure.identity.DefaultAzureCredential"), \
                    patch("azure.identity.get_bearer_token_provider"), \
                    patch("httpx.Client"), \
                    patch("openai.AzureOpenAI") as chat:
                namespace = {}
                exec(compile("".join(configure["source"]), str(NOTEBOOK), "exec"), namespace)
                self.assertEqual(chat.call_args.kwargs["azure_endpoint"], environment["FOUNDRY_ENDPOINT"])
                self.assertEqual(namespace["chat_model"], environment["CHAT_DEPLOYMENT"])
                namespace["kb"].close()
        finally:
            os.chdir(previous_directory)

    def test_probability_validation_and_exact_state(self):
        self.ns.update(
            credential=Mock(get_token=Mock(return_value=SimpleNamespace(token="test-only"))),
            scope="test-scope", decision_url="https://example.test", decision_model="sample",
        )
        for probability in [True, ".9", None, -0.1, 1.1, float("nan")]:
            response = Mock()
            response.json.return_value = {"answers": {"sufficient": {"noul": probability}}}
            self.ns["http"] = Mock(post=Mock(return_value=response))
            with self.subTest(probability=probability), self.assertRaises(ValueError):
                self.ns["score_sufficiency"]("Q", [DOC])
        response.json.return_value = {"answers": {"sufficient": {"noul": 0.9}}}
        self.assertEqual(self.ns["score_sufficiency"]("Q", [DOC]), 0.9)
        request = self.ns["http"].post.call_args.kwargs["json"]
        self.assertEqual(json.loads(request["state"]), {"question": "Q", "evidence": [DOC]})
        self.assertEqual(request["questions"], {"sufficient": self.ns["SUFFICIENT"]})

    def test_generated_citation_ids_and_truncation(self):
        def reply(text, reason="stop"):
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=text), finish_reason=reason
            )])
        self.ns["chat_model"] = "sample"
        create = Mock()
        self.ns["chat"] = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        for text, reason in [("No citations", "stop"), ("Made up [unknown]", "stop"), ("Cited [guide-1]", "length")]:
            create.return_value = reply(text, reason)
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.ns["generate_answer"]("Q", [DOC])
        create.return_value = reply("Documented [guide-1].")
        self.assertEqual(self.ns["generate_answer"]("Q", [DOC]), "Documented [guide-1].")
        system_prompt = create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("Use role, identity, and permission names exactly as they appear in the evidence.", system_prompt)
        self.assertIn("equivalent, interchangeable, or alternatives", system_prompt)
        self.assertIn("unless a supplied source explicitly establishes that relationship", system_prompt)

    def test_live_retrieval_shape_and_partial_response(self):
        result = SimpleNamespace(
            references=[SimpleNamespace(id="0", type="searchIndex", source_data=DOC)],
            activity=[SimpleNamespace(as_dict=lambda: {"searchIndexArguments": {"search": "planned query"}})],
        )
        kb = self.ns["kb"] = Mock()
        kb.retrieve.side_effect = lambda request, **kwargs: kwargs["cls"](
            SimpleNamespace(http_response=SimpleNamespace(status_code=200)), result, None
        )
        with patch.dict(self.ns["os"].environ, {"LEARN_SOURCE": "learn", "TEAM_SOURCE": "team"}):
            evidence = self.ns["retrieve"]("Question?")
        self.assertEqual(evidence["docs"][0]["id"], "ref-0")
        self.assertEqual(evidence["docs"][0]["document_key"], DOC["id"])
        request = kb.retrieve.call_args.args[0]
        self.assertEqual(request.retrieval_reasoning_effort.kind, "low")
        self.assertEqual(request.max_output_documents, 6)
        self.assertEqual(request.max_output_size, 6000)
        self.assertTrue(request.knowledge_source_params[0].fail_on_error)
        self.assertEqual(request.knowledge_source_params[0].kind, "mcpServer")
        self.assertNotIn("alwaysQuerySource", request.knowledge_source_params[0].as_dict())
        with self.assertRaises(ValueError):
            self.ns["require_complete"](
                SimpleNamespace(http_response=SimpleNamespace(status_code=206)), result, None
            )
        result.activity = [SimpleNamespace(as_dict=lambda: {"error": {"message": "partial"}})]
        with self.assertRaises(ValueError):
            self.ns["require_complete"](
                SimpleNamespace(http_response=SimpleNamespace(status_code=200)), result, None
            )

    def test_historical_replay_is_separate_and_unknown_question_fails(self):
        sys.path.insert(0, str(DATA))
        from replay_retrieval import QUESTIONS, recorded_retrieval
        self.assertTrue(recorded_retrieval(QUESTIONS["q28"]["question"], "low")["docs"])
        with self.assertRaises(ValueError):
            recorded_retrieval("This question has no recorded retrieval", "low")
        self.assertNotIn("recorded_retrieval", self.ns)

    def test_historical_evaluation_does_not_validate_current_rubric(self):
        metadata = json.loads((DATA / "single-call-scores.meta.json").read_text(encoding="utf-8"))
        self.assertNotEqual(metadata["rubric"], self.ns["SUFFICIENT"])
        self.assertEqual(metadata["scores_per_evidence_bundle"], 1)

    def test_threshold_is_selected_from_development_only(self):
        sys.path.insert(0, str(DATA))
        from replay_retrieval import QUESTIONS
        groups = json.loads((DATA / "evaluation-groups.json").read_text(encoding="utf-8"))
        dev_qids = {qid for group in groups.values() if group["split"] == "dev" for qid in group["questions"]}
        scores = [json.loads(line) for line in (DATA / "single-call-scores.jsonl").read_text(encoding="utf-8").splitlines()]
        dev = [row for row in scores if row["qid"] in dev_qids and row["effort"] == "low"]
        candidates = sorted({math.ceil(row["p"] * 100) / 100 for row in dev})
        selected = None
        for candidate in candidates:
            accepted = [row for row in dev if row["p"] >= candidate]
            if accepted and all(any(set(required) <= set(row["doc_ids"])
                                    for required in QUESTIONS[row["qid"]]["evidence_sets"])
                                for row in accepted):
                selected = candidate
                break
        self.assertEqual(selected, 0.96)
        self.assertNotEqual(selected, self.ns["ANSWER_THRESHOLD"])
        self.assertTrue({"q01", "q28", "q35"} <= dev_qids)
        self.assertTrue({"q39", "q42"}.isdisjoint(dev_qids))

    def test_http_error_status_is_preserved(self):
        self.ns["retrieve"] = Mock(return_value={"docs": [DOC]})
        request = httpx.Request("POST", "https://example.test")
        response = httpx.Response(429, request=request)
        self.ns["score_sufficiency"] = Mock(side_effect=httpx.HTTPStatusError(
            "rate limit", request=request, response=response
        ))
        self.ns["generate_answer"] = Mock()
        with self.assertLogs("evidence-support", level="ERROR") as logs:
            result = self.ns["answer_or_handoff"]("Question?")
        self.assertEqual(result["reason"], "service_error")
        self.assertIn("status=429", logs.output[0])
        self.ns["generate_answer"].assert_not_called()

    def test_mcp_and_index_normalize_without_losing_provenance(self):
        references = [
            SimpleNamespace(id="0", type="mcpServer", source_data={
                "title": "Public guidance", "content": "Platform facts",
                "contentUrl": "https://learn.microsoft.com/example",
            }),
            SimpleNamespace(id="1", type="searchIndex", source_data={
                **DOC, "source_path": "team-docs/app-profile.yaml",
                "application": "Atlas support app", "environment": "staging",
            }),
        ]
        docs = self.ns["normalize_references"](references)
        self.assertEqual([doc["id"] for doc in docs], ["ref-0", "ref-1"])
        self.assertEqual(docs[0]["url"], references[0].source_data["contentUrl"])
        self.assertEqual(docs[1]["source_path"], "team-docs/app-profile.yaml")
        self.assertEqual((docs[1]["application"], docs[1]["environment"]),
                         ("Atlas support app", "staging"))
        for invalid in [
            [references[0], references[0]],
            [SimpleNamespace(id="0", type="unknown", source_data=DOC)],
            [SimpleNamespace(id="0", type="mcpServer", source_data={"title": "no text"})],
        ]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.ns["normalize_references"](invalid)

    def test_learn_only_ablation_is_request_local(self):
        kb = self.ns["kb"] = Mock()
        kb.retrieve.return_value = SimpleNamespace(references=[], activity=[])
        with patch.dict(os.environ, {"LEARN_SOURCE": "learn", "TEAM_SOURCE": "team"}):
            self.ns["retrieve"]("Question?", include_team=False)
            before = kb.retrieve.call_args.args[0]
            self.ns["retrieve"]("Question?", include_team=True)
            after = kb.retrieve.call_args.args[0]
        self.assertTrue(before.knowledge_source_params[1].never_query_source)
        self.assertFalse(after.knowledge_source_params[1].never_query_source)
        for request in (before, after):
            self.assertNotIn("alwaysQuerySource", json.dumps(request.as_dict()))

    def test_json_wrapped_learn_result_keeps_the_article_title_and_url(self):
        article = {
            "title": "Managed identity guidance", "content": "Documented platform behavior.",
            "contentUrl": "https://learn.microsoft.com/example#managed-identity",
        }
        reference = SimpleNamespace(id="4", type="mcpServer", source_data={
            "title": "learn-source microsoft_docs_search 1", "content": json.dumps(article),
        })
        doc = self.ns["normalize_references"]([reference])[0]
        self.assertEqual(doc["id"], "ref-4")
        self.assertEqual(doc["title"], article["title"])
        self.assertEqual(doc["content"], article["content"])
        self.assertEqual(doc["url"], article["contentUrl"])

    def test_invalid_json_wrapped_learn_result_fails_explicitly(self):
        for content in ("{broken", '{"title":"Missing content"}'):
            reference = SimpleNamespace(id="0", type="mcpServer", source_data={
                "title": "tool response", "content": content,
            })
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.ns["normalize_references"]([reference])

    def test_pinned_sdk_serializes_the_actual_client_request(self):
        from azure.core.credentials import AzureKeyCredential
        from azure.core.pipeline.transport import HttpResponse, HttpTransport
        from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient

        transport = MagicMock(spec=HttpTransport)
        captured = []

        def send(request, **kwargs):
            captured.append(request)
            response = HttpResponse(request, None)
            response.status_code = 200
            response.headers = {"content-type": "application/json"}
            response.content_type = "application/json"
            response.body = lambda: b'{"response":[],"references":[],"activity":[]}'
            response.json = lambda: json.loads(response.body())
            return response

        transport.send.side_effect = send
        with KnowledgeBaseRetrievalClient(
            endpoint="https://example.search.windows.net", knowledge_base_name="example",
            credential=AzureKeyCredential("unit-test-only"), transport=transport,
        ) as client, patch.dict(os.environ, {"LEARN_SOURCE": "learn", "TEAM_SOURCE": "team"}):
            self.ns["kb"] = client
            self.assertEqual(self.ns["retrieve"]("Q", include_team=False)["docs"], [])
        self.assertEqual(len(captured), 1)
        self.assertIn("api-version=2026-08-01-preview", captured[0].url)
        body = json.loads(captured[0].body)
        self.assertEqual(body["maxOutputSize"], 6000)
        self.assertGreater(body["maxOutputSize"], 5000)
        self.assertNotIn("maxOutputSizeInTokens", body)
        self.assertEqual(body["knowledgeSourceParams"][0]["kind"], "mcpServer")
        self.assertTrue(body["knowledgeSourceParams"][1]["neverQuerySource"])

    def test_saved_live_example_matches_the_current_code_and_team_files(self):
        snapshot = json.loads((DATA / "learn-live-example.json").read_text(encoding="utf-8"))
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        code = ["".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"]
        self.assertEqual(snapshot["execution"]["mode"], "live")
        self.assertEqual(snapshot["execution"]["code_sha256"],
                         hashlib.sha256(json.dumps(code).encode()).hexdigest())
        for name, expected in snapshot["team_files_sha256"].items():
            self.assertEqual(hashlib.sha256((DATA / "team-docs" / name).read_bytes()).hexdigest(),
                             expected)
        self.assertEqual(set(snapshot["supporting_code_sha256"]),
                         {"team_data.py", "setup_learn.py", "gate_helpers.py"})
        for name, expected in snapshot["supporting_code_sha256"].items():
            self.assertEqual(hashlib.sha256((DATA / name).read_bytes()).hexdigest(), expected)
        self.assertEqual(snapshot["rubric"], self.ns["SUFFICIENT"])
        self.assertEqual(snapshot["threshold"], self.ns["ANSWER_THRESHOLD"])
        self.assertEqual({doc["kind"] for doc in snapshot["before"]["docs"]}, {"mcpServer"})
        self.assertEqual({doc["kind"] for doc in snapshot["after"]["docs"]},
                         {"mcpServer", "searchIndex"})
        for comparison in snapshot["comparisons"].values():
            self.assertGreaterEqual(comparison["p"], 0)
            self.assertLessEqual(comparison["p"], 1)
        for label, key in (("Learn only", "before"), ("Learn + team", "after")):
            self.assertEqual(snapshot["comparisons"][label]["sources"],
                             [doc["id"] for doc in snapshot[key]["docs"]])
        for result in [*snapshot["results"].values(), snapshot["retried"]]:
            self.assertNotEqual(result.get("reason"), "service_error")
            expected = "answer" if result["attempts"][-1]["p_sufficient"] >= snapshot["threshold"] else "handoff"
            self.assertEqual(result["decision"], expected)
            self.assertTrue(all("activity" in a for a in result["attempts"]))
        frozen = snapshot["frozen_comparison"]
        self.assertEqual(frozen["evidence"], snapshot["before"])
        self.assertEqual(frozen["gated"]["sources"], frozen["evidence"]["docs"])
        self.assertEqual(frozen["gated"]["attempts"][0]["activity"], frozen["evidence"]["activity"])
        intro = "".join(notebook["cells"][0]["source"])
        displayed = [
            frozen["gated"]["attempts"][-1]["p_sufficient"],
            *(result["attempts"][-1]["p_sufficient"] for result in snapshot["results"].values()),
        ]
        for probability in displayed:
            self.assertIn(f"{probability:.4f}", intro)
        original = json.loads((DATA / "learn-live-example-before-role-mitigation.json").read_text(encoding="utf-8"))
        self.assertEqual(snapshot["threshold"], original["threshold"])
        self.assertEqual(snapshot["threshold"], 0.95)
        self.assertEqual(snapshot["rubric"], original["rubric"])
        self.assertEqual(snapshot["team_files_sha256"], original["team_files_sha256"])
        self.assertEqual(snapshot["results"]["Platform"]["sources"],
                         original["results"]["Platform"]["sources"])
        self.assertEqual(len(snapshot["accepted_answer_reruns"]), 3)
        ledger_path = DATA / snapshot["manual_review"]["path"]
        self.assertEqual(hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
                         snapshot["manual_review"]["sha256"])
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        self.assertEqual(ledger["execution_completed_at_utc"], snapshot["completed_at_utc"])
        checked = [snapshot["results"]["Application context"], *snapshot["accepted_answer_reruns"]]
        self.assertEqual(len(ledger["checks"]), len(checked))
        for result, review in zip(checked, ledger["checks"]):
            self.assertEqual(result["decision"], review["decision"])
            self.assertEqual(result["sources"], snapshot["after"]["docs"])
            self.assertTrue(all(claim["supported"] for claim in review["claims"]))
            for claim in review["claims"]:
                self.assertTrue(set(claim["evidence_ids"]) <= {d["id"] for d in result["sources"]})


class SampleSetupTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(DATA))
        import setup_learn
        self.setup = setup_learn

    def test_deployment_aliases_are_not_model_identities(self):
        objects = self.setup.definitions({
            "prefix": "learn-team-test", "model_endpoint": "https://example.services.ai.azure.com",
            "chat_deployment": "support-chat", "embedding_deployment": "support-embeddings",
        })
        vector = objects["index"].as_dict()["vectorSearch"]["vectorizers"][0]["azureOpenAIParameters"]
        model = objects["kb"].as_dict()["models"][0]["azureOpenAIParameters"]
        self.assertEqual((vector["deploymentId"], vector["modelName"]),
                         ("support-embeddings", "text-embedding-3-small"))
        self.assertEqual((model["deploymentId"], model["modelName"]), ("support-chat", "gpt-4.1"))
        self.assertEqual(len(objects["kb"].as_dict()["knowledgeSources"]), 2)
        mcp = objects["learn"].as_dict()["mcpServerParameters"]
        self.assertEqual(mcp["serverURL"], "https://learn.microsoft.com/api/mcp")
        self.assertEqual([tool["name"] for tool in mcp["tools"]], ["microsoft_docs_search"])

    def test_team_chunks_are_small_stable_and_traceable(self):
        from team_data import load_team_documents
        documents = load_team_documents()
        self.assertEqual(documents, load_team_documents())
        self.assertEqual(len({doc["source_path"] for doc in documents}), 3)
        self.assertEqual(len({doc["id"] for doc in documents}), len(documents))
        for doc in documents:
            self.assertLessEqual(len(doc["content"]), 2000)
            self.assertTrue((DATA / doc["source_path"]).is_file())
            self.assertEqual(doc["environment"], "staging")

    def test_atlas_purpose_and_final_experiment_order(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cells = {cell["id"]: cell for cell in notebook["cells"]}
        order = list(cells)
        sequence = ["af1611b7", "accepted-answer-reruns-note", "accepted-answer-reruns",
                    "frozen-gate-note", "frozen-gate-example",
                    "frozen-gate-observation", "331cc2af", "7a8c1d37",
                    "f37c0e1e", "f269d087", "be4d4281", "next-experiment"]
        positions = [order.index(key) for key in sequence]
        self.assertEqual(positions, sorted(positions))
        profile = (DATA / "team-docs" / "app-profile.yaml").read_text(encoding="utf-8")
        self.assertIn("Summarize submitted IT tickets using a Foundry model", profile)
        intro = "".join(cells["2a5a996b"]["source"])
        self.assertIn("summarize submitted", intro)
        self.assertIn("unanswered question and retrieved evidence", intro)
        opening = intro.split("## What happened")[0]
        self.assertTrue(opening.startswith("A developer asks an internal support agent"))
        self.assertLess(opening.index("Microsoft-Decision-1"), opening.index("hypothesis"))
        self.assertLess(opening.index("hypothesis"), opening.index("**Atlas**"))
        self.assertGreaterEqual(len(opening.split()), 270)
        self.assertLessEqual(len(opening.split()), 300)
        hypothesis = ("Adding an evidence-sufficiency gate would withhold answers when "
                      "application-specific facts were missing, while allowing answers "
                      "when those facts were available.")
        self.assertEqual(opening.count(hypothesis), 1)
        self.assertEqual(opening.count("review packet:"), 1)
        self.assertNotIn("Container Apps", opening)
        self.assertNotIn("system-assigned", opening)
        context = "".join(cells["abd65717"]["source"])
        self.assertIn("system-assigned", context)
        self.assertNotIn("October 20", intro)
        self.assertIn("Ungated answer (excerpt)", intro)
        self.assertIn("Relevant evidence isn't always sufficient",
                      "".join(cells["next-experiment"]["source"]))
        packet = "".join(cells["7a8c1d37"]["source"])
        self.assertIn('results["Missing record"][key]', packet)
        self.assertIn('("question", "reason", "message", "sources")', packet)
        threshold = "".join(cells["2476b75e"]["source"])
        self.assertIn("illustrative threshold of 0.95", threshold)
        self.assertIn("representative labeled cases", threshold)
        lessons = "".join(cells["f37c0e1e"]["source"])
        observations, notes = lessons.split("<details>", 1)
        self.assertEqual(len(re.findall(r"(?m)^[123]\. \*\*", observations)), 3)
        for observation in re.findall(r"(?m)^[123]\. (.+)$", observations):
            self.assertGreaterEqual(len(re.split(r"(?<=[.!?])\s+(?=[A-Z])", observation)), 2)
            self.assertLessEqual(len(re.split(r"(?<=[.!?])\s+(?=[A-Z])", observation)), 3)
        self.assertEqual(notes.count("<summary>Evaluation and security notes</summary>"), 1)
        self.assertNotIn("<details open", lessons)
        self.assertNotIn("I found", observations)
        self.assertIn("authoring assistant's manual", observations)
        self.assertIn("author still needs to verify", observations)
        self.assertIn("Validate threshold stability, not just its value", intro)
        self.assertIn("possible unnecessary handoff", intro)
        self.assertIn("fraction of calls that cross each cutoff", notes)
        self.assertIn("No team answer", notes)
        for content in ("50 representative", "identical retained evidence",
                        "prompt-injection", "Optional: a bounded second retrieval"):
            self.assertIn(content, notes)
        self.assertNotIn("68ac2c6f", cells)
        helper_import = "".join(cells["9e5616db"]["source"])
        self.assertEqual(helper_import, "from gate_helpers import require_complete, normalize_references")

    def test_title_and_unchanged_retrieval_contract(self):
        import yaml
        entries = yaml.safe_load((DATA.parents[2] / "registry.yaml").read_text(encoding="utf-8"))
        entry = next(item for item in entries if item["slug"] == "foundry-iq-decision-1-gate")
        self.assertEqual(entry["title"], "Don't answer yet: an evidence gate with Foundry IQ")
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        source = next("".join(cell["source"]) for cell in notebook["cells"]
                      if cell["id"] == "retrieve-request")
        self.assertIn("max_output_size=6000, max_runtime_in_seconds=90", source)
        self.assertIn("include_activity=True, max_output_documents=6", source)

    def test_creation_requires_exact_plan_approval_before_azure_calls(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory) / "plan.local"
            plan_path.write_text(json.dumps({"config": {"prefix": "learn-team-test"}}), encoding="utf-8")
            with patch.object(self.setup, "PLAN", plan_path), \
                    patch.object(self.setup, "DefaultAzureCredential") as credential:
                with self.assertRaises(ValueError):
                    self.setup.create_sample("not-the-approved-plan")
                credential.assert_not_called()


if __name__ == "__main__":
    unittest.main()
