# Forgebook

**Your cookbook for building AI with [Microsoft Foundry](https://learn.microsoft.com/azure/foundry).**

Forgebook is a curated collection of runnable Jupyter notebook recipes, hands-on guides, and examples for building agents, model inference workflows, and multimodal apps with Microsoft Foundry.

> ✨ Browse recipes at **[microsoft-foundry.github.io/forgebook](https://microsoft-foundry.github.io/forgebook/)**

[![Site](https://img.shields.io/badge/Site-Live-brightgreen?logo=github)](https://microsoft-foundry.github.io/forgebook)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Notebooks](https://img.shields.io/badge/Format-Jupyter%20Notebooks-F37626?logo=jupyter)](notebooks/)

---

## Latest Recipes

| Recipe | Description | Tags |
|--------|-------------|------|
| [Create Your First Agent (Part 1)](https://microsoft-foundry.github.io/forgebook/notebook/foundry-agent-part-1/) | Step-by-step tutorial to deploy gpt-5-mini on Microsoft Foundry, create an AI agent with Web Search, and test it — all from the Foundry portal. Part 1 of 4. | `agents` |

## Get Started

### Prerequisites

- **Python 3.10+**
- **Azure account** — [Create one for free](https://aka.ms/free)
- **Microsoft Foundry resource** — [Set up Microsoft Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-foundry?view=foundry)

### Run Notebooks Locally

```bash
git clone https://github.com/microsoft-foundry/forgebook.git
cd forgebook
pip install -r requirements.txt
jupyter notebook
```

Most notebooks walk you through setting up Azure resources as part of the tutorial. Follow the instructions in each notebook to configure your environment.

### Publish a New Recipe

Forgebook is currently operating as a curated Microsoft-authored cookbook while the recipe format, content bar, and publishing workflow stabilize. Recipe publishing is focused on approved contributors from Foundry Developer Experience / Developer Marketing and the Foundry product group, including PM and engineering. Broader contribution paths may be added as the cookbook matures.

Approved Microsoft authors should follow the internal authoring workflow, then submit the finished notebook, assets, and metadata here for review.

1. Create your notebook in `notebooks/`
2. Add an entry to `registry.yaml`:
   ```yaml
   - slug: my-notebook
     path: notebooks/my-notebook.ipynb
     title: "My Awesome Notebook"
     authors:
       - github: your-username
   ```
3. Open a PR — CI validates, builds a live preview, and auto-deploys on merge

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full authoring guide, content guidelines, and PR checklist.

## Repository Structure

```
forgebook/
├── notebooks/          # Jupyter notebooks (source of truth)
│   ├── data/           # Sample datasets
│   └── media/          # Images referenced in notebooks
├── registry.yaml       # Notebook metadata for the site
└── site/               # Astro static site
```

Notebooks are the source of truth — they stay clean and portable with no site-specific metadata baked in. Authors register notebooks in `registry.yaml` and the site builds automatically.

## Topics

Recipes cover a range of AI development topics:

`agents` · `multi-agent` · `inference` · `knowledge` · `evaluation` · `fine-tuning` · `memory` · `multimodal` · `safety` · `local` · `tools` · `models` · `mai` · `agent-framework` · `a2a` · `langchain` · `mcp`

## Resources

- [Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/what-is-foundry)
- [Foundry Models](https://learn.microsoft.com/en-us/azure/foundry/concepts/foundry-models-overview)
- [Foundry Agent Service](https://learn.microsoft.com/en-us/azure/foundry/agents/overview)

## Data Collection

The Forgebook public site uses standard pseudonymous web telemetry. Microsoft uses these insights only to improve Forgebook content, recipe planning, and site performance. By choosing to use the public site, you consent to this telemetry.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the current authoring workflow and review checklist.

This project follows the [Microsoft Open Source Code of Conduct](CODE_OF_CONDUCT.md). For support options, see [SUPPORT.md](SUPPORT.md). To report security vulnerabilities, see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
