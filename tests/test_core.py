import re
from datetime import date
from pathlib import Path

from amazon_invoice_downloader.core import (
    DateWindow,
    Manifest,
    absolute_document_url,
    available_years,
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


SAMPLE_CARD = """
ORDER PLACED
January 5, 2010
TOTAL
$1,234.56
SHIP TO
Example Customer
ORDER # 123-1234567-1234567
View invoice
"""

FRENCH_CARD = """
COMMANDE EFFECTUÉE LE
24 juillet 2024
TOTAL DE LA COMMANDE
1 234,56 €
N° DE COMMANDE 234-2345678-2345678
Afficher la facture
"""

UK_CARD = """
ORDER PLACED
5 January 2023
ORDER TOTAL
£987.65
ORDER # 345-3456789-3456789
View invoice
"""


def test_parse_order_card_uses_labels_not_span_positions():
    order = parse_order_card(SAMPLE_CARD)
    assert order.order_id == "123-1234567-1234567"
    assert order.order_date == date(2010, 1, 5)
    assert order.total == "1234.56"
    assert not order.cancelled


def test_cancelled_order_is_detected():
    assert parse_order_card(SAMPLE_CARD + "\nCancelled\n").cancelled


def test_cancelled_order_does_not_require_a_total():
    card_without_total = re.sub(r"TOTAL\s*\$1,234\.56", "", SAMPLE_CARD)
    order = parse_order_card(card_without_total + "\nCancelled\n")
    assert order.cancelled
    assert order.total == "0.00"


def test_partial_order_fields_survive_a_missing_total():
    card_without_total = re.sub(r"TOTAL\s*\$1,234\.56", "", SAMPLE_CARD)
    fields = parse_order_card_fields(card_without_total)
    assert fields.order_id == "123-1234567-1234567"
    assert fields.order_date == date(2010, 1, 5)
    assert fields.total is None
    assert not fields.cancelled


def test_french_order_card_and_decimal_format_are_supported():
    order = parse_order_card(FRENCH_CARD)
    assert order.order_id == "234-2345678-2345678"
    assert order.order_date == date(2024, 7, 24)
    assert order.total == "1234.56"
    assert not order.cancelled


def test_french_cancelled_order_does_not_require_a_total():
    card_without_total = re.sub(r"TOTAL DE LA COMMANDE\s*1 234,56 €", "", FRENCH_CARD)
    order = parse_order_card(card_without_total + "\nCommande annulée\n")
    assert order.cancelled
    assert order.total == "0.00"


def test_uk_day_first_date_and_pound_total_are_supported():
    order = parse_order_card(UK_CARD)
    assert order.order_date == date(2023, 1, 5)
    assert order.total == "987.65"


def test_all_years_and_date_windows():
    assert parse_date_window(True, None, None) == DateWindow()
    assert parse_date_window(False, "2024", None).contains(date(2024, 6, 1))
    assert not parse_date_window(False, "2024", None).contains(date(2023, 12, 31))
    assert parse_date_window(False, None, "20230115-20230215").end == date(2023, 2, 15)
    assert parse_date_window(False, "<CUR_YEAR>", None).contains(date.today())


def test_available_years_are_filtered_and_newest_first():
    window = DateWindow(date(2015, 1, 1), date(2024, 12, 31))
    assert available_years(
        ["3 derniers mois", "commandes passées en 2024", "2010", " 2020 "],
        window,
    ) == [2024, 2020]


def test_year_can_be_read_from_localized_label_or_option_value():
    assert option_year("commandes passées en 2024", "year-2024") == 2024
    assert option_year("3 derniers mois", "year-2023") == 2023
    assert option_year("3 derniers mois", "last30") is None


def test_document_link_detection_and_filename():
    order = parse_order_card(SAMPLE_CARD)
    assert is_document_link("Invoice 1", "/gp/css/summary/print.html?orderID=123")
    assert not is_document_link("View invoice", "javascript:void(0)")
    assert pdf_filename(order) == "20100105_1234.56_USD_amazon_123-1234567-1234567.pdf"
    assert pdf_filename(order, 2).endswith("_02.pdf")
    assert pdf_filename(order, currency="GBP").endswith("_GBP_amazon_123-1234567-1234567.pdf")


def test_popover_and_request_links_are_not_documents():
    popover = "/your-orders/invoice/popover?orderId=123&ref_=fed_invoice_ajax"
    assert is_document_menu_link(popover)
    assert not is_document_link("Invoice", popover)
    assert not is_document_link("Facture", popover)
    assert not is_document_link("Request Invoice", "/request-invoice")
    assert not is_document_link("Demander une facture", "/demander-facture")
    assert not is_document_link("Note de crédit 1", "/credit-note/1")
    assert not is_document_link("Warranty/Pslip", "/your-orders/invoice/document")


def test_real_invoices_are_preferred_over_summary_and_non_invoice_links():
    links = [
        ("Printable Order Summary", "https://www.amazon.co.uk/summary/print"),
        ("Invoice 1", "https://www.amazon.co.uk/invoice/1"),
        ("Invoice 2", "https://www.amazon.co.uk/invoice/2"),
        ("Request Invoice", "https://www.amazon.co.uk/request-invoice"),
    ]
    assert preferred_document_links(links) == links[1:3]


def test_document_links_are_extracted_from_invoice_menu_html():
    html = """
    <ul>
      <li><a href="/summary/print"><span>Printable Order Summary</span></a></li>
      <li><a href="/invoice/1">Invoice 1</a></li>
      <li><a href="/invoice/2">Invoice 2</a></li>
      <li><a href="/request" aria-label="Request Invoice"></a></li>
    </ul>
    """
    links = document_links_from_html(html, "https://www.amazon.co.uk/")
    assert preferred_document_links(links) == [
        ("Invoice 1", "https://www.amazon.co.uk/invoice/1"),
        ("Invoice 2", "https://www.amazon.co.uk/invoice/2"),
    ]


def test_printable_summary_is_used_only_when_no_invoice_exists():
    summary = ("Récapitulatif de commande imprimable", "https://www.amazon.fr/summary/print")
    links = [summary, ("Demander une facture", "https://www.amazon.fr/request")]
    assert preferred_document_links(links) == [summary]


def test_link_menu_text_is_rejected_before_pdf_creation():
    assert is_document_menu_text("Printable Order Summary Invoice 1 Invoice 2 Invoice 3 Request Invoice")
    assert is_document_menu_text("Récapitulatif de commande imprimable Facture 1 Facture 2 Note de crédit 1")
    assert not is_document_menu_text("VAT Invoice Order 123 Invoice date 6 August 2026 Item description and totals")


def test_pdf_content_is_detected_by_signature_not_filename_or_header():
    assert is_pdf_content(b"%PDF-1.7\nreal document")
    assert is_pdf_content(b"metadata before signature\n%PDF-1.4\nreal document")
    assert not is_pdf_content(b"<html><title>invoice.pdf</title></html>")


def test_marketplace_controls_currency_and_relative_document_urls():
    uk = marketplace_for("uk")
    assert uk.domain == "amazon.co.uk"
    assert uk.currency == "GBP"
    assert uk.paper_format == "A4"
    assert absolute_document_url("/gp/css/summary/print.html", uk).startswith("https://www.amazon.co.uk/")
    assert marketplace_for("https://www.amazon.fr/orders").currency == "EUR"
    assert is_document_link("Afficher la facture", "/gp/css/summary/print.html")
    assert is_document_link("Récapitulatif de commande", "/some/document")


def test_manifest_is_append_only(tmp_path: Path):
    manifest = Manifest(tmp_path / "manifest.csv")
    manifest.append(status="saved", order_id="123-1234567-1234567")
    manifest.append(status="skipped_existing", order_id="123-1234567-1234567")
    text = manifest.path.read_text(encoding="utf-8-sig")
    assert text.count("timestamp,status") == 1
    assert text.count("123-1234567-1234567") == 2
