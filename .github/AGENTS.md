# .github/AGENTS.md

See [AGENTS.md](../AGENTS.md) at the repo root for full project documentation.

## CI/CD Quick Reference

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `deploy.yml` | Push to `main`, daily cron, manual | Refresh `popular.json` from App Insights, build, deploy to GitHub Pages |
| `preview.yml` | PR events | Validate, build with PR-scoped base, post preview URL |

## PR Checklist

1. `cd scripts && npx tsx validate-registry.ts` — registry + tags + authors
2. `cd site && npm run build` — full build with type checking
3. Keep notebook changes separate from site changes when possible
4. New notebooks need entries in `registry.yaml` with all required fields
5. New authors need approved entries in `authors.yaml` with `name` and `title`
6. Recipe PRs should be from approved Microsoft Forgebook authors or have maintainer approval while the cookbook stabilizes
