"""Pure helpers for parsing Amazon order cards and tracking download progress.

This module deliberately has no Playwright dependency.  Keeping the parsing and
manifest code separate makes it possible to test the parts most likely to break
when Amazon changes its page markup without opening a browser.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin


ORDER_ID_RE = re.compile(r"\b\d{3}-\d{7}-\d{7}\b")
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}
MONTH_PATTERN = "|".join(MONTHS)
DATE_MONTH_FIRST_RE = re.compile(
    rf"\b(?P<month>{MONTH_PATTERN})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+" r"(?P<year>\d{4})\b",
    re.IGNORECASE,
)
DATE_DAY_FIRST_RE = re.compile(
    rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{MONTH_PATTERN})\s+" r"(?P<year>\d{4})\b",
    re.IGNORECASE,
)
TOTAL_LABEL = r"(?:ORDER\s+TOTAL|TOTAL(?:\s+DE\s+LA\s+COMMANDE)?)"
CURRENCY_TOKEN = r"(?:US\$|\$|£|€|USD|GBP|EUR)"
AMOUNT_TOKEN = r"(?P<amount>\d[\d\s.,'’]*\d|\d)"
TOTAL_PATTERNS = (
    re.compile(rf"\b{TOTAL_LABEL}\b\s*{CURRENCY_TOKEN}\s*{AMOUNT_TOKEN}", re.IGNORECASE),
    re.compile(rf"\b{TOTAL_LABEL}\b\s*{AMOUNT_TOKEN}\s*{CURRENCY_TOKEN}", re.IGNORECASE),
)
INVOICE_TEXT_RE = re.compile(r"\b(invoice|facture)(?:\s+\d+)?\b", re.IGNORECASE)
SUMMARY_TEXT_RE = re.compile(
    r"\b(order\s+summary|printable\s+order\s+summary|" r"recapitulatif\s+de\s+commande(?:\s+imprimable)?)\b",
    re.IGNORECASE,
)
REQUEST_DOCUMENT_TEXT_RE = re.compile(r"\b(request\s+invoice|demander\s+une\s+facture)\b", re.IGNORECASE)
CREDIT_NOTE_TEXT_RE = re.compile(r"\b(credit\s+note|note\s+de\s+credit)\b", re.IGNORECASE)
DOCUMENT_HREF_RE = re.compile(r"(invoice|summary/print|print\.html)", re.IGNORECASE)
DOCUMENT_MENU_HREF_RE = re.compile(r"(/invoice/popover\b|invoice_ajax)", re.IGNORECASE)


@dataclass(frozen=True)
class Marketplace:
    """Amazon storefront settings that must stay consistent during a run."""

    domain: str
    currency: str
    paper_format: str

    @property
    def order_history_url(self) -> str:
        return f"https://www.{self.domain}/gp/css/order-history"

    @property
    def base_url(self) -> str:
        return f"https://www.{self.domain}/"


MARKETPLACES = {
    "amazon.com": Marketplace("amazon.com", "USD", "Letter"),
    "amazon.co.uk": Marketplace("amazon.co.uk", "GBP", "A4"),
    "amazon.fr": Marketplace("amazon.fr", "EUR", "A4"),
}
MARKETPLACE_ALIASES = {
    "com": "amazon.com",
    "us": "amazon.com",
    "usa": "amazon.com",
    "co.uk": "amazon.co.uk",
    "uk": "amazon.co.uk",
    "fr": "amazon.fr",
    "france": "amazon.fr",
}


@dataclass(frozen=True)
class DateWindow:
    """Inclusive date limits; ``None`` on both sides means every available year."""

    start: date | None = None
    end: date | None = None

    def contains(self, value: date) -> bool:
        return (self.start is None or value >= self.start) and (self.end is None or value <= self.end)

    def includes_year(self, year: int) -> bool:
        return (self.start is None or year >= self.start.year) and (self.end is None or year <= self.end.year)


@dataclass(frozen=True)
class OrderCardFields:
    """Best-effort fields retained even when a complete card cannot be parsed."""

    order_id: str | None
    order_date: date | None
    total: str | None
    cancelled: bool


@dataclass(frozen=True)
class OrderSummary:
    """Fields extracted from the visible text of a single Amazon order card."""

    order_id: str
    order_date: date
    total: str
    cancelled: bool


def marketplace_for(value: str) -> Marketplace:
    """Return a supported marketplace from a domain or convenient short name."""

    normalized = value.strip().lower()
    normalized = re.sub(r"^https?://", "", normalized).split("/", 1)[0]
    normalized = re.sub(r"^www\.", "", normalized)
    normalized = MARKETPLACE_ALIASES.get(normalized, normalized)
    try:
        return MARKETPLACES[normalized]
    except KeyError as exc:
        supported = ", ".join(MARKETPLACES)
        raise ValueError(f"Unsupported marketplace {value!r}; choose one of: {supported}") from exc


def _ascii_text(text: str) -> str:
    """Remove accents so one set of regular expressions handles French labels."""

    return "".join(
        character for character in unicodedata.normalize("NFKD", text) if not unicodedata.combining(character)
    )


def _parse_order_date(text: str) -> date | None:
    normalized = _ascii_text(" ".join(text.split()))
    for pattern in (DATE_MONTH_FIRST_RE, DATE_DAY_FIRST_RE):
        match = pattern.search(normalized)
        if match:
            return date(
                int(match.group("year")),
                MONTHS[match.group("month").lower()],
                int(match.group("day")),
            )
    return None


def _normalize_amount(value: str) -> str:
    """Convert US, UK, and French price formatting to a decimal string."""

    compact = re.sub(r"[\s'’]", "", value)
    if "," in compact and "." in compact:
        decimal_separator = "," if compact.rfind(",") > compact.rfind(".") else "."
        grouping_separator = "." if decimal_separator == "," else ","
        compact = compact.replace(grouping_separator, "").replace(decimal_separator, ".")
    elif "," in compact:
        head, tail = compact.rsplit(",", 1)
        compact = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else compact.replace(",", "")
    elif "." in compact:
        head, tail = compact.rsplit(".", 1)
        compact = f"{head.replace('.', '')}.{tail}" if len(tail) == 2 else compact.replace(".", "")
    try:
        return f"{Decimal(compact):.2f}"
    except InvalidOperation as exc:
        raise ValueError(f"Could not parse order total {value!r}") from exc


def _parse_order_total(text: str) -> str | None:
    normalized = " ".join(text.split())
    for pattern in TOTAL_PATTERNS:
        match = pattern.search(normalized)
        if match:
            return _normalize_amount(match.group("amount"))
    return None


def parse_date_window(all_years: bool, year: str | None, date_range: str | None) -> DateWindow:
    if all_years:
        return DateWindow()
    if date_range:
        try:
            start_text, end_text = date_range.split("-", 1)
            start = datetime.strptime(start_text, "%Y%m%d").date()
            end = datetime.strptime(end_text, "%Y%m%d").date()
        except ValueError as exc:
            raise ValueError("--date-range must use YYYYMMDD-YYYYMMDD") from exc
        if end < start:
            raise ValueError("--date-range end must not precede its start")
        return DateWindow(start, end)
    # Docopt returns the literal placeholder used by the upstream CLI default.
    selected_year = int(year) if year and year != "<CUR_YEAR>" else datetime.now().year
    return DateWindow(date(selected_year, 1, 1), date(selected_year, 12, 31))


def parse_order_card_fields(text: str) -> OrderCardFields:
    """Extract every recognizable field without requiring a complete card.

    Amazon occasionally omits a visible order total. The strict parser must
    still reject that card because the total is part of the output filename,
    but retaining its ID and date makes the manifest useful for diagnosis.
    """

    order_match = ORDER_ID_RE.search(text)
    normalized = _ascii_text(text)
    return OrderCardFields(
        order_id=order_match.group(0) if order_match else None,
        order_date=_parse_order_date(text),
        total=_parse_order_total(text),
        cancelled=bool(re.search(r"\b(cancelled|canceled|annulee?)\b", normalized, re.IGNORECASE)),
    )


def parse_order_card(text: str) -> OrderSummary:
    """Parse an order card by labels and patterns, never by fragile span indexes."""

    fields = parse_order_card_fields(text)
    missing = [
        name
        for name, match in (
            ("order ID", fields.order_id),
            ("order date", fields.order_date),
            ("order total", fields.total),
        )
        # Amazon frequently omits the total from cancelled cards. The total is
        # irrelevant because cancelled orders are logged but never downloaded.
        if match is None and not (name == "order total" and fields.cancelled)
    ]
    if missing:
        raise ValueError(f"Could not parse {', '.join(missing)} from order card")
    # The missing-field check above guarantees these required values and also
    # narrows their Optional types for static analyzers.
    assert fields.order_id is not None
    assert fields.order_date is not None
    return OrderSummary(
        order_id=fields.order_id,
        order_date=fields.order_date,
        total=fields.total or "0.00",
        cancelled=fields.cancelled,
    )


def option_year(*parts: str | None) -> int | None:
    """Extract a year from a localized option label or its HTML value.

    Amazon.com labels year filters with only the year, while other storefronts
    can use phrases such as "commandes passées en 2024".  The option value is
    also checked because it commonly contains a locale-independent
    ``year-2024`` value.
    """

    for part in parts:
        if part:
            match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", part)
            if match:
                return int(match.group(1))
    return None


def available_years(option_texts: Iterable[str], window: DateWindow) -> list[int]:
    years = {year for text in option_texts if (year := option_year(text)) is not None}
    return sorted((year for year in years if window.includes_year(year)), reverse=True)


def is_document_menu_link(href: str | None) -> bool:
    """Identify Amazon's link-list endpoint, which is not itself an invoice."""

    return bool(href and DOCUMENT_MENU_HREF_RE.search(href))


def document_link_kind(label: str, href: str | None) -> str | None:
    """Classify a printable document link while rejecting menu/request links."""

    if not href or href.startswith(("javascript:", "#")):
        return None
    if is_document_menu_link(href):
        return None

    normalized_label = _ascii_text(" ".join(label.split()))
    if REQUEST_DOCUMENT_TEXT_RE.search(normalized_label) or CREDIT_NOTE_TEXT_RE.search(normalized_label):
        return None
    if INVOICE_TEXT_RE.search(normalized_label):
        return "invoice"
    if SUMMARY_TEXT_RE.search(normalized_label):
        return "summary"
    # A meaningful but unknown label such as "Warranty/Pslip" must not be
    # promoted merely because Amazon happens to serve it from an invoice-like
    # path. Use the URL fallback only for genuinely unlabelled anchors.
    if not normalized_label and DOCUMENT_HREF_RE.search(href):
        return "invoice"
    return None


def is_document_link(label: str, href: str | None) -> bool:
    return document_link_kind(label, href) is not None


def preferred_document_links(links: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Prefer actual invoices; use printable summaries only when none exist."""

    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, url in links:
        if url not in seen and document_link_kind(label, url):
            seen.add(url)
            unique.append((label, url))

    invoices = [link for link in unique if document_link_kind(*link) == "invoice"]
    if invoices:
        return invoices
    return [link for link in unique if document_link_kind(*link) == "summary"]


class _AnchorParser(HTMLParser):
    """Collect anchor labels and targets from Amazon's invoice-menu fragment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._label_hint = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a" or self._href is not None:
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if href:
            self._href = href
            self._label_hint = attributes.get("aria-label") or attributes.get("title") or ""
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        label = " ".join(" ".join(self._text).split()) or self._label_hint
        self.links.append((label, self._href))
        self._href = None
        self._label_hint = ""
        self._text = []


def document_links_from_html(html_text: str, base_url: str) -> list[tuple[str, str]]:
    """Extract absolute document links from an authenticated menu response."""

    parser = _AnchorParser()
    parser.feed(html_text)
    parser.close()
    return [(label, urljoin(base_url, href)) for label, href in parser.links]


def is_document_menu_text(text: str) -> bool:
    """Detect a mistakenly opened invoice popover before it is printed to PDF."""

    normalized = _ascii_text(" ".join(text.split()))
    return (
        len(normalized) <= 400 and bool(SUMMARY_TEXT_RE.search(normalized)) and bool(INVOICE_TEXT_RE.search(normalized))
    )


def is_pdf_content(content: bytes) -> bool:
    """Return whether a response body contains a real PDF file.

    The PDF signature is normally the first five bytes, but the specification
    permits it anywhere in the first 1,024 bytes.  Checking the bytes is safer
    than trusting a server content type or a filename ending in ``.pdf``.
    """

    return b"%PDF-" in content[:1024]


def absolute_document_url(href: str, marketplace: Marketplace | str = "amazon.com") -> str:
    selected = marketplace_for(marketplace) if isinstance(marketplace, str) else marketplace
    return urljoin(selected.base_url, href)


def pdf_filename(summary: OrderSummary, document_index: int = 1, currency: str = "USD") -> str:
    """Use a deterministic name so an interrupted run can skip completed PDFs."""

    suffix = "" if document_index == 1 else f"_{document_index:02d}"
    return f"{summary.order_date:%Y%m%d}_{summary.total}_{currency}_amazon_{summary.order_id}{suffix}.pdf"


MANIFEST_FIELDS = [
    "timestamp",
    "status",
    "year",
    "page",
    "order_date",
    "order_total",
    "order_id",
    "document_index",
    "document_label",
    "document_url",
    "pdf_path",
    "error",
]


class Manifest:
    """Append-only audit log used for recovery and later CSV/PDF matching."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, **values: object) -> None:
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        row = {field: values.get(field, "") for field in MANIFEST_FIELDS}
        row["timestamp"] = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.path.open("a", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=MANIFEST_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow(row)
