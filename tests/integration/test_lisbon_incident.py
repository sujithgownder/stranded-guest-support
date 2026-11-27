"""End-to-end integration tests against the 60-ticket Lisbon incident dataset."""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
import unittest

from stranded_guest_support import (
    AgentRole,
    ListingStatus,
    OpenListing,
    PolicyToolGateway,
    SupportTeamOrchestrator,
    TicketType,
    is_open_listing_id,
    load_tickets_csv,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TICKETS_CSV = REPO_ROOT / "Lisbon Stranded Guest Tickets (16 Nov 2026).csv"


def build_synthetic_open_listings() -> list[OpenListing]:
    """Build deterministic open Lisbon listings (LST-100001..LST-100450) with adversarial traps."""
    listings: list[OpenListing] = []
    # Adversarial overpriced / unavailable listings at low IDs to ensure filter rejects them
    listings.append(
        OpenListing(
            listing_id="LST-100001",
            neighborhood="Alfama",
            property_type="Entire apartment",
            bedrooms=4,
            max_guests=8,
            available_from=date(2026, 11, 16),
            available_to=date(2026, 11, 26),
            nightly_price=Decimal("500.00"),  # Over 120% ceiling for standard bookings
            status=ListingStatus.AVAILABLE,
        )
    )
    listings.append(
        OpenListing(
            listing_id="LST-100002",
            neighborhood="Baixa",
            property_type="Entire apartment",
            bedrooms=4,
            max_guests=8,
            available_from=date(2026, 11, 16),
            available_to=date(2026, 11, 26),
            nightly_price=Decimal("50.00"),
            status=ListingStatus.ON_HOLD,
        )
    )
    listings.append(
        OpenListing(
            listing_id="LST-100003",
            neighborhood="Chiado",
            property_type="Entire apartment",
            bedrooms=4,
            max_guests=8,
            available_from=date(2026, 11, 16),
            available_to=date(2026, 11, 26),
            nightly_price=Decimal("50.00"),
            status=ListingStatus.BOOKED,
        )
    )

    # Create 447 comparable available listings (LST-100004..LST-100450) across Lisbon neighborhoods
    neighborhoods = [
        "Alfama",
        "Baixa",
        "Chiado",
        "Graca",
        "Bairro Alto",
        "Principe Real",
        "Estrela",
        "Belem",
        "Alcantara",
        "Parque das Nacoes",
    ]
    prices = [
        Decimal("64.00"),
        Decimal("74.00"),
        Decimal("86.00"),
        Decimal("94.00"),
        Decimal("108.00"),
        Decimal("124.00"),
        Decimal("138.00"),
        Decimal("152.00"),
        Decimal("196.00"),
        Decimal("238.00"),
        Decimal("278.00"),
        Decimal("345.00"),
        Decimal("410.00"),
    ]
    for idx in range(4, 451):
        nb = neighborhoods[idx % len(neighborhoods)]
        price = prices[idx % len(prices)]
        if price >= Decimal("345.00"):
            bedrooms = 4
            prop_type = "Entire townhouse"
        elif price >= Decimal("220.00"):
            bedrooms = 3
            prop_type = "Entire apartment"
        elif price >= Decimal("124.00"):
            bedrooms = 2
            prop_type = "Entire apartment"
        elif price >= Decimal("94.00") or idx % 2 == 0:
            bedrooms = 1
            prop_type = "Private room" if price < Decimal("94.00") else "Entire apartment"
        else:
            bedrooms = 0
            prop_type = "Entire studio"
        max_guests = max(2, bedrooms * 2) if bedrooms < 4 else 8
        listings.append(
            OpenListing(
                listing_id=f"LST-{100000 + idx}",
                neighborhood=nb,
                property_type=prop_type,
                bedrooms=bedrooms,
                max_guests=max_guests,
                available_from=date(2026, 11, 16),
                available_to=date(2026, 11, 26),
                nightly_price=price,
                status=ListingStatus.AVAILABLE,
            )
        )
    return listings


class LisbonIncidentIntegrationTests(unittest.TestCase):
    def test_all_60_lisbon_tickets_meet_aircover_policy(self) -> None:
        tickets = load_tickets_csv(TICKETS_CSV)
        self.assertEqual(len(tickets), 60)

        listings = build_synthetic_open_listings()
        listings_by_id = {l.listing_id: l for l in listings}
        gateway = PolicyToolGateway()
        orchestrator = SupportTeamOrchestrator(gateway=gateway)

        outcomes: Counter[str] = Counter()
        for ticket in tickets:
            resolution = orchestrator.handle_ticket(ticket, listings)
            outcomes[resolution.ticket_type.value] += 1
            self.assertEqual(resolution.ticket_type.value, ticket.expected_outcome)

            if resolution.ticket_type == TicketType.SAFETY:
                self.assertEqual(resolution.agent_role, AgentRole.SAFETY_AGENT)
                self.assertEqual(resolution.tool_used, "handoff_to_safety_agent")
                self.assertTrue(resolution.handoff_completed)
                self.assertIsNone(resolution.listing_id)
                self.assertIsNone(resolution.refund_amount)
            elif resolution.ticket_type == TicketType.REBOOKING:
                self.assertEqual(resolution.agent_role, AgentRole.REBOOKING_AGENT)
                self.assertEqual(resolution.tool_used, "hold_booking")
                self.assertIsNotNone(resolution.listing_id)
                assert resolution.listing_id is not None
                self.assertTrue(is_open_listing_id(resolution.listing_id))
                held_listing = listings_by_id[resolution.listing_id]
                self.assertLessEqual(held_listing.nightly_price, ticket.max_rebook_nightly_price)
                self.assertEqual(held_listing.status, ListingStatus.ON_HOLD)
            elif resolution.ticket_type == TicketType.REFUND:
                self.assertEqual(resolution.agent_role, AgentRole.REFUND_AGENT)
                self.assertEqual(resolution.tool_used, "issue_refund")
                self.assertIsNotNone(resolution.refund_amount)
                assert resolution.refund_amount is not None
                self.assertGreaterEqual(resolution.refund_amount, Decimal("0.01"))
                self.assertLessEqual(resolution.refund_amount, ticket.total_paid)

        self.assertEqual(outcomes, Counter({"rebooking": 34, "refund": 20, "safety": 6}))
        self.assertLessEqual(gateway.ledger.uplift_spent, Decimal("9000.00"))
        self.assertEqual(len(gateway.ledger.remedies_by_reservation), 60)

        # Verify zero pre-handoff or unauthorized tool calls were ever permitted
        for call in gateway.ledger.tool_calls:
            self.assertTrue(call.allowed)
            if call.ticket_id in gateway.safety_ticket_ids:
                self.assertEqual(call.tool_name, "handoff_to_safety_agent")


if __name__ == "__main__":
    unittest.main()
