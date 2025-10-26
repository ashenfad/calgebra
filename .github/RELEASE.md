# Release Guide

Quick reference for publishing new versions of calgebra to PyPI.

## Pre-Release Checklist

```bash
# 1. Update version in pyproject.toml
# 2. Update README.md if needed (status, examples, etc.)
# 3. Sync docs
./sync_docs.sh

# 4. Run tests
pytest tests/ -v

# 5. Check linting
ruff check calgebra/
black --check calgebra/

# 6. Commit changes
git add -A
git commit -m "Prepare v0.X.Y release"
git push
```

## Release Steps

```bash
# 1. Tag the release
git tag -a v0.X.Y -m "v0.X.Y: Brief description"
git push origin v0.X.Y

# 2. Create GitHub Release
# Go to: https://github.com/ashenfad/calgebra/releases/new
# - Choose tag: v0.X.Y
# - Title: v0.X.Y - Brief Title
# - Description: See template below
# - Publish release (NOT as pre-release)

# This triggers the publish.yml workflow which uploads to PyPI
```
