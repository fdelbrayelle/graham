# Releasing `graham`

## One-time setup

1. Create the project on PyPI (`graham-agent`) if not already created.
2. In PyPI project settings, configure a Trusted Publisher for this repo and workflow:
   - Owner: `fdelbrayelle`
   - Repository: `graham`
   - Workflow file: `.github/workflows/release.yml`
   - Environment: `pypi`
3. In GitHub repository settings, create an environment named `pypi` (no secret required for Trusted Publishing).

## Release flow

1. Update version in `pyproject.toml`.
2. Update `CHANGELOG.md`.
3. Commit and push to `main`.
4. Create and push a version tag:

```bash
git tag -a v0.1.1 -m "v0.1.1"
git push origin v0.1.1
```

5. GitHub Actions workflow `Release` will:
   - build wheel + sdist
   - run `twine check`
   - create/update the GitHub Release with artifacts
   - publish to PyPI
