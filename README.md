# Amazon Invoice Downloader

[![PyPI - Version](https://img.shields.io/pypi/v/amazon-invoice-downloader.svg)](https://pypi.org/project/amazon-invoice-downloader)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/amazon-invoice-downloader.svg)](https://pypi.org/project/amazon-invoice-downloader)

-----

**Table of Contents**

- [Installation](#installation)
- [License](#license)

## What it does


This program `amazon-invoice-downloader.py` is a utility script that uses the [Playwright](https://playwright.dev/) library to spin up a Chromium instance and automate the process of downloading invoices for Amazon purchases within a specified date range. The script logs into Amazon using the provided email and password, navigates to the "Returns & Orders" section, and retrieves invoices for the specified year or date range.

The user can provide their Amazon login credentials through multiple methods with the following precedence order:

1. **Command line arguments** (highest priority): `--email=<email> --password=<password>`
2. **Environment variables**: `$AMAZON_EMAIL` and `$AMAZON_PASSWORD`
3. **`.env` file** (lowest priority): Automatically loaded from `.env` files in the current directory or parent directories

The program will automatically search for `.env` files in the current directory and up to 3 parent directories, loading them only if the environment variables aren't already set.

The script accepts the date range either as a specific year (--year=<YYYY>) or as a date range (--date-range=<YYYYMMDD-YYYYMMDD>). If no date range is provided, the script defaults to the current year.

Once the invoices are retrieved, they are saved as PDF files in a local "downloads" directory. The filename of each PDF is formatted as `YYYYMMDD_<total>_amazon_<orderid>.pdf`, where YYYYMMDD is the date of the order, total is the total amount of the order (with dollar signs and commas removed), and orderid is the unique Amazon order ID.

The program has a built-in "human latency" function, sleep(), to mimic human behavior by introducing random pauses between certain actions. This can help prevent the script from being detected and blocked as a bot by Amazon.

The script will skip downloading a file if it already exists in the `./downloads` directory.

## Installation

```console
pip install amazon-invoice-downloader
playwright install
```

## Environment Setup

The program supports multiple ways to provide Amazon credentials with automatic `.env` file discovery. Here are the setup options:

### Option 1: .env File (Recommended)
Create a `.env` file in your project directory or any parent directory (up to 3 levels up):

```env
AMAZON_EMAIL=your_email@example.com
AMAZON_PASSWORD=your_password_here
```

The program will automatically find and load the `.env` file if environment variables aren't already set.

### Option 2: Environment Variables
Set environment variables directly:

```bash
export AMAZON_EMAIL=your_email@example.com
export AMAZON_PASSWORD=your_password_here
```

### Option 3: Command Line Arguments
Provide credentials directly when running the program:

```bash
amazon-invoice-downloader --email=your_email@example.com --password=your_password
```

**Note:** The `.env` file is already in `.gitignore` to prevent accidentally committing sensitive credentials.

## Usage

When running this program, Amazon may detect you are automation and introduce CAPTCHA's or make you login again.  Just do so, and once successfully logged in, the script will continue.

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
  amazon-invoice-downloader.py --year=2022  # Uses .env file or env vars $AMAZON_EMAIL and $AMAZON_PASSWORD
  amazon-invoice-downloader.py --date-range=20220101-20221231
  amazon-invoice-downloader.py --email=user@example.com --password=secret  # Defaults to current year
  amazon-invoice-downloader.py --email=user@example.com --password=secret --year=2022
  amazon-invoice-downloader.py --email=user@example.com --password=secret --date-range=20220101-20221231
  amazon-invoice-downloader.py --remote-debug  # Enable remote debugging for AI assistants
```


## License

`amazon-invoice-downloader` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
