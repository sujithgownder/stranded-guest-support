"""Unit tests for AirCover five safety condition triage and pre-handoff safety locks."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import unittest

from stranded_guest_support.models import (
    AgentRole,
    ListingStatus,
    OpenListing,
    SafetyCondition,
    SafetyHandoffRequiredError,
    SupportTicket,
    TicketType,
    UnauthorizedToolError,
)
from stranded_guest_support.safety import classify_ticket, detect_safety_conditions
from stranded_guest_support.tools import PolicyToolGateway


def make_ticket(
    *,
    ticket_id: str = "LIS-TKT-TEST",
    guest_requested: str = "rebooking",
    guest_message: str = "Host cancelled, need another flat.",
) -> SupportTicket:
    return SupportTicket(
        ticket_id=ticket_id,
        opened_at=datetime(2026, 11, 16, 14, 0, tzinfo=timezone.utc),
        reservation_id=f"RES-{ticket_id}",
        guest_name="Test Guest",
        guest_language="en",
        original_listing_id="LST-200001",
        original_listing_title="Test Listing",
        neighborhood="Alfama",
        property_type="Entire apartment",
        bedrooms=1,
        party_size=2,
        check_in_date=date(2026, 11, 16),
        check_out_date=date(2026, 11, 19),
        nightly_price=Decimal("100.00"),
        total_paid=Decimal("300.00"),
        host_id="HOST-4001",
        host_cancelled_at=datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc),
        host_last_reply_at=None,
        guest_requested=guest_requested,
        guest_message=guest_message,
    )


class SafetyTriageTests(unittest.TestCase):
    def test_detects_all_five_aircover_safety_conditions(self) -> None:
        cases = [
            (
                "refund",
                "Just refund me. I slipped on wet steps and my knee is bleeding badly.",
                SafetyCondition.INJURY_OR_MEDICAL_NEED,
            ),
            (
                "other",
                "The host's brother threatened to smash my phone and is still on the stairs.",
                SafetyCondition.THREAT_OR_VIOLENCE,
            ),
            (
                "rebooking",
                "I am 74, cafe asked me to leave, nowhere safe for me to wait and getting cold.",
                SafetyCondition.NOWHERE_SAFE_TO_WAIT,
            ),
            (
                "callback",
                "Please call me. I am 16 and travelling on my own, flat is locked and phone is on 9%.",
                SafetyCondition.UNACCOMPANIED_MINOR,
            ),
            (
                "refund",
                "A man followed me from the metro, I am scared to walk away.",
                SafetyCondition.STATED_FEAR_OF_PERSON,
            ),
        ]
        for requested, message, expected_condition in cases:
            ticket = make_ticket(guest_requested=requested, guest_message=message)
            detected = detect_safety_conditions(ticket.guest_message)
            self.assertIn(expected_condition, detected, msg=message)
            ticket_type, _ = classify_ticket(ticket)
            self.assertEqual(ticket_type, TicketType.SAFETY)

    def test_angry_words_and_callback_alone_stay_rebooking(self) -> None:
        angry = make_ticket(
            guest_requested="rebooking",
            guest_message="I am dying out here. Dragged four suitcases up this hill, before we all lose it.",
        )
        callback = make_ticket(
            guest_requested="callback",
            guest_message="Can someone call me please? We need a new studio near Principe Real.",
        )
        honeymoon = make_ticket(
            guest_requested="rebooking",
            guest_message="Worst day of our lives, standing here with every bag we own. Not an apology.",
        )
        for ticket in (angry, callback, honeymoon):
            self.assertEqual(detect_safety_conditions(ticket.guest_message), ())
            ticket_type, _ = classify_ticket(ticket)
            self.assertEqual(ticket_type, TicketType.REBOOKING)

    def test_safety_lock_blocks_refund_and_hold_before_handoff(self) -> None:
        ticket = make_ticket(
            ticket_id="LIS-TKT-0007",
            guest_requested="refund",
            guest_message="Just refund me. My knee is bleeding badly and I can hardly stand.",
        )
        listing = OpenListing(
            listing_id="LST-100001",
            neighborhood="Alfama",
            property_type="Entire apartment",
            bedrooms=1,
            max_guests=2,
            available_from=date(2026, 11, 16),
            available_to=date(2026, 11, 19),
            nightly_price=Decimal("110.00"),
            status=ListingStatus.AVAILABLE,
        )
        gateway = PolicyToolGateway()
        gateway.register_safety_ticket(ticket.ticket_id)

        with self.assertRaises(SafetyHandoffRequiredError):
            gateway.issue_refund(AgentRole.REFUND_AGENT, ticket, Decimal("300.00"))

        with self.assertRaises(SafetyHandoffRequiredError):
            gateway.hold_booking(AgentRole.REBOOKING_AGENT, ticket, listing)

        with self.assertRaises(UnauthorizedToolError):
            gateway.issue_refund(AgentRole.SAFETY_AGENT, ticket, Decimal("300.00"))

        with self.assertRaises(UnauthorizedToolError):
            gateway.hold_booking(AgentRole.SAFETY_AGENT, ticket, listing)


if __name__ == "__main__":
    unittest.main()
