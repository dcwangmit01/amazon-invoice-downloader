# Amazon Invoice Downloader

[![PyPI - Version](https://img.shields.io/pypi/v/amazon-invoice-downloader.svg)](https://pypi.org/project/amazon-invoice-downloader)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/amazon-invoice-downloader.svg)](https://pypi.org/project/amazon-invoice-downloader)

This project uses Playwright to visit the **Returns & Orders** pages on
Amazon.com, Amazon.co.uk, or Amazon.fr and print the available invoices or
printable order summaries to PDF.

> Amazon changes its markup periodically. Always supervise the first run and
> stop if Amazon displays unexpected account or security prompts.

## Safety and privacy

- Manual login is the default when credentials are not supplied. Passwords and
  MFA codes do not need to be stored by the program.
- Login cookies are stored in the selected profile directory. Treat each
  profile like a password: the standard profile names are excluded by
  `.gitignore` and should not be shared.
- The browser no longer uses `--disable-web-security` or a remotely accessible
  debugging port.
- The script uses conservative randomized delays. Do not run several copies at
  once or reduce the delays aggressively.
- The script does not bypass CAPTCHA or MFA. Complete those challenges yourself
  in the visible browser when Amazon requests them.

## Installation on Windows

Python 3.12 or newer and [`uv`](https://docs.astral.sh/uv/) are recommended:

```powershell
uv sync
uv run playwright install chromium
```

## Download a complete marketplace history

From the repository directory:

```powershell
uv run amazon-invoice-downloader --manual-login --all-years
```

The default marketplace is Amazon.com. The program opens a visible Chromium
window. Sign in manually,
complete MFA or CAPTCHA if requested, navigate to **Returns & Orders** if
necessary, and then return to the terminal and press Enter.

By default it creates:

- `downloads/*.pdf` — printed invoices and order summaries;
- `downloads/download-manifest.csv` — one audit record for every saved,
  skipped, cancelled, missing-link, or failed document;
- `.amazon-browser-profile/` — persistent cookies for subsequent runs.

Rerunning the same command is safe: a non-empty PDF with the expected
deterministic filename is skipped and recorded as `skipped_existing`.

Run the UK and French storefronts into separate destinations and browser
profiles. This prevents same-numbered files, cookies, and audit records from
different marketplaces from being mixed:

```powershell
# Amazon UK: PDF filenames use GBP.
uv run amazon-invoice-downloader --manual-login --all-years `
  --marketplace=amazon.co.uk `
  --output-dir=downloads-uk `
  --profile-dir=.amazon-browser-profile-uk

# Amazon France: PDF filenames use EUR.
uv run amazon-invoice-downloader --manual-login --all-years `
  --marketplace=amazon.fr `
  --output-dir=downloads-fr `
  --profile-dir=.amazon-browser-profile-fr
```

When `--manifest` is omitted, its path follows `--output-dir`, so these runs
create `downloads-uk/download-manifest.csv` and
`downloads-fr/download-manifest.csv`. Each storefront may require its own
interactive sign-in even when the underlying Amazon account is the same.

## Other date scopes and locations

```powershell
# One year
uv run amazon-invoice-downloader --manual-login --year=2024

# Inclusive date range
uv run amazon-invoice-downloader --manual-login --date-range=20230101-20231231

# Custom destinations
uv run amazon-invoice-downloader --manual-login --all-years `
  --output-dir="D:\AmazonInvoices" `
  --profile-dir="D:\AmazonBrowserProfile" `
  --manifest="D:\AmazonInvoices\manifest.csv"
```

Credential-based login remains available for compatibility, but manual login is
recommended because command-line arguments can be retained in shell history and
environment files can expose account passwords.

## Manifest statuses

| Status | Meaning |
| --- | --- |
| `saved` | PDF created successfully |
| `skipped_existing` | A prior non-empty PDF was found |
| `cancelled` | Amazon marks the order as cancelled |
| `outside_date_range` | Order is outside the requested partial-year range |
| `no_invoice_link` | No invoice/order-summary link was exposed |
| `parse_error` | Amazon's order-card markup could not be interpreted |
| `download_error` | A document URL failed or redirected to sign-in |

The manifest is append-only so interrupted and repeated runs retain their full
history. It also supplies the order IDs and source URLs needed for later matching
against an Amazon data export.

## Command reference

```text
amazon-invoice-downloader \
  [--manual-login] [--email=<email> --password=<password>] \
  [--all-years | --year=<YYYY> | --date-range=<YYYYMMDD-YYYYMMDD>] \
  [--marketplace=<domain>] [--output-dir=<path>] [--profile-dir=<path>] \
  [--manifest=<path>] \
  [--min-delay=<seconds>] [--max-delay=<seconds>]
```

Amazon may expose multiple documents for one order. They receive `_02`, `_03`,
and subsequent suffixes. Some marketplace orders may expose no invoice at all;
these are retained in the manifest rather than silently discarded.

| Marketplace | `--marketplace` | Filename currency |
| --- | --- | --- |
| United States | `amazon.com` | `USD` |
| United Kingdom | `amazon.co.uk` | `GBP` |
| France | `amazon.fr` | `EUR` |

## Development

```powershell
uv run pytest
uv run black --check .
uv run flake8 src/amazon_invoice_downloader tests
```

## License

MIT; see `LICENSE.txt`.
