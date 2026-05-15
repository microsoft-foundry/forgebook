# Copilot Instructions for Forgebook

A notebook-first AI cookbook publishing platform. Jupyter notebooks are the source of truth; metadata lives in `registry.yaml`.

## Code Review Focus Areas

When reviewing code in this repository:

- **Notebooks are sacred** — Never add site-specific metadata inside notebooks
- **Publishing is explicit** — Authors opt-in via `registry.yaml`, not auto-discovered
- **Credit is intentional** — Authors listed explicitly, not inferred from git history
- Avoid nested ternary operators for readability
- Prefer functional patterns where possible

## Registry Validation

For any changes to `registry.yaml`:
- Slugs must match pattern: `^[a-z0-9]+(?:-[a-z0-9]+)*$` (lowercase letters, numbers, hyphens only)
- Paths must start with `notebooks/` and end with `.ipynb`
- Required fields: `slug`, `path`, `title`, `authors` (at least one with `github` username)
- Optional: `description` (max 500 chars), `date` (YYYY-MM-DD), `tags`
- Tags must exist in `tags.yaml` — unknown tags fail CI
- Authors must exist in `authors.yaml` with `name` and `title`

## Technology Stack

- **Site**: Astro with TypeScript strict mode
- **Styling**: Tailwind CSS v4 (use `@custom-variant` syntax, not legacy config)
- **Components**: Use `.astro` extension
- **Links**: Always use `withBase()` or `import.meta.env.BASE_URL` — base path changes in PR previews
- **Testing**: Playwright with `baseURL: "http://localhost:4321/forgebook"`, role-based selectors

## Validation Commands

Before approving changes, verify these pass:

```bash
# Registry changes
cd scripts && npx tsx validate-registry.ts

# Site changes
cd site && npm run build    # Includes astro check
```

## Notebook Assets

Organize per-recipe in subdirectories matching the registry slug:
```
notebooks/media/<slug>/01-screenshot.png
notebooks/data/<slug>/sample.csv
```

Reference data and images using relative paths from notebooks:
```python
# From notebooks/my-notebook.ipynb (slug: my-notebook)
df = pd.read_csv("data/my-notebook/sample.csv")
```

For full project details, see [AGENTS.md](../AGENTS.md).
