"""Create/delete this run's Fabric lakehouse, tables, and ontology with Fabric REST APIs.

Requires azure-identity and requests; authenticates as the signed-in Azure CLI user.
Needs Contributor (or higher) on a workspace backed by an active F2+ or P1+ capacity.
Creates only new items named after IQ_RUN_NAME and never overwrites existing items.

    python prepare-fabric.py create   # prints FABRIC_ONTOLOGY_ID=...
    python prepare-fabric.py delete   # deletes only the items this script recorded

Ontology definition format:
https://learn.microsoft.com/rest/api/fabric/articles/item-management/definitions/ontology-definition
"""

import argparse
import base64
import csv
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

import requests
from azure.identity import AzureCliCredential


FABRIC = "https://api.fabric.microsoft.com/v1"
DATA_DIR = Path(__file__).resolve().parent
TABLES = (
    ("customers.csv", "customer", "Customer", "customer_id"),
    ("knowledge-bases.csv", "knowledgebase", "KnowledgeBase", "knowledge_base_id"),
    ("telemetry-samples.csv", "telemetrysample", "TelemetrySample", "telemetry_id"),
)
STRING_COLUMNS = {
    "telemetry_id", "event_time_utc", "customer_id", "customer_name",
    "customer_domain", "customer_tier", "region", "knowledge_base_id",
    "knowledge_base_name", "index_name", "sku", "status",
}
DOUBLE_COLUMNS = {"storage_gb", "error_rate_pct"}
CREDENTIAL = AzureCliCredential(process_timeout=60)
TOKENS = {}


def call(method, url, body=None, raw=None, ok_404=False):
    onelake = "onelake." in url.split("/")[2]
    scope = "https://storage.azure.com/.default" if onelake else "https://api.fabric.microsoft.com/.default"
    if scope not in TOKENS or TOKENS[scope].expires_on < time.time() + 120:
        TOKENS[scope] = CREDENTIAL.get_token(scope)
    headers = {"Authorization": f"Bearer {TOKENS[scope].token}"}
    if onelake:
        headers["x-ms-version"] = "2021-06-08"
    response = requests.request(method, url, headers=headers, json=body, data=raw, timeout=120)
    if ok_404 and response.status_code == 404:
        return response
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {url.split('?')[0]} -> {response.status_code}: {response.text[:500]}")
    return response


def fabric(method, path, body=None):
    """Call Fabric and wait for long-running operations (202 + Location)."""
    response = call(method, path if path.startswith("https://") else FABRIC + path, body)
    if response.status_code != 202:
        return response.json() if response.content else None
    location = response.headers["Location"]
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        time.sleep(min(max(int(response.headers.get("Retry-After", "10")), 5), 30))
        response = call("GET", location)
        status = response.json().get("status")
        if status in {"Succeeded", "Completed"}:
            return call("GET", location.rstrip("/") + "/result").json()
        if status in {"Failed", "Cancelled"}:
            raise RuntimeError(f"Fabric operation {status}: {response.text[:500]}")
    raise TimeoutError(f"Fabric operation still running: {location}")


def part(path, text):
    return {"path": path, "payload": base64.b64encode(text.encode()).decode(), "payloadType": "InlineBase64"}


def datatype(column):
    if column == "event_time_utc":
        return "dateTime"
    if column in DOUBLE_COLUMNS:
        return "double"
    return "string" if column in STRING_COLUMNS else "int64"


def ontology_definition(display_name, endpoint):
    """Bind each CSV-backed Delta table to an entity type, keyed by its ID column."""
    parts = {}
    refs = ""
    for filename, table, entity, key in TABLES:
        with (DATA_DIR / filename).open(encoding="utf-8", newline="") as handle:
            columns = csv.DictReader(handle).fieldnames
        table_text = f"table {table}\n\tlineageTag: {uuid.uuid4()}\n"
        entity_text = f"entity {entity}\n\tlineageTag: {uuid.uuid4()}\n\tbackingTable: {table}\n\tkeyProperty: {key}\n"
        for column in columns:
            kind = datatype(column)
            table_text += f"\n\tcolumn {column}\n\t\tdataType: {kind}\n\t\tsourceColumn: {column}\n"
            entity_text += (
                f"\n\tproperty {column}\n\t\tdataType: {kind}\n\t\tlineageTag: {uuid.uuid4()}\n"
                f"\n\t\tbackingConfiguration\n\t\t\tvalueColumn: {table}.{column}\n"
            )
        table_text += (
            f"\n\tpartition {table} = entity\n\t\tmode: directLake\n\t\tsource\n"
            f"\t\t\tentityName: {table}\n\t\t\tschemaName: dbo\n\t\t\texpressionSource: DatabaseQuery\n"
        )
        parts[f"tables/{table}.tmdl"] = table_text
        parts[f"entities/{entity}.tmdl"] = entity_text
        refs += f"ref table {table}\nref entity {entity}\n"
    parts.update({
        "relationships.tmdl": (
            "relationship knowledgebase_to_customer\n\tfromColumn: knowledgebase.customer_id\n"
            "\ttoColumn: customer.customer_id\n\n"
            "relationship telemetrysample_to_knowledgebase\n\tfromColumn: telemetrysample.knowledge_base_id\n"
            "\ttoColumn: knowledgebase.knowledge_base_id\n"
        ),
        "entityRelationships.tmdl": (
            "entityRelationship hasKnowledgeBase\n\tfromEntity: Customer\n\ttoEntity: KnowledgeBase\n"
            "\tbackingConfiguration\n\t\trelationship: knowledgebase_to_customer\n\n"
            "entityRelationship hasTelemetrySample\n\tfromEntity: KnowledgeBase\n\ttoEntity: TelemetrySample\n"
            "\tbackingConfiguration\n\t\trelationship: telemetrysample_to_knowledgebase\n"
        ),
        "expressions.tmdl": (
            'expression DatabaseQuery =\n\t\tlet\n\t\t    database = Sql.Database("'
            + endpoint["connectionString"] + '", "' + endpoint["id"] + '")\n\t\tin\n\t\t    database\n'
        ),
        "model.tmdl": "model Model\n\n" + refs + "ref namespace default\n",
        "database.tmdl": "database\n\tcompatibilityLevel: 1000000\n",
        "namespaces/default.tmdl": "namespace default\n\tlineageTag: default\n",
        ".platform": json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "Ontology", "displayName": display_name},
            "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
        }),
    })
    return {"parts": [part(path, text) for path, text in parts.items()]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("create", "delete"))
    args = parser.parse_args()
    run = os.environ["IQ_RUN_NAME"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,40}", run):
        raise ValueError("IQ_RUN_NAME must start with a lowercase letter; max 41 characters.")
    workspace = os.environ["FABRIC_WORKSPACE_ID"]
    base = f"/workspaces/{workspace}"
    state_path = Path(tempfile.gettempdir()) / "forgebook-iq" / run / "fabric-items.json"

    if args.action == "delete":
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["workspace"] != workspace or state["run"] != run:
            raise ValueError("Cleanup workspace/run does not match the recorded inventory.")
        for kind in ("ontology", "notebook", "lakehouse"):
            item = state["items"].get(kind)
            if not item:
                continue
            url = f"{FABRIC}{base}/items/{item['id']}"
            current = call("GET", url, ok_404=True)
            if current.status_code != 404:
                assert current.json()["displayName"] == item["displayName"], "Item was renamed; inspect it manually"
                call("DELETE", url)
            assert call("GET", url, ok_404=True).status_code == 404, f"{kind} still exists"
            del state["items"][kind]
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            print(f"Deleted Fabric {kind} {item['displayName']}")
        return

    started = time.monotonic()
    state = {"run": run, "workspace": workspace, "items": {}}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        print(f"Resuming the recorded attempt: {state_path}")
    state_path.parent.mkdir(parents=True, exist_ok=True)

    def save():
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def create(kind, body):
        if kind in state["items"]:
            return state["items"][kind]
        existing, page = [], fabric("GET", f"{base}/items?type={body['type']}")
        while True:
            existing += page["value"]
            if not page.get("continuationUri"):
                break
            page = fabric("GET", page["continuationUri"])
        if any(i["displayName"] == body["displayName"] for i in existing):
            raise FileExistsError(f"Refusing to overwrite Fabric item {body['displayName']}")
        state["items"][kind] = {**fabric("POST", f"{base}/items", body), "displayName": body["displayName"]}
        save()
        print(f"Created Fabric {kind} {body['displayName']} ({time.monotonic() - started:.0f}s)")
        return state["items"][kind]

    workspace_info = fabric("GET", base)
    capacity = next((c for c in fabric("GET", "/capacities")["value"]
                     if c["id"] == workspace_info.get("capacityId")), None)
    if not capacity or capacity["state"] != "Active" or not capacity["sku"].startswith(("F", "P")) \
            or capacity["sku"] == "FT1":
        raise RuntimeError("The workspace needs an active, paid F2+ or P1+ capacity (not trial).")
    print(f"Capacity {capacity['sku']} is active.")

    lake_name = run.replace("-", "_")
    lake = create("lakehouse", {
        "displayName": lake_name, "type": "Lakehouse", "creationPayload": {"enableSchemas": True},
    })
    details = fabric("GET", f"{base}/lakehouses/{lake['id']}")

    if "notebook" not in state["items"]:
        files = details["properties"]["oneLakeFilesPath"] + "/iq-brief"
        call("PUT", files + "?resource=directory")
        for filename, *_ in TABLES:
            contents = (DATA_DIR / filename).read_bytes()
            url = f"{files}/{filename}"
            call("PUT", url + "?resource=file")
            call("PATCH", url + "?action=append&position=0", raw=contents)
            call("PATCH", url + f"?action=flush&position={len(contents)}")
        print(f"Uploaded CSV files to Files/iq-brief ({time.monotonic() - started:.0f}s)")
        code = (DATA_DIR / "load-fabric-data.py").read_text(encoding="utf-8")
        notebook = {
            "nbformat": 4, "nbformat_minor": 5,
            "metadata": {
                "kernel_info": {"name": "synapse_pyspark"}, "language_info": {"name": "python"},
                "dependencies": {"lakehouse": {
                    "default_lakehouse": lake["id"], "default_lakehouse_name": lake_name,
                    "default_lakehouse_workspace_id": workspace, "known_lakehouses": [{"id": lake["id"]}],
                }},
            },
            "cells": [{"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                       "source": code.splitlines(keepends=True)}],
        }
        create("notebook", {
            "displayName": f"{run}-load", "type": "Notebook",
            "definition": {"format": "ipynb", "parts": [part("notebook-content.ipynb", json.dumps(notebook))]},
        })

    if state.get("load_status") != "Completed":
        if not state.get("job_location"):
            response = call("POST", f"{FABRIC}{base}/items/{state['items']['notebook']['id']}"
                                    "/jobs/instances?jobType=RunNotebook")
            state["job_location"] = response.headers["Location"]
            save()
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            job = call("GET", state["job_location"]).json()
            if job["status"] == "Completed":
                break
            if job["status"] in {"Failed", "Cancelled", "Deduped"}:
                raise RuntimeError(f"Load notebook {job['status']}: {json.dumps(job.get('failureReason'))}")
            time.sleep(20)
        else:
            raise TimeoutError("The load notebook is still running; rerun create to keep waiting.")
        state["load_status"] = "Completed"
        save()
        print(f"Loaded Delta tables dbo.customer, dbo.knowledgebase, dbo.telemetrysample "
              f"({time.monotonic() - started:.0f}s)")

    deadline = time.monotonic() + 600
    while True:
        endpoint = fabric("GET", f"{base}/lakehouses/{lake['id']}")["properties"]["sqlEndpointProperties"]
        if endpoint["provisioningStatus"] == "Success":
            break
        if time.monotonic() > deadline:
            raise TimeoutError("SQL analytics endpoint is still provisioning; rerun create later.")
        time.sleep(15)

    # Fabric IQ reads the tables through the SQL analytics endpoint. Spark-created
    # tables can be missing there until a metadata sync runs, so force one:
    # https://learn.microsoft.com/fabric/data-engineering/sql-analytics-endpoint-metadata-sync
    synced = fabric("POST", f"{base}/sqlEndpoints/{endpoint['id']}/refreshMetadata", {}) or {}
    statuses = {t["tableName"].lower(): t["status"] for t in synced.get("value", [])}
    unsynced = [f"dbo.{table}" for _, table, *_ in TABLES
                if statuses.get(f"dbo.{table}") not in {"Success", "NotRun"}]
    if unsynced:
        raise RuntimeError(f"SQL analytics endpoint did not sync {unsynced}: {statuses}")
    print(f"SQL analytics endpoint lists all 3 tables ({time.monotonic() - started:.0f}s)")

    ontology_name = f"{lake_name}_ontology"
    ontology = create("ontology", {
        "displayName": ontology_name, "type": "Ontology",
        "definition": ontology_definition(ontology_name, endpoint),
    })
    readback = fabric("POST", f"{base}/items/{ontology['id']}/getDefinition")
    paths = {p["path"] for p in readback["definition"]["parts"]}
    missing = {f"entities/{entity}.tmdl" for *_, entity, _ in TABLES} - paths
    if missing:
        raise RuntimeError(f"Ontology read-back is missing {sorted(missing)}")
    print(f"Ontology bound to 3 entity types and 2 relationships ({time.monotonic() - started:.0f}s)")
    print(f"FABRIC_ONTOLOGY_ID={ontology['id']}")
    print(f"Cleanup inventory (keep private): {state_path}")


if __name__ == "__main__":
    main()
