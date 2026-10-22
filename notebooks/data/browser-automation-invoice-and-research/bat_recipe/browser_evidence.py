from dataclasses import dataclass
import json


NATIVE_CALL_TYPES = {"browser_automation_preview_call", "browser_automation_call"}
NATIVE_OUTPUT_TYPES = {f"{kind}_output" for kind in NATIVE_CALL_TYPES}
CALL_ITEM_TYPES = NATIVE_CALL_TYPES | {"mcp_call"}
TOOL_ITEM_TYPES = CALL_ITEM_TYPES | NATIVE_OUTPUT_TYPES | {
    "mcp_list_tools", "mcp_approval_request",
}
MCP_SERVER_LABEL = "bat_toolbox"
MCP_TOOL_NAME = "browser_automation"
WORKSPACE_MCP_LABEL = "bat_workspace"
WORKSPACE_READ_TOOLS = {
    "create_browser_session", "browser_navigate", "browser_snapshot",
    "browser_find", "close_browser_session",
}
WORKSPACE_DRAFT_TOOLS = WORKSPACE_READ_TOOLS | {"browser_fill_form"}


@dataclass(frozen=True)
class BrowserObservation:
    invocation_id: str
    protocol: str
    output: str


def reconcile_tool_items(stream_items: list[dict], final_items: list[dict]) -> list[dict]:
    items = {}
    for item in stream_items + final_items:
        if item.get("type") not in {"message", "reasoning"}:
            key = item.get("id") or (item.get("type"), item.get("call_id"))
            items[key] = item
    return list(items.values())


def checked_output(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("BAT returned empty or missing tool output; browser outcome unverified")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, dict) and (
        decoded.get("error") or decoded.get("isError") is True
        or decoded.get("status") in ("error", "failed")
    ):
        raise RuntimeError("BAT returned a tool error, not successful browser evidence")
    return value


def browser_observations(evidence: list[dict], *, mode: str | None = None) -> list[BrowserObservation]:
    if any(not isinstance(item, dict) or item.get("type") not in TOOL_ITEM_TYPES
           for item in evidence):
        raise RuntimeError("Malformed or unsupported BAT evidence item")
    if any(item["type"] == "mcp_approval_request" for item in evidence):
        raise RuntimeError("MCP approval is pending; browser execution is not verified")
    native = [item for item in evidence if item["type"] in NATIVE_CALL_TYPES | NATIVE_OUTPUT_TYPES]
    mcp = [item for item in evidence if item["type"] == "mcp_call"]
    if native and mcp:
        raise RuntimeError("Mixed native and MCP evidence is not a verified single browser mode")
    observations = []
    if native:
        if mode in {"toolbox-mcp", "workspace-mcp"}:
            raise RuntimeError("Native evidence does not match the configured MCP mode")
        if any(not isinstance(item.get("call_id"), str) or not item["call_id"] for item in native):
            raise RuntimeError("BAT call/output is missing its correlation ID")
        calls = [item for item in native if item["type"] in NATIVE_CALL_TYPES]
        outputs = [item for item in native if item["type"] in NATIVE_OUTPUT_TYPES]
        call_ids = {item["call_id"] for item in calls}
        output_ids = {item["call_id"] for item in outputs}
        if (len(call_ids) != len(calls) or len(output_ids) != len(outputs)
                or call_ids != output_ids):
            raise RuntimeError("BAT call/output correlation is missing, duplicated or mismatched")
        by_id = {item["call_id"]: item for item in outputs}
        for call in calls:
            result = by_id[call["call_id"]]
            if result["type"] != f"{call['type']}_output":
                raise RuntimeError("BAT call/output protocol types do not match")
            if call.get("status") != "completed" or result.get("status") != "completed":
                raise RuntimeError("BAT call/output did not complete")
            observations.append(BrowserObservation(
                call["call_id"], call["type"], checked_output(result.get("output")),
            ))
    elif mcp:
        if mode == "native-ga":
            raise RuntimeError("MCP evidence does not match the configured native mode")
        ids = set()
        for call in mcp:
            identity = call.get("id")
            if not isinstance(identity, str) or not identity or identity in ids:
                raise RuntimeError("MCP invocation ID is missing or duplicated")
            ids.add(identity)
            label, name = call.get("server_label"), call.get("name")
            if label == MCP_SERVER_LABEL:
                allowed = name == MCP_TOOL_NAME and mode in (None, "toolbox-mcp")
            elif label == WORKSPACE_MCP_LABEL:
                allowed = name in WORKSPACE_DRAFT_TOOLS and mode in (None, "workspace-mcp")
            else:
                allowed = False
            if not allowed:
                raise RuntimeError("MCP call does not target the allowlisted BAT server/tool")
            if call.get("status") != "completed" or call.get("error"):
                raise RuntimeError("MCP browser call failed or did not complete")
            observations.append(BrowserObservation(
                identity, "mcp_call", checked_output(call.get("output")),
            ))
    if not observations:
        raise RuntimeError("Browser Automation Tool was not invoked")
    return observations


def verify_browser_outputs(evidence: list[dict], *, mode: str | None = None) -> int:
    return len(browser_observations(evidence, mode=mode))
