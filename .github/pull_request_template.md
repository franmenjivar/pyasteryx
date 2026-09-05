## What this changes

<!-- One or two sentences. What behaviour is different after this? -->

## Why

<!-- The bug, the gap, or the request. Link an issue if there is one. -->

## Checklist

- [ ] Tests cover the change (a fix has a test that fails without it)
- [ ] `pytest`, `ruff check .` and `mypy src/pyasteryx` pass locally
- [ ] No new runtime dependency (optional extras stay lazily imported)
- [ ] Specification files, if touched, were regenerated with `tools/xml_to_spec.py`
- [ ] `CHANGELOG.md` updated for anything user-visible
