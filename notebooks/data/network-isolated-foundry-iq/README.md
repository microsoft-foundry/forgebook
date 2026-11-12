# Private Foundry IQ lab assets

This is an **offline-authored, unapproved lab draft**, not a verified deployment or a security certification. Start with the accompanying Python notebook. Its default path runs only local regression tests and emits an all-BLOCKED live evidence bundle. Do not use the original PR deployment.

## Supported workflow and provenance

`infra/main.bicep` adapts the Microsoft Foundry skill's Standard BYO-VNet workflow. `infra/standard/` contains only the transitive Bicep dependency closure of official sample 15 at the revision in `provenance.json`; `LICENSE-foundry-samples.txt` preserves its license. The same revision supplies the hosted IQ toolbox sample and frozen `uv.lock`. These are checked-in files, not downloads from a moving branch at execution time.

Reviewed changes: Search S2 (one replica, one partition), semantic ranking, disabled Search local auth, no Foundry/Blob/ACR trusted-service bypass, explicit private source creation, a separate outside runner with NAT, a firewall default route, and outputs instead of author-specific identities. The wrapper exposes **no existing account/resource IDs** and keeps ACR public access disabled. Use a new, approved resource group and prefix. Internal vendored modules retain upstream reuse options; do not invoke them directly for this lab.

**Important support discrepancy:** sample 15's README says tools behind a VNet require sample 19. At the pinned revision, sample 19 uses the same `networkInjections` property and includes a Function example that opens public access. This recipe does not copy that exception. Current [networking architecture](https://learn.microsoft.com/azure/foundry/agents/concepts/agents-networking-deep-dive) describes a network-integrated tool data proxy. Service confirmation and prompt-tool path evidence remain deployment gates, not a guessed Bicep flag.

The source-specific [Blob documentation](https://learn.microsoft.com/azure/search/agentic-knowledge-source-how-to-blob#restrict-ingestion-to-a-private-network-preview) documents private ingestion at **2026-08-01-preview**, selected only at source creation, on S2/S3/L1/L2. The older [general private-link page](https://learn.microsoft.com/azure/foundry/how-to/configure-private-link) has conflicting generated-indexer guidance. Verify the newer contract in the approved region. Never patch a generated indexer, disable vectors, open a public endpoint or enable bypass to work around it.

## Inventory for cost approval

All counts are proposed, not deployed. West US 3 and the example model versions are candidates, not confirmed targets. `cost-inputs.json` is the coordinator's public USD PAYG snapshot, not a quote. Do not compute a misleading total before unresolved usage quantities and meter applicability are reviewed.

| Component | Proposed quantity / SKU | Cost uncertainty or scope |
|---|---|---|
| Foundry account/project | 1 S0 account, 1 Standard project, platform capability hosts | Service-managed runtime and state may add resources |
| Search | 1 S2 replica x 1 partition | $1.344/hour; semantic and agentic retrieval are additional |
| Models | 1 chat + 1 embedding deployment; candidate capacity 10 each | Token use, regional availability and residency SKU require approval |
| Hosted agent | 1 container, candidate 0.5 vCPU / 1 GiB | Actual Foundry Hosted meters: $0.0994/vCPU-hour + $0.0118/GiB-hour; scale/idle billing unverified |
| Storage | 1 Standard_ZRS account; `grid-policies/fixtures/` directory prefix | Hot ZRS: $0.023/GB-month, $0.0625/10K writes, $0.004/10K reads. Three fictional files; state, operations and retention quantities remain unapproved. LRS rates do not apply to this account. |
| Cosmos DB | 1 single-region account and platform-created state containers | Actual generated throughput needs readback; $0.008 per 100 RU/s-hour is not a serverless quote |
| ACR | 1 Premium registry | $1.6666/day plus applicable image storage/transfer |
| Private endpoints | 6 customer endpoints in pinned baseline; 2 Search shared links | Confirm billable link count; $0.01/endpoint-hour plus traffic |
| Network | 2 unpeered VNets; 1 Firewall Standard; 1 route table | Firewall $1.25/hour + separately listed $0.07 capacity-unit-hour + $0.016/GB; confirm scale billing |
| Administration | 1 Bastion Basic; 2 Linux D2s_v5 VMs, no VM public IPs; 2 x 32 GiB Standard SSD | Bastion $0.19/hour; VMs $0.096/hour each; disk/operations extra |
| Outside connectivity | 1 Standard NAT gateway; 1 static public IP | $0.045/hour + $0.045/GB processed; no peering, VPN or private DNS forwarding |
| Public IPs | 3 Standard IPs: Firewall, Bastion, outside NAT | $0.005/IP-hour; management/egress only, not service data-plane exceptions |
| Monitoring | 1 workspace, 1 App Insights, 1 AMPLS; private DNS zones | Ingestion, retention, firewall diagnostics and private query support need review |
| Private DNS | Existing zones in the pinned network modules | $0.50 Private Zone meter (API unit `1`; confirm zone-month billing) + $0.40/million queries at the listed first tier; confirm actual zone count |
| External canary | Task-owned harmless HTTPS/MCP canary, not yet selected | Hosting, TLS, logs and positive-control egress costs missing |

Bound the first test window before approval (suggested planning window: 4 hours, not a spending cap). Plan at least three independent trials per paired ingress surface and three fresh grounded/unrelated pairs for **each** agent. Explicitly budget cold starts, failure injections, Search query planning, embeddings, monitoring and retained resources. Do not automatically retry model calls or increase capacity after a 429. Budget alerts are not hard caps.

## Environments and commands

The notebook uses Python 3.11+ for offline work and Python 3.11+ with `requirements.txt` on the approved in-VNet host. The **hosted image requires Python 3.13** and its own frozen `uv.lock`; do not install that stack into the notebook kernel. Docker Linux/AMD64, uv, Bicep, Azure CLI, azd >=1.27.1 and its `azure.ai.agents` extension >=1.0.0-beta.9 belong on the separately approved execution hosts. No global tooling installation is part of notebook execution.

From the repository root, offline checks are:

```text
python -m unittest discover -s notebooks/data/network-isolated-foundry-iq -p "test_*.py" -v
python notebooks/data/network-isolated-foundry-iq/verify.py --output notebooks/data/network-isolated-foundry-iq/evidence.json
```

Set `BICEP_CLI` to an approved local Bicep executable to enable the compilation regression in `test_assets.py`; otherwise that one test is explicitly skipped. It compiles with `--no-restore` into a temporary local directory and checks the emitted dependency order and role scopes, without Azure access.

Integration executed all eight notebook cells in a fresh Python 3.12.10 Jupyter kernel at the repository root, using nbclient 0.11.0 and ipykernel 7.3.0 with `BICEP_CLI` set. All 37 tests passed without skips. The saved outputs are from that offline run; the hosted Python 3.13 runtime and all Azure operations remain unexecuted.

The verifier's exit **2** is intentional for missing evidence. It cannot certify a deployment from a list of hand-written PASS labels. The current command supports limited readback classifiers; the other matrix controls remain BLOCKED until documented service-specific collectors and human evidence review are available. Unit tests are synthetic and never become live receipts.

### Administrator: before any cloud execution

Confirm tenant/subscription, a **new** exact group/prefix, address-space nonoverlap, region, quotas, preview availability, model/runtime versions and ownership. Review all template-generated RBAC (including inherited roles), state-resource scopes, private image pull and public infrastructure dependencies. Standard setup grants are **not** described as globally minimal. Notebook/test-reader, deployer, Search indexing MI, project MI and actual hosted runtime principal are distinct roles.

Local compilation passes with the session-local official Bicep **0.47.16** (`build infra/main.bicep --no-restore`): zero errors and **27 inherited warnings** confined to `infra/standard/` (14 BCP318, 7 BCP321, 1 unused parameter, 3 unused variables, 2 hardcoded-environment URL warnings). No new suppressions were added. `knowledge-resources.bicep` takes the Standard account/Search/Storage names as string parameters, so its embedding/container/link/grant scopes are available at the start of that nested deployment. The root config uses its exported endpoints and IDs. Compilation is not ARM validation: what-if, region/API support and deployment remain pending. Use `infra/parameters.example.json` as a checklist, not an executable approval. It intentionally contains unresolved values. Resolve `approvedFqdns` from current [hosted networking prerequisites](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-code#firewall-requirements-for-private-virtual-networks) and [Container Apps networking](https://learn.microsoft.com/azure/container-apps/networking). Monitoring also disables public ingestion/query and local authentication; the inherited AppInsights connection stores a runtime-generated connection string, which is not proof of Entra-authenticated telemetry. Verify the actual exporter identity and supported grants before enabling tracing. The template defaults to deny at the firewall; an incomplete allowlist must block deployment, not trigger an allow-all rule. Resolve the required `vmImageVersion` parameter to an exact image version after the approved region is known; the template has no `latest` default.

Review an exact what-if and itemized total before requesting concrete approval. Target-side approval of the two Search shared links is a separate exact-resource action: read the pending IDs on Blob/model resources, verify the requester and target, approve only those run-owned connections. The template deliberately does not auto-approve arbitrary private endpoints. Confirm generated resources and effective DNS/routes rather than assuming ARM success proves reachability.

Read `config` from deployment outputs into a **private** JSON file. Required keys are those in `infra/main.bicep`'s `config` output. Keep project endpoints, resource IDs, principals, role assignments, full request IDs and full raw service receipts outside the checkout, in an existing access-controlled directory. Resolve and inspect credentials interactively; `DefaultAzureCredential` is not itself evidence of which principal was selected.

### In-VNet data-plane host: one source and one KB

`lab.py` has no import-time network actions. `render` writes definitions only. For each later operation, construct `plan_for(config, operation, fixture_directory)`, inspect the exact definitions and fixture digests, and save a separate approval envelope matching `digest(plan)`, with expiration, cost and support review references. `approval.example.json` is deliberately unapproved. The envelope is an operator authorization record, not a cryptographic approval service.

Authenticated HTTP requests never follow redirects: a 3xx response is retained privately and raised as `ServiceFailure`, without replaying a bearer token or changing POST to GET. DNS, timeout, TLS and other transport failures retain one private receipt with a bounded error category, not raw exception text or credentials; none are evidence of isolation and no hidden retry runs.

After approval, run each explicit operation with `--config <private-config> --evidence-dir <private-dir> --approval <private-approval>`:

1. `upload`: upload only the three named fictional files to the existing exact container/prefix with overwrite disabled. The source uses directory prefix `fixtures/`, matching `fixtures/<filename>` uploads and excluding `fixtures-unrelated`. Stop on partial failure; do not blindly rerun or widen the prefix.
2. `source`: verify absence, create the native Blob source with `networkAccessMode: private`, and poll at most 20 times, 30 seconds apart. Never modify generated children. A preexisting source blocks; read/compare before deciding a separately approved reconciliation.
3. Read `createdResources` from source creation/readback. Fetch the **observed** generated indexer, index, skillset and source definitions; do not guess names. Require private execution, the two correctly targeted approved links, fresh completed synchronization, `itemsUpdatesFailed=0`, exact source content and generated vectors. `verify.ingestion` checks the normalized receipt; missing content/vector observation blocks it.
4. `kb`: create one KB with one source, extractive evidence and low reasoning effort. The agents synthesize the final answer. Generated vectors plus [hybrid retrieval](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-retrieve) must be proven by readback, activity and paraphrase/content checks, not inferred from an embedding-model setting. Query-time private embedding access is a separate required control.
5. `retrieve`: issue the supported POST, saving raw response privately. This is billable and separately approved. It is **not** the outside negative test.

The creation-only network setting is not repaired in place. Failure of native private ingestion blocks the recipe; no replacement hand-built index or keyword-only fallback is supplied.

### Prompt agent and hosted agent: same endpoint, different identity

`definitions.py` builds the [documented prompt connection](https://learn.microsoft.com/azure/foundry/agents/how-to/foundry-iq-connect) (`RemoteTool`, `ProjectManagedIdentity`, Search audience, not shared to all) and `PromptAgentDefinition`-compatible payload with only `knowledge_base_retrieve`. The existing recipe already used Responses; this is not a migration from threads. `configure_agents.py` renders the exact connection/agent plans and gates the public-API writes behind separate approval. The definitions require fresh state review before execution. Create one version, read it back and pin the observed version on every invocation. Prompt calls use fresh Conversations/Responses.

`hosted/main.py` is actual hosted Responses source based on the pinned official IQ toolbox sample, not a local direct-retrieve surrogate. `hosted/azure.yaml` consumes a **prebuilt digest-pinned** private ACR image. Build from the in-VNet host with Linux/AMD64, approved Python 3.13 and uv image digests, then push to the private registry. `Dockerfile` intentionally has no unpinned default base image. Set `HOSTED_IMAGE_DIGEST`, `AZURE_AI_MODEL_DEPLOYMENT_NAME` and the **nonempty consumer** `TOOLBOX_ENDPOINT`; the platform injects `FOUNDRY_PROJECT_ENDPOINT`. Never set reserved platform variables yourself.

Use the documented azd agentic-identity connection and toolbox operations, not the prompt connection:

```text
azd ai connection create <hosted-connection> --kind remote-tool --target <same-kb-mcp-endpoint> --auth-type agentic-identity --audience https://search.azure.com/ --output json --no-prompt
azd ai toolbox create <toolbox-name> --from-file <reviewed-toolbox-definition> --output json --no-prompt
```

These are **post-approval operator examples, not commands run by this draft**. `toolbox_definition(config)` produces the exact single-tool JSON (JSON is YAML-compatible). Verify stored `AgenticIdentityToken`, audience, endpoint and allowlist. Do not run the official sample's public provisioning hooks. Initialize azd against the exact new project, select the already-private registry and inspect emitted configuration before `azd deploy grid-hosted`; never run unreviewed `azd up` provisioning. Deploy can assign roles automatically: include those writes in approval. Observe the actual published agent principal and separately approve any Search Index Data Reader, project Foundry User and ACR pull access it needs. Neither project nor blueprint identity proves runtime authorization.

[Private ACR guidance](https://learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent-private-azure-container-registry) separates build/push from runtime pull. Require a cold start from the private registry and the actual invocation surface. The documentation's hosted public-addressability caveat means private account configuration alone cannot PASS hosted ingress.

## Evidence and live matrix

The checked-in `evidence.json` contains **no live results**. `evidence.schema.json` describes its closed, credential-safe projection. `verify.public_bundle` copies only known control names/statuses, not arbitrary strings. This intentionally leaves `live_run` and `publish_ready` false; a future publication converter must review safe run time, source/API/SDK versions, aliases and evidence references before adding them. Raw private receipts must never be copied wholesale into the repository. Do not record tokens, keys, SAS, signed URLs, JWTs or authorization headers even in private evidence.

For ingress pairs, record the same method/path/body digest/API, target alias, token audience, observed principal and equivalent effective permissions on both hosts. A selected credential class is not principal equivalence. Decode only necessary token claims transiently or use supported identity diagnostics; never write the token. Compare claims/role readback privately. Use POST for retrieve, actual MCP protocol calls for MCP, and actual versioned agent invocation paths. Keep independent trial IDs and at least three trials; positive controls must validate content. An off-VNet runner must have no private route/DNS forwarding/VPN and must prove its public egress works.

`verify.paired` currently recognizes only a **correlated Search** `publicNetworkAccess: Disabled` denial with a successful private control. Both receipts must identify Search and match the supported POST endpoint/API contract for `paired-kb-retrieve` or `paired-kb-mcp`, including any query string. Search receipts cannot pass `paired-hosted-ingress`, `paired-prompt-ingress` or `dependent-data-planes`; those adapters remain BLOCKED. 401, RBAC 403, arbitrary 403, 404, 405, DNS/TLS failures, timeouts, 429 and 5xx never independently PASS isolation. A missing observation is BLOCKED or INCONCLUSIVE, never success.

For each agent, run grounded and unrelated questions in fresh conversations/sessions using the observed deployed version. Require correlated actual tool calls, available tool arguments/results, source versions, original citations and support for **each factual claim**. `verify.grounding` demands a source-text quote plus a reviewer evidence reference; citation markers alone fail. Retrieval errors must remain explicit failures, never `I don't know.`. Prompt instructions are not enforcement proof: tests must reject model-only/error-masking behavior.

Egress must be measured from **hosted code** and **prompt tool-service** separately. `hosted/egress_probe.py` sends only a random UUID to `/canary/<nonce>` on an approved task-owned HTTPS origin, without auth or data, and records no URL. In a separately approved test version, set `LAB_CANARY_ORIGIN`, `LAB_CANARY_NONCE` and `LAB_EGRESS_PROBE_APPROVAL=approved-task-owned-canary`; `hosted/main.py` invokes the probe before serving. Run the same probe outside as a positive control. Without the canary configuration the production entry point does not execute the helper. A temporary prompt MCP canary connection requires its own exact tool definition/approval and platform support confirmation; that adapter and canary hosting are **not implemented** in this draft. Absence of received traffic or a timeout alone proves nothing: require correlated firewall/tool-service diagnostics and an allowed private-dependency positive control. If tool-service diagnostics are unavailable, retain BLOCKED.

Authorization-negative tests, dependency outages, invalid inputs, cold starts, three-trial repeatability, route/PE mapping and drift checks remain required. Use only run-owned resources and separately approved failure injection. This harness cannot certify these from configuration booleans.

## Cleanup and residual risks

No cleanup code is provided or executed. Inventory the exact run-owned agent versions/sessions, role assignments, identities, state resources, PEs/DNS, images, VMs, canary and monitors, then obtain separate deletion approval. Follow [Foundry private-network lifecycle guidance](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks). Purge is irreversible and separately authorized. Verify deletion rather than treating an asynchronous request as completion.

Private endpoints restrict paths; they do not place Search, models or all platform components physically inside your VNet. Network controls do not replace RBAC, document authorization, prompt-injection defenses or review of model/data-residency boundaries. This fictional shared corpus has **no per-user document ACL enforcement**. Privileged administrators, approved public identity/control-plane dependencies and preview changes remain part of the assurance boundary.
