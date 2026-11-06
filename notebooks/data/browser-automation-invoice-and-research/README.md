# Browser automation companion

Run the tutorial in `notebooks\browser-automation-invoice-and-research.ipynb`.
This folder contains its scoped Python package, synthetic fixtures, and setup
helpers. Do not download the notebook without these files.

The pattern is draft-only and read-only: validate inputs in code, expose minimal
browser tools, and compare model claims with actual tool evidence. There is no
production submission, payment, duplicate database, or hard browser network
allowlist.

## Offline setup

From this directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

The notebook supports launch from the checkout root, `notebooks`, or this folder.
Select a kernel with these dependencies installed. Ordinary Run All does not load
`.env`, create Azure clients, provision resources, or make paid calls, even if
`LIVE_APPROVED` is inherited. The fixtures are included; do not regenerate or
overwrite the tutorial notebook.
The scoped `.gitattributes` keeps PDF fixtures binary so Windows line-ending
conversion does not rewrite them.

`bat_recipe` contains the contracts, runner, evidence checks, and workflows.
`scripts` contains local CLI helpers; run their module commands from this folder.
Fixture and instruction paths are anchored to this directory, not the caller's
working directory. Only this directory's ignored `.env` is loaded by live commands.

## Optional authorized cloud setup

Follow the notebook's full prerequisites before executing setup helpers. The
verified route is `BROWSER_MODE=workspace-mcp`, using:

```text
https://<region>.mcp.playwright.microsoft.com/playwrightworkspaces/<workspace-id>/mcp
```

Do not use the WebSocket `/browsers` endpoint. The project connection needs
`RemoteTool`, `ProjectManagedIdentity`, audience
`https://mcp.playwright.microsoft.com`, and workspace ARM metadata. The project's
managed identity needs Playwright Workspace Contributor at that workspace's scope.
The caller separately signs in through Azure CLI to the intended tenant.

After separate authorization, `scripts\create_mcp_connection.ps1` creates a
uniquely named connection and reads its metadata back. It does not grant roles.
Render a fresh synthetic form with `python -m scripts.render_demo <new-directory>`
and host only its HTML using `scripts\host_demo.ps1`. Hosting creates temporary
Azure resources and uploads public synthetic content; approve it separately.
Prior trial hosting is deleted and must not be reused.

Copy `.env.example` to `.env` and replace placeholders. Keep the marker from the
local `hosted-marker.json` out of prompts, instructions, schemas, and URLs. Use
an artifact directory outside the checkout and a valid research start date.
There are no credentials in the managed-identity browser configuration.
Both notebook and CLI reject artifact directories inside the checkout, including
the recipe's own source directory, before creating files or service clients.

## One recommended live sequence

Use either the notebook's deliberately enabled optional cell or the commands
below, not both. Authorize pricing and the bounded run before setting the flag:

```powershell
$env:LIVE_APPROVED = "1"
.\.venv\Scripts\python.exe -m scripts.diagnose_bat probe
# Stop on failure. Continue only after actual marker readback passed.
.\.venv\Scripts\python.exe -m scripts.diagnose_bat validate
.\.venv\Scripts\python.exe -m scripts.summarize_run '<absolute-artifact-directory>'
```

The CLI rejects unapproved live execution before agent creation. The validation
stage also rejects a missing, malformed, or future `RESEARCH_WINDOW_START` before
creating clients, agents, or invoice requests. The marker-only probe does not
require a research window; the combined notebook sequence checks it before
starting either stage.
The validation gate is tied to the current marker, URL, model, connection, and
browser mode.
Validation uses six requests: happy PDF extraction, drafting, three source runs,
and synthesis. It does not rerun the malicious PDF or repeat the historical
failed native-tool diagnostics. The ledger permits eight total requests and at
most two diagnostic probes. A second probe needs a distinct rationale and
remaining authorization; a failed probe is not automatic retry permission.

Run only one process against an artifact directory. Do not delete the ledger to
regain budget. Timeouts and request limits are not a hard billing cap or proof
that remote work stopped. Native/toolbox compatibility helpers remain available
for existing evidence tests; they are not an alternate recommended live path.

## Review and cleanup

Review `happy-draft.json` together with `happy-draft-verification.json`.
Successful execution requires actual tool output containing the current URL,
fresh marker, all nine values, zero submission attempts, and same-task session
closure. Research needs source-scoped navigation, direct quotes/dates or honest
limitations, session closure, and faithful synthesis.

Dated findings include `date_evidence_quote`: a copied publication/update
statement in the same browser output as the direct page URL and content quote.
The verifier compares its date with `published_or_updated`. It accepts labeled
Published, Updated, or Released statements using ISO `YYYY-MM-DD` or an English
month name with day and four-digit year, such as `Updated: September 15, 2026`.
Unrelated event dates or dates from another observation are not proof.
Unsupported or ambiguous date formats require `date_not_verified`, a null
`date_evidence_quote`, and an explicit limitation. A model-claimed date without
matching evidence fails verification; it is not silently corrected. An undated
finding is logged as `no_verified_findings`, not as a verified in-window change.

MCP discovery, pending approval, empty output, or final model prose is not proof.
No findings can be a truthful research outcome, not proof that no change occurred.
The historical manuscript's cloud results are not a fresh execution of this port.

The runner removes only its owned agent version and closes clients. After
review and deletion authorization, use a reviewed created-resource inventory
with `scripts\cleanup_demo.ps1`. Preserve shared resources and existing roles,
and independently verify deletion and any failed remote-session lifecycle.
Keep raw service evidence, identifiers, usage records, and artifacts local.
