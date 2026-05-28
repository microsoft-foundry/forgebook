# Review Comment Style

The best review sounds like a teammate, not a tribunal.

## Principles

- Be direct.
- Be evidence-based.
- One finding per bullet.
- Explain why it matters.
- Give a concrete fix.
- Praise one thing that should stay.
- Do not invent findings.
- Do not imply a command was run unless it was actually run.

## Severity labels

| Label | Meaning |
|---|---|
| Critical | Blocks publication |
| Required | Should fix before publishing |
| Optional | Improvement worth considering |
| Nit | Minor polish |
| Praise | Specific positive feedback |

## Finding format

Use this shape:

```markdown
- **Required:** Cell 5 introduces vector search without a When/What/How wrapper. The reader sees the API call but not the decision it teaches. Add three short lines before the cell: when to use vector search, what this query does, and which parameter to adapt.
```

For mechanical checks:

```markdown
- **Critical:** The registry entry uses tag `rag-agents`, but that tag is not listed in `tags.yaml`. Replace it with an existing tag or propose the new tag in a separate PR.
```

For writing:

```markdown
- **Optional:** The opener says "leverage the power of Microsoft Foundry." That reads like marketing copy and does not tell the reader what they will be able to do. Try: "This recipe shows how to evaluate a Foundry agent with a three-question smoke test before running a larger eval."
```

## Avoid

- Multi-issue bullets.
- Vague "improve clarity" comments.
- Style-only blockers.
- "Looks good overall" without evidence.
- Reprinting the whole notebook.
- Fixing prose silently when the user asked for review only.

## Praise rule

Include one specific positive note in every full review. Good praise tells the author what pattern to preserve:

```markdown
- **Praise:** The setup cell keeps clients and output directories separate from the evaluation logic. Keep that separation; it makes the later cells easier to copy into another project.
```
