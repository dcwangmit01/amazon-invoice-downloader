# Amazon Invoice Downloader

[![PyPI - Version](https://img.shields.io/pypi/v/amazon-invoice-downloader.svg)](https://pypi.org/project/amazon-invoice-downloader)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/amazon-invoice-downloader.svg)](https://pypi.org/project/amazon-invoice-downloader)

-----

**Table of Contents**

- [Installation](#installation)
- [License](#license)

## What it does


This program `amazon-invoice-downloader.py` is a utility script that uses the [Playwright](https://playwright.dev/) library to spin up a Chromium instance and automate the process of downloading invoices for Amazon purchases within a specified date range. The script logs into Amazon using the provided email and password, navigates to the "Returns & Orders" section, and retrieves invoices for the specified year or date range.

The user can provide their Amazon login credentials either through command line arguments (--email=<email> --password=<password>) or as environment variables ($AMAZON_EMAIL and $AMAZON_PASSWORD).

The script accepts the date range either as a specific year (--year=<YYYY>) or as a date range (--date-range=<YYYYMMDD-YYYYMMDD>). If no date range is provided, the script defaults to the current year.

Once the invoices are retrieved, they are saved as PDF files in a local "downloads" directory. The filename of each PDF is formatted as `YYYYMMDD_<total>_amazon_<orderid>.pdf`, where YYYYMMDD is the date of the order, total is the total amount of the order (with dollar signs and commas removed), and orderid is the unique Amazon order ID.

The program has a built-in "human latency" function, sleep(), to mimic human behavior by introducing random pauses between certain actions. This can help prevent the script from being detected and blocked as a bot by Amazon.

The script will skip downloading a file if it already exists in the `./downloads` directory.

## Installation

```console
pip install amazon-invoice-downloader
playwright install
```

## Usage

```console
$ amazon-invoice-downloader -h
Amazon Invoice Downloader

Usage:
  amazon-invoice-downloader.py \
    [--email=<email> --password=<password>] \
    [--year=<YYYY> | --date-range=<YYYYMMDD-YYYYMMDD>]
  amazon-invoice-downloader.py (-h | --help)

Login Options:
  --email=<email>          Amazon login email  [default: $AMAZON_EMAIL].
  --password=<password>    Amazon login password  [default: $AMAZON_PASSWORD].

Date Range Options:
  --date-range=<YYYYMMDD-YYYYMMDD>  Start and end date range
  --year=<YYYY>            Year, formatted as YYYY  [default: <CUR_YEAR>].

Options:
  -h --help                Show this screen.

Examples:
  amazon-invoice-downloader.py --year=2022  # This uses env vars $AMAZON_EMAIL and $AMAZON_PASSWORD
  amazon-invoice-downloader.py --date-range=20220101-20221231
  amazon-invoice-downloader.py --email=user@example.com --password=secret  # Defaults to current year
  amazon-invoice-downloader.py --email=user@example.com --password=secret --year=2022
  amazon-invoice-downloader.py --email=user@example.com --password=secret --date-range=20220101-20221231
```


## License

`amazon-invoice-downloader` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
