# Cookbook Review Rubric

Use this rubric to judge whether a Forgebook recipe is a skill-grade runnable lesson.

## 1. Thesis

Pass when the first paragraph names:

- the problem,
- the intended reader,
- the transferable pattern being taught.

Strong thesis:

> This recipe shows application developers how to turn traces into an agent improvement loop: collect failures, convert them into evals, and use the results to decide what to change next.

Weak thesis:

> This notebook demonstrates the Azure AI Foundry SDK.

Red flags:

- The opening starts with product background.
- The title is doing all the work.
- The reader cannot predict the conclusion from the intro.

## 2. Opinionated defaults

Pass when the recipe makes at least one explicit recommendation and gives a short reason.

Look for:

- "Use X as the default because..."
- "Prefer X over Y when..."
- "Keep Y only for..."
- "Avoid Z unless..."

Fail when the recipe only says "you can use X or Y depending on your needs" without helping the reader choose.

## 3. When / What / How triad

Each technique should be wrapped in:

```markdown
**When to use:** the symptom or scenario
**What it does:** the mechanism in one sentence
**How to adapt:** the knob the reader can turn
```

The triad turns features into reusable skills. Use it for sections that teach a pattern, not for boilerplate setup.

## 4. Code cell discipline

Every code cell should earn its place with:

- a directive before the cell,
- code that is as small as the lesson allows,
- nearby explanation of the important lever,
- visible output, saved artifact, or a reason no output is expected.

Red flags:

- Bare code cells with no surrounding prose.
- Helper setup mixed with business logic.
- Long cells that teach multiple concepts.
- Empty outputs after cells that should produce visible evidence.
- Broad `try/except` blocks that hide failures from readers.

## 5. Before/after evidence

Pass when at least 80% of substantive techniques show paired evidence:

- input image -> output image,
- failing behavior -> fixed behavior,
- baseline metric -> improved metric,
- raw trace -> labeled failure,
- unoptimized prompt -> improved prompt,
- before config -> after config.

Evidence is the recipe's currency. Without before/after evidence, the reader cannot calibrate whether the technique is worth adopting.

## 6. Runnability

Pass when the recipe states:

- required environment variables and API keys,
- runtime and cost estimate,
- one-line dependency setup,
- whether live services are required,
- any cached fallback or sample data behavior,
- cells run top-to-bottom in a clean environment.

Critical failures:

- Hidden credentials or hardcoded tenant IDs.
- Missing package installs.
- Unclear model/deployment names.
- Cells depend on state created out of order.
- Notebook requires local files not committed under `notebooks/data/<slug>/` or `notebooks/media/<slug>/`.

## 7. Scope

Pass when the recipe can be summarized in one sentence starting with "How to...".

Good scope:

> How to evaluate a Foundry agent by turning failed traces into an eval dataset.

Bad scope:

> How to create an agent, add tools, deploy it, monitor it, optimize prompts, and build a dashboard.

Split when:

- the recipe teaches two audiences,
- the setup is longer than the lesson,
- the takeaway artifact is ambiguous,
- a section can be deleted without weakening the core pattern.

## 8. Dev-to-dev voice

Pass when it reads like a senior developer helping another developer:

- direct,
- specific,
- tradeoffs admitted,
- "you" and "we" used naturally,
- no marketing gloss.

Flag corporate or AI-sounding language using `writing-quality.md`.

## 9. Failure modes

Pass when failure modes are first-class content:

```markdown
| Symptom | Likely cause | Fix |
|---|---|---|
| 401 from project client | Wrong credential scope | Run `az login --tenant ...` and confirm project endpoint |
```

Strong recipes name what goes wrong and how to recover. Weak recipes only show the happy path.

## 10. Takeaway artifact

Pass when the reader leaves with something they can lift into their own project:

- prompt skeleton,
- eval dataset schema,
- reusable helper function,
- config template,
- command sequence,
- checklist,
- generated handoff file.

Fail when the only artifact is "the whole notebook."

## Severity guidance

| Severity | Use for |
|---|---|
| Critical | Cannot publish: broken runnability, missing thesis, unsafe secret handling, invalid registry metadata |
| Required | Should fix before publish: missing evidence, unclear prerequisites, no failure modes |
| Optional | Improves quality but does not block publication |
| Nit | Minor phrasing, formatting, or polish |
| Praise | A specific thing worth keeping |

## Anti-rationalization table

| Rationalization | Reality |
|---|---|
| "The code is the thesis." | Code shows what. A thesis explains why this pattern matters. |
| "The defaults are obvious." | Obvious to the author is not obvious to the reader. State the recommendation. |
| "The output proves it worked." | Output without a before state does not prove the technique improved anything. |
| "It runs on my machine." | Runnability means a clean reader environment, not author state. |
| "It is comprehensive." | Comprehensive often means unfocused. One recipe, one transferable pattern. |
| "The notebook is the artifact." | A notebook is a lesson. The artifact is what the reader copies into their project. |
