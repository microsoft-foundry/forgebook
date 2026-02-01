# Contributing to Forgebook

Thank you for your interest in contributing to Forgebook! This guide will help you publish notebooks quickly.

## Quick Start: Publishing a Notebook

### 1. Create Your Notebook

Add your Jupyter notebook to the `notebooks/` directory:

```
notebooks/
└── examples/
    └── my-notebook.ipynb
```

**Important:** Do NOT add any site-specific metadata inside your notebook. Keep notebooks clean and portable.

### 2. Register Your Notebook

Add an entry to `registry.yaml` at the root of the repository:

```yaml
- slug: my-notebook
  path: notebooks/examples/my-notebook.ipynb
  title: "My Awesome Notebook"
  description: "A brief description of what this notebook demonstrates."
  date: "2026-02-01"
  authors:
    - github: your-github-username
  tags:
    - getting-started
    - tutorial
```

### 3. Push and Deploy

Push your changes to `main` (or open a PR). The site will automatically build and deploy.

## Registry Fields

### Required Fields

| Field | Description |
|-------|-------------|
| `slug` | URL-safe identifier (lowercase, hyphens allowed) |
| `path` | Path to notebook relative to repo root |
| `title` | Display title |
| `authors` | List of author GitHub usernames |

### Optional Fields

| Field | Description |
|-------|-------------|
| `description` | Short description for previews (max 500 chars) |
| `date` | Publication date (YYYY-MM-DD) |
| `tags` | Topic tags for categorization |

## Multiple Authors

Notebooks can have multiple authors. Order is preserved:

```yaml
authors:
  - github: first-author
  - github: second-author
```

## Author Profiles

By default, author info is fetched from GitHub (name, avatar). To customize, add an entry to `authors.yaml`:

```yaml
your-username:
  name: "Your Display Name"
  website: "https://your-website.com"
  avatar: "https://custom-avatar-url.png"
```

## Validation

Before pushing, validate your registry entry:

```bash
cd scripts
npx tsx validate-registry.ts
```

## Guidelines

1. **Keep notebooks clean** — No site-specific metadata inside notebooks
2. **Clear titles** — Be descriptive but concise
3. **Add descriptions** — Help readers know what to expect
4. **Tag appropriately** — Use existing tags when possible
5. **Test locally** — Run notebooks before publishing

## Local Development

### Running Notebooks

```bash
pip install -r requirements.txt
jupyter notebook
```

### Building the Site

```bash
cd site
npm install
npm run dev
```

## Need Help?

Open an issue on GitHub if you have questions or run into problems.
