# SPDX-FileCopyrightText: 2023-present David C Wang <dcwangmit01@gmail.com>
#
# SPDX-License-Identifier: MIT
import sys

if __name__ == "__main__":
    from amazon_invoice_downloader.cli import amazon_invoice_downloader

    sys.exit(amazon_invoice_downloader())
