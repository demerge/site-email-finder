# Contributing to site-email-finder

Thanks for considering a contribution! This project is intentionally small
and readable — please keep PRs focused and easy to review.

## Getting set up

```bash
git clone https://github.com/YOUR-USERNAME/site-email-finder.git
cd site-email-finder
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running tests

```bash
pytest -q
```

Tests use [`responses`](https://github.com/getsentry/responses) to mock
HTTP calls — no real network access needed to run the suite.

## Linting

```bash
ruff check .
```

## Project layout

```
src/site_email_finder/
  config.py      Default settings (contact paths, blocklist, field map, etc.)
  extractor.py   Fetching + email-extraction logic (pure functions, no CLI/IO)
  io_utils.py    CSV reading/writing helpers, field-map resolution
  cli.py         Argument parsing and the main run loop
tests/           pytest suite, one file per module
examples/        Sample input CSV + example YAML config
```

Keep `extractor.py` and `io_utils.py` free of `print()`/CLI concerns so
they stay easy to unit test and reuse from other scripts or notebooks.

## Ideas for contributions

- Support for JS-rendered pages (e.g. an optional Playwright/Selenium backend)
- Concurrent crawling with a configurable worker pool
- A `--format` flag for JSON/JSONL output alongside CSV
- Smarter contact-page discovery (parse `<nav>` links instead of guessing paths)
- Additional false-positive filters (more junk-domain patterns, phone-number-shaped strings, etc.)
- A GitHub Action / Docker image for scheduled runs

Feel free to open an issue to discuss a bigger change before you start
coding, or just open a PR directly for smaller fixes.

## Submitting a pull request

1. Fork the repo and create a branch off `main`.
2. Make your change, with a test if it changes behavior.
3. Run `pytest -q` and `ruff check .` locally.
4. Open a PR describing what changed and why. Link any related issue.

## Code of Conduct

Be respectful and constructive. Harassment or abusive behavior of any kind
isn't tolerated.

## Reporting bugs / requesting features

Please use the issue templates under **Issues → New Issue**.
