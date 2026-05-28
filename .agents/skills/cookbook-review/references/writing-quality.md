# Forgebook Writing Quality

Forgebook recipes should read like a senior developer pulling a teammate aside: direct, practical, and opinionated enough to save the reader a decision.

## Voice target

- Audience: developers learning Microsoft Foundry by running code.
- Tone: direct, code-first, technically precise, warm at the edges.
- Style: "Here is the pattern; here is when it breaks; here is what to copy."
- Use "you" and "we" naturally.
- Admit tradeoffs out loud.
- Prefer concrete nouns and verbs over product-marketing abstractions.

## AI-pattern watchlist

Flag these when they appear without real content:

- "delve into"
- "leverage"
- "robust"
- "pivotal"
- "seamlessly"
- "cutting-edge"
- "state-of-the-art"
- "unlock the power/potential"
- "in today's rapidly evolving landscape"
- "it is important to note"
- "it is worth mentioning"
- "comprehensive guide"
- "powerful tool that enables"
- "in conclusion"
- "to summarize"
- "this tutorial has shown"

Preferred replacements:

| Instead of | Prefer |
|---|---|
| leverage | use |
| robust | specific property: retries, typed outputs, isolated eval data |
| seamless | describe the actual integration point |
| unlock | create, build, run, evaluate, deploy |
| it is important to note | state the warning directly |
| in this section we will | delete it or say the action |

## Openers that usually fail

Weak:

> In this notebook, we will explore how Azure AI Foundry can be leveraged to create powerful agentic solutions.

Better:

> This recipe shows how to turn failed agent traces into eval cases so you can decide whether a prompt change actually helped.

Weak:

> Microsoft Foundry provides a robust platform for building intelligent applications.

Better:

> Use this pattern when your agent works in demos but regresses after prompt edits.

## Concision rules

- Delete throat-clearing.
- Replace nominalizations with verbs: "perform an evaluation" -> "evaluate".
- Delete sentences that only announce the next cell.
- Keep markdown cells close to the code they explain.
- Use bullets when the reader needs to scan knobs, prerequisites, or failure modes.

## Markdown rules inside notebooks

- No leading `# H1`.
- Use `##` and `###` for internal structure.
- Do not skip heading levels.
- No decorative emoji in headings.
- Use Markdown links: `[text](url)`.
- Use relative paths for local notebook media and data.

## Review question

For every prose section, ask:

> If I deleted this paragraph, would the reader lose a decision, warning, or technique?

If not, recommend deletion or compression.
