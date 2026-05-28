---
applyTo: "notebooks/**/*.ipynb,notebooks/media/**,notebooks/data/**,registry.yaml,authors.yaml,tags.yaml"
---

When performing Copilot code review on Forgebook recipe changes, apply the cookbook review standard from `.agents/skills/cookbook-review/`.

Review recipes as runnable lessons, not API demos. A good recipe teaches one transferable Microsoft Foundry pattern with a thesis, evidence, and a takeaway artifact the reader can reuse.

Focus on these gates first:

- Registry entries must include valid `slug`, `path`, `title`, and `authors`; optional tags must exist in `tags.yaml`.
- Authors in `registry.yaml` must exist in `authors.yaml` with `name` and `title`.
- Slugs must match `^[a-z0-9]+(?:-[a-z0-9]+)*$`.
- Notebook paths must start with `notebooks/` and end with `.ipynb`.
- Notebook content must not include site-specific publishing metadata.
- Notebooks should not start with `# H1`; the page title comes from `registry.yaml`.
- Media paths should use `notebooks/media/<slug>/...`; data paths should use `notebooks/data/<slug>/...`.
- Recipe titles should ideally be 60 characters or fewer; descriptions should ideally be 200 characters or fewer for card display.
- Do not approve recipes with hardcoded secrets, tenant-specific values, private endpoints, or unsupported/private APIs.

For changed notebooks, assess:

- Thesis: can the reader tell the pattern being taught in the first 30 seconds?
- Scope: does it teach one reusable decision, not a broad feature tour?
- Runnability: can the notebook run top-to-bottom with documented prerequisites?
- Code cell discipline: each code cell should be introduced, explained, or produce meaningful output.
- Evidence: does the recipe show that the technique worked through outputs, checks, screenshots, or measurable results?
- Failure modes: does it name common errors and recovery paths?
- Takeaway: does the reader leave with a copyable artifact, command, helper, template, or pattern?
- Voice: keep prose direct, practical, and developer-to-developer; flag generic AI-sounding filler.

Use findings with clear severity:

- Blocker: prevents publication, runnability, safety, or correctness.
- Required: should be fixed before merge.
- Advisory: improves clarity, maintainability, or reader experience.

Before suggesting approval, confirm the PR passes the relevant validation command: `cd scripts && npx tsx validate-registry.ts`. For site-impacting changes, also expect `cd site && npm run build`.
