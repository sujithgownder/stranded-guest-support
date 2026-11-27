"""Unit tests for PolicyToolGateway role enforcement, hold_booking, and stay locks."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import unittest

from stranded_guest_support.models import (
    AgentRole,
    ListingStatus,
    OpenListing,
    PolicyViolationError,
    SupportTicket,
    UnauthorizedToolError,
)
from stranded_guest_support.tools import PolicyToolGateway


def make_ticket(**overrides: object) -> SupportTicket:
    defaults: dict[str, object] = {
        "ticket_id": "LIS-TKT-0200",
        "opened_at": datetime(2026, 11, 16, 14, 0, tzinfo=timezone.utc),
        "reservation_id": "RES-2026-10200",
        "guest_name": "Guest",
        "guest_language": "en",
        "original_listing_id": "LST-200001",
        "original_listing_title": "Original Flat",
        "neighborhood": "Baixa",
        "property_type": "Entire apartment",
        "bedrooms": 1,
        "party_size": 2,
        "check_in_date": date(2026, 11, 16),
        "check_out_date": date(2026, 11, 19),
        "nightly_price": Decimal("110.00"),
        "total_paid": Decimal("330.00"),
        "host_id": "HOST-4001",
        "host_cancelled_at": datetime(2026, 11, 16, 8, 12, tzinfo=timezone.utc),
        "host_last_reply_at": None,
        "guest_requested": "rebooking",
        "guest_message": "Cancelled by host.",
    }
    defaults.update(overrides)
    return SupportTicket(**defaults)  # type: ignore[arg-type]


def make_listing(**overrides: object) -> OpenListing:
    defaults: dict[str, object] = {
        "listing_id": "LST-100001",
        "neighborhood": "Baixa",
        "property_type": "Entire apartment",
        "bedrooms": 1,
        "max_guests": 2,
        "available_from": date(2026, 11, 16),
        "available_to": date(2026, 11, 19),
        "nightly_price": Decimal("132.00"),
        "status": ListingStatus.AVAILABLE,
    }
    defaults.update(overrides)
    return OpenListing(**defaults)  # type: ignore[arg-type]


class ToolGatewayHoldBookingTests(unittest.TestCase):
    def test_hold_booking_role_isolation_and_success(self) -> None:
        ticket = make_ticket()
        listing = make_listing()
        gateway = PolicyToolGateway()

        with self.assertRaises(UnauthorizedToolError):
            gateway.hold_booking(AgentRole.REFUND_AGENT, ticket, listing)

        with self.assertRaises(UnauthorizedToolError):
            gateway.hold_booking(AgentRole.SAFETY_AGENT, ticket, listing)

        record = gateway.hold_booking(AgentRole.REBOOKING_AGENT, ticket, listing)
        self.assertTrue(record.allowed)
        self.assertEqual(listing.status, ListingStatus.ON_HOLD)
        self.assertEqual(gateway.ledger.uplift_spent, Decimal("66.00"))
        self.assertEqual(gateway.ledger.remedies_by_reservation[ticket.reservation_id], "rebooking")

    def test_hold_booking_rejects_above_120_percent_and_double_hold(self) -> None:
        ticket = make_ticket()
        overpriced = make_listing(listing_id="LST-100002", nightly_price=Decimal("132.01"))
        gateway = PolicyToolGateway()

        with self.assertRaises(PolicyViolationError):
            gateway.hold_booking(AgentRole.REBOOKING_AGENT, ticket, overpriced)

        valid = make_listing(listing_id="LST-100003", nightly_price=Decimal("120.00"))
        gateway.hold_booking(AgentRole.REBOOKING_AGENT, ticket, valid)

        another = make_listing(listing_id="LST-100004", nightly_price=Decimal("110.00"))
        with self.assertRaises(PolicyViolationError):
            gateway.hold_booking(AgentRole.REBOOKING_AGENT, ticket, another)


class ToolGatewayIssueRefundTests(unittest.TestCase):
    def test_issue_refund_role_isolation_and_bounds(self) -> None:
        # Promo-code ticket: 4 nights at 120.00 = 480.00, but total_paid = 432.00
        promo_ticket = make_ticket(
            ticket_id="LIS-TKT-0028",
            reservation_id="RES-2026-10028",
            check_in_date=date(2026, 11, 16),
            check_out_date=date(2026, 11, 20),
            nightly_price=Decimal("120.00"),
            total_paid=Decimal("432.00"),
            guest_requested="refund",
        )
        gateway = PolicyToolGateway()

        with self.assertRaises(UnauthorizedToolError):
            gateway.issue_refund(AgentRole.REBOOKING_AGENT, promo_ticket, Decimal("432.00"))

        with self.assertRaises(UnauthorizedToolError):
            gateway.issue_refund(AgentRole.SAFETY_AGENT, promo_ticket, Decimal("432.00"))

        with self.assertRaises(PolicyViolationError):
            gateway.issue_refund(AgentRole.REFUND_AGENT, promo_ticket, Decimal("0.00"))

        with self.assertRaises(PolicyViolationError):
            gateway.issue_refund(AgentRole.REFUND_AGENT, promo_ticket, Decimal("432.01"))

        record = gateway.issue_refund(AgentRole.REFUND_AGENT, promo_ticket, Decimal("432.00"))
        self.assertTrue(record.allowed)
        self.assertEqual(record.refund_amount, Decimal("432.00"))
        self.assertEqual(gateway.ledger.remedies_by_reservation[promo_ticket.reservation_id], "refund")

    def test_one_remedy_per_stay_prevents_combining_hold_and_refund(self) -> None:
        ticket = make_ticket(reservation_id="RES-2026-10201")
        listing = make_listing(listing_id="LST-100005")
        gateway = PolicyToolGateway()

        gateway.hold_booking(AgentRole.REBOOKING_AGENT, ticket, listing)
        with self.assertRaises(PolicyViolationError):
            gateway.issue_refund(AgentRole.REFUND_AGENT, ticket, Decimal("330.00"))

        refund_first = make_ticket(ticket_id="LIS-TKT-0202", reservation_id="RES-2026-10202")
        gateway.issue_refund(AgentRole.REFUND_AGENT, refund_first, Decimal("330.00"))
        with self.assertRaises(PolicyViolationError):
            gateway.hold_booking(
                AgentRole.REBOOKING_AGENT,
                refund_first,
                make_listing(listing_id="LST-100006"),
            )


if __name__ == "__main__":
    unittest.main()
