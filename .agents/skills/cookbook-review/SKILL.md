---
name: cookbook-review
description: Review Microsoft Foundry Forgebook cookbook notebooks for quality, correctness, developer experience, and publication readiness. Use this whenever the user asks to review a notebook, judge a recipe, audit a cookbook entry, check registry.yaml metadata, assess whether a Foundry example is ready to publish, remove AI-sounding cookbook prose, or improve a tutorial/recipe before submission. Triggers on "review this notebook", "is this recipe good", "cookbook quality", "Forgebook review", "check my Foundry notebook", "ready to publish", "audit this recipe", and similar requests even when the user does not explicitly say "skill" or "rubric".
compatibility: Works best in the Forgebook repository with file-read access and Python 3.10+ available for optional health checks.
---

# Cookbook Review Skill

Review Forgebook recipes as runnable lessons, not as API demos. A good recipe teaches one transferable Microsoft Foundry pattern with a thesis, evidence, and a takeaway artifact the reader can reuse tomorrow.

Use this skill in read-only review mode by default. Do not edit notebooks or registry files unless the user explicitly asks you to apply fixes.

## Review contract

Every review should answer:

1. Can the reader run this top-to-bottom?
2. Can the reader tell what pattern they are learning in the first 30 seconds?
3. Does the recipe teach one reusable decision, or does it drift into a feature tour?
4. Is there evidence that the technique worked?
5. Does the reader leave with a copyable artifact, template, command, or pattern?

Load these references as needed:

| Need | Read |
|---|---|
| Full scoring criteria | `references/rubric-detail.md` |
| Forgebook registry, author, tag, media, and notebook rules | `references/forgebook-contract.md` |
| Dev-to-dev voice, banned AI phrases, concision rules | `references/writing-quality.md` |
| How to write findings and severity labels | `references/review-comment-style.md` |
| Final report shape | `assets/review-report-template.md` |

## Intake

Start by identifying the review target:

- **Notebook review**: a `.ipynb` file, notebook diff, or rendered notebook page.
- **Registry review**: a `registry.yaml` entry or cookbook metadata.
- **Publication review**: full PR/content readiness, including notebook, registry, authors, tags, media/data paths, and narrative quality.
- **Writing-only review**: prose voice, AI-isms, structure, and clarity.

If the user did not specify scope, assume **publication review** for new recipes and **changed-content review** for PR diffs.

Before scoring, state a short hypothesis:

```text
Hypothesis: This is a [quickstart/tutorial/deep-dive/demo/reference] for [beginner/intermediate/expert] readers.
Success criterion: After running it, the reader should be able to [do one concrete thing].
Confidence: [high/medium/low] based on [title/imports/sections/registry entry].
```

Ask at most one clarifying question only if the answer would change the verdict. Otherwise proceed with reasonable assumptions and list them in the report.

## Workflow

### Phase 1: Mechanical gates

Check the fast, objective rules first. In the Forgebook repository, use the optional script when possible:

```bash
python .agents/skills/cookbook-review/scripts/recipe-health-check.py <notebook.ipynb> --repo-root .
```

Mechanical gates:

- Registry fields are valid when a registry entry is present.
- Notebook path starts with `notebooks/` and ends with `.ipynb`.
- Slug follows `^[a-z0-9]+(?:-[a-z0-9]+)*$`.
- Authors exist in `authors.yaml` with `name` and `title`.
- Tags exist in `tags.yaml`.
- Notebook does not start with `# H1`; the page title comes from `registry.yaml`.
- Notebook contains no site-specific publishing metadata.
- Media references use `media/<slug>/...`; data references use `data/<slug>/...`.
- Code cells are not bare code dumps: each should be introduced by a directive, explained by nearby prose, or produce meaningful output.

Treat mechanical failures as high-signal. Do not bury them under style feedback.

### Phase 2: Ten-axis recipe score

Score against the ten qualities in `references/rubric-detail.md`. Use the default weights unless the user asks for pass/fail only:

| Axis | Weight |
|---|---:|
| Thesis | 15 |
| Opinionated defaults | 10 |
| When / What / How triad | 10 |
| Code cell discipline | 10 |
| Before/after evidence | 15 |
| Runnability | 15 |
| Scope | 10 |
| Dev-to-dev voice | 5 |
| Failure modes | 5 |
| Takeaway artifact | 5 |

Verdict tiers:

| Score | Verdict |
|---:|---|
| 90-100 | Publish |
| 75-89 | Publish after fixes |
| 60-74 | Revise and resubmit |
| <60 | Not ready |

Override rule: a recipe with a critical runnability failure, missing thesis, or no reproducible evidence cannot receive "Publish" even if the weighted score is high.

### Phase 3: Adversarial pass

Before finalizing, run a skeptical pass:

- Is the thesis just a feature description?
- Are defaults actually opinionated, or hedged with "you can also"?
- Are outputs committed but not reproducible?
- Is the before/after evidence specific enough to calibrate the improvement?
- Are failure modes named as first-class content?
- Is the takeaway a copyable artifact, or merely "the notebook"?

Use this pass to catch false positives, not to invent issues.

### Phase 4: Report

Use the template in `assets/review-report-template.md`. Keep findings direct and evidence-based:

- Lead with the verdict.
- Separate blockers from advisory improvements.
- Give one finding per bullet.
- For each required fix, include why it matters and what to change.
- Include at least one thing the recipe already does well.

## Modes

Support these scope flags if the user uses them:

- `--registry-only`: validate only registry, authors, tags, slug, and paths.
- `--writing-only`: review thesis, structure, voice, AI-isms, and takeaway artifact.
- `--mechanical-only`: run objective checks and skip subjective scoring.
- `--score-only`: return only scorecard and verdict.
- `--fix-plan`: return a prioritized patch plan without editing files.

## Approval standard

Approve when the recipe clearly increases the cookbook's value and a reader can reproduce the lesson. Do not require perfection. Do not rubber-stamp. The bar is: "Would a Microsoft Foundry engineer share this as the reference example in a teammate's chat?"
