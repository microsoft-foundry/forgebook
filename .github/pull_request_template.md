## Description

<!-- What does this PR do? Link to any related issue(s). -->

Closes #

## Review focus

<!-- What should reviewers pay closest attention to? Product accuracy, notebook flow, metadata, site UI, etc. -->

---

## Checklist

### Notebook contributions

_Skip if this PR only touches site code._

- [ ] Recipe author is an approved Microsoft Forgebook author, or this contribution has maintainer approval
- [ ] Recipe was drafted or validated through the internal authoring workflow
- [ ] Foundry PM, engineering, or DX reviewer has checked product accuracy and positioning
- [ ] Notebook added to `notebooks/` directory
- [ ] Entry added to `registry.yaml` with all required fields (`slug`, `path`, `title`, `authors`)
- [ ] Approved author entry exists in `authors.yaml` (with at least `name` and `title`)
- [ ] Tags are from the allowed list in `tags.yaml`
- [ ] Registry validation passes: `cd scripts && npx tsx validate-registry.ts`
- [ ] Notebook runs cleanly end-to-end
- [ ] Cell outputs cleared before committing
- [ ] No site-specific metadata inside the notebook
- [ ] No secrets, tenant-specific values, or private endpoints are committed
- [ ] Images stored in `notebooks/media/<slug>/` with descriptive alt text
- [ ] Data files stored in `notebooks/data/<slug>/` when applicable

### Site changes

_Skip if this PR only adds a notebook._

- [ ] Site builds without errors: `cd site && npm run build`
- [ ] No TypeScript errors: `cd site && npx astro check`
