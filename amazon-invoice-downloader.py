#!/usr/bin/env python

"""Amazon Invoice Downloader

Usage:
  amazon-invoice-downloader.py <email> <password> <num_receipts>
  amazon-invoice-downloader.py (-h | --help)

Arguments:
  email          Amazon login email.
  password       Amazon login password.
  num_receipts   The number of most recent receipts to download.

Options:
  -h --help     Show this screen.
"""

from playwright.sync_api import sync_playwright, TimeoutError
from datetime import datetime
import random
import time
import os
from docopt import docopt


def sleep():
    # Add human latency

    # Generate a random sleep time between 3 and 5 seconds
    sleep_time = random.uniform(2, 5)
    # Sleep for the generated time
    time.sleep(sleep_time)


def amazon_invoice_downloader(playwright, email, password, num_receipts):
    # Ensure the location exists for where we will save our downloads
    target_dir = os.getcwd() + "/" + "downloads"
    os.makedirs(target_dir, exist_ok=True)

    # Create Playwright context with Chromium
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()

    page = context.new_page()
    # page.set_default_timeout(10000)
    page.goto("https://www.amazon.com/")
    page.get_by_role("link", name="Sign in", exact=True).click()

    page.get_by_label("Email").click()
    page.get_by_label("Email").fill(email)
    page.get_by_role("button", name="Continue").click()

    page.get_by_label("Password").click()
    page.get_by_label("Password").fill(password)
    page.get_by_label("Keep me signed in").check()
    page.get_by_role("button", name="Sign in").click()

    page.get_by_role("link", name="Returns & Orders").click()
    sleep()

    # Get a list of years from the select options
    select = page.query_selector('select[name="orderFilter"]')
    years = select.inner_text().split("\n")[2:]  # skip the first two text options

    # Year Loop
    save_count = 0
    for year in years:
        if save_count >= num_receipts:
            break

        # Select the right year in the order filter
        page.locator("#a-autoid-1-announce").click()  # Time Range Dropdown Filter
        page.get_by_role("option", name=year).click()  # Select the year (descending order, most recent first)
        sleep()

        # Pagination Loop
        pagination = 0
        while save_count < num_receipts:
            # Order Loop
            order_cards = page.query_selector_all(".js-order-card")
            for order_card in order_cards:
                if save_count >= num_receipts:
                    break

                print(f"year{year} pagination{pagination} order{save_count}")
                spans = order_card.query_selector_all("span")

                date = datetime.strptime(spans[1].inner_text(), "%B %d, %Y").strftime("%Y%m%d")
                total = spans[3].inner_text().replace("$", "").replace(",", "")  # remove dollar sign and commas
                orderid = spans[9].inner_text()

                file_name = f"{target_dir}/{date}_{total}_amazon_{orderid}.pdf"

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
                save_count += 1

            pagination += 1

            # Go to the next page pagination, and continue downloading
            #   if there is not a next page then break
            try:
                page.get_by_role("link", name="Next →").click()
                sleep()
            except TimeoutError:
                print("Timeout Error")
                break

    # Close the browser
    context.close()
    browser.close()


if __name__ == "__main__":
    arguments = docopt(__doc__)

    with sync_playwright() as playwright:
        amazon_invoice_downloader(
            playwright, arguments["<email>"], arguments["<password>"], int(arguments["<num_receipts>"])
        )
