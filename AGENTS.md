# AGENTS.md

A curated Microsoft Foundry cookbook where approved Microsoft authors publish Jupyter notebook "recipes" and readers learn to build on Microsoft Foundry. Notebooks are the source of truth; all publishing metadata lives in `registry.yaml`.

## Project Structure

```
forgebook/
├── notebooks/           # Jupyter notebooks (source of truth)
│   ├── data/            # Sample datasets, organized per-recipe
│   │   └── <slug>/      # e.g. data/foundry-agent-part-1/
│   ├── media/           # Images referenced in notebooks, organized per-recipe
│   │   └── <slug>/      # e.g. media/foundry-agent-part-1/
│   └── examples/        # Example notebooks
├── registry.yaml        # Publishing metadata — opt-in per notebook
├── authors.yaml         # Author profiles (name + title required)
├── tags.yaml            # Allowed tags — CI rejects unknown tags
├── site/                # Astro static site
│   └── src/
│       ├── components/  # .astro components
│       ├── layouts/     # Page layouts
│       ├── lib/         # Core TS: registry.ts, notebook.ts, telemetry.ts
│       ├── pages/       # Route pages (index, notebook/[slug], RSS)
│       ├── data/        # popular.json (auto-generated, do not edit)
│       └── styles/      # global.css (Tailwind v4)
│   └── tests/           # Playwright e2e tests
├── scripts/             # validate-registry.ts, fetch-popular.ts
└── .github/workflows/   # CI: deploy (also refreshes popular.json), preview
```

## Setup Commands

```bash
# Notebooks
pip install -r requirements.txt
jupyter notebook

# Site
cd site && npm install
npm run dev      # Dev server at localhost:4321/forgebook
npm run build    # Production build (includes astro check)
```

## Validation — Run Before Every Commit

```bash
cd scripts && npx tsx validate-registry.ts   # Registry + tags + authors
cd site && npm run build                      # Full build with type checking
```

## Content Pipeline

### How Notebooks Become Pages
1. Approved author drafts or validates the recipe through the internal authoring workflow, then adds `.ipynb` to `notebooks/` and an entry to `registry.yaml`
2. Content loader ([site/src/lib/registry.ts](site/src/lib/registry.ts)) reads `registry.yaml`, resolves authors from `authors.yaml`
3. Notebook renderer ([site/src/lib/notebook.ts](site/src/lib/notebook.ts)) converts cells to HTML:
   - `notebookjs` + JSDOM + DOMPurify (sanitization)
   - Prism.js highlighting (Python, JS, TS, bash, JSON, YAML)
   - KaTeX for math (`$inline$` and `$$block$$`)
   - `marked` with GFM + footnotes for markdown cells
4. Each notebook gets two routes: `/notebook/<slug>/` (rendered) and `/notebook/<slug>.md` (raw markdown)

### Image and Data Organization
- Organize per-recipe: `notebooks/media/<slug>/` and `notebooks/data/<slug>/`
- Create the subdirectory if it doesn't exist — name it after the registry slug
- Example: `notebooks/media/foundry-agent-part-1/01-project-home.png`
- Served via symlink at `site/public/notebook/media` (subdirectories work automatically)
- Use relative paths in notebooks: `media/<slug>/image.png`
- The renderer rewrites relative paths to absolute URLs using the site base path

### Tags
- Must exist in `tags.yaml` — unknown tags fail both the validator and the content loader
- Two groups: Core Capabilities (agents, inference, evaluation, etc.) and Integrations (langchain, mcp, etc.)

### Popular Notebooks
- `site/src/data/popular.json` is refreshed by `deploy.yml` (on every push to `main`, on the daily 06:00 UTC cron, and on manual dispatch) by querying App Insights click data via OIDC.
- The committed copy is a fallback: if the App Insights query fails, the build logs a warning and reuses the last good `popular.json` so the deploy never breaks on a transient telemetry outage.
- **Never edit popular.json manually** — it gets overwritten on the next deploy.
- Homepage shows "Most Popular" section only when ≥12 recipes exist

## Registry Format

```yaml
- slug: my-notebook           # Required: lowercase, hyphens only (^[a-z0-9]+(?:-[a-z0-9]+)*$)
  path: notebooks/my.ipynb    # Required: must start with notebooks/, end with .ipynb
  title: "My Notebook"        # Required: display title
  authors:                    # Required: at least one
    - github: username        # Must exist in authors.yaml with name + title
  description: "..."          # Optional: max 500 chars
  date: "2026-02-01"          # Optional: YYYY-MM-DD
  tags:                       # Optional: must exist in tags.yaml
    - agents
```

### Authors (authors.yaml)
- Keyed by GitHub username. `name` and `title` are **required** — the build throws if missing
- Avatar falls back to `github.com/<user>.png`; social links optional

## Code Style

### TypeScript/Astro (site/)
- Strict TypeScript mode
- Tailwind CSS v4 — use `@custom-variant` syntax, not legacy config
- Components use `.astro` extension
- Use `withBase()` or `import.meta.env.BASE_URL` for internal links — base path changes in PR previews
- Prefer functional patterns; avoid nested ternaries

### Python (notebooks/)
- Python 3.10+
- Keep notebooks clean — no site-specific metadata inside notebooks
- Don't start notebooks with `# H1` — the page header comes from the registry title
- Organize images in `media/<slug>/` and data in `data/<slug>/` — create the directory if it doesn't exist
- Reference with relative paths: `media/<slug>/01-image.png`, `data/<slug>/sample.csv`

## Testing

- **Framework**: Playwright with 4 device profiles (mobile, android, tablet, desktop)
- **Base URL**: `http://localhost:4321/forgebook`
- **Run**: `cd site && npx playwright test`
- **Patterns**: Use role-based selectors (`getByRole`), not CSS selectors

## CI/CD

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `deploy.yml` | Push to `main`, daily cron, manual | Refresh `popular.json` from App Insights, build, deploy to GitHub Pages |
| `preview.yml` | PR events | Validate, build with PR-scoped base, post preview URL |

## Telemetry

- App Insights via `@microsoft/applicationinsights-web` — connection string from `PUBLIC_APP_INSIGHTS_CONNECTION_STRING`
- No-op in dev (console warning only)
- Tracks: page views, click events, scroll depth, Core Web Vitals
- `window.__telemetry` bridge for inline scripts

## Key Principles

1. **Notebooks are sacred** — No site-specific metadata inside notebooks
2. **Publishing is explicit** — Authors opt-in via `registry.yaml`
3. **Credit is intentional** — Authors listed explicitly, not inferred from git
4. **Tags are curated** — Must exist in `tags.yaml`; propose new tags via PR
5. **Automation removes toil** — CI handles conversion, deployment, and popularity tracking
6. **Publishing is curated while stabilizing** — Recipe publishing is focused on approved Foundry DX / Developer Marketing and product group authors while broader contribution paths mature

## PR Guidelines

- Validate registry before committing
- Run `npm run build` in `site/` to catch build errors
- Keep notebook changes separate from site changes when possible
- Add new notebooks to `registry.yaml` with all required fields
- See [CONTRIBUTING.md](CONTRIBUTING.md) for the full author workflow

## PR Guidelines

- Validate registry before committing
- Run `npm run build` in `site/` to catch build errors
- Keep notebook changes separate from site changes when possible
- Add new notebooks to `registry.yaml` with all required fields
