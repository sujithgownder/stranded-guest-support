"""CSV loaders for stranded guest tickets and open Lisbon listings."""

from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from .models import ListingStatus, OpenListing, SupportTicket, TWO_PLACES


def parse_decimal(raw: str) -> Decimal:
    """Parse a string currency value into a 2-decimal-place Decimal."""
    return Decimal(raw.strip()).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def parse_iso_date(raw: str) -> date:
    """Parse a YYYY-MM-DD date string."""
    return date.fromisoformat(raw.strip())


def parse_iso_datetime(raw: str) -> datetime | None:
    """Parse an optional ISO-8601 UTC timestamp string."""
    cleaned = raw.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = f"{cleaned[:-1]}+00:00"
    dt = datetime.fromisoformat(cleaned)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def load_tickets_csv(path: str | Path) -> list[SupportTicket]:
    """Load SupportTicket records from a stranded-guest tickets CSV file."""
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        tickets: list[SupportTicket] = []
        for row in reader:
            expected = (row.get("expected_outcome") or "").strip() or None
            opened_at = parse_iso_datetime(row["opened_at"])
            if opened_at is None:
                raise ValueError(f"opened_at is required for ticket {row.get('ticket_id')}")
            tickets.append(
                SupportTicket(
                    ticket_id=row["ticket_id"].strip(),
                    opened_at=opened_at,
                    reservation_id=row["reservation_id"].strip(),
                    guest_name=row["guest_name"].strip(),
                    guest_language=row["guest_language"].strip(),
                    original_listing_id=row["original_listing_id"].strip(),
                    original_listing_title=row["original_listing_title"].strip(),
                    neighborhood=row["neighborhood"].strip(),
                    property_type=row["property_type"].strip(),
                    bedrooms=int(row["bedrooms"]),
                    party_size=int(row["party_size"]),
                    check_in_date=parse_iso_date(row["check_in_date"]),
                    check_out_date=parse_iso_date(row["check_out_date"]),
                    nightly_price=parse_decimal(row["nightly_price"]),
                    total_paid=parse_decimal(row["total_paid"]),
                    host_id=row["host_id"].strip(),
                    host_cancelled_at=parse_iso_datetime(row.get("host_cancelled_at", "")),
                    host_last_reply_at=parse_iso_datetime(row.get("host_last_reply_at", "")),
                    guest_requested=row["guest_requested"].strip(),
                    guest_message=row["guest_message"].strip(),
                    expected_outcome=expected,
                )
            )
        return tickets


def load_open_listings_csv(path: str | Path) -> list[OpenListing]:
    """Load OpenListing records from an open Lisbon listings CSV file."""
    csv_path = Path(path)
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        listings: list[OpenListing] = []
        for row in reader:
            raw_rating = (row.get("rating") or "").strip()
            raw_instant = (row.get("instant_book") or "").strip().lower()
            listings.append(
                OpenListing(
                    listing_id=row["listing_id"].strip(),
                    neighborhood=row["neighborhood"].strip(),
                    bedrooms=int(row["bedrooms"]),
                    max_guests=int(row["max_guests"]),
                    available_from=parse_iso_date(row["available_from"]),
                    available_to=parse_iso_date(row["available_to"]),
                    nightly_price=parse_decimal(row["nightly_price"]),
                    status=ListingStatus(row["status"].strip()),
                    property_type=(row.get("property_type") or "").strip(),
                    host_id=(row.get("host_id") or "").strip(),
                    title=(row.get("title") or "").strip(),
                    instant_book=raw_instant == "true",
                    rating=parse_decimal(raw_rating) if raw_rating else None,
                )
            )
        return listings
