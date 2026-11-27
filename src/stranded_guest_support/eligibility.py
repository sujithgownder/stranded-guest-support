"""Locked-out guest eligibility, 5-part comparable-home validation, and neighborhood ranking."""

from __future__ import annotations

from decimal import Decimal
import re
from typing import Sequence

from .models import ListingStatus, OpenListing, SupportTicket, TWO_PLACES

ACCESS_ISSUE_PATTERN = re.compile(
    r"\b(lockbox is empty|empty lockbox|key ?box is empty|wrong code|"
    r"code(?: for the lockbox)? does not work|no one at the door|"
    r"nobody is here|no key inside|flat is locked|locked out|cannot get in|"
    r"host(?: has)? not answered|host never replied|phone switched off|unreachable)\b",
    re.IGNORECASE,
)

# Symmetrical adjacency map for Lisbon neighborhoods seen in the incident dataset.
LISBON_NEIGHBORHOOD_ADJACENCY: dict[str, frozenset[str]] = {
    "Alfama": frozenset({"Baixa", "Graca", "Mouraria"}),
    "Baixa": frozenset({"Alfama", "Chiado", "Bairro Alto", "Graca", "Mouraria"}),
    "Chiado": frozenset({"Baixa", "Bairro Alto", "Principe Real", "Santos"}),
    "Bairro Alto": frozenset({"Chiado", "Principe Real", "Baixa", "Estrela", "Santos"}),
    "Principe Real": frozenset({"Bairro Alto", "Chiado", "Estrela", "Lapa"}),
    "Graca": frozenset({"Alfama", "Baixa", "Mouraria"}),
    "Estrela": frozenset({"Principe Real", "Bairro Alto", "Alcantara", "Lapa", "Campo de Ourique"}),
    "Alcantara": frozenset({"Estrela", "Belem", "Santos", "Lapa"}),
    "Belem": frozenset({"Alcantara"}),
    "Parque das Nacoes": frozenset(),
}


def is_open_listing_id(listing_id: str) -> bool:
    """Return True if listing_id falls within the open Lisbon inventory range LST-100001..LST-100450."""
    if not listing_id.startswith("LST-"):
        return False
    suffix = listing_id[4:]
    if not suffix.isdigit():
        return False
    num = int(suffix)
    return 100001 <= num <= 100450


def qualifies_for_rebooking(ticket: SupportTicket) -> bool:
    """Return True when at least one AirCover locked-out qualifying condition holds."""
    if ticket.host_cancelled_at is not None:
        days_before = (ticket.check_in_date - ticket.host_cancelled_at.date()).days
        if 0 <= days_before <= 30:
            return True

    if ticket.host_last_reply_at is None or ticket.host_last_reply_at <= ticket.opened_at:
        return True

    return bool(ACCESS_ISSUE_PATTERN.search(ticket.guest_message))


def is_comparable_home(ticket: SupportTicket, listing: OpenListing) -> bool:
    """Return True only when listing is open-inventory and passes all 5 comparable-home tests."""
    if not is_open_listing_id(listing.listing_id):
        return False
    if listing.available_from > ticket.check_in_date or listing.available_to < ticket.check_out_date:
        return False
    if listing.max_guests < ticket.party_size:
        return False
    if listing.bedrooms < ticket.bedrooms:
        return False
    if listing.status != ListingStatus.AVAILABLE:
        return False
    if listing.nightly_price > ticket.max_rebook_nightly_price:
        return False
    return True


def calculate_uplift(ticket: SupportTicket, listing: OpenListing) -> Decimal:
    """Compute total EUR uplift across the full stay, clamped at EUR 0.00."""
    nightly_diff = listing.nightly_price - ticket.nightly_price
    if nightly_diff <= Decimal("0.00"):
        return Decimal("0.00")
    return (nightly_diff * ticket.nights).quantize(TWO_PLACES)


def _neighborhood_rank(ticket_neighborhood: str, listing_neighborhood: str) -> int:
    """Return 0 for exact match, 1 for neighbouring Lisbon area, 2 otherwise."""
    if listing_neighborhood.casefold() == ticket_neighborhood.casefold():
        return 0
    neighbours = LISBON_NEIGHBORHOOD_ADJACENCY.get(ticket_neighborhood, frozenset())
    if any(n.casefold() == listing_neighborhood.casefold() for n in neighbours):
        return 1
    return 2


def select_comparable_listings(
    ticket: SupportTicket,
    open_listings: Sequence[OpenListing],
    *,
    excluded_listing_ids: frozenset[str] = frozenset(),
) -> list[OpenListing]:
    """Filter and rank passing comparable homes by neighborhood preference then lowest price."""
    candidates = [
        listing
        for listing in open_listings
        if listing.listing_id not in excluded_listing_ids and is_comparable_home(ticket, listing)
    ]
    candidates.sort(
        key=lambda listing: (
            _neighborhood_rank(ticket.neighborhood, listing.neighborhood),
            listing.nightly_price,
            listing.bedrooms,
            listing.listing_id,
        )
    )
    return candidates
