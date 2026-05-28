# Contributing to Forgebook

Forgebook is currently operating as a curated Microsoft-authored cookbook for Microsoft Foundry. During this initial phase, recipe publishing is focused on approved contributors from Foundry Developer Experience / Developer Marketing and the Foundry product group, including PM and engineering.

This lets us establish the content bar, review process, recipe format, and publishing workflow before broader contribution paths are considered. External feedback on existing recipes and site issues is still useful; recipe proposal intake may expand as the cookbook matures.

If you are an approved Microsoft Forgebook author, this guide will help you prepare and publish notebook recipes.

## Before You Start

**Planning a new recipe?** Follow the internal authoring workflow, then [open an Internal Recipe Proposal](https://github.com/microsoft-foundry/forgebook/issues/new?template=new-recipe.yml) so maintainers can align on scope before you write code.

For site bugs, use the [Bug Report template](https://github.com/microsoft-foundry/forgebook/issues/new?template=bug-report.yml).

## Adding a Notebook

1. Draft or validate the recipe using the internal authoring workflow
2. Add your Jupyter notebook to `notebooks/`
3. Add an entry to `registry.yaml`:
   ```yaml
   - slug: my-notebook
     path: notebooks/my-notebook.ipynb
     title: "My Awesome Notebook"
     description: "A brief description of what this notebook demonstrates."
     date: "2026-02-01"
     authors:
       - github: your-github-username
     tags:
       - agents
   ```
4. Confirm your approved author profile exists in `authors.yaml`:
   ```yaml
   your-github-username:
     name: "Your Display Name"
     title: "Your Role or Title"
   ```
5. Validate and open a PR:
   ```bash
   cd scripts && npx tsx validate-registry.ts
   ```

CI runs registry validation and site build automatically. A live preview URL is posted on your PR.

Recipe PRs should include review from the relevant Foundry DX, PM, or engineering owner for technical accuracy and product positioning.

## Registry Schema

| Field | Required | Description |
|-------|----------|-------------|
| `slug` | Yes | URL-safe identifier (`^[a-z0-9]+(?:-[a-z0-9]+)*$`) |
| `path` | Yes | Path from repo root (`notebooks/*.ipynb`) |
| `title` | Yes | Display title |
| `authors` | Yes | At least one `- github: username` entry |
| `description` | No | Max 500 characters |
| `date` | No | Publication date (`YYYY-MM-DD`) |
| `tags` | No | Topic tags from `tags.yaml` |

## Notebook Guidelines

- **No site metadata in notebooks** — keep them clean and portable
- **Don't start with `# H1`** — the page header comes from `registry.yaml`'s `title`; starting with H1 duplicates it
- **Store images in `notebooks/media/<slug>/`** — reference with relative paths (`media/<slug>/image.png`)
- **Store data in `notebooks/data/<slug>/`** — reference with relative paths (`data/<slug>/sample.csv`)
- **Test locally** — run notebooks end-to-end before publishing
- **Add descriptions** — help readers know what to expect on the homepage card
- **Use tags from `tags.yaml`** — the validator rejects unknown tags
- **No secrets or tenant-specific values** — use environment variables and placeholders

## Review Expectations

Before requesting review, confirm that the recipe:

- Teaches a practical Microsoft Foundry scenario rather than duplicating product documentation
- Uses supported public APIs, SDKs, model names, and portal flows
- Has clear prerequisites, setup steps, and expected outcomes
- Includes useful explanations without adding site-specific metadata to the notebook
- Uses approved author metadata and curated tags
- Keeps assets in slug-specific `notebooks/media/` or `notebooks/data/` folders

## Need Help?

For recipe scope, publishing workflow, or review questions, reach out to [@microsoft-foundry/forgebook-maintainers](https://github.com/orgs/microsoft-foundry/teams/forgebook-maintainers). For issues with an existing recipe or the site, [open an issue](https://github.com/microsoft-foundry/forgebook/issues/new/choose).
