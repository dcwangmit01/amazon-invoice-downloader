# SPDX-FileCopyrightText: 2023-present David C Wang <dcwangmit01@gmail.com>
#
# SPDX-License-Identifier: MIT

"""
Amazon Invoice Downloader

Usage:
  amazon-invoice-downloader.py \
    [--email=<email> --password=<password>] \
    [--year=<YYYY> | --date-range=<YYYYMMDD-YYYYMMDD>]
  amazon-invoice-downloader.py (-h | --help)
  amazon-invoice-downloader.py (-v | --version)

Login Options:
  --email=<email>          Amazon login email  [default: $AMAZON_EMAIL].
  --password=<password>    Amazon login password  [default: $AMAZON_PASSWORD].

Date Range Options:
  --date-range=<YYYYMMDD-YYYYMMDD>  Start and end date range
  --year=<YYYY>                     Year, formatted as YYYY  [default: <CUR_YEAR>].

Options:
  -h --help                Show this screen.
  -v --version             Show version.

Examples:
  amazon-invoice-downloader.py --year=2022  # Uses .env file or env vars $AMAZON_EMAIL and $AMAZON_PASSWORD
  amazon-invoice-downloader.py --date-range=20220101-20221231
  amazon-invoice-downloader.py --email=user@example.com --password=secret  # Defaults to current year
  amazon-invoice-downloader.py --email=user@example.com --password=secret --year=2022
  amazon-invoice-downloader.py --email=user@example.com --password=secret --date-range=20220101-20221231

Features:
  - Remote debugging enabled on port 9222 for AI MCP Servers
  - Virtual authenticator configured to prevent passkey dialogs
  - Stealth mode enabled to avoid detection

Credential Precedence:
  1. Command line arguments (--email, --password)
  2. Environment variables ($AMAZON_EMAIL, $AMAZON_PASSWORD)
  3. .env file (automatically loaded if env vars not set)
"""

import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from docopt import docopt
from dotenv import load_dotenv
from playwright.sync_api import TimeoutError, sync_playwright
from playwright_stealth import Stealth

from ..__about__ import __version__


def load_env_if_needed():
    """Load environment variables from .env file if it exists and variables aren't set."""
    # Check if Amazon credentials are already set in environment
    amazon_email = os.environ.get('AMAZON_EMAIL')
    amazon_password = os.environ.get('AMAZON_PASSWORD')

    # If both are already set, no need to load .env
    if amazon_email and amazon_password:
        return

    # Look for .env file in current directory and parent directories
    current_dir = Path.cwd()
    env_file = None

    # Check current directory and up to 3 parent directories
    for i in range(4):
        check_path = current_dir / '.env'
        if check_path.exists():
            env_file = check_path
            break
        current_dir = current_dir.parent

    if env_file:
        print(f"Loading environment variables from {env_file}")
        load_dotenv(env_file)
    else:
        print("No .env file found in current directory or parent directories")


def sleep():
    # Add human latency
    # Generate a random sleep time between 3 and 5 seconds
    sleep_time = random.uniform(2, 5)
    # Sleep for the generated time
    time.sleep(sleep_time)


def run(playwright, args):
    email = args.get("--email")
    if email == "$AMAZON_EMAIL":
        email = os.environ.get("AMAZON_EMAIL")

    password = args.get("--password")
    if password == "$AMAZON_PASSWORD":
        password = os.environ.get("AMAZON_PASSWORD")

    # Parse date ranges int start_date and end_date
    if args["--date-range"]:
        start_date, end_date = args["--date-range"].split("-")
    elif args["--year"] != "<CUR_YEAR>":
        start_date, end_date = args["--year"] + "0101", args["--year"] + "1231"
    else:
        year = str(datetime.now().year)
        start_date, end_date = year + "0101", year + "1231"
    start_date = datetime.strptime(start_date, "%Y%m%d")
    end_date = datetime.strptime(end_date, "%Y%m%d")

    # Ensure the location exists for where we will save our downloads
    target_dir = os.getcwd() + "/" + "downloads"
    os.makedirs(target_dir, exist_ok=True)

    # Create Playwright context with Chromium
    # Always use CDP for virtual authenticator and remote debugging
    print("🚀 Launching Chromium with CDP debugging on port 9222")
    print("📱 You can connect to this browser at: http://localhost:9222")
    print("🔗 AI assistant can control this browser instance via CDP")

    # Launch browser with CDP endpoint
    browser = playwright.chromium.launch(
        headless=False,
        args=[
            '--remote-debugging-port=9222',
            '--remote-debugging-address=0.0.0.0',
            '--disable-web-security',
            '--disable-features=VizDisplayCompositor',
        ],
    )

    # Connect to the browser using CDP
    browser = playwright.chromium.connect_over_cdp("http://localhost:9222")

    # Create context and page
    context = browser.new_context()
    page = context.new_page()

    # Set up virtual authenticator to prevent passkey dialogs
    print("🔐 Setting up virtual authenticator to disable passkeys")
    try:
        client = page.context.new_cdp_session(page)
        client.send("WebAuthn.enable")
        client.send(
            "WebAuthn.addVirtualAuthenticator",
            {
                "options": {
                    "protocol": "ctap2",
                    "transport": "internal",
                    "hasResidentKey": True,
                    "hasUserVerification": True,
                    "isUserVerified": True,
                    "automaticPresenceSimulation": True,
                }
            },
        )
        print("✅ Virtual authenticator configured successfully")
    except Exception as e:
        print(f"⚠️ Warning: Could not configure virtual authenticator: {e}")

    Stealth().apply_stealth_sync(page)

    # Wait for page to fully load
    page.goto("https://amazon.com/")
    page.wait_for_load_state("domcontentloaded")

    # Check if we're on the less fully featured page
    test_less_featured_page = page.query_selector('a:has-text("Returns & Orders")')
    if not test_less_featured_page:
        print("Less featured page detected, navigating to sign-in...")
        page.query_selector('a:has-text("Your Account")').click()
        page.wait_for_load_state("domcontentloaded")
        sleep()

    page.query_selector('a:has-text("Hello, sign in")').click()
    page.wait_for_load_state("domcontentloaded")
    sleep()

    if email:
        page.get_by_label("Email").fill(email)
        page.get_by_role("button", name="Continue").click()
        page.wait_for_load_state("domcontentloaded")
        sleep()

    if password:
        page.get_by_label("Password").fill(password)
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.wait_for_load_state("domcontentloaded")
        sleep()

    # Check for 2FA page
    if page.query_selector('title:has-text("Two-Step Verification")'):
        print("🔐 2FA detected - please complete authentication in browser")
        while page.query_selector('title:has-text("Two-Step Verification")'):
            time.sleep(1)
        print("✅ 2FA completed")
    page.wait_for_load_state("domcontentloaded")

    page.wait_for_selector("a >> text=Returns & Orders", timeout=0).click()
    sleep()

    # Get a list of years from the select options
    select = page.query_selector("select#time-filter")
    years = select.inner_text().split("\n")  # skip the first two text options

    # Filter years to include only numerical years (YYYY)
    years = [year for year in years if year.isnumeric()]

    # Filter years to the include only the years between start_date and end_date inclusively
    years = [year for year in years if start_date.year <= int(year) <= end_date.year]
    years.sort(reverse=True)

    # Year Loop (Run backwards through the time range from years to pages to orders)
    for year in years:
        # Select the year in the order filter
        page.select_option('form[action="/your-orders/orders"] select#time-filter', value=f"year-{year}")
        sleep()

        # Page Loop
        first_page = True
        done = False
        while not done:
            # Go to the next page pagination, and continue downloading
            #   if there is not a next page then break
            try:
                if first_page:
                    first_page = False
                else:
                    page.get_by_role("link", name="Next →").click()
                sleep()  # sleep after every page load
            except TimeoutError:
                # There are no more pages
                break

            # Order Loop
            order_cards = page.query_selector_all(".order-card.js-order-card")
            for order_card in order_cards:
                # Parse the order card to create the date and file_name
                spans = order_card.query_selector_all("span")
                # Debug:
                # for i,s in enumerate(spans): print(i, s.inner_text())

                # Skip cancelled orders
                if spans[4].inner_text().strip().lower() == "cancelled":
                    continue

                date = datetime.strptime(spans[1].inner_text(), "%B %d, %Y")
                total = spans[3].inner_text().replace("$", "").replace(",", "")  # remove dollar sign and commas
                orderid = spans[8].inner_text()
                date_str = date.strftime("%Y%m%d")
                file_name = f"{target_dir}/{date_str}_{total}_amazon_{orderid}.pdf"

                if date > end_date:
                    continue
                elif date < start_date:
                    done = True
                    break

                if os.path.isfile(file_name):
                    print(f"File [{file_name}] already exists")
                else:
                    print(f"Saving file [{file_name}]")
                    # Save
                    link = "https://www.amazon.com/" + order_card.query_selector(
                        'xpath=//a[contains(text(), "View invoice")]'
                    ).get_attribute("href")
                    invoice_page = context.new_page()
                    invoice_page.goto(link)
                    invoice_page.pdf(
                        path=file_name,
                        format="Letter",
                        margin={"top": ".5in", "right": ".5in", "bottom": ".5in", "left": ".5in"},
                    )
                    invoice_page.close()

    # Close the browser
    context.close()
    browser.close()


def amazon_invoice_downloader():
    # Load environment variables from .env file if needed
    load_env_if_needed()

    args = docopt(__doc__)
    # print(args)
    if args['--version']:
        print(__version__)
        sys.exit(0)

    with sync_playwright() as playwright:
        run(playwright, args)
