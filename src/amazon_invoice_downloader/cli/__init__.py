# SPDX-FileCopyrightText: 2023-present David C Wang <dcwangmit01@gmail.com>
#
# SPDX-License-Identifier: MIT

"""
Amazon Invoice Downloader

Usage:
  amazon-invoice-downloader.py \
    [--email=<email> --password=<password>] \
    [--domain=<domain>] \
    [--year=<YYYY> | --date-range=<YYYYMMDD-YYYYMMDD>]
  amazon-invoice-downloader.py (-h | --help)
  amazon-invoice-downloader.py (-v | --version)

Login Options:
  --email=<email>          Amazon login email  [default: $AMAZON_EMAIL].
  --password=<password>    Amazon login password  [default: $AMAZON_PASSWORD].

Domain Options:
  --domain=<domain>        Amazon domain to use, e.g. amazon.nl  [default: $AMAZON_DOMAIN].

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
  amazon-invoice-downloader.py --domain=amazon.nl --year=2024

Features:
  - Remote debugging enabled on port 9222 for AI MCP Servers
  - Virtual authenticator configured to prevent passkey dialogs
  - Stealth mode enabled to avoid detection

Credential Precedence:
  1. Command line arguments (--email, --password, --domain)
  2. Environment variables ($AMAZON_EMAIL, $AMAZON_PASSWORD, $AMAZON_DOMAIN)
  3. .env file (automatically loaded if env vars not set)
  4. Default domain: amazon.com
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

DUTCH_MONTHS = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "augustus": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}


def parse_date(date_str, domain):
    """Parse a date string, handling Dutch month names for .nl domains."""
    date_str = date_str.strip()
    if "amazon.nl" in domain or "amazon.de" in domain:
        parts = date_str.lower().split()
        if len(parts) == 3:
            try:
                day = int(parts[0])
                month = DUTCH_MONTHS.get(parts[1], 0)
                year = int(parts[2])
                if month:
                    return datetime(year, month, day)
            except ValueError:
                pass
    return datetime.strptime(date_str, "%B %d, %Y")


def parse_total(total_str, domain):
    """Parse total amount, handling Dutch currency formatting (€ 1.234,56)."""
    if "amazon.nl" in domain or "amazon.de" in domain:
        # Dutch format: € 249,03 or € 1.234,56
        return total_str.replace("€", "").replace(".", "").replace(",", ".").strip()
    # US format: $249.03
    return total_str.replace("$", "").replace(",", "")

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

    domain = args.get("--domain")
    if domain == "$AMAZON_DOMAIN" or not domain:
        domain = os.environ.get("AMAZON_DOMAIN", "amazon.com")

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

    # Launch Chromium with remote debugging for AI assistant / CDP access
    print("🚀 Launching Chromium with CDP debugging on port 9222")
    print("📱 You can connect to this browser at: http://localhost:9222")

    browser = playwright.chromium.launch(
        headless=False,
        args=[
            '--remote-debugging-port=9222',
            '--remote-debugging-address=0.0.0.0',
            '--disable-features=WebAuthentication',
        ],
    )

    # Create context and page directly (no second connect_over_cdp to avoid stale session issues)
    context = browser.new_context()
    page = context.new_page()

    Stealth().apply_stealth_sync(page)

    # Disable WebAuthn/Credentials API via JS so Amazon shows email/password form instead of passkey UI.
    # Using a JS override is safer than a CDP virtual authenticator, which actively triggers the passkey flow.
    page.add_init_script("""
        Object.defineProperty(navigator, 'credentials', {
            configurable: true,
            get: () => ({
                get: () => Promise.reject(new DOMException('NotAllowedError')),
                create: () => Promise.reject(new DOMException('NotAllowedError')),
                store: () => Promise.resolve(),
                preventSilentAccess: () => Promise.resolve(),
            })
        });
        if (window.PublicKeyCredential) {
            window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable = () => Promise.resolve(false);
            window.PublicKeyCredential.isConditionalMediationAvailable = () => Promise.resolve(false);
        }
    """)

    # Determine locale-specific selectors based on domain
    is_dutch = "amazon.nl" in domain
    sign_in_text = "hallo, inloggen" if is_dutch else "Hello, sign in"
    your_account_text = "Uw account" if is_dutch else "Your Account"
    returns_orders_text = "Retourzendingen" if is_dutch else "Returns & Orders"
    view_invoice_text = "Factuur" if is_dutch else "View invoice"
    next_page_text = "Volgende →" if is_dutch else "Next →"
    cancelled_text = "geannuleerd" if is_dutch else "cancelled"
    email_label = "E-mailadres" if is_dutch else "Email"
    continue_button = "Doorgaan" if is_dutch else "Continue"
    password_label = "Wachtwoord" if is_dutch else "Password"
    sign_in_button = "Aanmelden" if is_dutch else "Sign in"
    two_factor_title = "Verificatie in twee stappen" if is_dutch else "Two-Step Verification"

    # Build direct sign-in URL to avoid redirect chains that cause ERR_ABORTED
    assoc_handle_map = {
        "amazon.nl": "nlflex",
        "amazon.de": "deflex",
        "amazon.co.uk": "gbflex",
        "amazon.fr": "frflex",
        "amazon.es": "esflex",
        "amazon.it": "itflex",
        "amazon.com": "usflex",
    }
    assoc_handle = assoc_handle_map.get(domain, "usflex")
    from urllib.parse import quote
    return_to = quote(f"https://www.{domain}/")
    signin_url = (
        f"https://www.{domain}/ap/signin"
        f"?openid.pape.max_auth_age=900"
        f"&openid.return_to={return_to}"
        f"&openid.assoc_handle={assoc_handle}"
        f"&openid.mode=checkid_setup"
        f"&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
    )
    page.goto(signin_url, wait_until="domcontentloaded")
    print(f"Sign-in URL: {page.url}")

    # Amazon has two sign-in page variants:
    #   /ap/signin  → classic flow: #ap_email + #continue, then #ap_password + #signInSubmit
    #   /ax/claim   → unified flow: #ap_email_login + #auth-credential-autofill-hint + submit
    is_ax_claim = "/ax/claim" in page.url or "/ax/get" in page.url

    if is_ax_claim:
        # /ax/claim two-step flow: email first, then password after submit
        print("Detected /ax/claim sign-in flow")
        page.wait_for_selector("#ap_email_login", timeout=30000)
        if email:
            page.locator("#ap_email_login").fill(email)
            page.locator('form#ap_login_form [type=submit]').click()
            page.wait_for_load_state("domcontentloaded")
            sleep()
        if password:
            # Password step: may be on same page (revealed) or new page (/ax/get)
            page.wait_for_selector("#ap_password, #auth-credential-autofill-hint, #ap_password_login", timeout=30000)
            pwd_field = (
                page.query_selector("#ap_password") or
                page.query_selector("#ap_password_login") or
                page.query_selector("#auth-credential-autofill-hint")
            )
            if pwd_field:
                pwd_field.fill(password)
            page.locator('[type=submit]').first.click()
            page.wait_for_load_state("domcontentloaded")
            sleep()
    else:
        # Classic /ap/signin two-step flow
        print("Detected /ap/signin sign-in flow")
        page.wait_for_selector("#ap_email", timeout=30000)
        if email:
            page.locator("#ap_email").fill(email)
            page.locator("#continue").click()
            page.wait_for_load_state("domcontentloaded")
            sleep()
        if password:
            page.locator("#ap_password").fill(password)
            page.locator("#signInSubmit").click()
            page.wait_for_load_state("domcontentloaded")
            sleep()

    # Check for 2FA page
    if page.query_selector(f'title:has-text("{two_factor_title}")'):
        print("🔐 2FA detected - please complete authentication in browser")
        while page.query_selector(f'title:has-text("{two_factor_title}")'):
            time.sleep(1)
        print("✅ 2FA completed")
    page.wait_for_load_state("domcontentloaded")

    page.wait_for_selector(f"a >> text={returns_orders_text}", timeout=0).click()
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
                    page.get_by_role("link", name=next_page_text).click()
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
                if order_card.inner_text().strip().lower().find(cancelled_text) != -1:
                    continue

                date = parse_date(spans[1].inner_text(), domain)
                total = parse_total(spans[3].inner_text(), domain)
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
                    # Navigate to the invoice popover/index page
                    popover_href = order_card.query_selector(
                        f'xpath=//a[contains(text(), "{view_invoice_text}")]'
                    ).get_attribute("href")
                    popover_url = f"https://www.{domain}{popover_href if popover_href.startswith('/') else '/' + popover_href}"
                    invoice_page = context.new_page()
                    invoice_page.goto(popover_url)
                    invoice_page.wait_for_load_state("domcontentloaded")

                    # On amazon.nl the popover lists actual invoice PDFs under /documents/download/
                    # On amazon.com the popover IS the invoice — save it directly
                    download_links = invoice_page.query_selector_all('a[href*="/documents/download/"]')

                    if download_links:
                        # /documents/download/ links are direct PDF files — download bytes directly
                        # using Playwright's request context (shares auth cookies with the browser)
                        for i, dl_link in enumerate(download_links):
                            suffix = f"_{i + 1}" if len(download_links) > 1 else ""
                            dl_file = file_name.replace(".pdf", f"{suffix}.pdf")
                            if os.path.isfile(dl_file):
                                print(f"File [{dl_file}] already exists")
                                continue
                            print(f"Saving file [{dl_file}]")
                            dl_href = dl_link.get_attribute("href")
                            dl_url = f"https://www.{domain}{dl_href}"
                            response = context.request.get(dl_url)
                            with open(dl_file, "wb") as f:
                                f.write(response.body())
                    else:
                        # Direct invoice page (amazon.com style) — render as PDF
                        print(f"Saving file [{file_name}]")
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
