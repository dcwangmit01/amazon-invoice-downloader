# SPDX-FileCopyrightText: 2023-present David C Wang <dcwangmit01@gmail.com>
#
# SPDX-License-Identifier: MIT

"""
Amazon Invoice Downloader

Usage:
  amazon-invoice-downloader.py \
    [--email=<email> --password=<password>] \
    [--year=<YYYY> | --date-range=<YYYYMMDD-YYYYMMDD>] \
    [--request-only]
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
  --request-only           Nur 'Rechnung anfordern'-Bestellungen abarbeiten (normale Downloads überspringen).

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

    # Request-only mode: skip normal downloads, only process "Rechnung anfordern"
    request_only = args.get("--request-only", False)

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

    # Navigate directly to order history - Amazon redirects to login if needed
    page.goto("https://www.amazon.de/gp/css/order-history")
    page.wait_for_load_state("domcontentloaded")
    sleep()

    # Try to login if redirected to sign-in page
    email_field = page.query_selector('#ap_email')
    if email_field and email:
        email_field.fill(email)
        continue_btn = page.query_selector('#continue')
    # Handle login - credentials from .env or manual entry
    # If on signin page, try auto-fill; otherwise user logs in manually
    try:
        email_field = page.query_selector('#ap_email')
        if email_field and email:
            email_field.fill(email)
            cont = page.query_selector('#continue')
            if cont:
                cont.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2)
    except Exception:
        pass

    try:
        pw_field = page.query_selector('#ap_password')
        if pw_field and password:
            pw_field.fill(password)
            signin = page.query_selector('#signInSubmit')
            if signin:
                signin.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(2)
    except Exception:
        pass

    # Wait until we leave any auth/login page (2FA, CAPTCHA, signin)
    print(f"📍 URL after login attempt: {page.url}")
    auth_pages = ['ap/mfa', 'ap/cvf', 'ap/challenge', 'ap/signin', 'ap/forgotpassword', 'ax/claim', 'chrome-error://']
    printed_msg = False
    waited = 0
    while waited < 300:
        try:
            current_url = page.evaluate("window.location.href")
        except Exception:
            try:
                current_url = page.url
            except Exception:
                current_url = ""
        if not any(x in current_url for x in auth_pages):
            break
        if not printed_msg:
            print("🔐 Auth/Login page detected - please complete in browser...")
            printed_msg = True
        time.sleep(3)
        waited += 3
    print(f"✅ Auth complete (URL: {page.url})")

    # Navigate to order history
    page.goto("https://www.amazon.de/your-orders/orders")
    page.wait_for_load_state("domcontentloaded")
    time.sleep(5)
    print(f"📍 Orders page: {page.url}")

    # Get a list of years from the select options - try multiple selectors
    select = (
        page.query_selector("select#time-filter")
        or page.query_selector("select#orderFilter")
        or page.query_selector("select[name='timeFilter']")
        or page.query_selector("select[name='orderFilter']")
    )
    if not select:
        print("⚠️ Time filter not found. Debugging page...")
        print(f"  Page title: {page.title()}")
        print(f"  URL: {page.url}")
        all_selects = page.query_selector_all("select")
        print(f"  Found {len(all_selects)} select elements:")
        for i, s in enumerate(all_selects):
            try:
                sid = s.get_attribute('id') or 'no-id'
                sname = s.get_attribute('name') or 'no-name'
                stext = s.inner_text()[:200].replace('\n', ' | ')
                print(f"    [{i}] id={sid}, name={sname}, options={stext}")
            except Exception as e:
                print(f"    [{i}] error reading: {e}")
        raise Exception("Could not find time filter - see debug output above")
    years = select.inner_text().split("\n")  # skip the first two text options

    # Filter years to include only numerical years (YYYY)
    years = [year for year in years if year.isnumeric()]

    # Filter years to the include only the years between start_date and end_date inclusively
    years = [year for year in years if start_date.year <= int(year) <= end_date.year]
    years.sort(reverse=True)

    # Year Loop (Run backwards through the time range from years to pages to orders)
    for year in years:
        # Select the year in the order filter
        print(f"🔍 Selecting year: year-{year}")
        try:
            select.select_option(value=f"year-{year}")
            time.sleep(3)
            print(f"📍 After filter: {page.evaluate('window.location.href')}")
        except Exception as e:
            print(f"❌ Select failed: {e}")
            # Fallback: navigate directly
            page.goto(f"https://www.amazon.de/your-orders/orders?timeFilter=year-{year}")
            time.sleep(5)
            print(f"📍 After direct nav: {page.evaluate('window.location.href')}")
        sleep()

        # Collect orders with "Rechnung anfordern" for batch processing at the end
        pending_requests = []

        if request_only:
            print()
            print(f"  ⚡ REQUEST-ONLY Modus: Nur 'Rechnung anfordern'-Bestellungen werden gesucht")
            print()

        # Page Loop - URL-based pagination (Weiter-Button unreliable on amazon.de)
        page_index = 0
        while True:
            if page_index > 0:
                page_url = f"https://www.amazon.de/your-orders/orders?timeFilter=year-{year}&startIndex={page_index}"
                print(f"  📄 Loading page: startIndex={page_index}")
                page.goto(page_url)
                sleep()

            # Check if we have order cards on this page
            order_cards_check = page.query_selector_all(".order-card.js-order-card")
            if not order_cards_check:
                print(f"  ✅ No more orders found at startIndex={page_index}")
                break
            print(f"  📦 Found {len(order_cards_check)} orders on page (startIndex={page_index})")

            # Order Loop
            order_cards = page.query_selector_all(".order-card.js-order-card")
            for order_card in order_cards:
                # Parse the order card to create the date and file_name
                spans = order_card.query_selector_all("span")
                # Debug:
                # for i,s in enumerate(spans): print(f"  span[{i}]: {s.inner_text()[:80]}")

                # Skip cancelled orders
                if spans[4].inner_text().strip().lower() in ["cancelled", "storniert"]:
                    continue

                # Parse German date format (e.g. "1. Januar 2025")
                date_text = spans[1].inner_text().strip()
                try:
                    date = datetime.strptime(date_text, "%B %d, %Y")
                except ValueError:
                    try:
                        # German: "1. Januar 2025" or "01. Januar 2025"
                        months_de = {
                            "Januar": 1,
                            "Februar": 2,
                            "März": 3,
                            "April": 4,
                            "Mai": 5,
                            "Juni": 6,
                            "Juli": 7,
                            "August": 8,
                            "September": 9,
                            "Oktober": 10,
                            "November": 11,
                            "Dezember": 12,
                        }
                        parts = date_text.replace(".", "").split()
                        day = int(parts[0])
                        month = months_de.get(parts[1], 1)
                        year_val = int(parts[2])
                        date = datetime(year_val, month, day)
                    except Exception:
                        print(f"⚠️ Could not parse date: {date_text}, skipping")
                        continue
                total = (
                    spans[3].inner_text().replace("EUR", "").replace("€", "").replace(".", "").replace(",", ".").strip()
                )  # handle EUR format
                orderid = spans[8].inner_text()
                date_str = date.strftime("%Y%m%d")
                # Sanitize orderid: remove newlines, limit length
                orderid = orderid.replace("\n", " ").strip()[:60]
                orderid = "".join(c for c in orderid if c.isalnum() or c in " -_").strip()

                # Extract product name(s) from order card for better filenames
                product_name = ""
                try:
                    # Try multiple selectors - Amazon uses different structures
                    product_links = (
                        order_card.query_selector_all('a[href*="/dp/"]')
                        or order_card.query_selector_all('a[href*="/gp/product/"]')
                        or order_card.query_selector_all('.yohtmlc-product-title')
                        or order_card.query_selector_all('[class*="product-title"]')
                        or order_card.query_selector_all('[class*="item-title"]')
                    )
                    names = []
                    if product_links:
                        for pl in product_links:
                            name = pl.inner_text().strip()
                            if name and len(name) > 2 and name not in names:
                                names.append(name)
                    # Fallback: look for all links inside order card, filter out navigation/action links
                    if not names:
                        all_links = order_card.query_selector_all("a")
                        skip_texts = [
                            "rechnung", "invoice", "bestelldetails", "order details",
                            "archiv", "stornieren", "cancel", "zurück", "return",
                            "problem", "hilfe", "help", "nochmal", "bewert",
                            "review", "schreib", "write", "tracking", "sendung",
                            "artikel", "erneut", "kaufen", "buy again",
                        ]
                        for al in all_links:
                            name = al.inner_text().strip()
                            href = al.get_attribute("href") or ""
                            if not name or len(name) < 4 or len(name) > 200:
                                continue
                            if any(s in name.lower() for s in skip_texts):
                                continue
                            # Product links typically go to /dp/ or /gp/ or have long titles
                            if "/dp/" in href or "/gp/" in href or len(name) > 15:
                                if name not in names:
                                    names.append(name)
                    if names:
                        product_name = " + ".join(names)
                        if len(product_name) > 80:
                            product_name = product_name[:77] + "..."
                except Exception:
                    pass

                # Sanitize product name for filename
                if product_name:
                    safe_name = "".join(c for c in product_name if c.isalnum() or c in " -_+äöüÄÖÜß.,").strip()
                    file_name = f"{target_dir}/{date_str}_{total}_amazon_{safe_name}.pdf"
                    print(f"  🏷️ Product: {product_name[:60]}")
                else:
                    file_name = f"{target_dir}/{date_str}_{total}_amazon_{orderid}.pdf"
                    print(f"  🏷️ No product name found, using order ID: {orderid}")

                if date > end_date:
                    continue
                elif date < start_date:
                    done = True
                    break

                if os.path.isfile(file_name):
                    if not request_only:
                        print(f"File [{file_name}] already exists")
                    # File exists = invoice already downloaded, skip in all modes
                    continue

                if True:
                    if request_only:
                        print(f"  🔍 Checking for 'Rechnung anfordern'...")
                    else:
                        print(f"Saving file [{file_name}]")
                    # Save - find invoice link (German: "Rechnung", English: "View invoice")
                    invoice_link = (
                        order_card.query_selector('xpath=//a[contains(text(), "Rechnung")]')
                        or order_card.query_selector('xpath=//a[contains(text(), "View invoice")]')
                        or order_card.query_selector('xpath=//a[contains(text(), "Invoice")]')
                    )
                    if not invoice_link:
                        if not request_only:
                            print(f"  ⚠️ No invoice link found for order {file_name}, skipping")
                        continue
                    href = invoice_link.get_attribute("href")
                    if href.startswith("http"):
                        link = href
                    else:
                        link = "https://www.amazon.de/" + href
                    invoice_page = context.new_page()
                    invoice_page.set_viewport_size({"width": 1920, "height": 1080})
                    invoice_page.goto(link)
                    time.sleep(3)
                    # Check if this order only has "Rechnung anfordern" (no existing invoice)
                    # If so, collect for later — after all normal downloads are done,
                    # we'll go through these and let the user request them one by one.
                    try:
                        request_btns = invoice_page.query_selector_all('a:has-text("Rechnung anfordern"), a:has-text("Request invoice")')
                        existing_invoices = [
                            btn for btn in invoice_page.query_selector_all('a:has-text("Rechnung")')
                            if "anfordern" not in btn.inner_text().lower()
                            and "request" not in btn.inner_text().lower()
                        ]
                        if request_btns and not existing_invoices:
                            # No downloadable invoice yet — save for later processing
                            pending_requests.append({
                                "date_str": date_str,
                                "total": total,
                                "product_name": product_name or orderid,
                                "file_name": file_name,
                                "url": invoice_page.url,
                            })
                            # Also log immediately to file (in case process dies)
                            log_file = os.path.join(target_dir, "rechnung_anfordern.txt")
                            log_line = f"{date_str} | {total} EUR | {product_name or orderid} | {invoice_page.url}"
                            existing_lines = set()
                            if os.path.exists(log_file):
                                with open(log_file, "r") as lf:
                                    existing_lines = set(lf.read().splitlines())
                            if log_line not in existing_lines:
                                with open(log_file, "a") as lf:
                                    if not existing_lines:
                                        lf.write("# Bestellungen mit 'Rechnung anfordern'\n\n")
                                    lf.write(log_line + "\n")
                            print(f"  📋 'Rechnung anfordern' — wird am Ende gesammelt abgearbeitet")
                            invoice_page.close()
                            continue
                    except Exception as e:
                        print(f"  ⚠️ Invoice request check failed: {e}")
                    # In request-only mode, skip actual downloads
                    if request_only:
                        invoice_page.close()
                        continue
                    # Find ALL invoice links (orders can have multiple invoices)
                    # Exclude "Rechnung anfordern" links - only get actual download links
                    all_rechnung_links = invoice_page.query_selector_all('a:has-text("Rechnung")')
                    invoice_btns = [
                        btn for btn in all_rechnung_links
                        if "anfordern" not in btn.inner_text().lower()
                        and "request" not in btn.inner_text().lower()
                    ]
                    if not invoice_btns:
                        invoice_btns = invoice_page.query_selector_all('a[href*="invoice"]')
                    if invoice_btns:
                        print(f"  📄 Found {len(invoice_btns)} invoice(s)")
                        for inv_idx, invoice_btn in enumerate(invoice_btns):
                            invoice_href = invoice_btn.get_attribute("href")
                            if not invoice_href:
                                continue
                            if not invoice_href.startswith("http"):
                                invoice_href = "https://www.amazon.de" + invoice_href
                            # Build filename - for multiple invoices, try to get
                            # context from surrounding text (seller name, amount)
                            if len(invoice_btns) > 1:
                                inv_label = ""
                                try:
                                    # Try to get context from parent element (often contains seller/amount)
                                    parent = invoice_btn.evaluate_handle("el => el.closest('div, tr, li, td')")
                                    if parent:
                                        parent_text = parent.inner_text().replace("\n", " ").strip()
                                        # Extract useful info: look for seller or amount
                                        # Remove generic words
                                        for remove in ["Rechnung", "Invoice", "herunterladen", "download", "PDF"]:
                                            parent_text = parent_text.replace(remove, "")
                                        inv_label = parent_text.strip()[:60]
                                        inv_label = "".join(c for c in inv_label if c.isalnum() or c in " -_äöüÄÖÜß.,").strip()
                                except Exception:
                                    pass
                                if inv_label and len(inv_label) > 3:
                                    inv_file_name = f"{target_dir}/{date_str}_{total}_amazon_{orderid}_{inv_label}.pdf"
                                else:
                                    inv_file_name = f"{target_dir}/{date_str}_{total}_amazon_{orderid}_{inv_idx + 1}.pdf"
                            else:
                                inv_file_name = file_name
                            # Download the PDF directly via fetch (avoids PDF viewer capture)
                            print(f"  📥 Downloading invoice {inv_idx + 1}/{len(invoice_btns)}...")
                            inv_saved = False
                            try:
                                pdf_data = invoice_page.evaluate("""
                                    async (url) => {
                                        const response = await fetch(url, {credentials: 'include'});
                                        const contentType = response.headers.get('content-type') || '';
                                        const buffer = await response.arrayBuffer();
                                        return {
                                            contentType: contentType,
                                            data: Array.from(new Uint8Array(buffer))
                                        };
                                    }
                                """, invoice_href)
                                if 'pdf' in pdf_data['contentType'].lower():
                                    with open(inv_file_name, 'wb') as f:
                                        f.write(bytes(pdf_data['data']))
                                    inv_saved = True
                                    print(f"  ✅ Saved (direct PDF download): {os.path.basename(inv_file_name)}")
                                else:
                                    print(f"  📄 HTML invoice, using page.pdf()...")
                                    inv_page = context.new_page()
                                    inv_page.set_viewport_size({"width": 1920, "height": 1080})
                                    inv_page.goto(invoice_href)
                                    time.sleep(3)
                                    inv_page.pdf(
                                        path=inv_file_name,
                                        format="A4",
                                        print_background=True,
                                        margin={"top": ".5in", "right": ".5in", "bottom": ".5in", "left": ".5in"},
                                    )
                                    inv_page.close()
                                    inv_saved = True
                                    print(f"  ✅ Saved (page print): {os.path.basename(inv_file_name)}")
                            except Exception as e:
                                print(f"  ⚠️ Invoice {inv_idx + 1} download failed: {e}")
                                if not inv_saved:
                                    try:
                                        inv_page = context.new_page()
                                        inv_page.set_viewport_size({"width": 1920, "height": 1080})
                                        inv_page.goto(invoice_href)
                                        time.sleep(3)
                                        inv_page.pdf(
                                            path=inv_file_name,
                                            format="A4",
                                            print_background=True,
                                            margin={"top": ".5in", "right": ".5in", "bottom": ".5in", "left": ".5in"},
                                        )
                                        inv_page.close()
                                        print(f"  ✅ Saved (fallback): {os.path.basename(inv_file_name)}")
                                    except Exception as e2:
                                        print(f"  ❌ Could not save invoice {inv_idx + 1}: {e2}")
                            sleep()
                    else:
                        print(f"  ⚠️ No invoice links found on intermediate page, saving page as-is")
                        invoice_page.pdf(
                            path=file_name,
                            format="A4",
                            print_background=True,
                            margin={"top": ".5in", "right": ".5in", "bottom": ".5in", "left": ".5in"},
                        )
                        print(f"  ✅ Saved (page print)!")
                    invoice_page.close()

            # Next page
            page_index += 10

    # Process pending "Rechnung anfordern" orders
    if pending_requests:
        print()
        print(f"  ╔══════════════════════════════════════════════════════════════╗")
        print(f"  ║  📋 {len(pending_requests)} Bestellung(en) mit 'Rechnung anfordern'          ║")
        print(f"  ║  Bitte jeweils im Browser die Rechnung beantragen.          ║")
        print(f"  ║  Nach jeder Beantragung Enter drücken zum Fortfahren.       ║")
        print(f"  ║  Oder 's' + Enter zum Überspringen einer Bestellung.        ║")
        print(f"  ╚══════════════════════════════════════════════════════════════╝")
        print()

        # Log file was already written inline during the main loop
        log_file = os.path.join(target_dir, "rechnung_anfordern.txt")
        print(f"  📋 Protokoll: {log_file}")
        print()

        for idx, pr in enumerate(pending_requests):
            print(f"  ── Rechnung anfordern {idx + 1}/{len(pending_requests)} ──")
            print(f"  📅 {pr['date_str']}  💰 {pr['total']} EUR  🏷️ {pr['product_name'][:50]}")

            # Open the intermediate page in the browser
            req_page = context.new_page()
            req_page.set_viewport_size({"width": 1920, "height": 1080})
            req_page.goto(pr["url"])
            time.sleep(2)

            # Click the "Rechnung anfordern" button to start the Amazon assistant
            try:
                request_btns = req_page.query_selector_all('a:has-text("Rechnung anfordern"), a:has-text("Request invoice")')
                if request_btns:
                    request_btns[0].click()
                    time.sleep(2)
            except Exception:
                pass

            print(f"  👉 Bitte im Browser die Rechnung beantragen...")
            user_input = input(f"  ⏎ Enter wenn fertig (oder 's' zum Überspringen): ").strip().lower()

            if user_input == 's':
                print(f"  ⏭️ Übersprungen")
                req_page.close()
                continue

            # Reload and try to download the now-available invoice
            print(f"  🔄 Seite wird neu geladen...")
            req_page.reload()
            time.sleep(3)

            # Look for invoice links
            all_rechnung_links = req_page.query_selector_all('a:has-text("Rechnung")')
            invoice_btns = [
                btn for btn in all_rechnung_links
                if "anfordern" not in btn.inner_text().lower()
                and "request" not in btn.inner_text().lower()
            ]
            if not invoice_btns:
                invoice_btns = req_page.query_selector_all('a[href*="invoice"]')

            if invoice_btns:
                print(f"  📄 Found {len(invoice_btns)} invoice(s)")
                for inv_idx, invoice_btn in enumerate(invoice_btns):
                    invoice_href = invoice_btn.get_attribute("href")
                    if not invoice_href:
                        continue
                    if not invoice_href.startswith("http"):
                        invoice_href = "https://www.amazon.de" + invoice_href

                    inv_file_name = pr["file_name"]
                    if len(invoice_btns) > 1:
                        base, ext = os.path.splitext(inv_file_name)
                        inv_file_name = f"{base}_{inv_idx + 1}{ext}"

                    print(f"  📥 Downloading invoice {inv_idx + 1}/{len(invoice_btns)}...")
                    try:
                        pdf_data = req_page.evaluate("""
                            async (url) => {
                                const response = await fetch(url, {credentials: 'include'});
                                const contentType = response.headers.get('content-type') || '';
                                const buffer = await response.arrayBuffer();
                                return {
                                    contentType: contentType,
                                    data: Array.from(new Uint8Array(buffer))
                                };
                            }
                        """, invoice_href)
                        if 'pdf' in pdf_data['contentType'].lower():
                            with open(inv_file_name, 'wb') as f:
                                f.write(bytes(pdf_data['data']))
                            print(f"  ✅ Saved: {os.path.basename(inv_file_name)}")
                        else:
                            inv_page = context.new_page()
                            inv_page.set_viewport_size({"width": 1920, "height": 1080})
                            inv_page.goto(invoice_href)
                            time.sleep(3)
                            inv_page.pdf(
                                path=inv_file_name,
                                format="A4",
                                print_background=True,
                                margin={"top": ".5in", "right": ".5in", "bottom": ".5in", "left": ".5in"},
                            )
                            inv_page.close()
                            print(f"  ✅ Saved (page print): {os.path.basename(inv_file_name)}")
                    except Exception as e:
                        print(f"  ❌ Download failed: {e}")
            else:
                print(f"  ⚠️ Keine Rechnungs-Links gefunden — Rechnung evtl. noch nicht bereit")

            req_page.close()

        print(f"\n  📋 Protokoll gespeichert: {log_file}")

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
