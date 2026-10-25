"""Reference normalization for the Foundry IQ evidence-gate recipe."""

import json


def require_complete(pipeline_response, result, _headers):
    if pipeline_response.http_response.status_code != 200:
        raise ValueError("Incomplete knowledge base response")
    if any(activity.as_dict().get("error") for activity in result.activity or []):
        raise ValueError("Knowledge base activity reported an error")
    return result


def normalize_references(references) -> list[dict]:
    docs = []
    for ref in references or []:
        if ref.type not in ("mcpServer", "searchIndex"):
            raise ValueError(f"Unsupported reference type: {ref.type}")
        data = ref.source_data
        if (ref.type == "mcpServer" and isinstance(data, dict)
                and isinstance(data.get("content"), str) and data["content"].lstrip().startswith("{")):
            data = json.loads(data["content"])
        if not isinstance(data, dict) or any(
            not isinstance(data.get(key), str) or not data[key].strip()
            for key in ("title", "content")
        ) or not isinstance(ref.id, str) or not ref.id.strip():
            raise ValueError("Reference must include an id and source title/content")
        docs.append({
            "id": f"ref-{ref.id}", "title": data["title"], "content": data["content"],
            "kind": ref.type, "source_path": data.get("source_path"),
            "url": data.get("contentUrl"), "document_key": data.get("id"),
            "application": data.get("application"), "environment": data.get("environment"),
        })
    if len({doc["id"] for doc in docs}) != len(docs):
        raise ValueError("Duplicate citation reference IDs")
    return docs
