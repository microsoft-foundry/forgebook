## Description

<!-- What does this PR do? Link to any related issue(s). -->

Closes #

---

## Checklist

### Notebook contributions

_Skip if this PR only touches site code._

- [ ] Notebook added to `notebooks/` directory
- [ ] Entry added to `registry.yaml` with all required fields (`slug`, `path`, `title`, `authors`)
- [ ] Author entry exists in `authors.yaml` (with at least `name` and `title`)
- [ ] Tags are from the allowed list in `tags.yaml`
- [ ] Registry validation passes: `cd scripts && npx tsx validate-registry.ts`
- [ ] Notebook runs cleanly end-to-end
- [ ] Cell outputs cleared before committing
- [ ] No site-specific metadata inside the notebook
- [ ] Images stored in `notebooks/media/` with descriptive alt text

### Site changes

_Skip if this PR only adds a notebook._

- [ ] Site builds without errors: `cd site && npm run build`
- [ ] No TypeScript errors: `cd site && npx astro check`
