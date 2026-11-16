"""Create/delete this run's Search objects from the published synthetic report.

Requires azure-identity and requests; authenticates as the signed-in CLI user.
Does not create services, change IAM, or overwrite pre-existing Search objects.
"""

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from azure.identity import AzureCliCredential


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "delete"))
    args = parser.parse_args()
    run = os.environ["IQ_RUN_NAME"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", run):
        raise ValueError("IQ_RUN_NAME must start with a lowercase letter; max 41 characters.")
    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"].rstrip("/")
    if not re.fullmatch(r"https://[a-z0-9-]+\.search\.windows\.net", endpoint):
        raise ValueError("Use the public-cloud Search service HTTPS endpoint.")
    state_path = Path(tempfile.gettempdir()) / "forgebook-iq" / run / "search-sources.json"
    credential = AzureCliCredential()
    version = "2026-08-01-preview"

    def request(method, path, body=None, *, creating=False):
        headers = {"Authorization": f"Bearer {credential.get_token('https://search.azure.com/.default').token}"}
        if creating:
            headers["If-None-Match"] = "*"
        result = requests.request(method, f"{endpoint}/{path}?api-version={version}",
                                  headers=headers, json=body, timeout=90)
        result.raise_for_status()
        return result.json() if result.content else None

    if args.action == "delete":
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["endpoint"] != endpoint or state["run"] != run:
            raise ValueError("Cleanup endpoint/run does not match the recorded inventory.")
        for path in reversed(state["created"][:]):
            request("DELETE", path)
            state["created"].remove(path)
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            print(f"Deleted {path}")
        return

    if state_path.exists():
        raise FileExistsError(f"Inspect or clean up the prior attempt first: {state_path}")
    data_dir = Path(__file__).resolve().parent
    report = (data_dir / "account-report.md").read_text(encoding="utf-8")
    report_url = os.environ["IQ_REPORT_URL"]
    parsed = urlparse(report_url)
    if parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com":
        raise ValueError("IQ_REPORT_URL must be the public GitHub Raw permalink for account-report.md.")
    published = requests.get(report_url, timeout=60)
    published.raise_for_status()
    if published.text.replace("\r\n", "\n") != report.replace("\r\n", "\n"):
        raise ValueError("The published report differs from this checkout; use its exact commit permalink.")
    index_name, source_name, base_name = f"{run}-reports", f"{run}-source", f"{run}-kb"
    names = (f"indexes/{index_name}", f"knowledgesources/{source_name}", f"knowledgebases/{base_name}")
    for path in names:
        response = requests.get(
            f"{endpoint}/{path}?api-version={version}",
            headers={"Authorization": f"Bearer {credential.get_token('https://search.azure.com/.default').token}"},
            timeout=60,
        )
        if response.status_code != 404:
            response.raise_for_status()
            raise FileExistsError(f"Refusing to overwrite {path}")
    state = {"run": run, "endpoint": endpoint, "created": []}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def create(path, definition):
        request("PUT", path, definition, creating=True)
        state["created"].append(path)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"Created {path}")

    fields = [{"name": "id", "type": "Edm.String", "key": True, "filterable": True}]
    for name in ("customer_id", "report_reference", "report_date", "title", "url", "content"):
        fields.append({
            "name": name, "type": "Edm.String", "retrievable": True,
            "searchable": name not in {"url", "report_date"},
            "filterable": name in {"customer_id", "report_reference", "report_date"},
        })
    create(names[0], {
        "name": index_name, "fields": fields,
        "semantic": {"defaultConfiguration": "brief", "configurations": [{
            "name": "brief", "prioritizedFields": {
                "titleField": {"fieldName": "title"},
                "prioritizedContentFields": [{"fieldName": "content"}],
                "prioritizedKeywordsFields": [{"fieldName": "customer_id"}],
            },
        }]},
    })
    metadata = {
        key: re.search(rf"^{label}: \*\*(.+?)\*\*$", report, re.MULTILINE)[1]
        for key, label in (("customer_id", "Customer ID"), ("report_reference", "Report reference"),
                           ("report_date", "Report date"))
    }
    result = request("POST", f"indexes/{index_name}/docs/index", {"value": [{
        "@search.action": "upload", "id": metadata["report_reference"], **metadata,
        "title": re.search(r"^# (.+)$", report, re.MULTILINE)[1],
        "url": report_url, "content": report,
    }]})
    if not result["value"] or not all(item["status"] for item in result["value"]):
        raise RuntimeError(f"Report upload failed: {result}")
    create(names[1], {
        "name": source_name, "kind": "searchIndex",
        "searchIndexParameters": {
            "searchIndexName": index_name,
            "sourceDataFields": [{"name": name} for name in (
                "customer_id", "report_reference", "report_date", "title", "url", "content",
            )],
        },
    })
    create(names[2], {
        "name": base_name,
        "description": "Public single-customer synthetic report; no sensitive documents.",
        "knowledgeSources": [{"name": source_name}],
        "outputMode": "extractiveData", "retrievalReasoningEffort": {"kind": "minimal"},
    })
    print(f"FOUNDRY_IQ_KB_MCP_URL={endpoint}/knowledgebases/{base_name}/mcp?api-version={version}")
    print(f"Cleanup inventory (keep private): {state_path}")


if __name__ == "__main__":
    main()
