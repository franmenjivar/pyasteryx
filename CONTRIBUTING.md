# Contributing to pyasteryx

Thanks for your interest. This document covers how changes get into the project.

## Branching

`main` is always releasable. Every change — including documentation and
one-line fixes — lands through a pull request from a topic branch. Nothing is
pushed directly to `main`.

Name the branch after the kind of change it carries:

| Prefix | For |
|---|---|
| `feat/` | new capability (a category, a reader, an exporter) |
| `fix/` | a defect in existing behaviour |
| `perf/` | speed or memory, with no behaviour change |
| `docs/` | README, docstrings, examples |
| `test/` | tests only |
| `chore/` | build, CI, dependencies, tooling |
| `spec/` | regenerating or adding an ASTERIX specification |
| `release/` | version bump and changelog for a release |

Use a short, descriptive slug: `feat/cat034-support`, `fix/fspec-fx-overrun`,
`spec/cat062-1.19`.

Keep a branch to one concern. A branch that fixes a bug and also reformats
three files is two pull requests.

## The loop

```bash
git switch main && git pull
git switch -c fix/short-slug

# ... make the change, with tests ...

pytest
ruff check .
mypy src/pyasteryx

git push -u origin fix/short-slug
```

Open a pull request against `main`. CI runs the test matrix (Python 3.10–3.13
on Linux, plus macOS and Windows), lint and type checks, and verifies the wheel
builds and installs standalone. It must be green before merge.

Pull requests are squash-merged, so the PR title becomes the commit subject on
`main`. Write it as an imperative sentence: *Fix FSPEC overrun on a truncated
record*, not *fixed stuff*.

### Branch protection

`main` is protected and the rules apply to everyone, maintainers included:
a pull request is required, all CI checks must pass, history stays linear, and
force pushes and branch deletion are refused. There is no way to push straight
to `main`; the protection is not advisory.

Two things worth knowing if you administer the repository:

- The required checks are pinned **by name**. Adding a new matrix entry is
  safe, but *removing* one — dropping a Python version, say — leaves a required
  check that will never report again, and every merge blocks until the required
  list is updated to match. Change the matrix and the required checks together.
- The escape hatch is Settings → Branches → *Do not allow bypassing the above
  settings*. Nothing can permanently lock you out.

## What a change needs

**Tests.** A bug fix gets a test that fails before it and passes after. A new
feature gets tests for the normal path, the absent-data path, and the
malformed-input path — ASTERIX data in the field is frequently one of the last
two.

**No new runtime dependencies.** `import pyasteryx` is dependency-free and
stays that way. Anything heavier belongs behind an optional extra, imported
lazily inside the function that needs it (see `exporters/frames.py`).

**Python 3.10 compatibility.** The floor is declared in `pyproject.toml` and
enforced by CI. It is easy to miss on a newer local interpreter — `tomllib`
looked fine locally and broke the 3.10 job.

**Specifications are generated, never hand-edited.** Category definitions under
`src/pyasteryx/spec/data/` come from the
[CroatiaControlLtd/asterix](https://github.com/CroatiaControlLtd/asterix) XML
via `tools/xml_to_spec.py`. To add or correct one, change the converter or take
a newer upstream XML and regenerate:

```bash
python tools/xml_to_spec.py asterix_cat062_1_19.xml \
    src/pyasteryx/spec/data/cat062/1.19.json
```

Files are written minified. Pass `--pretty` when you want to diff two
conversions by eye, but commit the minified form.

## Releasing

1. Branch `release/vX.Y.Z`.
2. Bump `version` in `pyproject.toml`, `__version__` in
   `src/pyasteryx/__init__.py`, and `version` in `CITATION.cff`. A test asserts
   the first two agree.
3. Add the `CHANGELOG.md` entry.
4. PR, green CI, merge.
5. Tag and push:
   ```bash
   git switch main && git pull
   git tag -a vX.Y.Z -m "pyasteryx X.Y.Z"
   git push origin vX.Y.Z
   ```

The tag triggers the workflow, which runs the full matrix and then publishes to
PyPI via Trusted Publishing. Creating a GitHub Release from the tag also
prompts Zenodo to archive the tarball and mint a DOI.

Order matters for a first-time setup:

- **Enable Zenodo before creating the release.** Zenodo only archives releases
  published after the repository toggle is switched on. Release first and no
  DOI is minted, and you need a throwaway version to get one.
- **The PyPI trusted publisher must match the OIDC claims exactly.** The
  workflow filename is `ci.yml` — registering `ci.yaml` fails with
  `invalid-publisher`, which reads like a broken setup but is a one-character
  typo. If a publish fails this way, fix the PyPI entry and re-run the failed
  job on the existing run; no new tag or release is needed.

After a release, update `CITATION.cff` with the new version DOI. The concept
DOI never changes.
