# Contributing to Forgebook

Thank you for your interest in contributing! This guide will help you publish notebooks quickly.

## Before You Start

**Planning a new recipe?** [Open a New Recipe Proposal](https://github.com/microsoft-foundry/forgebook/issues/new?template=new-recipe.yml) first so maintainers can align on scope before you write code.

For site bugs, use the [Bug Report template](https://github.com/microsoft-foundry/forgebook/issues/new?template=bug-report.yml).

## Adding a Notebook

1. Add your Jupyter notebook to `notebooks/`
2. Add an entry to `registry.yaml`:
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
3. Add yourself to `authors.yaml`:
   ```yaml
   your-github-username:
     name: "Your Display Name"
     title: "Your Role or Title"
   ```
4. Validate and open a PR:
   ```bash
   cd scripts && npx tsx validate-registry.ts
   ```

CI runs registry validation and site build automatically. A live preview URL is posted on your PR.

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
- **Store images in `notebooks/media/`** — reference with relative paths (`media/image.png`)
- **Test locally** — run notebooks end-to-end before publishing
- **Add descriptions** — help readers know what to expect on the homepage card
- **Use tags from `tags.yaml`** — the validator rejects unknown tags

## Need Help?

[Open an issue](https://github.com/microsoft-foundry/forgebook/issues/new/choose) or reach out to [@microsoft-foundry/forgebook-maintainers](https://github.com/orgs/microsoft-foundry/teams/forgebook-maintainers).
