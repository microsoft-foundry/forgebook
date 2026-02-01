# Forgebook

A notebook-first AI cookbook publishing platform.

## Overview

Forgebook is a publishing system where Jupyter notebooks are the source of truth. Authors write notebooks, add minimal metadata to `registry.yaml`, and the site is automatically built and deployed.

## Quick Start

### For Notebook Authors

1. Create your notebook in `notebooks/`
2. Add an entry to `registry.yaml`:
   ```yaml
   - slug: my-notebook
     path: notebooks/my-notebook.ipynb
     title: "My Awesome Notebook"
     authors:
       - github: your-username
   ```
3. Push to `main` — the site deploys automatically

### For Consumers

Clone and run notebooks locally:

```bash
git clone https://github.com/your-org/forgebook.git
cd forgebook
pip install -r requirements.txt
jupyter notebook
```

## Repository Structure

```
forgebook/
├── notebooks/          # Jupyter notebooks (source of truth)
├── registry.yaml       # Publishing metadata
├── site/               # Astro static site (for maintainers)
└── requirements.txt    # Python dependencies for notebooks
```

## Philosophy

1. **Notebooks are sacred** — No site-specific metadata inside notebooks
2. **Publishing is explicit** — Authors opt-in via registry.yaml
3. **Credit is intentional** — Authors listed explicitly, not inferred
4. **Automation removes toil** — CI handles conversion and deployment
5. **Speed beats perfection** — Publish quickly, iterate often

## License

MIT
