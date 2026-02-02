# AGENTS.md

A notebook-first AI cookbook publishing platform. Jupyter notebooks are the source of truth; metadata lives in `registry.yaml`.

## Project Structure

```
forgebook/
├── notebooks/          # Jupyter notebooks (source of truth)
├── registry.yaml       # Publishing metadata for notebooks
├── authors.yaml        # Optional author profile overrides
├── site/               # Astro static site
│   └── src/
│       ├── components/ # Astro components
│       ├── layouts/    # Page layouts
│       ├── lib/        # TypeScript utilities
│       └── pages/      # Route pages
└── scripts/            # Validation tooling
```

## Setup Commands

### Python (Notebooks)

```bash
pip install -r requirements.txt
jupyter notebook
```

### Site Development

```bash
cd site
npm install
npm run dev      # Start dev server
npm run build    # Production build
```

## Validation

Always validate registry changes before committing:

```bash
cd scripts
npx tsx validate-registry.ts
```

## Code Style

### TypeScript/Astro (site/)
- Strict TypeScript mode enabled
- Tailwind CSS v4 for styling
- Use functional patterns where possible
- Components use `.astro` extension

### Python (notebooks/)
- Python 3.10+
- Keep notebooks clean—no site-specific metadata inside notebooks
- Run and test notebooks before publishing

## Registry Format

Entries in `registry.yaml` follow this structure:

```yaml
- slug: my-notebook           # Required: URL-safe identifier
  path: notebooks/my.ipynb    # Required: Path from repo root
  title: "My Notebook"        # Required: Display title
  authors:                    # Required: At least one author
    - github: username
  description: "..."          # Optional: Max 500 chars
  date: "2026-02-01"          # Optional: YYYY-MM-DD
  tags:                       # Optional: Topic tags
    - tutorial
```

### Slug Format
- Lowercase letters, numbers, hyphens only
- Pattern: `^[a-z0-9]+(?:-[a-z0-9]+)*$`

### Path Format
- Must start with `notebooks/` and end with `.ipynb`

## Testing Instructions

1. Validate registry: `cd scripts && npx tsx validate-registry.ts`
2. Build site: `cd site && npm run build`
3. Check for TypeScript errors: `cd site && npx astro check`

## Key Principles

1. **Notebooks are sacred** — No site-specific metadata inside notebooks
2. **Publishing is explicit** — Authors opt-in via registry.yaml
3. **Credit is intentional** — Authors listed explicitly, not inferred
4. **Automation removes toil** — CI handles conversion and deployment

## PR Guidelines

- Validate registry before committing
- Run `npm run build` in `site/` to catch build errors
- Keep notebook changes separate from site changes when possible
- Add new notebooks to `registry.yaml` with all required fields
