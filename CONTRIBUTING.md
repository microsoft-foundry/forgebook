# Contributing to Forgebook

Thank you for your interest in contributing to Forgebook! This guide will help you publish notebooks quickly.

## Before You Start

**Planning a new recipe?** [Open a New Recipe Proposal](https://github.com/microsoft-foundry/forgebook/issues/new?template=new-recipe.yml) first. This lets maintainers align on scope, audience, and tags before you write code — preventing wasted effort on content that may need significant rework.

For site bug reports, use the [Bug Report template](https://github.com/microsoft-foundry/forgebook/issues/new?template=bug-report.yml).

## PR Workflow

1. **File an issue** — Use the [New Recipe Proposal](https://github.com/microsoft-foundry/forgebook/issues/new?template=new-recipe.yml) template
2. **Create a branch** — Branch from `main`
3. **Add your notebook** — Place it in `notebooks/` and add a `registry.yaml` entry
4. **Validate** — Run `cd scripts && npx tsx validate-registry.ts`
5. **Open a PR** — The PR template will guide you through the checklist
6. **CI checks** — Registry validation and site build run automatically
7. **Preview** — A live preview URL is posted on your PR so you can verify rendering
8. **Review** — `@microsoft-foundry/forgebook-maintainers` will be auto-assigned
9. **Merge** — Once approved, merge to `main` and the site deploys automatically

## Quick Start: Publishing a Notebook

### 1. Create Your Notebook

Add your Jupyter notebook to the `notebooks/` directory:

```
notebooks/
└── my-notebook.ipynb
```

**Important:** Do NOT add any site-specific metadata inside your notebook. Keep notebooks clean and portable.

### 2. Register Your Notebook

Add an entry to `registry.yaml` at the root of the repository:

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
    - inference
```

### 3. Push and Deploy

Push your changes to `main` (or open a PR). The site will automatically build and deploy.

---

## Content Authoring Guidelines

### Markdown Support

Forgebook renders markdown cells with full GitHub Flavored Markdown (GFM) support including:

| Feature | Syntax | Notes |
|---------|--------|-------|
| **Bold** | `**text**` | |
| *Italic* | `*text*` | |
| ~~Strikethrough~~ | `~~text~~` | |
| `Inline code` | `` `code` `` | |
| Tables | `\| col1 \| col2 \|` | Full alignment support |
| Task lists | `- [x] Done` | Renders checkboxes |
| Footnotes | `text[^1]` and `[^1]: note` | Auto-numbered |
| Math (inline) | `$E=mc^2$` | KaTeX rendering |
| Math (block) | `$$\int_0^\infty e^{-x^2}dx$$` | |
| Blockquotes | `> quote` | Nested supported |
| Collapsible | `<details><summary>` | HTML5 details |

### Embedding YouTube Videos

Use iframe embeds for YouTube videos. The site automatically wraps them in responsive containers.

**Recommended Format:**

```html
<iframe width="560" height="315" 
  src="https://www.youtube.com/embed/VIDEO_ID" 
  title="YouTube video player" 
  frameborder="0" 
  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
  allowfullscreen>
</iframe>
```

**Size Requirements (per YouTube):**
- Minimum: 200px × 200px
- Recommended for 16:9: **480px wide × 270px tall** or larger
- The site wraps iframes in `aspect-video` responsive containers

**Useful Parameters:**

| Parameter | Example | Description |
|-----------|---------|-------------|
| `controls` | `?controls=0` | Hide player controls |
| `start` | `?start=120` | Start at 2 minutes |
| `end` | `?end=300` | End at 5 minutes |
| `loop` | `?loop=1&playlist=VIDEO_ID` | Loop single video |
| `rel` | `?rel=0` | Related videos from same channel only |
| `cc_load_policy` | `?cc_load_policy=1` | Show captions by default |

**Trusted Domains:** Only `youtube.com`, `youtube-nocookie.com`, and `vimeo.com` embeds are allowed.

### Embedding Images

**External Images:**

```markdown
![Alt text](https://example.com/image.png)
```

**Notebook Images:**

Store images in `notebooks/media/` and reference them with relative paths:

```markdown
![Alt text](media/my-image.png)
```

From a subdirectory notebook (e.g., `notebooks/examples/foo.ipynb`):

```markdown
![Alt text](../media/my-image.png)
```

**Best Practices:**
- Use descriptive alt text for accessibility
- Prefer SVG for logos and diagrams
- Keep images under 500KB when possible
- Use CDN-hosted images for external URLs

### Code Blocks

Fenced code blocks support syntax highlighting:

````markdown
```python
def hello(name: str) -> str:
    return f"Hello, {name}!"
```
````

Supported languages: Python, JavaScript, TypeScript, JSON, YAML, Bash, SQL, and more.

---

## Registry Schema

### Required Fields

| Field | Pattern | Description |
|-------|---------|-------------|
| `slug` | `^[a-z0-9]+(?:-[a-z0-9]+)*$` | URL-safe identifier |
| `path` | `^notebooks/.*\.ipynb$` | Path from repo root |
| `title` | string | Display title |
| `authors` | array | At least one author |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `description` | string | Max 500 characters |
| `date` | `YYYY-MM-DD` | Publication date |
| `tags` | array | Topic tags (from `tags.yaml`) |

### Author Entry

Each author must have a GitHub username:

```yaml
authors:
  - github: username1
  - github: username2
```

## Author Profiles

All authors must be defined in `authors.yaml` with at least a `name` and `title`:

```yaml
your-username:
  name: "Your Display Name"
  title: "Your Role or Title"
  # Optional fields:
  avatar: "https://custom-avatar-url.png"
  linkedinUrl: "https://linkedin.com/in/yourprofile"
  xUrl: "https://x.com/yourhandle"
```

---

## Validation

Always validate before pushing:

```bash
cd scripts
npx tsx validate-registry.ts
```

Build the site to catch rendering issues:

```bash
cd site
npm run build
```

## Guidelines

1. **Keep notebooks clean** — No site-specific metadata inside notebooks
2. **Clear titles** — Be descriptive but concise
3. **Add descriptions** — Help readers know what to expect
4. **Tag from the allowed list** — Use tags defined in `tags.yaml`; the validator rejects unknown tags
5. **Test locally** — Run notebooks end-to-end before publishing
6. **Clear outputs** — Remove cell outputs before committing
7. **Responsive embeds** — Use recommended iframe sizes
8. **Alt text** — Always add alt text to images

> The [PR template](https://github.com/microsoft-foundry/forgebook/blob/main/.github/pull_request_template.md) includes a full checklist — use it as your final pre-submit check.

### Title and Description

The page header automatically displays the `title` from `registry.yaml`, so **do not start your notebook with an `# H1` title** — it will appear twice on the published page.

Instead, start your notebook with the content itself. An italic subtitle is a nice convention:

```markdown
*A short subtitle or tagline for the notebook*

Your content starts here...
```

The `description` in `registry.yaml` is used for search indexing and the card on the homepage — it doesn't appear on the notebook page itself, so it can differ from any subtitle in your notebook.

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
npm run dev      # Development server
npm run build    # Production build
npm run preview  # Preview production build
```

### Previewing Your Notebook on the Site

After adding your notebook and registry entry, verify it renders correctly:

```bash
cd site
npm run build    # Build with your changes
npm run preview  # Serve at http://localhost:4321/forgebook/
```

Open `http://localhost:4321/forgebook/` and find your notebook card on the homepage. Click through to confirm:

- Title and description display correctly
- Markdown, code blocks, and images render as expected
- Embedded videos and iframes are responsive
- Navigation links work (home, raw markdown, GitHub source)

**Note:** When your PR is opened, CI will automatically build a live preview and post the URL as a comment on your PR — no local setup required. Local preview is optional but recommended for faster iteration.

## Need Help?

- **Questions or problems?** [Open an issue](https://github.com/microsoft-foundry/forgebook/issues/new/choose)
- **Maintainers:** [@microsoft-foundry/forgebook-maintainers](https://github.com/orgs/microsoft-foundry/teams/forgebook-maintainers)
