# Cookbook review: Verify Private Retrieval with Foundry IQ

**Verdict: Revise and resubmit; not publish-ready.** The offline lesson and regression evidence are usable. The live security claims cannot yet be substantiated, and several execution adapters/support questions remain unresolved.

**Upstream Forgebook score: 73/100 across its required ten axes.** The factory's additional Learning objectives axis is advisory for this upstream review and does not change that score.

**Factory score: 78/105 across eleven axes, or 74.3/100 normalized.** Both totals use the original grades below; normalization is not the upstream ten-axis score. No weights or grades were changed to manufacture a 100/100 result. This is an author-performed cookbook-review pass, not an independent security audit.

## Hypothesis and scope

Hypothesis: an expert tutorial for platform engineers. Success means reproducing private retrieval and distinguishing network denials from authorization/application errors across prompt and hosted agents. Confidence: high in the intended lesson; low in unexecuted platform compatibility. Changed-content/publication review covers notebook, registry, author, data assets, official template deltas and saved offline outputs. The original PR deployment is excluded.

## Scorecard

| Axis | Score | Evidence |
|---|---:|---|
| Thesis | 15/15 | First paragraph identifies reader, false-positive problem and paired-control pattern |
| Opinionated defaults | 9/10 | BYO VNet, one native source, hybrid/private requirement, no downgrade; final platform defaults unresolved |
| When / What / How | 9/10 | Explicit triads for boundaries, ingestion, consumer identities and classification |
| Code cell discipline | 9/10 | Eight short Python cells, explanatory prose, genuine saved local outputs; much live logic necessarily in helper assets |
| Before/after evidence | 4/15 | Immutable original classifier reproduction: 5/8 error fixtures falsely passed; corrected suite rejects all eight. No Azure before/after proof |
| Runnability | 4/15 | Clean offline execution succeeds; live target/cost, ARM validation, hosted startup, canary adapter and platform contracts remain blocked |
| Scope | 8/10 | One assurance pattern; infrastructure and two runtimes still make the operator appendix substantial |
| Dev-to-dev voice | 5/5 | Specific decisions and limits; historical assurance claims removed |
| Failure modes | 5/5 | Auth versus network, stale sync, wrong verb, throttling, pull failures and error-masking table |
| Takeaway artifact | 5/5 | Copyable fail-closed verifier, tests, source/KB definitions, private templates and runtime source |
| **Upstream ten-axis total** | **73/100** | Required Forgebook rubric; live evidence and runnability gaps block publication |
| Learning objectives (factory-only advisory) | 5/5 | Three actionable objectives; conclusion maps offline achievements and uncompleted live work explicitly |
| **Factory eleven-axis total** | **78/105** | **74.3/100 normalized**, not the upstream score |

## Blockers and required fixes

- **Blocker:** no separate target/cost/operation approval and no live run. All 17 required live controls remain BLOCKED. Obtain concrete approval, then run both deployed agents, private native ingestion/hybrid embeddings and paired ingress across at least three independent trials. Never replace this with static booleans or unit-test outputs.
- **Blocker:** ARM validation, what-if, region support, effective routing and exact deployment/RBAC deltas remain unverified. A coordinator-supplied session-local official Bicep 0.47.16 compiler exposed 11 BCP120/BCP307 errors in the original wrapper. Moving the dependent resources into a string-parameterized nested module fixes them: local compilation now passes with zero errors. The 27 remaining warnings are inherited from `infra/standard/` (14 BCP318, 7 BCP321, 1 unused parameter, 3 unused variables and 2 hardcoded-environment URL warnings). No new suppressions or guessed resource names were introduced; local compilation is not Azure validation.
- **Blocker:** official sample 15 excludes private tool traffic; sample 19's injection property does not establish a supported delta, and its public Function exception was deliberately not adopted. Reconcile current supported prompt/tool-service networking with the service owner before deployment.
- **Blocker:** actual private hosted ingress, observed agentic identity, private ACR pull/cold start and Entra-authenticated private telemetry are unproven. Run the Python 3.13 frozen adapter and documented azd workflow on the approved host. Capture real version/principal/image/connection/toolbox readbacks.
- **Required:** the CLI evaluates selected normalized readbacks, not the entire live matrix. Non-Search denial adapters, prompt-tool canary hosting/invocation, source-content/vector/hybrid collectors, authorization/failure injection and repeated-run reconciliation need service-contract review and implementation. Do not describe the current harness as an automated end-to-end verifier.
- **Required:** complete the itemized total: NAT/DNS and Hot ZRS usage at the supplied rates, canary hosting, actual state throughput, Firewall capacity-meter applicability, bounded usage, monitoring/retention and resource retention duration. Public unit prices alone are not approval.
- **Required before relying on the hosted preview:** verify the Linux-built SVG and immutable GitHub source URLs after the approved push. Local browser checks cover the HTML/raw Markdown routes and recipe-local SVG; the Windows checkout represents the tracked media symlink as a text file, so only that SVG was copied into generated `dist` for local verification. No tracked site or symlink behavior was changed. The global Open in GitHub action still targets `main`; the recipe supplies an explicit pinned notebook link and clone/checkout instructions instead.

## Adversarial pass

The title no longer says verified. Saved outputs contain only actual local execution and explicit live BLOCKED states. Tests intentionally contain synthetic PASS fixtures to exercise the positive classifier branch; those are not published as Azure results. Source citations require supporting text plus a review reference, not just citation markers. The open adapters and preview documentation conflict are visible in the notebook/runbook. The raw private evidence location remains separate from the closed public projection. There are no fabricated screenshots.

## Mechanical outcomes

| Check | Result | Evidence |
|---|---|---|
| Factory registry / author / curated tags | PASS (author-reported) | `npm run validate`, one recipe, zero registry warnings |
| Upstream registry / author / curated tags | PASS | `npx tsx validate-registry.ts`, 19 recipes, zero warnings |
| Upstream notebook health | PASS | Eight checks, zero failures, zero warnings after saving offline outputs |
| Python source / module closure | PASS (static only) | `test_assets.py`; does not imply Bicep or SDK runtime compatibility |
| Offline regressions | PASS | 37 tests with `BICEP_CLI` set, none skipped; includes original error fixtures, control/service binding, redirect and transport receipts, Blob directory boundary and compiled dependencies |
| Notebook execution | PASS (offline only) | All eight code cells executed in a fresh Jupyter kernel at the repository root; actual outputs saved; nbformat schema validated |
| Public evidence schema | PASS | JSON Schema validation; 17 BLOCKED controls, no observed live timestamp |
| Bicep compilation | PASS (local only) | Official 0.47.16, `--no-restore`; zero errors, 27 inherited vendor warnings |
| ARM validation / what-if | BLOCKED | Cloud approval absent; no ARM operations run |
| Hosted startup / deployment / actual retrieval | BLOCKED | No Python 3.13 runtime/tooling setup or cloud approval |
| Azure mutations / uploads / invocations / cleanup | NOT RUN | Explicit approval boundary maintained |

The factory workflow baseline was `dc808da9901b075bab2d2594b22512ee5164f556`; the corrected export was `e3e1781fde931b34169e441ed66931e836d8ca10`. The validated integration code, data and notebook snapshot is `af2a2e5e6a26ae11f179be37f9cca8d909cf74e2`. Subsequent prose links pin that snapshot without changing its executable cells or helper code. Integration preserved the original axis grades while adding the bounded Python corrections, compiled nested module and SVG fallback. The ten-axis score remains 73/100 and the factory score remains 78/105 because the core live runnability/evidence gaps are unchanged.

The clean integration run used Windows ARM64, Python 3.12.10, nbclient 0.11.0, ipykernel 7.3.0, nbformat 5.11.1, jsonschema 4.26.0 and jupyter-client 8.10.0. The kernel executable was explicitly selected from the ignored worktree-root `.venv`, its working directory was the repository root, and `BICEP_CLI` identified the approved session-local compiler. This is a real kernel run, not the earlier `exec()`-based check. The hosted Python 3.13 runtime was not executed.

Factory authoring initially lacked `tsx` and PyYAML. Integration restored existing locked npm dependencies after missing-tool failures, then restored only notebook-runner validation dependencies after `nbclient` was missing. A deeper virtual environment exceeded Windows path limits; it was removed and recreated at the shorter ignored worktree-root path. No global packages, CLI extensions or dependency manifests were changed. The compiler remains session-local.

## What is working

The before/after classifier reproduction makes the original error concrete. The notebook now has a portable Python-only default path, preserves one KB/two distinct consumer identities, and does not conflate cloud resource configuration with demonstrated controls. The private creation-only ingestion property, actual hosted source, frozen dependencies and explicit no-downgrade rules are worth retaining.
