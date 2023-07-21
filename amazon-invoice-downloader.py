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

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException
import random
import time
import os
import json
from docopt import docopt


def sleep():
    # Add human latency

    # Generate a random sleep time between 3 and 5 seconds
    sleep_time = random.uniform(3, 5)
    # Sleep for the generated time
    time.sleep(sleep_time)


def amazon_invoice_downloader(email, password, num_receipts):
    # Ensure the location exists for where we will save our downloads
    target_dir = os.getcwd() + "/" + "downloads"
    os.makedirs(target_dir, exist_ok=True)

    # Create chrome options for saving pages as PDF
    options = webdriver.ChromeOptions()
    settings = {
        "recentDestinations": [
            {
                "id": "Save as PDF",
                "origin": "local",
                "account": "",
            }
        ],
        "selectedDestinationId": "Save as PDF",
        "version": 2,
    }

    prefs = {
        "printing.print_preview_sticky_settings.appState": json.dumps(settings),
        "savefile.default_directory": target_dir,
    }

    options.add_experimental_option("prefs", prefs)
    options.add_argument("--kiosk-printing")

    # Initiate the browser
    driver = webdriver.Chrome(options=options)

    # Open Amazon website
    driver.get("https://www.amazon.com")
    sleep()

    # Click sign in button
    signin_elem = driver.find_element(By.PARTIAL_LINK_TEXT, "sign in")
    signin_elem.click()
    sleep()

    # Enter and submit email
    email_elem = driver.find_element(By.NAME, "email")
    email_elem.send_keys(email)

    continue_elem = driver.find_element(By.ID, "continue")
    continue_elem.click()
    sleep()

    # Enter and submit password
    password_elem = driver.find_element(By.NAME, "password")
    password_elem.send_keys(password)

    submit_elem = driver.find_element(By.ID, "signInSubmit")
    submit_elem.click()
    sleep()

    # Click the orders button
    orders_elem = driver.find_element(By.PARTIAL_LINK_TEXT, "Orders")
    orders_elem.click()
    sleep()

    # Get a list of years from the select options
    select = Select(driver.find_element(By.NAME, "orderFilter"))
    years = [i.text for i in select.options[2:]]  # skip the first two text options

    # Year Loop
    save_count = 0
    for year_select_index in range(2, len(years) + 2):
        if save_count >= num_receipts:
            break

        # Select the right year in the order filter
        Select(driver.find_element(By.NAME, "orderFilter")).select_by_index(year_select_index)
        sleep()

        # Pagination Loop
        while True and save_count <= num_receipts:
            num_invoices_on_page = len(driver.find_elements(By.PARTIAL_LINK_TEXT, "View invoice"))
            # Invoice Loop
            for i in range(num_invoices_on_page):
                invoice_elem = driver.find_elements(By.PARTIAL_LINK_TEXT, "View invoice")[i]
                invoice_elem.click()
                sleep()
                driver.execute_script("window.print();")
                save_count += 1
                driver.back()
                sleep()

            if save_count > num_receipts:
                break

            # Check if there is a next
            if num_invoices_on_page < 10:
                # Then there is not a next page pagination of receipts
                break

            # Go to the next page pagination, and continue downloading
            #   if there is not a next page then break
            try:
                next_elem = driver.find_element(By.PARTIAL_LINK_TEXT, "Next")
                next_elem.click()
            except NoSuchElementException:
                break

    # Close the driver
    driver.quit()


if __name__ == "__main__":
    arguments = docopt(__doc__)

    amazon_invoice_downloader(arguments["<email>"], arguments["<password>"], int(arguments["<num_receipts>"]))
