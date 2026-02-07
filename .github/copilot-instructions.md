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

## Technology Stack

- **Site**: Astro with TypeScript strict mode
- **Styling**: Tailwind CSS v4 (use `@custom-variant` syntax, not legacy config)
- **Components**: Use `.astro` extension
- **Testing**: Playwright with `baseURL: "http://localhost:4321/forgebook"`

## Validation Commands

Before approving changes, verify these pass:

```bash
# Registry changes
cd scripts && npx tsx validate-registry.ts

# Site changes
cd site && npm run build    # Includes astro check
```

## Project Layout

```
forgebook/
├── notebooks/          # Jupyter notebooks (source of truth)
│   ├── data/           # Sample datasets for notebooks
│   └── media/          # Images referenced in notebooks
├── registry.yaml       # Publishing metadata
├── authors.yaml        # Optional author profile overrides
├── site/               # Astro static site
│   └── src/
│       ├── components/ # Astro components
│       ├── layouts/    # Page layouts
│       ├── lib/        # TypeScript utilities
│       └── pages/      # Route pages
└── scripts/            # Validation tooling
```

## Notebook Assets

Reference data and images using relative paths from notebooks:
```python
# From notebooks/my-notebook.ipynb
df = pd.read_csv("data/sample.csv")

# From notebooks/examples/hello-world.ipynb
df = pd.read_csv("../data/sample.csv")
```
