# Contributing

Thanks for helping improve POE Trade Flipper.

## How to contribute

1. Open an **issue** first for larger changes (refactors, new data sources) so we can align on direction.
2. **Fork** the repository and create a branch from `main`.
3. Keep pull requests **focused** (one feature or fix per PR).
4. Match existing **code style** (formatting, naming, minimal unrelated diffs).
5. If you change behavior visible in the UI, add a short note in **CHANGELOG.md** under `[Unreleased]`.

## Running locally

```bash
pip install -r requirements.txt
python app.py
```

## What we won’t merge

- Dependencies that phone home or require proprietary keys for basic use.
- Scraping that violates site terms of service.

## Code of conduct

Be respectful in issues and PRs. Maintainers may close discussions that are hostile or off-topic.
