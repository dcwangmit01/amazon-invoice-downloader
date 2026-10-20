# SPDX-FileCopyrightText: 2023-present David C Wang <dcwangmit01@gmail.com>
#
# SPDX-License-Identifier: MIT

"""
Amazon Invoice Downloader

Usage:
  amazon-invoice-downloader \
    [--manual-login] [--email=<email> --password=<password>] \
    [--all-years | --year=<YYYY> | --date-range=<YYYYMMDD-YYYYMMDD>] \
    [--marketplace=<domain>] [--output-dir=<path>] [--profile-dir=<path>] \
    [--manifest=<path>] \
    [--min-delay=<seconds>] [--max-delay=<seconds>]
  amazon-invoice-downloader (-h | --help)
  amazon-invoice-downloader (-v | --version)

Login Options:
  --manual-login              Always log in interactively; never type stored credentials.
  --email=<email>             Amazon login email [default: $AMAZON_EMAIL].
  --password=<password>       Amazon login password [default: $AMAZON_PASSWORD].

Date Range Options:
  --all-years                 Process every year offered by Amazon's order-history page.
  --date-range=<range>        Inclusive range formatted YYYYMMDD-YYYYMMDD.
  --year=<YYYY>               A single year [default: <CUR_YEAR>].

Marketplace Options:
  --marketplace=<domain>      Amazon storefront: amazon.com, amazon.co.uk, or
                              amazon.fr [default: amazon.com].

Output Options:
  --output-dir=<path>         PDF destination [default: ./downloads].
  --profile-dir=<path>        Persistent Chromium profile [default: ./.amazon-browser-profile].
  --manifest=<path>           CSV progress log; defaults inside the output directory.
  --min-delay=<seconds>       Minimum delay between actions [default: 2].
  --max-delay=<seconds>       Maximum delay between actions [default: 5].

Options:
  -h --help                   Show this screen.
  -v --version                Show version.
"""

from __future__ import annotations

import os
import random
import re
import sys
import time
from pathlib import Path
from docopt import docopt
from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, Playwright, TimeoutError, sync_playwright
from playwright_stealth import Stealth

from ..__about__ import __version__
from ..core import (
    DateWindow,
    Manifest,
    Marketplace,
    absolute_document_url,
    document_links_from_html,
    is_document_menu_link,
    is_document_menu_text,
    is_document_link,
    is_pdf_content,
    marketplace_for,
    option_year,
    parse_date_window,
    parse_order_card,
    parse_order_card_fields,
    pdf_filename,
    preferred_document_links,
)


def load_env_if_needed() -> None:
    """Load a nearby .env only for backward compatibility with the upstream tool."""

    if os.environ.get("AMAZON_EMAIL") and os.environ.get("AMAZON_PASSWORD"):
        return
    current_dir = Path.cwd()
    for _ in range(4):
        env_file = current_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            return
        current_dir = current_dir.parent


def human_pause(min_delay: float, max_delay: float) -> None:
    """A conservative pause reduces load and makes the run easier to interrupt."""

    time.sleep(random.uniform(min_delay, max_delay))


def _credential(value: str | None, environment_name: str) -> str | None:
    if not value or value == f"${environment_name}":
        return os.environ.get(environment_name)
    return value


def _wait_for_order_history(page: Page) -> None:
    """Pause for interactive login/MFA and continue only on a real order page."""

    if page.locator("select#time-filter").count():
        return
    print("\nComplete Amazon login, MFA, or CAPTCHA in the browser window.")
    print("Navigate to 'Returns & Orders' if Amazon does not do so automatically.")
    input("Press Enter here after the order-history page is visible... ")
    # Do not call page.goto() here. Amazon often performs one last asynchronous
    # authentication redirect after MFA; starting another navigation at the
    # same moment causes Playwright's "interrupted by another navigation" error.
    # Locator waits survive page navigations and are therefore race-safe.
    page.locator("select#time-filter").wait_for(state="visible", timeout=60_000)


def _login(
    page: Page,
    email: str | None,
    password: str | None,
    manual_login: bool,
    marketplace: Marketplace,
) -> None:
    page.goto(marketplace.order_history_url, wait_until="domcontentloaded")
    if page.locator("select#time-filter").count():
        return

    # Manual login is the default when either credential is absent.  Passwords
    # should not be put in shell history merely to use this downloader.
    if manual_login or not (email and password):
        _wait_for_order_history(page)
        return

    email_box = page.locator('input[type="email"], input[name="email"]').first
    if email_box.count():
        email_box.fill(email)
        page.get_by_role("button", name=re.compile(r"continue|continuer", re.I)).click()
        page.wait_for_load_state("domcontentloaded")
    password_box = page.locator('input[type="password"], input[name="password"]').first
    if password_box.count():
        password_box.fill(password)
        page.get_by_role("button", name=re.compile(r"sign in|s['’]identifier|connexion", re.I)).click()
        page.wait_for_load_state("domcontentloaded")
    _wait_for_order_history(page)


def _links_from_scope(scope: Locator, marketplace: Marketplace) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    anchors = scope.locator("a")
    for index in range(anchors.count()):
        anchor = anchors.nth(index)
        try:
            label = " ".join(anchor.inner_text().split())
            href = anchor.get_attribute("href")
        except Exception:
            continue
        if is_document_link(label, href):
            links.append((label or "Invoice", absolute_document_url(href, marketplace)))
    return links


def _links_from_invoice_menus(
    card: Locator,
    page: Page,
    marketplace: Marketplace,
) -> list[tuple[str, str]]:
    """Resolve invoice-menu endpoints with the signed-in browser session.

    On the UK and French storefronts the visible ``Invoice``/``Facture``
    control points to an HTML fragment containing the actual document links.
    Navigating to that endpoint and printing it creates a PDF containing only
    link names.  BrowserContext.request shares the browser's cookies, allowing
    us to inspect the fragment without opening or printing the menu itself.
    """

    links: list[tuple[str, str]] = []
    seen_menu_urls: set[str] = set()
    anchors = card.locator("a")
    for index in range(anchors.count()):
        try:
            href = anchors.nth(index).get_attribute("href")
        except Exception:
            continue
        if not is_document_menu_link(href):
            continue

        menu_url = absolute_document_url(href, marketplace)
        if menu_url in seen_menu_urls:
            continue
        seen_menu_urls.add(menu_url)

        try:
            response = page.context.request.get(menu_url, timeout=30_000)
            try:
                if not response.ok:
                    print("Warning: Amazon's invoice menu returned " f"HTTP {response.status} for {menu_url}")
                    continue
                menu_html = response.text()
            finally:
                # APIRequestContext otherwise retains response bodies until
                # the browser context closes, which adds up over many years.
                try:
                    response.dispose()
                except Exception:
                    pass
            menu_links = document_links_from_html(menu_html, marketplace.base_url)
            if not menu_links:
                print(f"Warning: Amazon's invoice menu contained no links: {menu_url}")
            links.extend(menu_links)
        except Exception as exc:
            # Keep a long archival run moving. The order will be recorded as
            # no_invoice_link if neither this endpoint nor a UI fallback works.
            print(f"Warning: could not read Amazon's invoice menu {menu_url}: {exc}")
    return links


def _document_links(card: Locator, page: Page, marketplace: Marketplace) -> list[tuple[str, str]]:
    """Collect direct links and links revealed by Amazon's invoice popover.

    Amazon has used both a direct "View invoice" link and a JavaScript popover
    containing "Invoice 1" / "Printable Order Summary" links.  Scanning the
    order card first prevents accidentally assigning another order's invoice.
    """

    links = _links_from_scope(card, marketplace)
    links.extend(_links_from_invoice_menus(card, page, marketplace))
    toggles = card.locator("a").filter(
        has_text=re.compile(
            r"^\s*(?:view\s+(?:or\s+print\s+)?invoice|invoice|" r"afficher\s+la\s+facture|facture)\s*$",
            re.I,
        )
    )
    for index in range(toggles.count()):
        toggle = toggles.nth(index)
        href = toggle.get_attribute("href")
        # Normal URLs were handled above, including UK/FR invoice-menu
        # endpoints. Clicking is retained only for JavaScript-only variants.
        if href and not href.startswith(("javascript:", "#")):
            continue
        try:
            toggle.click()
            # Popovers are attached near the document root rather than nested
            # inside the order card, so only inspect currently visible ones.
            popovers = page.locator(".a-popover:visible, .a-popover-wrapper:visible")
            popovers.first.wait_for(state="visible", timeout=10_000)
            for popover_index in range(popovers.count()):
                links.extend(_links_from_scope(popovers.nth(popover_index), marketplace))
        except Exception:
            # A failed popover is recorded later as a missing-link order; it
            # should not terminate a multi-year archival run.
            pass
        finally:
            # Close the current menu before scanning the next order. Otherwise
            # an older visible popover could be mistaken for that order's menu.
            page.keyboard.press("Escape")

    # Orders can expose a printable summary, one or more invoices, credit
    # notes, and an invoice-request form. Download every real invoice; use the
    # printable summary only when Amazon exposes no invoice for the order.
    return preferred_document_links(links)


def _order_cards(page: Page) -> Locator:
    # The first selector is Amazon's 2025 markup; fallbacks cover older layouts.
    selectors = [".order-card.js-order-card", ".order-card", "div.order"]
    for selector in selectors:
        cards = page.locator(selector)
        if cards.count():
            return cards
    return page.locator(".order-card.js-order-card")


def _wait_for_order_page(page: Page, selected_value: str | None = None) -> None:
    """Wait until a newly navigated order-history document is usable.

    Waiting only for ``domcontentloaded`` is insufficient on Amazon.fr: the
    year selector can initiate its navigation slightly after Playwright checks
    the current document's load state. Locator and JavaScript waits below are
    evaluated again after navigation, avoiding stale execution contexts.
    """

    select = page.locator("select#time-filter")
    select.wait_for(state="visible", timeout=60_000)
    if selected_value is not None:
        page.wait_for_function(
            """value => {
                const select = document.querySelector('select#time-filter');
                return select && select.value === value;
            }""",
            arg=selected_value,
            timeout=60_000,
        )


def _select_year(page: Page, select_value: str) -> None:
    """Select a year while explicitly synchronizing with Amazon's navigation."""

    select = page.locator("select#time-filter")
    try:
        # Register the navigation listener before changing the option; calling
        # wait_for_load_state only afterwards can miss a delayed navigation.
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30_000):
            select.select_option(value=select_value)
    except TimeoutError:
        # Some Amazon variants update the order list in place. In that case no
        # document navigation is expected, and the selected-value wait below
        # is the authoritative readiness check.
        pass
    _wait_for_order_page(page, select_value)


def _next_page(page: Page) -> bool:
    next_link = page.locator("li.a-last:not(.a-disabled) a, .a-pagination .a-last:not(.a-disabled) a").first
    if not next_link.count():
        return False
    try:
        # Pagination is normally a full navigation. Register first so a fast
        # response cannot finish before the wait begins.
        with page.expect_navigation(wait_until="domcontentloaded", timeout=60_000):
            next_link.click()
    except TimeoutError:
        # Retain compatibility with an AJAX pagination variant, then confirm
        # that the order-history controls are attached to a live document.
        pass
    _wait_for_order_page(page)
    return True


def _save_document(
    page: Page,
    url: str,
    destination: Path,
    paper_format: str,
) -> None:
    # UK and French invoices are often served as an existing PDF. Calling
    # page.pdf() on Chromium's built-in PDF viewer prints the viewer surface,
    # producing a tiny blank/black PDF. Fetch through BrowserContext.request,
    # which shares the signed-in browser cookies, and preserve Amazon's bytes.
    response = None
    try:
        response = page.context.request.get(
            url,
            headers={"Referer": page.url},
            timeout=60_000,
        )
        if response.ok:
            content = response.body()
            if is_pdf_content(content):
                destination.write_bytes(content)
                return
        else:
            print("Warning: direct invoice download returned " f"HTTP {response.status}; trying browser printing")
    except Exception as exc:
        # Some older Amazon document endpoints work only as browser
        # navigations. Keep the original HTML print path as a fallback.
        print(f"Warning: direct invoice download failed; trying browser printing: {exc}")
    finally:
        if response is not None:
            try:
                response.dispose()
            except Exception:
                pass

    invoice_page = page.context.new_page()
    try:
        invoice_page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        # A login redirect here would otherwise create a convincing but useless
        # PDF.  Stop and let the manifest identify the affected document.
        if invoice_page.locator('input[type="password"], input[name="password"]').count():
            raise RuntimeError("Invoice page redirected to Amazon sign-in")
        if is_document_menu_link(invoice_page.url):
            raise RuntimeError("Document URL resolved to Amazon's invoice-link menu")
        body_text = invoice_page.locator("body").inner_text(timeout=30_000)
        if is_document_menu_text(body_text):
            raise RuntimeError("Document page contains invoice links instead of an invoice")
        invoice_page.pdf(
            path=str(destination),
            format=paper_format,
            print_background=True,
            margin={"top": ".5in", "right": ".5in", "bottom": ".5in", "left": ".5in"},
        )
    finally:
        invoice_page.close()


def _process_year(
    page: Page,
    year: int,
    select_value: str,
    window: DateWindow,
    marketplace: Marketplace,
    output_dir: Path,
    manifest: Manifest,
    min_delay: float,
    max_delay: float,
) -> None:
    _select_year(page, select_value)
    human_pause(min_delay, max_delay)
    page_number = 1

    while True:
        cards = _order_cards(page)
        # Count once per page. A second count previously created a narrow race
        # in which a late Amazon.fr navigation invalidated the first locator.
        card_count = cards.count()
        print(f"Year {year}, page {page_number}: {card_count} order cards")
        if card_count == 0:
            # An empty year cannot have another results page. Returning here
            # also avoids querying pagination while Amazon settles its
            # empty-results layout.
            return
        for card_index in range(card_count):
            card = cards.nth(card_index)
            card_text = ""
            try:
                card_text = card.inner_text()
                summary = parse_order_card(card_text)
            except Exception as exc:
                # Preserve any independently parseable ID/date/total. This is
                # enough to reconcile unusual cards without storing customer
                # addresses or product text in the diagnostic manifest.
                try:
                    fields = parse_order_card_fields(card_text)
                    order_id = fields.order_id or ""
                    order_date = fields.order_date.isoformat() if fields.order_date else ""
                    order_total = fields.total or ""
                except Exception:
                    order_id = ""
                    order_date = ""
                    order_total = ""
                manifest.append(
                    status="parse_error",
                    year=year,
                    page=page_number,
                    order_date=order_date,
                    order_total=order_total,
                    order_id=order_id,
                    error=str(exc),
                )
                continue
            base = dict(
                year=year,
                page=page_number,
                order_date=summary.order_date.isoformat(),
                order_total=summary.total,
                order_id=summary.order_id,
            )
            if summary.cancelled:
                manifest.append(status="cancelled", **base)
                continue
            if not window.contains(summary.order_date):
                manifest.append(status="outside_date_range", **base)
                continue

            links = _document_links(card, page, marketplace)
            if not links:
                manifest.append(status="no_invoice_link", **base)
                continue

            for document_index, (label, url) in enumerate(links, start=1):
                filename = pdf_filename(summary, document_index, marketplace.currency)
                destination = output_dir / filename
                details = dict(
                    **base,
                    document_index=document_index,
                    document_label=label,
                    document_url=url,
                    pdf_path=str(destination.resolve()),
                )
                if destination.exists() and destination.stat().st_size > 0:
                    print(f"Already downloaded: {filename}")
                    manifest.append(status="skipped_existing", **details)
                    continue
                try:
                    print(f"Saving: {filename} ({label})")
                    _save_document(page, url, destination, marketplace.paper_format)
                    manifest.append(status="saved", **details)
                except Exception as exc:
                    # Remove partial output so a later run can retry it.
                    destination.unlink(missing_ok=True)
                    manifest.append(status="download_error", error=repr(exc), **details)
                human_pause(min_delay, max_delay)

        if not _next_page(page):
            return
        page_number += 1
        human_pause(min_delay, max_delay)


def run(playwright: Playwright, args: dict[str, object]) -> None:
    email = _credential(args.get("--email"), "AMAZON_EMAIL")
    password = _credential(args.get("--password"), "AMAZON_PASSWORD")
    window = parse_date_window(bool(args["--all-years"]), args.get("--year"), args.get("--date-range"))
    marketplace = marketplace_for(str(args["--marketplace"]))
    output_dir = Path(str(args["--output-dir"])).expanduser().resolve()
    profile_dir = Path(str(args["--profile-dir"])).expanduser().resolve()
    manifest_arg = args.get("--manifest")
    manifest_path = (
        Path(str(manifest_arg)).expanduser().resolve() if manifest_arg else output_dir / "download-manifest.csv"
    )
    min_delay = float(args["--min-delay"])
    max_delay = float(args["--max-delay"])
    if min_delay < 0 or max_delay < min_delay:
        raise ValueError("Delays must satisfy 0 <= --min-delay <= --max-delay")
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(manifest_path)

    # A persistent context retains Amazon cookies between runs.  It also avoids
    # remote debugging and --disable-web-security, both of which unnecessarily
    # weaken the browser used to access a sensitive account.
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        accept_downloads=True,
    )
    try:
        page = context.pages[0] if context.pages else context.new_page()
        Stealth().apply_stealth_sync(page)
        _login(page, email, password, bool(args["--manual-login"]), marketplace)

        select = page.locator("select#time-filter")
        # Some storefronts populate the year options after the select itself is
        # visible. Labels are localized, but either the label or value should
        # eventually contain a four-digit year.
        try:
            page.wait_for_function(
                r"""() => Array.from(document.querySelectorAll('select#time-filter option'))
                .some(option => /(?:19|20)\d{2}/.test(
                    `${option.textContent || ''} ${option.value || ''}`))""",
                timeout=15_000,
            )
        except TimeoutError:
            # Continue to the diagnostic below so a changed Amazon UI produces
            # useful option labels instead of an opaque Playwright timeout.
            pass

        option_values: dict[int, str] = {}
        option_descriptions: list[str] = []
        options = select.locator("option")
        for index in range(options.count()):
            option = options.nth(index)
            text = option.inner_text().strip()
            value = option.get_attribute("value") or ""
            option_descriptions.append(f"{text!r} ({value!r})")
            year = option_year(text, value)
            if year is not None:
                option_values[year] = value or f"year-{year}"

        years = sorted(
            (year for year in option_values if window.includes_year(year)),
            reverse=True,
        )
        if not years:
            observed = ", ".join(option_descriptions) or "none"
            raise RuntimeError(
                "Amazon did not offer any order-history years matching the "
                f"requested range. Observed options: {observed}"
            )

        print(
            f"Processing {len(years)} year(s) from {marketplace.domain} "
            f"in {marketplace.currency}: {', '.join(map(str, years))}"
        )
        for year in years:
            _process_year(
                page,
                year,
                option_values[year],
                window,
                marketplace,
                output_dir,
                manifest,
                min_delay,
                max_delay,
            )
    finally:
        context.close()


def amazon_invoice_downloader() -> int:
    load_env_if_needed()
    args = docopt(__doc__, version=__version__)
    try:
        with sync_playwright() as playwright:
            run(playwright, args)
    except (ValueError, RuntimeError, TimeoutError, PlaywrightError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
