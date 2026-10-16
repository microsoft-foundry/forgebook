"""Separate approved prompt/connection writes. Never deploys hosted agents implicitly."""
import argparse
import json
from pathlib import Path

from definitions import digest, prompt_definition, prompt_connection, validate_config
from lab import approval, Client, ServiceFailure, create_absent, private_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["render", "prompt-connection", "prompt-agent"])
    parser.add_argument("--for-operation", choices=["prompt-connection", "prompt-agent"], default="prompt-connection")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    c = json.loads(args.config.read_text(encoding="utf-8"))
    validate_config(c)
    evidence = private_directory(args.evidence_dir)
    operation = args.for_operation if args.operation == "render" else args.operation
    definition = prompt_connection(c) if operation == "prompt-connection" else prompt_definition(c)
    plan = {"operation": operation, "config": c, "definition": definition}
    if args.operation == "render":
        with (evidence / f"{operation}-plan.json").open("x", encoding="utf-8") as file:
            json.dump({"plan": plan, "plan_digest": digest(plan)}, file, indent=2)
        print("Offline prompt plan written privately; no Azure calls")
        return
    if args.approval is None:
        raise PermissionError("BLOCKED: separate exact prompt-operation approval required")
    approval(args.approval, plan)
    from azure.identity import DefaultAzureCredential
    with DefaultAzureCredential() as credential:
        client = Client(credential, evidence)
        if operation == "prompt-connection":
            url = f'https://management.azure.com{c["project_resource_id"]}/connections/{c["prompt_connection"]}?api-version=2025-10-01-preview'
            create_absent(client, url, "https://management.azure.com/.default", definition)
        else:
            endpoint = c["project_endpoint"].rstrip("/")
            scope = "https://ai.azure.com/.default"
            try:
                client.request("GET", f'{endpoint}/agents/{c["prompt_agent"]}?api-version=v1', scope)
            except ServiceFailure as error:
                if error.status != 404:
                    raise
            else:
                raise RuntimeError("Existing agent: stop for exact version reconciliation")
            # Do not retry an ambiguous POST; inspect its private receipt before deciding ownership.
            created = client.request("POST", f"{endpoint}/agents?api-version=v1", scope, definition)
            if not created.get("versions", {}).get("latest"):
                raise RuntimeError("Agent creation acknowledged but version readback is incomplete")
            client.request("GET", f'{endpoint}/agents/{c["prompt_agent"]}?api-version=v1', scope)
    print("Write completed; pin and independently verify the returned version before invocation")


if __name__ == "__main__":
    main()
