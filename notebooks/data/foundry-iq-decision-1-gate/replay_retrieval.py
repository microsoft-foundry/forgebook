"""Replay recorded Foundry IQ evidence; never substitute it for a failed live call."""

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent


def load_questions() -> dict[str, dict]:
    return {
        question["id"]: question
        for question in (
            json.loads(line)
            for line in (DATA / "questions.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }


def load_documents() -> dict[str, dict]:
    documents = {}
    for path in sorted((DATA / "corpus").glob("*.md")):
        _, front, body = path.read_text(encoding="utf-8").split("---\n", 2)
        metadata = dict(re.findall(r'^(\w+): "?(.*?)"?$', front, re.M))
        documents[metadata["id"]] = {
            "id": metadata["id"],
            "title": metadata["title"],
            "content": f"# {metadata['title']}\n\n{body.strip()}",
        }
    return documents


QUESTIONS = load_questions()
DOCUMENTS = load_documents()
TRACES = {
    (QUESTIONS[row["qid"]]["question"], row["effort"]): row
    for row in (
        json.loads(line)
        for line in (DATA / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    )
}


def recorded_retrieval(question: str, effort: str) -> dict:
    """Return an exact saved question/effort pair, not a new search result."""
    if (question, effort) not in TRACES:
        raise ValueError("No recorded retrieval for this question/effort; use live mode.")
    trace = TRACES[(question, effort)]
    return {
        "docs": [DOCUMENTS[doc_id] for doc_id in trace["doc_ids"]],
        "queries": trace["queries"],
    }
