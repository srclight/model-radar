# Release

Version bump, PyPI publish, and MCP registry update for model-radar.

## When to Use

When you need to cut a new release of model-radar.

## Steps

### 1. Pre-flight checks

```sh
python -m pytest tests/ -v
ruff check src/ tests/
```

All tests must pass and lint must be clean before proceeding.

### 2. Decide the version

Follow semver: MAJOR.MINOR.PATCH
- PATCH: bug fixes, provider data updates
- MINOR: new MCP tools, new providers, new features
- MAJOR: breaking API changes (rare)

Check current version:
```sh
grep '^version' pyproject.toml
```

### 3. Bump version in BOTH files

These must match exactly:

1. `pyproject.toml` -> `version = "X.Y.Z"`
2. `src/model_radar/__init__.py` -> `__version__ = "X.Y.Z"`

### 4. Update server.json if needed

If the PyPI package version in `server.json` is stale, update the `version` fields to match. This is the MCP registry manifest.

### 5. Commit the version bump

```sh
git add pyproject.toml src/model_radar/__init__.py server.json
git commit -m "bump: vX.Y.Z -- <one-line summary of changes>"
```

### 6. Merge to master and tag

```sh
git checkout develop && git merge --no-ff feature/xxx   # if on feature branch
git checkout master && git merge develop --no-ff -m "release: vX.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z -- <summary>"
git checkout develop
git push origin master develop --tags
```

### 7. Create GitHub release

```sh
gh release create vX.Y.Z --title "vX.Y.Z" --notes "<release notes>"
```

This triggers the publish workflow which:
- Builds and publishes to PyPI via trusted publisher (OIDC)
- Publishes to MCP Registry via mcp-publisher (OIDC)

### 8. Verify

- Check PyPI: `pip install model-radar-mcp==X.Y.Z` works
- Check MCP Registry listing is updated

## Checklist

- [ ] Tests pass
- [ ] Lint clean
- [ ] Version bumped in pyproject.toml AND __init__.py
- [ ] server.json version updated if stale
- [ ] Commit message includes version and summary
- [ ] Merged develop -> master with --no-ff
- [ ] Tag created and pushed
- [ ] GitHub release created (triggers CI publish)
