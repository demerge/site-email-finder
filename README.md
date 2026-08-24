# site-email-finder

Crawl business websites listed in a CSV export (Yellow Pages, Google Places,
or anything similar) and pull out contact email addresses that aren't
already in your data — homepage first, then a handful of likely contact
pages (`/contact`, `/about`, etc.).

Built to be **format-agnostic**: point it at any CSV via a field-mapping
config, not just one particular scraper's schema.

- [Why this exists](#why-this-exists)
- [Features](#features)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Customizing the column mapping](#customizing-the-column-mapping)
- [All CLI options](#all-cli-options)
- [How the crawl works](#how-the-crawl-works)
- [Output files](#output-files)
- [Resuming an interrupted run](#resuming-an-interrupted-run)
- [Contributing](#contributing)
- [License](#license)

## Why this exists

Lead lists exported from scrapers (Yellow Pages, Google Places/Maps, etc.)
often have a `website` column but no `email` column filled in, even though
the business's email is sitting right there in the page HTML or behind a
`mailto:` link. This tool fills that gap in bulk, politely and repeatably.

## Features

- 🔧 **Configurable field mapping** — works with any CSV schema, not just one export format
- 🌐 Homepage + fallback contact-page crawling (`contact`, `contact-us`, `about`, etc. — configurable)
- 🧹 Filters out junk matches (tracking pixels, placeholder domains, image/script false-positives)
- ⏸️ **Resumable** — safe to stop and restart; already-processed rows are skipped
- 📝 Per-site log so you can see exactly what happened for every row (found / not found / no website / had email already)
- 🧪 Tested with `pytest`

## Installation

Requires Python 3.9+.

```bash
git clone https://github.com/demerge/site-email-finder.git
cd site-email-finder
pip install -e .
```

Or, without installing as a package:

```bash
pip install -r requirements.txt
```

### Windows users

1. Install Python from [python.org/downloads](https://www.python.org/downloads/) — tick **"Add python.exe to PATH"** during setup.
2. Open PowerShell or Command Prompt in the project folder.
3. Run the `pip install` command above.

## Quick start

```bash
site-email-finder path/to/your_export.csv
```

(or, if you didn't install it as a package: `python -m site_email_finder path/to/your_export.csv`)

This produces:
- `contacts_with_found_emails.csv` — rows in `Name,Email,Bio,Company,Profile` format
- `crawl_log.csv` — one row per input row, showing the crawl outcome

Try it on the bundled sample first:

```bash
site-email-finder examples/sample_input.csv --limit 5
```

## Customizing the column mapping

By default the tool expects columns like `name`, `email`, `website`,
`primaryCategory`, `description`, `address/city`, `address/state`,
`profileUrl` (a Yellow-Pages-style export). **Your CSV almost certainly
uses different column names — that's fine.**

Point individual fields at your own columns with `--map`:

```bash
site-email-finder mydata.csv \
  --map Name=business_name \
  --map Email=contact_email \
  --map Website=site_url
```

Or use a YAML config for a full remap (see [`examples/config.example.yaml`](examples/config.example.yaml)):

```bash
site-email-finder mydata.csv --config my_config.yaml
```

`--map` flags always win over a `--config` file, which always wins over the
built-in defaults.

## All CLI options

```
site-email-finder INPUT_CSV [options]

  -o, --output PATH          Output CSV (default: contacts_with_found_emails.csv)
  --log PATH                 Crawl log CSV (default: crawl_log.csv)
  --config PATH              YAML file overriding field mapping / options
  --map Output=column        Override one field mapping (repeatable)
  --contact-paths [PATH ...] Contact-page paths to try (default: contact, contact-us,
                              contactus, about, about-us, get-in-touch)
  --timeout SECONDS          Per-request timeout (default: 10)
  --delay SECONDS            Delay between sites (default: 1.0)
  --save-every N             Flush output to disk every N rows (default: 25)
  --limit N                  Only process the first N rows (handy for testing)
  --recrawl-existing-email   Crawl every site even if the CSV already has an email
```

## How the crawl works

For each row without an email:

1. Fetch the homepage. Scan the HTML for email-shaped text and `mailto:` links.
2. If nothing's found, try each configured contact-page path on the same
   domain, in order, stopping as soon as one yields an email.
3. Clean the results: lowercase, dedupe, and drop obvious false positives
   (image/script filenames, tracking domains, placeholder addresses like
   `you@example.com`).
4. Take the first valid email found.

Rows that already have an email in the input CSV are passed through
untouched (skip this behavior with `--recrawl-existing-email`). Rows with
no website and no existing email are logged as `no_website` and left out of
the output CSV.

## Output files

**`contacts_with_found_emails.csv`**

```csv
Name,Email,Bio,Company,Profile
Eliza Jane Events,info@elizajaneevents.com,Wedding planner in Rochester NY,Eliza Jane Events,http://elizajaneevents.com/
```

**`crawl_log.csv`** — one row per input row:

```csv
Name,Website,Status,EmailsFound
Eliza Jane Events,http://elizajaneevents.com/,found:info@elizajaneevents.com,info@elizajaneevents.com
Some Other Biz,http://otherbiz.com,no_email_found,
No Website Co,,no_website,
Had One Already,http://hadone.com,had_email_already,
```

## Resuming an interrupted run

The tool checks `(Name, Profile)` pairs already present in your output file
and skips them. If you `Ctrl+C` partway through a large run, just re-run
the exact same command — it picks up where it left off instead of
re-crawling everything.

## Contributing

Contributions are very welcome — new output formats, smarter contact-page
discovery, JS-rendered page support, better false-positive filtering, you
name it. See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

## License

[MIT](LICENSE) — do whatever you like with it.

## Disclaimer

Only crawl sites you have the right to crawl, respect `robots.txt` and each
site's terms of service, and follow applicable email/anti-spam laws (e.g.
CAN-SPAM, GDPR, CASL) for whatever you do with the addresses you collect.
This tool fetches publicly served HTML; it doesn't bypass logins, CAPTCHAs,
or any other access controls.
