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

**Repository Images:**

Place images in `site/public/images/` and reference with the base path:

```markdown
![Alt text](/forgebook/images/my-image.png)
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
| `tags` | array | Topic tags |

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
4. **Tag appropriately** — Use existing tags when possible
5. **Test locally** — Run notebooks before publishing
6. **Responsive embeds** — Use recommended iframe sizes
7. **Alt text** — Always add alt text to images

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

## Need Help?

Open an issue on GitHub if you have questions or run into problems.
